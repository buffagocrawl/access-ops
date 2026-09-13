"""Focused end-to-end checks for the first Access Ops vertical slice."""
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import GrantResult, MockOkta
from access_ops.models import Decision, EmployeeStatus, RequestStatus, RevocationStatus
from access_ops.workflow import Workflow


@pytest.fixture
def system(tmp_path):
    configuration = load_configuration(Path(__file__).resolve().parents[1] / "config")
    database = Database(tmp_path / "workflow.db")
    provider = MockOkta(tmp_path / "provider.db")
    workflow = Workflow(configuration, database, provider)
    yield workflow, database, provider
    provider.close()
    database.close()


def submit(workflow, **overrides):
    fields = dict(employee_id="UDEMO001", application="GitHub", access_level="Read",
                  business_reason="Read engineering documentation", duration="Permanent")
    return workflow.submit(**(fields | overrides))


def test_golden_path_and_committed_order(system, tmp_path, monkeypatch):
    workflow, database, provider = system
    observations = []
    original = provider.grant

    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            observations.append((reader.get(request.request_id).status,
                                 [e.event_type for e in reader.events(request.request_id)],
                                 provider.access_list()))
        finally:
            reader.close()
        return original(request)

    monkeypatch.setattr(provider, "grant", observe)
    response = submit(workflow)
    request = database.get(response.request_id)
    assert observations == [(RequestStatus.PROVISIONING,
                             ["REQUEST_AUTO_APPROVED", "PROVISIONING_STARTED"], [])]
    assert request.status == RequestStatus.ACTIVE
    assert request.provisioning_result == GrantResult.GRANTED
    assert database.policy_reference(request.request_id) == ("GH-READ-ENG", 1)
    assert provider.access_list() == [("UDEMO001", "GitHub", "Read")]
    assert response.request_id.startswith("REQ-")
    assert response.request_id in response.message
    assert "access is granted in the mock directory" in response.message
    events = database.events(request.request_id)
    assert [e.event_type for e in events] == [
        "REQUEST_AUTO_APPROVED", "PROVISIONING_STARTED", "PROVISIONING_SUCCEEDED"]
    assert [(e.previous_status, e.new_status) for e in events] == [
        (None, RequestStatus.APPROVED), (RequestStatus.APPROVED, RequestStatus.PROVISIONING),
        (RequestStatus.PROVISIONING, RequestStatus.ACTIVE)]
    assert all(e.policy_version == 1 and "GH-READ-ENG" in e.details for e in events)
    assert events[0].timestamp <= events[1].timestamp <= events[2].timestamp
    assert request.updated_at == events[2].timestamp
    assert all(request.business_reason not in e.details for e in events)


def test_repeat_processing_and_provider_idempotency_survive_reopen(system, tmp_path):
    workflow, database, provider = system
    response = submit(workflow)
    assert workflow.process(response.request_id) == response
    assert len(database.events(response.request_id)) == 3
    reopened = Database(tmp_path / "workflow.db")
    reopened_provider = MockOkta(tmp_path / "provider.db")
    try:
        again = Workflow(workflow.configuration, reopened, reopened_provider)
        assert again.process(response.request_id) == response
        assert reopened_provider.grant(reopened.get(response.request_id)) == GrantResult.ALREADY_EXISTS
        assert len(reopened_provider.access_list()) == 1
    finally:
        reopened.close()
        reopened_provider.close()


def test_existing_access_is_confirmed_without_second_grant(system):
    workflow, database, provider = system
    first = submit(workflow)
    second = submit(workflow)
    assert first.request_id != second.request_id  # Submission deduplication is deferred.
    assert database.get(second.request_id).status == RequestStatus.ACTIVE
    assert database.get(second.request_id).provisioning_result == GrantResult.ALREADY_EXISTS
    assert database.get(second.request_id).starts_at is None
    assert database.get(second.request_id).expires_at is None
    assert len(provider.access_list()) == 1


@pytest.mark.parametrize("overrides", [
    {"employee_id": "unknown"}, {"employee_id": "UDEMO004"},
    {"employee_id": "UDEMO002"},
    {"employee_id": "UDEMO011", "access_level": "Write"},
    {"application": "Notion", "access_level": "Standard"},
    {"application": "Unknown"}, {"access_level": "Owner"},
    {"duration": "2 days"}, {"duration": ""}, {"business_reason": "  "},
    {"application": ""}, {"access_level": None}, {"business_reason": None},
])
def test_invalid_or_out_of_slice_intake_never_calls_provider(system, monkeypatch, overrides):
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit(workflow, **overrides)
    assert response.request_id is not None
    assert database.events(response.request_id)[0].event_type == "INTAKE_STOPPED"
    assert calls == []
    assert provider.access_list() == []
    assert database.connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 0


@pytest.mark.parametrize("change", ["disabled", "ambiguous", "human", "duration"])
def test_configuration_controls_authorization(system, monkeypatch, change):
    workflow, _, provider = system
    policies = workflow.configuration.policies
    first = policies[0]
    if change == "disabled":
        first = replace(first, enabled=False)
    elif change == "human":
        first = replace(first, decision=Decision.APPROVAL_REQUIRED)
    elif change == "duration":
        first = replace(first, permanent_allowed=False)
    policies = (first,) + policies[1:]
    if change == "ambiguous":
        policies += (first,)
    workflow.configuration = replace(workflow.configuration, policies=policies)
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    assert submit(workflow).request_id is not None
    assert calls == []


def test_pre_audit_failure_rolls_back_and_blocks_provider(system, monkeypatch):
    workflow, database, provider = system
    database.connection.execute("""
        CREATE TRIGGER fail_pre BEFORE INSERT ON audit_events
        WHEN NEW.event_type = 'PROVISIONING_STARTED'
        BEGIN SELECT RAISE(ABORT, 'private database failure'); END
    """)
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit(workflow)
    assert database.get(response.request_id).status == RequestStatus.APPROVED
    assert [e.event_type for e in database.events(response.request_id)] == ["REQUEST_AUTO_APPROVED"]
    assert calls == []
    assert "private" not in response.message


@pytest.mark.parametrize("result", [GrantResult.FAILED, None, "GRANTED", RuntimeError("private token")])
def test_no_active_without_explicit_provider_confirmation(system, monkeypatch, result):
    workflow, database, provider = system

    def unconfirmed(request):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(provider, "grant", unconfirmed)
    response = submit(workflow)
    assert database.get(response.request_id).status == RequestStatus.PROVISIONING_FAILED
    assert database.events(response.request_id)[-1].event_type == "PROVISIONING_FAILED"
    assert provider.access_list() == []
    assert "private" not in response.message
    assert "access is granted" not in response.message
    assert workflow.process(response.request_id).request_id == response.request_id


