"""Human-directed ownership actions preserve deterministic checks and evidence."""
from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from access_ops.administration import PolicyAdministration
from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import MockOkta
from access_ops.workflow import Workflow

ROOT = Path(__file__).resolve().parents[1]
OWNER = "UDEMO009"


@pytest.fixture
def system(tmp_path):
    directory = tmp_path / "config"
    shutil.copytree(ROOT / "config", directory)
    db = Database(tmp_path / "workflow.db")
    provider = MockOkta(tmp_path / "provider.db")
    workflow = Workflow(load_configuration(directory), db, provider)
    yield workflow, db, provider, PolicyAdministration(directory, db)
    provider.close()
    db.close()


def request(workflow, employee="UDEMO001", level="Read", duration="Permanent"):
    return workflow.submit(employee, "GitHub", level, "Project work", duration).request_id


@pytest.mark.parametrize("employee,reviewer", [("UDEMO001", "UDEMO005"), ("UDEMO002", "UDEMO006")])
@pytest.mark.parametrize("reason", ["", " \t\n "])
def test_rejection_requires_reason_in_service(system, employee, reviewer, reason):
    w, db, provider, _ = system
    rid = request(w, employee, "Write")
    status = db.get(rid).status
    assert "reason" in w.reject(rid, reviewer, reason).message
    assert db.get(rid).status == status
    assert db.events(rid)[-1].event_type == "REJECTION_REASON_REQUIRED"
    assert not provider.access_list()


@pytest.mark.parametrize("employee,actor", [("UDEMO001", "UDEMO001"), ("UDEMO001", "UDEMO006"),
                                         ("UDEMO002", "UDEMO002"), ("UDEMO002", "UDEMO005"),
                                         ("UDEMO001", "UDEMO004")])
def test_rejection_reason_never_bypasses_reviewer(system, employee, actor):
    w, db, provider, _ = system
    rid = request(w, employee, "Write")
    status = db.get(rid).status
    w.reject(rid, actor, "Valid human reason")
    assert db.get(rid).status == status
    assert db.events(rid)[-1].event_type == "APPROVAL_REJECTED"
    assert not provider.access_list()


@pytest.mark.parametrize("employee,reviewer,event_type", [("UDEMO001", "UDEMO005", "REQUEST_REJECTED"),
                                                        ("UDEMO002", "UDEMO006", "EXCEPTION_REJECTED")])
def test_reasoned_rejection_persists_and_is_final(system, tmp_path, employee, reviewer, event_type):
    w, db, provider, _ = system
    rid = request(w, employee, "Write")
    response = w.reject(rid, reviewer, "  Work was cancelled  ")
    assert "Work was cancelled" in response.message
    reopened = Database(tmp_path / "workflow.db")
    try:
        assert reopened.get(rid).status == "REJECTED"
        event = reopened.events(rid)[-1]
        assert event.event_type == event_type and event.actor == reviewer
        assert event.details.endswith("Reason: Work was cancelled")
        assert event.timestamp and event.previous_status != "REJECTED"
    finally:
        reopened.close()
    w.approve(rid, reviewer)
    assert db.get(rid).status == "REJECTED" and not provider.access_list()


@pytest.mark.parametrize("actor,reason,confirmed", [(OWNER, "", True), (OWNER, " \t ", True),
                                                  (OWNER, "Done", False), ("UDEMO001", "Done", True),
                                                  ("unknown", "Done", True), ("UDEMO004", "Done", True)])
def test_manual_removal_guards(system, actor, reason, confirmed):
    w, db, provider, _ = system
    rid = request(w)
    w.remove_access(rid, actor, reason, confirmed=confirmed)
    assert db.get(rid).status == "ACTIVE"
    assert len(w.active_access()) == 1 and provider.access_list()
    assert db.events(rid)[-1].event_type == "MANUAL_REVOCATION_BLOCKED"


def test_manual_removal_audit_precedes_provider_and_preserves_history(system, monkeypatch, tmp_path):
    w, db, provider, _ = system
    rid = request(w)
    original = provider.revoke
    def observe(req):
        reader = Database(tmp_path / "workflow.db")
        try:
            event = reader.events(rid)[-1]
            assert event.event_type == "MANUAL_REVOCATION_STARTED"
            assert event.actor == OWNER and "Project ended" in event.details
        finally:
            reader.close()
        return original(req)
    monkeypatch.setattr(provider, "revoke", observe)
    before = len(db.events(rid))
    response = w.remove_access(rid, OWNER, " Project ended ", confirmed=True)
    assert "Access removed" in response.message
    assert not w.active_access() and not provider.access_list()
    assert db.get(rid).status == "REVOKED"
    assert db.get(rid).revocation_status == "REVOKED"
    assert len(db.events(rid)) == before + 2
    assert "Project ended" in db.events(rid)[-1].details
    assert db.request_rows()[0]["request_id"] == rid


