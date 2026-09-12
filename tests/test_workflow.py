"""Focused end-to-end checks for the first Access Ops vertical slice."""
from dataclasses import replace
from pathlib import Path

import pytest

from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import GrantResult, MockOkta
from access_ops.models import Decision, EmployeeStatus, RequestStatus
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
    assert len(provider.access_list()) == 1


@pytest.mark.parametrize("overrides", [
    {"employee_id": "unknown"}, {"employee_id": "UDEMO004"},
    {"employee_id": "UDEMO002"},
    {"employee_id": "UDEMO002", "access_level": "Write"},
    {"employee_id": "UDEMO011", "access_level": "Write"},
    {"application": "Notion", "access_level": "Standard"},
    {"application": "Unknown"}, {"access_level": "Owner"},
    {"duration": "7 days"}, {"duration": ""}, {"business_reason": "  "},
    {"application": ""}, {"access_level": None}, {"business_reason": None},
])
def test_invalid_or_out_of_slice_intake_never_calls_provider(system, monkeypatch, overrides):
    workflow, database, provider = system
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    response = submit(workflow, **overrides)
    assert response.request_id is None
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
    assert submit(workflow).request_id is None
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
    assert database.get(response.request_id).status == RequestStatus.APPROVED
    assert provider.access_list() == []
    assert len(database.events(response.request_id)) == 1


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
def test_unresolvable_manager_fails_closed(system, manager):
    workflow, database, provider = system
    workflow.configuration = replace(workflow.configuration, employees=tuple(
        replace(e, manager_slack_id=manager) if e.slack_user_id == "UDEMO001" else e
        for e in workflow.configuration.employees))
    response = submit(workflow, access_level="Write")
    assert response.request_id is None
    assert "manager could not be resolved" in response.message
    assert provider.access_list() == []


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