def test_post_audit_failure_does_not_claim_success_or_retry(system):
    workflow, database, provider = system
    database.connection.execute("""
        CREATE TRIGGER fail_post BEFORE INSERT ON audit_events
        WHEN NEW.event_type = 'PROVISIONING_SUCCEEDED'
        BEGIN SELECT RAISE(ABORT, 'private database failure'); END
    """)
    response = submit(workflow)
    assert database.get(response.request_id).status == RequestStatus.PROVISIONING
    assert len(provider.access_list()) == 1
    assert "check the access state" in response.message
    assert "private" not in response.message
    workflow.process(response.request_id)
    assert len(database.events(response.request_id)) == 2


@pytest.mark.parametrize("change", ["inactive", "policy"])
def test_revalidation_after_creation_before_provider(system, monkeypatch, change):
    workflow, database, provider = system
    original = database.create

    def create_then_change(*args):
        original(*args)
        config = workflow.configuration
        if change == "inactive":
            config = replace(config, employees=tuple(
                replace(e, status=EmployeeStatus.INACTIVE) if e.slack_user_id == "UDEMO001" else e
                for e in config.employees))
        else:
            config = replace(config, policies=tuple(replace(p, policy_version=2) for p in config.policies))
        workflow.configuration = config

    monkeypatch.setattr(database, "create", create_then_change)
    response = submit(workflow)
    assert database.get(response.request_id).status == RequestStatus.REJECTED
    assert provider.access_list() == []
    assert [e.event_type for e in database.events(response.request_id)] == ["REQUEST_AUTO_APPROVED", "REVALIDATION_FAILED"]


def test_unknown_request_cannot_provision(system):
    workflow, _, provider = system
    assert "not found" in workflow.process("REQ-invented").message
    assert provider.access_list() == []


def test_write_pending_survives_reopen_without_provisioning(system, tmp_path, monkeypatch):
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit(workflow, access_level="Write")
    reopened = Database(tmp_path / "workflow.db")
    try:
        request = reopened.get(response.request_id)
        assert request.status == RequestStatus.PENDING_APPROVAL
        assert request.assigned_approver_id == "UDEMO005"
        assert reopened.policy_reference(request.request_id) == ("GH-WRITE-ENG", 1)
        assert [e.event_type for e in reopened.events(request.request_id)] == ["REQUEST_SUBMITTED"]
        assert Workflow(workflow.configuration, reopened, provider).process(request.request_id) == response
    finally:
        reopened.close()
    assert "pending manager approval" in response.message
    assert calls == []
    assert provider.access_list() == []


@pytest.mark.parametrize("reviewer", ["UDEMO002", "UDEMO001", "unknown", "UDEMO004"])
def test_unauthorized_approval_preserves_pending(system, monkeypatch, reviewer):
    workflow, database, provider = system
    response = submit(workflow, access_level="Write")
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    result = workflow.approve(response.request_id, reviewer)
    assert "Approval rejected" in result.message
    assert database.get(response.request_id).status == RequestStatus.PENDING_APPROVAL
    events = database.events(response.request_id)
    assert [e.event_type for e in events] == ["REQUEST_SUBMITTED", "APPROVAL_ATTEMPTED", "APPROVAL_REJECTED"]
    assert all(e.actor == reviewer for e in events[1:])
    assert calls == []
    assert provider.access_list() == []


def test_manager_approval_commits_revalidation_before_mock_grant(system, tmp_path, monkeypatch):
    workflow, database, provider = system
    response = submit(workflow, access_level="Write")
    original = provider.grant
    observations = []

    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            events = reader.events(request.request_id)
            observations.append([e.event_type for e in events])
            assert reader.get(request.request_id).status == RequestStatus.PROVISIONING
            assert events[2].actor == "UDEMO005"
            assert events[2].timestamp <= events[3].timestamp <= events[4].timestamp
        finally:
            reader.close()
        return original(request)

    monkeypatch.setattr(provider, "grant", observe)
    result = workflow.approve(response.request_id, "UDEMO005")
    assert observations == [["REQUEST_SUBMITTED", "APPROVAL_ATTEMPTED", "REQUEST_APPROVED",
                             "REVALIDATION_SUCCEEDED", "PROVISIONING_STARTED"]]
    assert database.get(response.request_id).status == RequestStatus.ACTIVE
    assert database.get(response.request_id).provisioning_result == GrantResult.GRANTED
    assert provider.access_list() == [("UDEMO001", "GitHub", "Write")]
    assert "GitHub Write access is granted" in result.message
    assert database.events(response.request_id)[-1].event_type == "PROVISIONING_SUCCEEDED"
    assert "Approval rejected" in workflow.approve(response.request_id, "UDEMO005").message
    assert len(observations) == 1


@pytest.mark.parametrize("change", ["inactive", "missing", "department", "manager", "policy"])
@pytest.mark.parametrize("timing", ["pending", "after_approval"])
def test_approval_revalidates_current_trusted_configuration(system, monkeypatch, change, timing):
    workflow, database, provider = system
    response = submit(workflow, access_level="Write")

    def change_configuration():
        config = workflow.configuration
        if change == "policy":
            config = replace(config, policies=tuple(replace(p, policy_version=2) for p in config.policies))
        else:
            employees = []
            for employee in config.employees:
                if employee.slack_user_id == "UDEMO001":
                    if change == "missing":
                        continue
                    changes = {"inactive": {"status": EmployeeStatus.INACTIVE},
                               "department": {"department": "Product"},
                               "manager": {"manager_slack_id": "UDEMO006"}}
                    employee = replace(employee, **changes[change])
                employees.append(employee)
            config = replace(config, employees=tuple(employees))
        workflow.configuration = config

    if timing == "pending":
        change_configuration()
    else:
        original = database.transition

        def transition_then_change(request, event):
            original(request, event)
            if event.event_type == "REQUEST_APPROVED":
                change_configuration()

        monkeypatch.setattr(database, "transition", transition_then_change)
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    result = workflow.approve(response.request_id, "UDEMO005")
    assert database.get(response.request_id).status == RequestStatus.REJECTED
    assert [e.event_type for e in database.events(response.request_id)] == [
        "REQUEST_SUBMITTED", "APPROVAL_ATTEMPTED", "REQUEST_APPROVED", "REVALIDATION_FAILED"]
    assert "access is granted" not in result.message
    assert calls == []
    assert provider.access_list() == []