def test_failed_removal_keeps_current_grant_and_reason(system):
    w, db, provider, _ = system
    rid = request(w)
    provider.fail_revoke = True
    w.remove_access(rid, OWNER, "Contract ended", confirmed=True)
    assert db.get(rid).status == "REVOCATION_FAILED"
    assert len(w.active_access()) == 1 and provider.access_list()
    assert "Contract ended" in db.events(rid)[-1].details
    assert w.notifications.deliveries()


def test_active_access_uses_original_grant_not_duplicate_requests(system):
    w, db, provider, _ = system
    original = request(w)
    duplicate = request(w)
    assert db.get(duplicate).status == "ACTIVE"
    assert [g["request_id"] for g in w.active_access()] == [original]
    w.remove_access(duplicate, OWNER, "Wrong reference", confirmed=True)
    assert provider.access_list()
    w.remove_access(original, OWNER, "Done", confirmed=True)
    assert not w.active_access()
    assert len(db.request_rows()) == 2
    assert db.get(duplicate).status == "ACTIVE"  # historical outcome was not rewritten


@pytest.mark.parametrize("fail", [False, True])
def test_expired_current_access_follows_actual_provider_presence(system, fail):
    w, db, provider, _ = system
    rid = request(w, duration="1 day")
    provider.fail_revoke = fail
    assert len(w.active_access()) == 1
    w.process_expired_access(now=db.get(rid).expires_at)
    assert bool(w.active_access()) == fail
    assert db.get(rid).status == ("REVOCATION_FAILED" if fail else "REVOKED")


def test_manual_pre_audit_failure_blocks_provider(system, monkeypatch):
    w, db, provider, _ = system
    rid = request(w)
    original = db.append_event
    def fail(event):
        if event.event_type == "MANUAL_REVOCATION_STARTED":
            raise RuntimeError("audit unavailable")
        original(event)
    monkeypatch.setattr(db, "append_event", fail)
    w.remove_access(rid, OWNER, "Done", confirmed=True)
    assert db.get(rid).status == "ACTIVE"
    assert provider.access_list()
    assert not any(e.event_type == "MANUAL_REVOCATION_STARTED" for e in db.events(rid))


def test_policy_save_reload_audit_and_unchanged_history(system):
    w, db, _, service = system
    rid = request(w)
    before_request, before_events = db.get(rid), db.events(rid)
    revision = service.revision()
    before, after = service.preview("GH-READ-ENG", {"max_duration_days": 29}, OWNER, revision)
    assert before["max_duration_days"] == 30 and after["policy_version"] == 2
    service.save("GH-READ-ENG", {"max_duration_days": 29}, OWNER, revision)
    config = load_configuration(service.directory)
    assert config.policies[0].max_duration_days == 29
    assert config.policies[0].policy_version == 2
    history = db.configuration_history()
    assert [e["outcome"] for e in history] == ["SAVE_SUCCEEDED", "SAVE_STARTED"]
    assert json.loads(history[0]["before_json"])["max_duration_days"] == 30
    assert json.loads(history[0]["after_json"])["max_duration_days"] == 29
    assert history[0]["actor"] == OWNER and history[0]["timestamp"]
    assert db.get(rid) == before_request and db.events(rid) == before_events
    service.save("GH-READ-ENG", {"max_duration_days": 30}, OWNER, service.revision())
    assert load_configuration(service.directory).policies[0].policy_version == 3
    assert len(db.configuration_history()) == 4


