"""Exercise the real Streamlit UI against isolated, persistent mock state."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import MockOkta
from access_ops.policy_engine import match_policy
from access_ops.workflow import Workflow

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCESS_OPS_DATA_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def submit(app, employee="UDEMO001", level="Read", reason="Review documentation"):
    app.selectbox(key="employee").set_value(employee)
    app.selectbox(key="access_GitHub").set_value(level)
    app.text_area(key="reason").set_value(reason)
    app.selectbox(key="duration").set_value("Permanent")
    click(app, "Submit request")


def test_auto_approval_persistence_and_reruns_do_not_submit(app, tmp_path):
    assert [tab.label for tab in app.tabs] == ["Employee Request", "Reviewer Inbox", "IT Operations"]
    submit(app)
    assert any("Auto-approved" in message.value for message in app.success)
    reference = app.code[0].value
    app.run()
    fresh = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not fresh.exception
    db, provider = Database(tmp_path / "workflow.db"), MockOkta(tmp_path / "provider.db")
    try:
        assert len(db.request_rows()) == 1
        assert db.get(reference).status == "ACTIVE"
        assert provider.access_list() == [("UDEMO001", "GitHub", "Read")]
        assert len(db.recent_audit_rows()) == 3
        # Explicit repeat submission preserves backend duplicate behavior.
        submit(app)
        assert len(db.request_rows()) == 2
        assert len(provider.access_list()) == 1
    finally:
        db.close()
        provider.close()


@pytest.mark.parametrize("employee,reason", [("UDEMO004", "Need access"), ("UDEMO001", "")])
def test_validation_feedback_and_audit_only_reference(app, tmp_path, employee, reason):
    submit(app, employee=employee, reason=reason)
    assert any("Validation failure" in message.value for message in app.error)
    db = Database(tmp_path / "workflow.db")
    try:
        assert db.request_rows() == []
        assert db.recent_audit_rows()[0]["event_type"] == "INTAKE_STOPPED"
        assert app.code[0].value == db.recent_audit_rows()[0]["request_id"]
    finally:
        db.close()


def test_manager_actions_use_backend_authorization(app, tmp_path):
    submit(app, level="Write")
    assert any(message.value == "Pending approval" for message in app.info)
    for reviewer in ("UDEMO001", "UDEMO006"):
        app.selectbox(key="reviewer").set_value(reviewer)
        click(app, "Approve")
        assert any("rejected by the backend" in message.value for message in app.error)
    app.selectbox(key="reviewer").set_value("UDEMO005")
    click(app, "Deny")
    assert any("rejected by the backend" in message.value for message in app.error)
    click(app, "Approve")
    assert any("Approved — access confirmed" in message.value for message in app.success)
    db = Database(tmp_path / "workflow.db")
    try:
        assert db.request_rows()[0]["status"] == "ACTIVE"
        events = db.recent_audit_rows()
        assert sum(e["event_type"] == "APPROVAL_REJECTED" for e in events) == 3
    finally:
        db.close()


@pytest.mark.parametrize("action,status", [("Approve", "ACTIVE"), ("Deny", "REJECTED")])
def test_exception_actions(app, tmp_path, action, status):
    submit(app, employee="UDEMO002", level="Write")
    assert any(message.value == "Exception review" for message in app.warning)
    app.selectbox(key="reviewer").set_value("UDEMO006")
    click(app, action)
    assert app.success
    db = Database(tmp_path / "workflow.db")
    try:
        assert db.request_rows()[0]["status"] == status
    finally:
        db.close()


def test_provider_failure_is_not_presented_as_success(app, monkeypatch):
    monkeypatch.setattr(MockOkta, "grant", lambda self, request: None)
    submit(app)
    assert not app.success
    assert any("System failure" in message.value for message in app.error)
    assert any("PROVISIONING_FAILED" in message.value for message in app.caption)


def test_catalog_change_uses_configured_policy(app):
    app.selectbox(key="application").set_value("Notion").run()
    assert app.selectbox(key="access_Notion").options == ["Standard"]
    app.text_area(key="reason").set_value("Project notes")
    click(app, "Submit request")
    assert any("Auto-approved" in message.value for message in app.success)
    assert not app.error


@pytest.mark.parametrize("application", list(dict.fromkeys(
    p.application for p in load_configuration(ROOT / "config").policies
)))
def test_each_application_appears_in_it_operations_after_ui_request(app, application):
    config = load_configuration(ROOT / "config")
    policy = next(p for p in config.policies if p.application == application and p.enabled
                  and p.permanent_allowed and p.decision in ("AUTO_APPROVE", "APPROVAL_REQUIRED"))
    employee = next(e for e in config.employees if e.status == "active"
                    and match_policy(config, e.slack_user_id, application, policy.access_level) == policy)
    app.selectbox(key="employee").set_value(employee.slack_user_id)
    app.selectbox(key="application").set_value(application).run()
    app.selectbox(key=f"access_{application}").set_value(policy.access_level)
    app.text_area(key="reason").set_value("Catalog QA")
    app.selectbox(key="duration").set_value("Permanent")
    click(app, "Submit request")
    if policy.decision == "APPROVAL_REQUIRED":
        reviewer = employee.manager_slack_id if policy.approver_type == "MANAGER" else policy.approver_id
        app.selectbox(key="reviewer").set_value(reviewer)
        click(app, "Approve")
    assert app.success
    frames = [element.value for element in app.tabs[2].dataframe]
    directory = next(frame for frame in frames if list(frame.columns) == ["employee", "application", "access_level"])
    assert directory.iloc[0]["application"] == application
    assert directory.iloc[0]["access_level"] == policy.access_level
    assert employee.name in directory.iloc[0]["employee"]


def test_temporary_intake_uses_workflow_expiration(app, tmp_path):
    app.text_area(key="reason").set_value("Short documentation review")
    app.selectbox(key="access_GitHub").set_value("Read")
    app.selectbox(key="duration").set_value("1 day")
    click(app, "Submit request")
    db = Database(tmp_path / "workflow.db")
    try:
        request = db.get(app.code[0].value)
        assert request.temporary
        assert (request.expires_at - request.starts_at).total_seconds() == 86400
    finally:
        db.close()


def test_startup_error_is_safe(tmp_path, monkeypatch):
    invalid = tmp_path / "file"
    invalid.write_text("not a directory")
    monkeypatch.setenv("ACCESS_OPS_DATA_DIR", str(invalid))
    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception
    assert "System failure" in app.error[0].value
    assert str(invalid) not in app.error[0].value


@pytest.mark.parametrize("fail_revoke,status", [(False, "REVOKED"), (True, "REVOCATION_FAILED")])
def test_operations_show_persisted_expiration_results(app, tmp_path, fail_revoke, status):
    db = Database(tmp_path / "workflow.db")
    provider = MockOkta(tmp_path / "provider.db", fail_revoke=fail_revoke)
    try:
        workflow = Workflow(load_configuration(ROOT / "config"), db, provider)
        response = workflow.submit("UDEMO001", "GitHub", "Read", "Short review", "1 day")
        workflow.process_expired_access(now=db.get(response.request_id).expires_at)
        app.run()
        assert not app.exception
        frames = [element.value for element in app.dataframe]
        assert any("status" in frame.columns and status in frame["status"].values for frame in frames)
        assert len(provider.access_list()) == int(fail_revoke)
    finally:
        db.close()
        provider.close()