@pytest.mark.parametrize("manager", [None, "unknown", "UDEMO001", "UDEMO004"])
def test_unresolvable_manager_fails_closed(system, monkeypatch, manager):
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    workflow.configuration = replace(workflow.configuration, employees=tuple(
        replace(e, manager_slack_id=manager) if e.slack_user_id == "UDEMO001" else e
        for e in workflow.configuration.employees))
    response = submit(workflow, access_level="Write")
    assert database.get(response.request_id).status == RequestStatus.PENDING_APPROVAL
    assert database.get(response.request_id).assigned_approver_id is None
    assert [e.event_type for e in database.events(response.request_id)] == ["REQUEST_SUBMITTED", "APPROVAL_ROUTING_FAILED"]
    assert workflow.process(response.request_id) == response
    workflow.approve(response.request_id, "UDEMO005")
    assert database.get(response.request_id).status == RequestStatus.PENDING_APPROVAL
    assert "manager could not be resolved" in response.message
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("event_type", ["APPROVAL_ATTEMPTED", "REQUEST_APPROVED", "REVALIDATION_SUCCEEDED"])
def test_approval_audit_failure_blocks_grant(system, monkeypatch, event_type):
    workflow, database, provider = system
    response = submit(workflow, access_level="Write")
    original = database.append_event

    def fail(event):
        if event.event_type == event_type:
            raise RuntimeError("private database error")
        original(event)

    monkeypatch.setattr(database, "append_event", fail)
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    result = workflow.approve(response.request_id, "UDEMO005")
    expected = RequestStatus.APPROVED if event_type == "REVALIDATION_SUCCEEDED" else RequestStatus.PENDING_APPROVAL
    assert database.get(response.request_id).status == expected
    assert calls == []
    assert "private" not in result.message


def submit_exception(workflow):
    return submit(workflow, employee_id="UDEMO002", access_level="Write",
                  business_reason="Update launch website documentation")


def test_exception_pending_and_reviewer_details_survive_reopen(system, tmp_path, monkeypatch):
    from access_ops.notifications import exception_review

    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit_exception(workflow)
    reopened = Database(tmp_path / "workflow.db")
    try:
        request = reopened.get(response.request_id)
        assert request.status == RequestStatus.EXCEPTION_REVIEW
        assert request.assigned_approver_id == "UDEMO006"
        assert request.assigned_approver_id != workflow.configuration.employee("UDEMO002").manager_slack_id
        assert reopened.policy_reference(request.request_id) == ("GH-WRITE-EXCEPTION", 2)
        assert not request.temporary and request.expires_at is None
        message = exception_review(request).message
        assert all(value in message for value in (
            "UDEMO006", "GitHub", "Write", "Permanent", request.business_reason, "Approve or reject"))
        assert Workflow(workflow.configuration, reopened, provider).process(request.request_id) == response
    finally:
        reopened.close()
    assert "outside the normal eligibility policy" in response.message
    assert "may be legitimate" in response.message
    assert "routed for exception review" in response.message
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("reviewer", ["UDEMO002", "UDEMO009", "UDEMO005", "unknown", "UDEMO004"])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_exception_unauthorized_decisions_preserve_review(system, reviewer, action):
    workflow, database, provider = system
    response = submit_exception(workflow)
    result = getattr(workflow, action)(response.request_id, reviewer)
    assert "Approval rejected" in result.message
    assert database.get(response.request_id).status == RequestStatus.EXCEPTION_REVIEW
    assert database.events(response.request_id)[-1].event_type == "APPROVAL_REJECTED"
    assert database.events(response.request_id)[-1].actor == reviewer
    assert provider.access_list() == []


def test_exception_approval_commits_audit_before_mock_okta(system, tmp_path, monkeypatch):
    workflow, database, provider = system
    response = submit_exception(workflow)
    original = provider.grant
    calls = []
    expected = ["EXCEPTION_DETECTED", "EXCEPTION_ROUTED", "APPROVAL_ATTEMPTED",
                "EXCEPTION_APPROVED", "REVALIDATION_SUCCEEDED", "PROVISIONING_STARTED"]

    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            assert reader.get(request.request_id).status == RequestStatus.PROVISIONING
            assert [e.event_type for e in reader.events(request.request_id)] == expected
            assert reader.events(request.request_id)[3].actor == "UDEMO006"
        finally:
            reader.close()
        calls.append(request.request_id)
        return original(request)

    monkeypatch.setattr(provider, "grant", observe)
    result = workflow.approve(response.request_id, "UDEMO006")
    assert database.get(response.request_id).status == RequestStatus.ACTIVE
    assert database.get(response.request_id).provisioning_result == GrantResult.GRANTED
    assert provider.access_list() == [("UDEMO002", "GitHub", "Write")]
    assert "access is granted in the mock directory" in result.message
    events = database.events(response.request_id)
    assert [e.event_type for e in events] == expected + ["PROVISIONING_SUCCEEDED"]
    assert all(e.policy_version == 2 and "GH-WRITE-EXCEPTION" in e.details for e in events)
    assert events[3].previous_status == RequestStatus.EXCEPTION_REVIEW
    assert events[3].new_status == RequestStatus.APPROVED
    assert "Approval rejected" in workflow.approve(response.request_id, "UDEMO006").message
    assert calls == [response.request_id]


def test_exception_rejection_is_final_and_persisted(system, tmp_path):
    workflow, database, provider = system
    response = submit_exception(workflow)
    assert "was rejected" in workflow.reject(response.request_id, "UDEMO006").message
    reopened = Database(tmp_path / "workflow.db")
    try:
        assert reopened.get(response.request_id).status == RequestStatus.REJECTED
        event = reopened.events(response.request_id)[-1]
        assert event.event_type == "EXCEPTION_REJECTED" and event.actor == "UDEMO006"
    finally:
        reopened.close()
    workflow.approve(response.request_id, "UDEMO006")
    workflow.process(response.request_id)
    assert provider.access_list() == []


@pytest.mark.parametrize("reviewer", [None, "unknown", "UDEMO002", "UDEMO004"])
def test_exception_unresolvable_reviewer_preserves_request_and_audit(system, monkeypatch, reviewer):
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    workflow.configuration = replace(workflow.configuration, policies=tuple(
        replace(p, approver_id=reviewer) if p.policy_id == "GH-WRITE-EXCEPTION" else p
        for p in workflow.configuration.policies))
    response = submit_exception(workflow)
    assert response.request_id is not None
    assert "Review is blocked" in response.message
    request = database.get(response.request_id)
    assert request.status == RequestStatus.EXCEPTION_REVIEW
    assert request.assigned_approver_id is None
    assert [e.event_type for e in database.events(response.request_id)] == [
        "EXCEPTION_DETECTED", "EXCEPTION_ROUTING_FAILED"]
    workflow.approve(response.request_id, "UDEMO006")
    workflow.process(response.request_id)
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("change", ["inactive", "missing", "department", "policy", "duration", "reviewer"])
@pytest.mark.parametrize("timing", ["pending", "after_approval"])
def test_exception_revalidates_before_provisioning(system, monkeypatch, change, timing):
    workflow, database, provider = system
    response = submit_exception(workflow)

    def change_configuration():
        config = workflow.configuration
        if change in ("policy", "duration", "reviewer"):
            changes = {"policy": {"policy_version": 3}, "duration": {"permanent_allowed": False},
                       "reviewer": {"approver_id": "UDEMO007"}}
            config = replace(config, policies=tuple(
                replace(p, **changes[change]) if p.policy_id == "GH-WRITE-EXCEPTION" else p
                for p in config.policies))
        else:
            employees = []
            for e in config.employees:
                if e.slack_user_id == "UDEMO002":
                    if change == "missing":
                        continue
                    e = replace(e, **({"status": EmployeeStatus.INACTIVE} if change == "inactive"
                                      else {"department": "Finance"}))
                employees.append(e)
            config = replace(config, employees=tuple(employees))
        workflow.configuration = config

    if timing == "pending":
        change_configuration()
    else:
        original = database.transition

        def transition_then_change(request, event):
            original(request, event)
            if event.event_type == "EXCEPTION_APPROVED":
                change_configuration()

        monkeypatch.setattr(database, "transition", transition_then_change)
    result = workflow.approve(response.request_id, "UDEMO006")
    blocked_at_review = change == "reviewer" and timing == "pending"
    assert database.get(response.request_id).status == (
        RequestStatus.EXCEPTION_REVIEW if blocked_at_review else RequestStatus.REJECTED)
    assert database.events(response.request_id)[-1].event_type == (
        "APPROVAL_REJECTED" if blocked_at_review else "REVALIDATION_FAILED")
    assert "access is granted" not in result.message
    assert provider.access_list() == []