@pytest.mark.parametrize("policy,changes", [
    ("GH-READ-ENG", {"enabled": "yes"}), ("GH-READ-ENG", {"max_duration_days": -1}),
    ("GH-READ-ENG", {"application": "Unknown"}), ("GH-READ-ENG", {"access_level": "Admin"}),
    ("GH-READ-ENG", {"policy_version": 999}), ("GH-READ-ENG", {"eligible_titles": ["Invented"]}),
    ("GH-READ-ENG", {"eligible_departments": []}),
    ("GH-WRITE-EXCEPTION", {"eligible_departments": ["Engineering"]}),
    ("GH-WRITE-EXCEPTION", {"approver_id": None}),
    ("GH-WRITE-EXCEPTION", {"approver_id": "UDEMO004"}),
    ("GH-WRITE-EXCEPTION", {"approver_type": "MANAGER", "approver_id": None}),
    ("GH-ADMIN-ENG", {"permanent_allowed": True}),
    ("GH-READ-ENG", {"decision": "AI_APPROVE"}),
    ("GH-READ-ENG", {"temporary_allowed": False}),
])
def test_bad_policy_changes_leave_source_unchanged(system, policy, changes):
    _, db, _, service = system
    original = (service.directory / "access_policies.csv").read_bytes()
    with pytest.raises(ValueError):
        service.save(policy, changes, OWNER, service.revision())
    assert (service.directory / "access_policies.csv").read_bytes() == original
    assert db.configuration_history()[0]["outcome"] == "SAVE_REJECTED_OR_FAILED"


def test_policy_save_rejects_stale_review_and_unauthorized_actor(system):
    _, _, _, service = system
    revision = service.revision()
    with pytest.raises(ValueError):
        service.save("GH-READ-ENG", {"max_duration_days": 29}, "UDEMO001", revision)
    service.save("GH-READ-ENG", {"max_duration_days": 29}, OWNER, revision)
    with pytest.raises(ValueError, match="changed"):
        service.save("GH-READ-ENG", {"max_duration_days": 28}, OWNER, revision)


def test_config_pre_audit_failure_prevents_file_change(system, monkeypatch):
    _, db, _, service = system
    original = (service.directory / "access_policies.csv").read_bytes()
    def fail(*args):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(db, "config_event", fail)
    with pytest.raises(RuntimeError):
        service.save("GH-READ-ENG", {"max_duration_days": 29}, OWNER, service.revision())
    assert (service.directory / "access_policies.csv").read_bytes() == original


def test_config_completion_audit_failure_reports_uncertainty(system, monkeypatch):
    _, db, _, service = system
    original = db.config_event
    def fail(policy, actor, outcome, before, after):
        if outcome == "SAVE_SUCCEEDED":
            raise RuntimeError("completion audit unavailable")
        original(policy, actor, outcome, before, after)
    monkeypatch.setattr(db, "config_event", fail)
    with pytest.raises(RuntimeError):
        service.save("GH-READ-ENG", {"max_duration_days": 29}, OWNER, service.revision())
    assert load_configuration(service.directory).policies[0].max_duration_days == 29
    assert db.configuration_history()[0]["outcome"] == "SAVE_STARTED"


def test_pending_request_revalidates_after_policy_edit(system):
    w, db, provider, service = system
    rid = request(w, level="Write")
    original_ref = db.policy_reference(rid)
    service.save("GH-WRITE-ENG", {"max_duration_days": 29}, OWNER, service.revision())
    updated = Workflow(load_configuration(service.directory), db, provider)
    updated.approve(rid, "UDEMO005")
    assert db.get(rid).status == "REJECTED"
    assert db.policy_reference(rid) == original_ref
    assert db.events(rid)[-1].event_type == "REVALIDATION_FAILED"
    assert not provider.access_list()


@pytest.mark.parametrize("changes", [
    {"status": "PENDING_APPROVAL"}, {"status": "REVOKED"},
    {"provisioning_result": "ALREADY_EXISTS"}, {"starts_at": None}, {"expires_at": None},
])
def test_manual_removal_rejects_inconsistent_source_lifecycle(system, monkeypatch, changes):
    w, db, provider, _ = system
    rid = request(w, duration="1 day")
    original = db.get(rid)
    monkeypatch.setattr(db, "get", lambda selected: replace(original, **changes))
    calls = []
    monkeypatch.setattr(provider, "revoke", lambda req: calls.append(req) or True)
    w.remove_access(rid, OWNER, "Done", confirmed=True)
    assert calls == [] and provider.access_list()
    assert db.events(rid)[-1].event_type == "MANUAL_REVOCATION_BLOCKED"


def test_manual_removal_requires_provisioning_evidence(system, monkeypatch):
    w, db, provider, _ = system
    rid = request(w)
    events = db.events(rid)
    monkeypatch.setattr(db, "events", lambda selected: [e for e in events if e.event_type != "PROVISIONING_SUCCEEDED"])
    calls = []
    monkeypatch.setattr(provider, "revoke", lambda req: calls.append(req) or True)
    w.remove_access(rid, OWNER, "Done", confirmed=True)
    assert not calls and provider.access_list()


