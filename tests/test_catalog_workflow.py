"""All shipped granting policies use the same authorized provider contract."""
from dataclasses import replace
from pathlib import Path

import pytest

from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import MockOkta
from access_ops.models import ApproverType, Decision, EmployeeStatus
from access_ops.policy_engine import match_policy
from access_ops.workflow import Workflow

CONFIG = load_configuration(Path(__file__).resolve().parents[1] / "config")
POLICIES = [p for p in CONFIG.policies if p.enabled and p.decision != Decision.REJECT]
HUMAN_POLICIES = [p for p in POLICIES if p.decision != Decision.AUTO_APPROVE]


def scenario(policy):
    for employee in CONFIG.employees:
        if employee.status != EmployeeStatus.ACTIVE:
            continue
        reviewer = employee.manager_slack_id if policy.approver_type == ApproverType.MANAGER else policy.approver_id
        if (match_policy(CONFIG, employee.slack_user_id, policy.application, policy.access_level) == policy
                and reviewer != employee.slack_user_id):
            return employee.slack_user_id, reviewer
    raise AssertionError(f"No synthetic employee for {policy.policy_id}")


@pytest.fixture
def system(tmp_path):
    database = Database(tmp_path / "workflow.db")
    provider = MockOkta(tmp_path / "provider.db")
    yield Workflow(CONFIG, database, provider), database, provider
    provider.close()
    database.close()


def submit(workflow, policy):
    employee, reviewer = scenario(policy)
    response = workflow.submit(employee, policy.application, policy.access_level,
                               "Catalog demo", "1 day")
    return response, employee, reviewer


def test_every_configured_application_has_a_granting_policy():
    assert len({p.application for p in CONFIG.policies}) == 5
    assert {p.application for p in POLICIES} == {p.application for p in CONFIG.policies}


@pytest.mark.parametrize("policy", POLICIES, ids=lambda p: p.policy_id)
def test_authorized_catalog_path_is_audited_and_durable(system, tmp_path, monkeypatch, policy):
    workflow, database, provider = system
    human = policy.decision != Decision.AUTO_APPROVE
    approval = ("EXCEPTION_APPROVED" if policy.decision == Decision.EXCEPTION_REVIEW else
                "REQUEST_APPROVED" if human else "REQUEST_AUTO_APPROVED")
    calls = []
    original = provider.grant

    def observe(request):
        reader = Database(tmp_path / "workflow.db")
        try:
            events = reader.events(request.request_id)
            types = [e.event_type for e in events]
            assert reader.get(request.request_id).status == "PROVISIONING"
            assert reader.policy_reference(request.request_id) == (policy.policy_id, policy.policy_version)
            assert types[-1] == "PROVISIONING_STARTED"
            assert types.index(approval) < types.index("PROVISIONING_STARTED")
            if human:
                assert types.index(approval) < types.index("REVALIDATION_SUCCEEDED") < types.index("PROVISIONING_STARTED")
                assert any(e.event_type == approval and e.actor == scenario(policy)[1] for e in events)
            calls.append(request.request_id)
        finally:
            reader.close()
        return original(request)

    monkeypatch.setattr(provider, "grant", observe)
    response, employee, reviewer = submit(workflow, policy)
    request = database.get(response.request_id)
    assert request is not None
    if human:
        assert request.status == ("EXCEPTION_REVIEW" if policy.decision == Decision.EXCEPTION_REVIEW else "PENDING_APPROVAL")
        assert request.assigned_approver_id == reviewer
        workflow.process(request.request_id)
        assert calls == [] and provider.access_list() == []
        response = workflow.approve(request.request_id, reviewer)
    assert "access is granted" in response.message
    assert calls == [request.request_id]
    reader, directory = Database(tmp_path / "workflow.db"), MockOkta(tmp_path / "provider.db")
    try:
        saved = reader.get(request.request_id)
        assert saved.status == "ACTIVE" and saved.provisioning_result == "GRANTED"
        assert saved.expires_at > saved.starts_at
        assert directory.access_list() == [(employee, policy.application, policy.access_level)]
        assert reader.events(request.request_id)[-1].event_type == "PROVISIONING_SUCCEEDED"
    finally:
        reader.close()
        directory.close()


@pytest.mark.parametrize("policy", HUMAN_POLICIES, ids=lambda p: p.policy_id)
def test_catalog_human_approval_cannot_be_bypassed(system, monkeypatch, policy):
    workflow, database, provider = system
    response, employee, reviewer = submit(workflow, policy)
    calls = []
    monkeypatch.setattr(provider, "grant", lambda request: calls.append(request))
    wrong_reviewer = next(e.slack_user_id for e in CONFIG.employees
                          if e.status == EmployeeStatus.ACTIVE and e.slack_user_id not in (employee, reviewer))
    for actor in (employee, wrong_reviewer, "unknown", "UDEMO004"):
        workflow.approve(response.request_id, actor)
        assert database.events(response.request_id)[-1].event_type == "APPROVAL_REJECTED"
    # Even a corrupted APPROVED row cannot replace the required audit evidence.
    with database.connection:
        database.connection.execute("UPDATE requests SET status = 'APPROVED' WHERE request_id = ?",
                                    (response.request_id,))
    workflow.process(response.request_id)
    assert database.get(response.request_id).status == "REJECTED"
    assert calls == [] and provider.access_list() == []


@pytest.mark.parametrize("policy", HUMAN_POLICIES, ids=lambda p: p.policy_id)
def test_catalog_revalidates_after_approval(system, monkeypatch, policy):
    workflow, database, provider = system
    response, employee, reviewer = submit(workflow, policy)
    original = database.transition

    def change_after_approval(request, event):
        original(request, event)
        if event.event_type in ("REQUEST_APPROVED", "EXCEPTION_APPROVED"):
            workflow.configuration = replace(CONFIG, employees=tuple(
                replace(e, status=EmployeeStatus.INACTIVE) if e.slack_user_id == employee else e
                for e in CONFIG.employees))

    monkeypatch.setattr(database, "transition", change_after_approval)
    workflow.approve(response.request_id, reviewer)
    assert database.get(response.request_id).status == "REJECTED"
    assert database.events(response.request_id)[-1].event_type == "REVALIDATION_FAILED"
    assert provider.access_list() == []


@pytest.mark.parametrize("policy", POLICIES, ids=lambda p: p.policy_id)
def test_catalog_provider_failure_never_becomes_active(system, policy):
    workflow, database, provider = system
    provider.fail_grant = True
    response, _, reviewer = submit(workflow, policy)
    if reviewer:
        workflow.approve(response.request_id, reviewer)
    assert database.get(response.request_id).status == "PROVISIONING_FAILED"
    assert database.events(response.request_id)[-1].event_type == "PROVISIONING_FAILED"
    assert provider.access_list() == []