@pytest.mark.parametrize("event_type", ["EXCEPTION_APPROVED", "REVALIDATION_SUCCEEDED", "PROVISIONING_STARTED"])
def test_exception_audit_failure_blocks_provider(system, monkeypatch, event_type):
    workflow, database, provider = system
    response = submit_exception(workflow)
    original = database.append_event

    def fail(event):
        if event.event_type == event_type:
            raise RuntimeError("private database error")
        original(event)

    monkeypatch.setattr(database, "append_event", fail)
    result = workflow.approve(response.request_id, "UDEMO006")
    assert database.get(response.request_id).status != RequestStatus.ACTIVE
    assert provider.access_list() == []
    assert "private" not in result.message


@pytest.mark.parametrize("change", ["inactive", "missing"])
def test_exception_reviewer_unavailable_while_pending(system, change):
    workflow, database, provider = system
    response = submit_exception(workflow)
    employees = tuple(
        replace(e, status=EmployeeStatus.INACTIVE) if e.slack_user_id == "UDEMO006" else e
        for e in workflow.configuration.employees
        if not (change == "missing" and e.slack_user_id == "UDEMO006"))
    workflow.configuration = replace(workflow.configuration, employees=employees)
    assert "Approval rejected" in workflow.approve(response.request_id, "UDEMO006").message
    assert database.get(response.request_id).status == RequestStatus.EXCEPTION_REVIEW
    assert database.events(response.request_id)[-1].event_type == "APPROVAL_REJECTED"
    assert provider.access_list() == []


def test_exception_reviewer_is_configured_not_hardcoded(system):
    from access_ops.models import ApproverType

    workflow, database, provider = system
    workflow.configuration = replace(workflow.configuration, policies=tuple(
        replace(p, approver_type=ApproverType.IT_SECURITY, approver_id="UDEMO007")
        if p.policy_id == "GH-WRITE-EXCEPTION" else p for p in workflow.configuration.policies))
    response = submit_exception(workflow)
    assert database.get(response.request_id).assigned_approver_id == "UDEMO007"
    assert "Approval rejected" in workflow.approve(response.request_id, "UDEMO006").message
    workflow.approve(response.request_id, "UDEMO007")
    assert database.get(response.request_id).status == RequestStatus.ACTIVE
    assert provider.access_list() == [("UDEMO002", "GitHub", "Write")]


def test_exception_provider_failure_preserves_approval(system, monkeypatch):
    workflow, database, provider = system
    response = submit_exception(workflow)
    monkeypatch.setattr(provider, "grant", lambda request: GrantResult.FAILED)
    result = workflow.approve(response.request_id, "UDEMO006")
    assert database.get(response.request_id).status == RequestStatus.PROVISIONING_FAILED
    events = database.events(response.request_id)
    assert any(e.event_type == "EXCEPTION_APPROVED" and e.actor == "UDEMO006" for e in events)
    assert events[-1].event_type == "PROVISIONING_FAILED"
    assert provider.access_list() == []
    assert "Access could not be confirmed" in result.message


@pytest.mark.parametrize("overrides,phrase,status", [
    ({"business_reason": "  "}, "Provide a business reason", RequestStatus.NEEDS_INFORMATION),
    ({"business_reason": None}, "Provide a business reason", RequestStatus.NEEDS_INFORMATION),
    ({"application": "Github"}, "application is unsupported", RequestStatus.REJECTED),
    ({"access_level": "write"}, "access level is unsupported for GitHub", RequestStatus.REJECTED),
    ({"employee_id": "UDEMO004"}, "account is inactive", RequestStatus.REJECTED),
    ({"employee_id": "unknown"}, "not found in the trusted directory", RequestStatus.REJECTED),
])
def test_invalid_intake_has_durable_deterministic_audit(system, tmp_path, monkeypatch, overrides, phrase, status):
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))

    def unexpected_policy(*args):
        pytest.fail("Invalid intake must stop before policy execution")

    monkeypatch.setattr("access_ops.workflow.match_policy", unexpected_policy)
    for _ in range(2):
        response = submit(workflow, **overrides)
        assert phrase in response.message
        assert response.request_id in response.message
        reader = Database(tmp_path / "workflow.db")
        try:
            assert reader.get(response.request_id) is None  # No invented policy/employee.
            events = reader.events(response.request_id)
            assert len(events) == 1
            event = events[0]
            assert (event.event_type, event.previous_status, event.new_status) == ("INTAKE_STOPPED", None, status)
            assert event.policy_version is None and event.actor == "access_ops"
            assert phrase in event.details
        finally:
            reader.close()
        workflow.process(response.request_id)
        workflow.approve(response.request_id, "UDEMO005")
        assert database.events(response.request_id) == events
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("mode", ["removed", "disabled", "unmatched", "ambiguous"])
def test_missing_or_ambiguous_policy_is_audited_and_closed(system, monkeypatch, mode):
    workflow, database, provider = system
    config = workflow.configuration
    policy = next(p for p in config.policies if p.policy_id == "GH-READ-ENG")
    policies = tuple(p for p in config.policies if p != policy)
    if mode == "disabled":
        policies += (replace(policy, enabled=False),)
    elif mode == "unmatched":
        policies += (replace(policy, eligible_departments=frozenset({"Finance"})),)
    elif mode == "ambiguous":
        policies += (policy, replace(policy, policy_id="CONFLICT"))
    workflow.configuration = replace(config, policies=policies)
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit(workflow)
    assert "configuration correction" in response.message
    assert "No enabled policy" in response.message if mode != "ambiguous" else "Policy configuration" in response.message
    event = database.events(response.request_id)[0]
    assert event.event_type == "INTAKE_STOPPED" and event.new_status == RequestStatus.REJECTED
    assert event.policy_version is None
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("boundary", ["policy", "audit"])
def test_intake_internal_errors_return_fixed_safe_feedback(system, monkeypatch, boundary):
    workflow, database, provider = system

    def fail(*args):
        raise RuntimeError("Traceback: sqlite secret=private-token database=/private/access.db")

    if boundary == "policy":
        monkeypatch.setattr("access_ops.workflow.match_policy", fail)
        response = submit(workflow)
    else:
        monkeypatch.setattr(database, "append_event", fail)
        response = submit(workflow, business_reason="")
    assert "could not be recorded safely" in response.message
    assert "Contact IT" in response.message
    assert all(value not in response.message for value in ("Traceback", "sqlite", "private-token", "/private", "RuntimeError"))
    assert provider.access_list() == []
    assert database.connection.execute("SELECT count(*) FROM requests").fetchone()[0] == 0