def test_explicit_manual_retry_preserves_both_reasons(system):
    w, db, provider, _ = system
    rid = request(w)
    provider.fail_revoke = True
    w.remove_access(rid, OWNER, "Initial removal", confirmed=True)
    assert w.active_access()
    provider.fail_revoke = False
    w.remove_access(rid, OWNER, "Retry after provider recovery", confirmed=True)
    assert not w.active_access() and db.get(rid).status == "REVOKED"
    events = db.events(rid)
    assert any(e.event_type == "REVOCATION_FAILED" and "Initial removal" in e.details for e in events)
    assert "Retry after provider recovery" in events[-1].details


def test_normal_rejection_rechecks_current_manager_authority(system):
    w, db, provider, _ = system
    rid = request(w, level="Write")
    w.configuration = replace(w.configuration, employees=tuple(
        replace(e, manager_slack_id="UDEMO009") if e.slack_user_id == "UDEMO001" else e
        for e in w.configuration.employees))
    w.reject(rid, "UDEMO005", "Old manager attempt")
    assert db.get(rid).status == "PENDING_APPROVAL"
    assert db.events(rid)[-1].event_type == "APPROVAL_REJECTED"
    assert not provider.access_list()

NEW_POLICY = {"eligible_departments": ["Engineering"], "eligible_titles": ["Software Engineer"],
              "decision": "AUTO_APPROVE", "approver_type": "NONE", "approver_id": None,
              "temporary_allowed": False, "max_duration_days": 0, "permanent_allowed": True, "enabled": True}


def test_application_create_disable_reenable_is_audited_and_preserves_grants(system):
    w, db, provider, service = system
    revision = service.revision()
    service.preview_application("Linear", ["Read"], NEW_POLICY, OWNER, revision)
    service.create_application("Linear", ["Read"], NEW_POLICY, OWNER, revision)
    created = load_configuration(service.directory)
    assert created.application("Linear").enabled and created.application_access["Linear"] == frozenset({"Read"})
    added = Workflow(created, db, provider)
    rid = added.submit("UDEMO001", "Linear", "Read", "Plan work", "Permanent").request_id
    assert db.get(rid).status == "ACTIVE" and provider.access_list()[-1] == ("UDEMO001", "Linear", "Read")
    service.set_application_enabled("Linear", False, OWNER, service.revision(), confirmed=True)
    disabled = load_configuration(service.directory)
    assert not disabled.application("Linear").enabled
    blocked = Workflow(disabled, db, provider).submit("UDEMO001", "Linear", "Read", "No bypass", "Permanent")
    assert blocked.request_id and db.get(rid).status == "ACTIVE" and ("UDEMO001", "Linear", "Read") in provider.access_list()
    assert "disabled" in blocked.message.lower()
    service.set_application_enabled("Linear", True, OWNER, service.revision(), confirmed=True)
    assert load_configuration(service.directory).application("Linear").enabled
    outcomes = [event["outcome"] for event in db.configuration_history()]
    assert "APPLICATION_ADD_SUCCEEDED" in outcomes and "APPLICATION_DISABLED_SUCCEEDED" in outcomes and "APPLICATION_REENABLED_SUCCEEDED" in outcomes


@pytest.mark.parametrize("name,levels,changes", [
    ("", ["Read"], NEW_POLICY), ("GitHub", ["Read"], NEW_POLICY), ("Linear", ["Unknown"], NEW_POLICY),
    ("Linear", ["Read"], {**NEW_POLICY, "decision": "AI_APPROVE"}),
    ("Linear", ["Read"], {**NEW_POLICY, "decision": "APPROVAL_REQUIRED", "approver_type": "APPLICATION_OWNER", "approver_id": None}),
])
def test_application_create_rejects_invalid_configuration(system, name, levels, changes):
    _, db, _, service = system
    source = (service.directory / "access_policies.csv").read_bytes()
    with pytest.raises(ValueError):
        service.create_application(name, levels, changes, OWNER, service.revision())
    assert (service.directory / "access_policies.csv").read_bytes() == source


def test_disable_requires_confirmation(system):
    _, _, _, service = system
    with pytest.raises(ValueError, match="Confirm"):
        service.set_application_enabled("Notion", False, OWNER, service.revision(), confirmed=False)
    assert load_configuration(service.directory).application("Notion").enabled