# Phase 6, Step 15: temporary access on the existing workflow paths.


@pytest.mark.parametrize("duration,days", [("1 day", 1), ("7 days", 7), ("30 days", 30), ("90 days", 90), ("Permanent", None)])
def test_duration_lifecycle_round_trip(system, tmp_path, duration, days):
    workflow, database, provider = system
    now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    workflow.clock = lambda: now
    if days == 90:
        workflow.configuration = replace(workflow.configuration, policies=tuple(
            replace(p, max_duration_days=90) if p.policy_id == "GH-READ-ENG" else p
            for p in workflow.configuration.policies))
    response = submit(workflow, duration=duration)
    reopened = Database(tmp_path / "workflow.db")
    try:
        request = reopened.get(response.request_id)
        assert request.status == RequestStatus.ACTIVE
        assert request.duration == duration
        assert request.starts_at == now
        assert request.expires_at == (now + timedelta(days=days) if days else None)
        assert request.temporary == (days is not None)
        assert request.revocation_status == (RevocationStatus.PENDING if days else RevocationStatus.NOT_APPLICABLE)
    finally:
        reopened.close()


@pytest.mark.parametrize("duration,changes", [
    ("2 days", {}), ("7", {}), ("permanent", {}), (" 7 days", {}),
    ("90 days", {}), ("30 days", {"max_duration_days": 7}),
    ("Permanent", {"permanent_allowed": False}), ("1 day", {"temporary_allowed": False}),
])
def test_duration_rejected_without_substitution(system, monkeypatch, duration, changes):
    workflow, database, provider = system
    workflow.configuration = replace(workflow.configuration, policies=tuple(
        replace(p, **changes) if p.policy_id == "GH-READ-ENG" else p for p in workflow.configuration.policies))
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit(workflow, duration=duration)
    assert database.get(response.request_id) is None
    assert database.events(response.request_id)[0].new_status == RequestStatus.REJECTED
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("employee,reviewer,status", [
    ("UDEMO001", "UDEMO005", RequestStatus.PENDING_APPROVAL),
    ("UDEMO002", "UDEMO006", RequestStatus.EXCEPTION_REVIEW),
])
def test_pending_duration_starts_only_after_approval(system, tmp_path, employee, reviewer, status):
    from access_ops.notifications import exception_review
    workflow, database, provider = system
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    workflow.clock = lambda: now
    response = submit(workflow, employee_id=employee, access_level="Write", duration="7 days")
    reopened = Database(tmp_path / "workflow.db")
    try:
        request = reopened.get(response.request_id)
        assert request.status == status and request.duration == "7 days"
        assert request.starts_at is None and request.expires_at is None
        assert request.revocation_status == RevocationStatus.PENDING
        assert "7 days" in exception_review(request).message
    finally:
        reopened.close()
    now += timedelta(days=10)
    workflow.approve(response.request_id, reviewer)
    request = database.get(response.request_id)
    assert request.starts_at == now and request.expires_at == now + timedelta(days=7)


@pytest.mark.parametrize("employee,reviewer", [("UDEMO001", "UDEMO005"), ("UDEMO002", "UDEMO006")])
@pytest.mark.parametrize("changes", [{"temporary_allowed": False}, {"max_duration_days": 1}])
def test_temporary_duration_revalidated_after_approval(system, monkeypatch, employee, reviewer, changes):
    workflow, database, provider = system
    response = submit(workflow, employee_id=employee, access_level="Write", duration="7 days")
    original = database.transition
    def change_after_approval(request, event):
        original(request, event)
        if event.event_type in ("REQUEST_APPROVED", "EXCEPTION_APPROVED"):
            workflow.configuration = replace(workflow.configuration, policies=tuple(
                replace(p, **changes) for p in workflow.configuration.policies))
    monkeypatch.setattr(database, "transition", change_after_approval)
    workflow.approve(response.request_id, reviewer)
    assert database.get(response.request_id).status == RequestStatus.REJECTED
    assert database.get(response.request_id).duration == "7 days"
    assert database.events(response.request_id)[-1].event_type == "REVALIDATION_FAILED"
    assert provider.access_list() == []


def test_expiration_audit_removal_and_repeat_survive_reopen(system, tmp_path, monkeypatch):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    history = database.events(request.request_id)
    calls = []
    original = provider.revoke
    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            assert reader.get(request.request_id).status == RequestStatus.EXPIRED
            assert [e.event_type for e in reader.events(request.request_id)][-2:] == ["ACCESS_EXPIRED", "REVOCATION_STARTED"]
        finally:
            reader.close()
        calls.append(request.request_id)
        return original(request)
    monkeypatch.setattr(provider, "revoke", observe)
    assert workflow.process_expired_access(request.expires_at - timedelta(microseconds=1)) == []
    assert provider.access_list() and database.events(request.request_id) == history
    assert "was removed" in workflow.process_expired_access(request.expires_at)[0].message
    reopened = Database(tmp_path / "workflow.db")
    try:
        saved = reopened.get(request.request_id)
        assert saved.status == RequestStatus.REVOKED and saved.revocation_status == RevocationStatus.REVOKED
        assert saved.starts_at == request.starts_at and saved.expires_at == request.expires_at
        events = reopened.events(request.request_id)
        assert events[:len(history)] == history
        assert [e.event_type for e in events[len(history):]] == ["ACCESS_EXPIRED", "REVOCATION_STARTED", "REVOCATION_SUCCEEDED"]
        assert all(e.timestamp == request.expires_at for e in events[len(history):])
        assert Workflow(workflow.configuration, reopened, provider).process_expired_access(request.expires_at + timedelta(days=1)) == []
    finally:
        reopened.close()
    assert calls == [request.request_id] and provider.access_list() == []


def test_permanent_never_expires(system, monkeypatch):
    workflow, database, provider = system
    response = submit(workflow)
    history = database.events(response.request_id)
    monkeypatch.setattr(provider, "revoke", lambda request: pytest.fail("Permanent access cannot be revoked"))
    assert workflow.process_expired_access(datetime(2100, 1, 1, tzinfo=timezone.utc)) == []
    assert database.events(response.request_id) == history and provider.access_list()


@pytest.mark.parametrize("event_type", ["ACCESS_EXPIRED", "REVOCATION_STARTED"])
def test_expiration_audit_failure_blocks_revoke(system, monkeypatch, event_type):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    original = database.append_event
    def fail(event):
        if event.event_type == event_type:
            raise RuntimeError("private database error")
        original(event)
    monkeypatch.setattr(database, "append_event", fail)
    monkeypatch.setattr(provider, "revoke", lambda request: pytest.fail("Audit must commit first"))
    assert "private" not in workflow.process_expired_access(request.expires_at)[0].message
    assert provider.access_list()


def test_expiration_cannot_remove_another_stored_grant(system):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    with provider.connection:
        provider.connection.execute("UPDATE mock_access SET grant_key = ?", ("another-request:grant",))
    workflow.process_expired_access(request.expires_at)
    assert provider.access_list()
    assert database.get(request.request_id).revocation_status == RevocationStatus.PENDING
    assert database.get(request.request_id).status == RequestStatus.REVOCATION_FAILED
    assert database.events(request.request_id)[-1].event_type == "REVOCATION_FAILED"


def test_existing_access_cannot_be_assigned_a_new_expiration(system):
    workflow, database, provider = system
    submit(workflow)
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    assert request.status == RequestStatus.PROVISIONING_FAILED
    assert request.starts_at is None and request.expires_at is None
    assert workflow.process_expired_access(datetime(2100, 1, 1, tzinfo=timezone.utc)) == []
    assert provider.access_list()


def test_expiration_rejects_naive_time(system):
    workflow, _, _ = system
    with pytest.raises(ValueError, match="timezone-aware"):
        workflow.process_expired_access(datetime(2026, 9, 12))


@pytest.mark.parametrize("column,value", [("duration", "Permanent"), ("provisioning_result", "ALREADY_EXISTS"), ("starts_at", None)])
def test_inconsistent_expiration_state_blocks_provider(system, monkeypatch, column, value):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    with database.connection:
        database.connection.execute(f"UPDATE requests SET {column} = ? WHERE request_id = ?", (value, request.request_id))
    monkeypatch.setattr(provider, "revoke", lambda request: pytest.fail("Inconsistent lifecycle cannot revoke"))
    workflow.process_expired_access(request.expires_at)
    assert database.events(request.request_id)[-1].event_type == "REVOCATION_BLOCKED"
    assert provider.access_list()


def test_legacy_database_migration_preserves_permanent_history(system, tmp_path):
    workflow, database, _ = system
    response = submit(workflow)
    history = database.events(response.request_id)
    # Reproduce the preceding slice's schema, then reopen through the migration.
    with database.connection:
        for column in ("duration", "temporary", "starts_at", "expires_at", "revocation_status"):
            database.connection.execute(f"ALTER TABLE requests DROP COLUMN {column}")
    reopened = Database(tmp_path / "workflow.db")
    try:
        request = reopened.get(response.request_id)
        assert request.duration == "Permanent" and not request.temporary
        assert request.starts_at is None and request.expires_at is None
        assert request.revocation_status == RevocationStatus.NOT_APPLICABLE
        assert reopened.events(response.request_id) == history
    finally:
        reopened.close()


# Phase 6, Step 16: explicit deterministic provider failures.


@pytest.mark.parametrize("fail_grant", [False, True])
@pytest.mark.parametrize("employee,level,reviewer,approval", [
    ("UDEMO001", "Read", None, "REQUEST_AUTO_APPROVED"),
    ("UDEMO001", "Write", "UDEMO005", "REQUEST_APPROVED"),
    ("UDEMO002", "Write", "UDEMO006", "EXCEPTION_APPROVED"),
])
def test_injected_grant_outcome_and_committed_approval(system, tmp_path, monkeypatch,
                                                      fail_grant, employee, level, reviewer, approval):
    workflow, database, _ = system
    provider = MockOkta(tmp_path / "injected.db", fail_grant=fail_grant)
    workflow.provider = provider
    calls = []
    original = provider.grant

    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            events = reader.events(request.request_id)
            assert reader.get(request.request_id).status == RequestStatus.PROVISIONING
            assert events[-1].event_type == "PROVISIONING_STARTED"
            assert any(e.event_type == approval and e.new_status == RequestStatus.APPROVED
                       and e.actor == (reviewer or "access_ops") for e in events)
            if reviewer:
                assert events[-2].event_type == "REVALIDATION_SUCCEEDED"
        finally:
            reader.close()
        calls.append(request.request_id)
        return original(request)

    monkeypatch.setattr(provider, "grant", observe)
    try:
        response = submit(workflow, employee_id=employee, access_level=level, duration="1 day")
        if reviewer:
            assert calls == []
            response = workflow.approve(response.request_id, reviewer)
        reader = Database(tmp_path / "workflow.db")
        try:
            request = reader.get(response.request_id)
            events = reader.events(response.request_id)
            assert request.status == (RequestStatus.PROVISIONING_FAILED if fail_grant else RequestStatus.ACTIVE)
            assert events[-1].event_type == ("PROVISIONING_FAILED" if fail_grant else "PROVISIONING_SUCCEEDED")
            assert any(e.event_type == approval for e in events)
        finally:
            reader.close()
        if fail_grant:
            assert request.provisioning_result == GrantResult.FAILED
            assert request.starts_at is None and request.expires_at is None
            assert provider.access_list() == []
            assert response.message == (
                "Access Ops: Approval succeeded, but provisioning failed. Access could not be confirmed. "
                f"Contact IT with this request ID; do not resubmit. Request ID: {response.request_id}.")
            workflow.process(response.request_id)
            assert database.events(response.request_id) == events
        else:
            assert request.provisioning_result == GrantResult.GRANTED
            assert provider.access_list() == [(employee, "GitHub", level)]
        assert calls == [response.request_id]
    finally:
        provider.close()


@pytest.mark.parametrize("fail_revoke", [False, True])
@pytest.mark.parametrize("employee,reviewer", [("UDEMO001", "UDEMO005"), ("UDEMO002", "UDEMO006")])
def test_injected_revoke_outcome_preserves_durable_history(system, tmp_path, monkeypatch,
                                                         fail_revoke, employee, reviewer):
    workflow, database, _ = system
    provider = MockOkta(tmp_path / "injected.db", fail_revoke=fail_revoke)
    workflow.provider = provider
    calls = []
    original = provider.revoke

    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            assert reader.get(request.request_id).status == RequestStatus.EXPIRED
            assert [e.event_type for e in reader.events(request.request_id)][-2:] == [
                "ACCESS_EXPIRED", "REVOCATION_STARTED"]
        finally:
            reader.close()
        calls.append(request.request_id)
        return original(request)

    monkeypatch.setattr(provider, "revoke", observe)
    try:
        response = submit(workflow, employee_id=employee, access_level="Write", duration="1 day")
        workflow.approve(response.request_id, reviewer)
        request = database.get(response.request_id)
        history = database.events(response.request_id)
        access = provider.access_list()
        result = workflow.process_expired_access(request.expires_at)
        reader = Database(tmp_path / "workflow.db")
        try:
            saved = reader.get(request.request_id)
            assert saved == replace(request, status=(RequestStatus.REVOCATION_FAILED if fail_revoke else RequestStatus.REVOKED),
                                    revocation_status=(RevocationStatus.PENDING if fail_revoke else RevocationStatus.REVOKED),
                                    updated_at=request.expires_at)
            events = reader.events(request.request_id)
            assert events[:len(history)] == history
            expected = ["ACCESS_EXPIRED", "REVOCATION_STARTED"]
            expected += (["PROVIDER_ATTEMPT_FAILED", "REVOCATION_FAILED"] if fail_revoke
                         else ["REVOCATION_SUCCEEDED"])
            assert [e.event_type for e in events[len(history):]] == expected
            assert events[-1].new_status == saved.status
            assert provider.access_list() == (access if fail_revoke else [])
            if fail_revoke:
                assert "removal was not confirmed" in result[0].message
                assert "Contact IT" in result[0].message and "no automatic retry" in result[0].message
                assert "was removed" not in result[0].message
            else:
                assert "was removed" in result[0].message
            again = Workflow(workflow.configuration, reader, provider)
            assert again.process_expired_access(request.expires_at + timedelta(days=1)) == []
            assert reader.get(request.request_id) == saved
            assert reader.events(request.request_id) == events
            assert calls == [request.request_id]
        finally:
            reader.close()
    finally:
        provider.close()


def test_revoke_exception_is_durable_and_safe(system, monkeypatch):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)

    def fail(request):
        raise RuntimeError("Traceback private-token /private/provider.db")

    monkeypatch.setattr(provider, "revoke", fail)
    result = workflow.process_expired_access(request.expires_at)[0]
    assert database.get(request.request_id).status == RequestStatus.REVOCATION_FAILED
    assert database.events(request.request_id)[-1].event_type == "REVOCATION_FAILED"
    assert provider.access_list()
    assert all(word not in result.message for word in ("Traceback", "private-token", "/private", "RuntimeError"))
    assert "Contact IT" in result.message


def test_revoke_injection_does_not_affect_permanent_access(system, tmp_path):
    workflow, database, _ = system
    provider = MockOkta(tmp_path / "injected.db", fail_revoke=True)
    workflow.provider = provider
    try:
        response = submit(workflow)
        request = database.get(response.request_id)
        history = database.events(response.request_id)
        assert request.status == RequestStatus.ACTIVE
        assert workflow.process_expired_access(datetime(2100, 1, 1, tzinfo=timezone.utc)) == []
        assert database.get(response.request_id) == request
        assert database.events(response.request_id) == history
        assert provider.access_list() == [("UDEMO001", "GitHub", "Read")]
    finally:
        provider.close()


# Phase 6, Step 17: bounded retries at the provider boundary.


@pytest.mark.parametrize("operation", ["grant", "revoke"])
@pytest.mark.parametrize("failures,permanent,attempts,success", [
    (0, False, 1, True), (1, False, 2, True), (2, False, 3, True),
    (3, False, 3, False), (5, False, 3, False), (0, True, 1, False),
])
@pytest.mark.parametrize("employee,reviewer", [("UDEMO001", "UDEMO005"), ("UDEMO002", "UDEMO006")])
def test_provider_retry_lifecycle(system, tmp_path, monkeypatch, operation, failures, permanent,
                                  attempts, success, employee, reviewer):
    from access_ops.integrations.mock_okta import operation_id
    workflow, database, _ = system
    provider = MockOkta(tmp_path / "retry.db", **{
        f"transient_{operation}_failures": failures, f"fail_{operation}": permanent})
    workflow.provider = provider
    calls = []
    original = getattr(provider, operation)

    def observe(request):
        key = operation_id(request, operation)
        reader = Database(tmp_path / "workflow.db")
        try:
            events = reader.events(request.request_id)
            if calls:
                assert events[-1].event_type == "PROVIDER_RETRYING"
                assert f"{operation} attempt {len(calls) + 1}" in events[-1].details
            else:
                assert events[-1].event_type == ("PROVISIONING_STARTED" if operation == "grant" else "REVOCATION_STARTED")
            assert key in events[-1].details
        finally:
            reader.close()
        calls.append(key)
        return original(request)

    monkeypatch.setattr(provider, operation, observe)
    try:
        response = submit(workflow, employee_id=employee, access_level="Write", duration="1 day")
        approval = "REQUEST_APPROVED" if employee == "UDEMO001" else "EXCEPTION_APPROVED"
        response = workflow.approve(response.request_id, reviewer)
        before = database.get(response.request_id)
        history = database.events(response.request_id)
        if operation == "revoke":
            response = workflow.process_expired_access(before.expires_at)[0]
        request = database.get(response.request_id)
        events = database.events(response.request_id)
        key = f"{response.request_id}:{operation}"
        assert calls == [key] * attempts
        assert sum(e.event_type == approval and e.actor == reviewer for e in events) == 1
        assert sum(e.event_type == "REVALIDATION_SUCCEEDED" for e in events) == 1
        failed = [e for e in events if e.event_type == "PROVIDER_ATTEMPT_FAILED"]
        assert len(failed) == (attempts - 1 if success else attempts)
        for number, event in enumerate(failed, 1):
            assert key in event.details and f"{operation} attempt {number}" in event.details
            assert ("non-retryable" if permanent else "transient") in event.details
        assert sum(e.event_type == "PROVIDER_RETRYING" for e in events) == attempts - 1
        final_event = ("PROVISIONING_" if operation == "grant" else "REVOCATION_") + ("SUCCEEDED" if success else "FAILED")
        assert events[-1].event_type == final_event
        assert key in events[-1].details and f"attempt {attempts}" in events[-1].details
        assert sum(e.event_type == final_event for e in events) == 1
        if operation == "grant":
            assert request.status == (RequestStatus.ACTIVE if success else RequestStatus.PROVISIONING_FAILED)
            assert provider.access_list() == ([(employee, "GitHub", "Write")] if success else [])
            workflow.process(request.request_id)
        else:
            assert request.status == (RequestStatus.REVOKED if success else RequestStatus.REVOCATION_FAILED)
            assert request.revocation_status == (RevocationStatus.REVOKED if success else RevocationStatus.PENDING)
            assert request.starts_at == before.starts_at and request.expires_at == before.expires_at
            assert events[:len(history)] == history
            assert provider.access_list() == ([] if success else [(employee, "GitHub", "Write")])
            assert workflow.process_expired_access(before.expires_at + timedelta(days=1)) == []
        assert calls == [key] * attempts and database.events(request.request_id) == events
        if not success:
            assert "Contact IT" in response.message
            assert "Simulated" not in response.message and "TransientProviderError" not in response.message
    finally:
        provider.close()


@pytest.mark.parametrize("operation", ["grant", "revoke"])
@pytest.mark.parametrize("error", [PermissionError("authentication private-token"),
                                  PermissionError("authorization private-token"),
                                  ValueError("invalid input private-token"),
                                  RuntimeError("configuration private-token")])
def test_unclassified_provider_errors_are_never_retried(system, monkeypatch, operation, error):
    workflow, database, provider = system
    calls = []
    def fail(request):
        calls.append(request.request_id)
        raise error
    if operation == "revoke":
        response = submit(workflow, duration="1 day")
    monkeypatch.setattr(provider, operation, fail)
    if operation == "grant":
        response = submit(workflow)
    else:
        response = workflow.process_expired_access(database.get(response.request_id).expires_at)[0]
    assert calls == [response.request_id]
    events = database.events(response.request_id)
    assert events[-2].event_type == "PROVIDER_ATTEMPT_FAILED"
    assert "non-retryable" in events[-2].details
    assert not any(e.event_type == "PROVIDER_RETRYING" for e in events)
    assert "private-token" not in response.message


@pytest.mark.parametrize("operation", ["grant", "revoke"])
@pytest.mark.parametrize("event_type", ["PROVIDER_ATTEMPT_FAILED", "PROVIDER_RETRYING"])
def test_retry_audit_failure_blocks_next_provider_call(system, monkeypatch, operation, event_type):
    from access_ops.integrations.mock_okta import TransientProviderError
    workflow, database, provider = system
    calls = []
    def fail(request):
        calls.append(request.request_id)
        raise TransientProviderError("private-token")
    if operation == "revoke":
        response = submit(workflow, duration="1 day")
    original = database.append_event
    def fail_audit(event):
        if event.event_type == event_type:
            raise TransientProviderError("Even this exception outside the provider must not retry")
        original(event)
    monkeypatch.setattr(database, "append_event", fail_audit)
    monkeypatch.setattr(provider, operation, fail)
    if operation == "grant":
        response = submit(workflow)
    else:
        response = workflow.process_expired_access(database.get(response.request_id).expires_at)[0]
    assert calls == [response.request_id]
    assert database.get(response.request_id).status == (RequestStatus.PROVISIONING if operation == "grant" else RequestStatus.EXPIRED)
    assert "private-token" not in response.message
    assert not any(e.event_type == event_type for e in database.events(response.request_id))


def test_operation_replay_survives_reopen_and_does_not_touch_replacement_grant(system, tmp_path):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    assert provider.grant(request) == GrantResult.ALREADY_EXISTS
    assert len(provider.access_list()) == 1
    workflow.process_expired_access(request.expires_at)
    reopened = MockOkta(tmp_path / "provider.db")
    try:
        assert reopened.revoke(request) is True  # Previously confirmed removal.
        assert reopened.grant(request) == GrantResult.FAILED  # Never resurrect revoked access.
        assert reopened.access_list() == []
        replacement = replace(request, request_id="REQ-replacement")
        assert reopened.grant(replacement) == GrantResult.GRANTED
        assert reopened.revoke(request) is True
        assert reopened.access_list() == [(request.requester_slack_id, "GitHub", "Read")]
        assert reopened.connection.execute("SELECT grant_key FROM mock_access").fetchone()[0] == "REQ-replacement:grant"
        assert {row[0] for row in reopened.connection.execute("SELECT operation_id FROM mock_operations")} == {
            f"{request.request_id}:grant", f"{request.request_id}:revoke", "REQ-replacement:grant"}
        with pytest.raises(ValueError, match="different access"):
            reopened.revoke(replace(request, access_level="Write"))
    finally:
        reopened.close()


@pytest.mark.parametrize("operation", ["grant", "revoke"])
def test_provider_operation_record_and_mutation_are_atomic(system, operation):
    workflow, database, provider = system
    response = submit(workflow, duration="1 day")
    request = database.get(response.request_id)
    provider.connection.execute("""
        CREATE TRIGGER fail_operation BEFORE INSERT ON mock_operations
        BEGIN SELECT RAISE(ABORT, 'private database error'); END
    """)
    if operation == "grant":
        target = replace(request, request_id="REQ-other", access_level="Write")
    else:
        target = request
    before = provider.access_list()
    with pytest.raises(Exception, match="private database error"):
        getattr(provider, operation)(target)
    assert provider.access_list() == before
    assert provider.connection.execute("SELECT 1 FROM mock_operations WHERE operation_id = ?",
                                       (f"{target.request_id}:{operation}",)).fetchone() is None


@pytest.mark.parametrize("operation", ["grant", "revoke"])
def test_transient_then_permanent_failure_stops_immediately(system, monkeypatch, operation):
    from access_ops.integrations.mock_okta import TransientProviderError
    workflow, database, provider = system
    calls = []
    def fail(request):
        calls.append(request.request_id)
        if len(calls) == 1:
            raise TransientProviderError("private timeout")
        raise PermissionError("private authentication error")
    if operation == "revoke":
        response = submit(workflow, duration="1 day")
    monkeypatch.setattr(provider, operation, fail)
    if operation == "grant":
        response = submit(workflow)
    else:
        response = workflow.process_expired_access(database.get(response.request_id).expires_at)[0]
    assert calls == [response.request_id] * 2
    failures = [e for e in database.events(response.request_id) if e.event_type == "PROVIDER_ATTEMPT_FAILED"]
    assert "transient" in failures[0].details and "non-retryable" in failures[1].details
    assert "private" not in response.message


def test_already_existing_grant_operation_is_remembered(system):
    workflow, database, provider = system
    first = submit(workflow)
    second = submit(workflow)
    request = database.get(second.request_id)
    assert provider.grant(request) == GrantResult.ALREADY_EXISTS
    assert provider.revoke(database.get(first.request_id)) is True
    assert provider.grant(request) == GrantResult.FAILED
    assert provider.access_list() == []


@pytest.mark.parametrize("boundary", ["validation", "configuration", "revalidation", "pre_audit"])
def test_transient_error_outside_provider_never_enters_retry_loop(system, monkeypatch, boundary):
    from access_ops.integrations.mock_okta import TransientProviderError
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    def fail(*args):
        raise TransientProviderError("private error outside provider")
    if boundary == "revalidation":
        response = submit(workflow, access_level="Write")
        monkeypatch.setattr(workflow, "_validate", fail)
        response = workflow.approve(response.request_id, "UDEMO005")
        assert database.events(response.request_id)[-1].event_type == "REVALIDATION_FAILED"
    else:
        if boundary == "validation":
            monkeypatch.setattr(workflow, "_validate", fail)
        elif boundary == "configuration":
            monkeypatch.setattr("access_ops.workflow.match_policy", fail)
        else:
            original = database.append_event
            def fail_audit(event):
                if event.event_type == "PROVISIONING_STARTED":
                    fail()
                original(event)
            monkeypatch.setattr(database, "append_event", fail_audit)
        response = submit(workflow)
    assert calls == [] and provider.access_list() == []
    assert "private" not in response.message
