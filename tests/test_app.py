"""Exercise the real Streamlit UI against isolated, persistent mock state."""
from pathlib import Path
import csv
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from access_ops.config import load_configuration
from access_ops.administration import PolicyAdministration
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


def test_reviewer_inbox_filters_actionable_requests_to_the_assigned_reviewer(app, tmp_path):
    submit(app, level="Write")
    assert any(message.value == "Pending approval" for message in app.info)

    # Mike is the assigned manager and sees Alice's Write request as actionable.
    app.selectbox(key="reviewer").set_value("UDEMO005").run()
    assert app.selectbox(key="review_request").options
    assert any(button.label == "Approve" for button in app.button)

    # The reviewer picker exposes configured authority only; Alice has none.
    reviewers = app.selectbox(key="reviewer").options
    assert not any("Alice Engineer" in reviewer for reviewer in reviewers)
    for reviewer in ("Mike Manager", "Grace GitHubOwner", "Ivan ITSecurity", "Dana DataOwner", "Sam SalesManager"):
        assert any(reviewer in option for option in reviewers)
    # Grace has exception-review authority, but not for Alice's manager approval.
    app.selectbox(key="reviewer").set_value("UDEMO006").run()
    assert not [select for select in app.selectbox if select.key == "review_request"]
    assert not any(button.label in ("Approve", "Reject") for button in app.button)

    # Selecting Mike again leaves the authorized review behavior unchanged.
    app.selectbox(key="reviewer").set_value("UDEMO005").run()
    click(app, "Approve")
    assert any("Approved — access confirmed" in message.value for message in app.success)
    db = Database(tmp_path / "workflow.db")
    try:
        assert db.request_rows()[0]["status"] == "ACTIVE"
        events = db.recent_audit_rows()
        assert sum(e["event_type"] == "REQUEST_APPROVED" for e in events) == 1
    finally:
        db.close()


@pytest.mark.parametrize("action,status", [("Approve", "ACTIVE"), ("Reject", "REJECTED")])
def test_exception_actions(app, tmp_path, action, status):
    submit(app, employee="UDEMO002", level="Write")
    assert any(message.value == "Exception review" for message in app.warning)
    app.selectbox(key="reviewer").set_value("UDEMO006").run()
    if action == "Reject":
        next(field for field in app.text_area if field.label == "Rejection reason").set_value("No launch work remains")
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
        app.selectbox(key="reviewer").set_value(reviewer).run()
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


@pytest.mark.parametrize("label,employee,level,duration,status", [
    ("1 · Auto-approval", "UDEMO001", "Read", "Permanent", "ACTIVE"),
    ("2 · Manager approval", "UDEMO001", "Write", "Permanent", "PENDING_APPROVAL"),
    ("3 · Configured exception", "UDEMO002", "Write", "7 days", "EXCEPTION_REVIEW"),
    ("4 · Inactive employee", "UDEMO004", "Read", "1 day", None),
])
def test_demo_prefill_waits_for_normal_submit(app, tmp_path, label, employee, level, duration, status):
    app.selectbox(key="application").set_value("Notion").run()
    click(app, label)
    db = Database(tmp_path / "workflow.db")
    try:
        assert db.request_rows() == []
        assert db.recent_audit_rows() == []
        assert app.selectbox(key="employee").value == employee
        assert app.selectbox(key="access_GitHub").value == level
        assert app.selectbox(key="duration").value == duration
        app.run()
        assert db.request_rows() == []
        click(app, "Submit request")
        if status:
            assert db.request_rows()[0]["status"] == status
        else:
            assert db.request_rows() == []
            assert db.recent_audit_rows()[0]["event_type"] == "INTAKE_STOPPED"
    finally:
        db.close()


def test_manual_review_is_visible_as_policy_hold_not_system_failure(app, tmp_path):
    app.selectbox(key="application").set_value("Figma").run()
    app.selectbox(key="access_Figma").set_value("Editor")
    app.text_area(key="reason").set_value("Review design handoff")
    click(app, "Submit request")
    assert any("Manual IT review" in message.value for message in app.warning)
    assert not app.error
    assert not app.success
    app.selectbox(key="ops_filter").set_value("Needs follow-up").run()
    assert any("MANUAL_REVIEW" in frame.value.get("status", []).values
               for frame in app.tabs[2].dataframe if "status" in frame.value.columns)
    assert not any(button.label == "Approve" for button in app.button)


def test_simplified_navigation_and_no_process_guides(app):
    assert [tab.label for tab in app.tabs] == ["Employee Request", "Reviewer Inbox", "IT Operations"]
    assert app.selectbox(key="employee").label == "Acting employee (simulated identity)"
    assert app.selectbox(key="reviewer").label == "Acting reviewer (simulated authority)"
    assert not any("Alice Engineer" in reviewer for reviewer in app.selectbox(key="reviewer").options)
    assert app.radio(key="it_section").options == ["Operations", "Active Access", "Configuration"]
    content = " ".join(str(e.value) for e in app.markdown)
    assert "Collect & validate" not in content and "Decide & route" not in content
    for section in ("Active Access", "Configuration", "Operations"):
        app.radio(key="it_section").set_value(section).run()
        assert not app.exception
        assert not any("demo could not load" in e.value for e in app.error)
        assert any(e.value == "Viewing as Olivia Operations" for e in app.tabs[2].caption)
        assert not any(e.key == "admin_actor" for e in app.selectbox)


@pytest.mark.parametrize("field,value", [("status", "inactive"), ("title", "Financial Analyst")])
def test_it_workspace_hidden_when_fixed_owner_loses_authority(tmp_path, monkeypatch, field, value):
    directory = tmp_path / "config"
    shutil.copytree(ROOT / "config", directory)
    employee_file = directory / "employees.csv"
    with employee_file.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        columns = reader.fieldnames
        employees = list(reader)
    for employee in employees:
        if employee["slack_user_id"] == "UDEMO009":
            employee[field] = value
        if field == "status" and employee["manager_slack_id"] == "UDEMO009":
            # Keep the directory valid so this exercises the workspace permission check.
            employee["manager_slack_id"] = ""
    with employee_file.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        writer.writerows(employees)
    monkeypatch.setenv("ACCESS_OPS_CONFIG_DIR", str(directory))
    monkeypatch.setenv("ACCESS_OPS_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    assert any(e.value == "You do not have access to IT Operations." for e in app.tabs[2].error)
    assert not app.tabs[2].dataframe
    assert not app.tabs[2].radio
    assert not app.tabs[2].selectbox


def test_normal_reject_ui_requires_reason_and_shows_history(app, tmp_path):
    submit(app, level="Write")
    app.selectbox(key="reviewer").set_value("UDEMO005").run()
    click(app, "Reject")
    assert any("Enter a rejection reason" in e.value for e in app.warning)
    db = Database(tmp_path / "workflow.db")
    try:
        rid = db.request_rows()[0]["request_id"]
        assert db.get(rid).status == "PENDING_APPROVAL"
        app.text_area(key=f"rejection_reason_{rid}").set_value("  Project was cancelled  ")
        click(app, "Reject")
        assert db.get(rid).status == "REJECTED"
        assert "Project was cancelled" in db.events(rid)[-1].details
        assert any("Project was cancelled" in str(e.value) for e in app.text)
        assert any("Project was cancelled" in str(e.value) for e in app.markdown)
    finally:
        db.close()


def test_active_access_ui_remove_confirmation_and_reason(app, tmp_path):
    submit(app)
    app.radio(key="it_section").set_value("Active Access").run()
    assert any("Alice Engineer" in str(frame.value) for frame in app.tabs[2].dataframe)
    click(app, "Remove this access")
    assert any("Enter a removal reason" in e.value for e in app.warning)
    db, provider = Database(tmp_path / "workflow.db"), MockOkta(tmp_path / "provider.db")
    try:
        rid = db.request_rows()[0]["request_id"]
        assert provider.access_list()
        app.text_area(key=f"remove_reason_{rid}").set_value("Task complete")
        app.checkbox(key=f"remove_confirm_{rid}").check()
        click(app, "Remove this access")
        assert not provider.access_list()
        assert db.get(rid).status == "REVOKED"
        assert "Task complete" in db.events(rid)[-1].details
        assert any("No current access grants" in e.value for e in app.info)
    finally:
        db.close()
        provider.close()


def test_config_ui_validate_save_restore_isolated_copy(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    shutil.copytree(ROOT / "config", directory)
    monkeypatch.setenv("ACCESS_OPS_CONFIG_DIR", str(directory))
    monkeypatch.setenv("ACCESS_OPS_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.radio(key="it_section").set_value("Configuration").run()
    app.number_input(key="policy_GH-READ-ENG_1max_duration_days").set_value(29)
    click(app, "Validate changes")
    assert load_configuration(directory).policies[0].max_duration_days == 30
    click(app, "Save reviewed changes")
    assert not app.error
    assert load_configuration(directory).policies[0].max_duration_days == 29
    app.number_input(key="policy_GH-READ-ENG_2max_duration_days").set_value(30)
    click(app, "Validate changes")
    click(app, "Save reviewed changes")
    config = load_configuration(directory)
    assert config.policies[0].max_duration_days == 30 and config.policies[0].policy_version == 3
    db = Database(tmp_path / "workflow.db")
    try:
        assert len(db.configuration_history()) == 4
        assert [row["outcome"] for row in db.configuration_history()].count("SAVE_SUCCEEDED") == 2
    finally:
        db.close()


def test_application_lifecycle_updates_employee_options(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    shutil.copytree(ROOT / "config", directory)
    monkeypatch.setenv("ACCESS_OPS_CONFIG_DIR", str(directory))
    monkeypatch.setenv("ACCESS_OPS_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert "Linear" not in app.selectbox(key="application").options
    database = Database(tmp_path / "workflow.db")
    try:
        service = PolicyAdministration(directory, database)
        changes = {"eligible_departments": ["Engineering"], "eligible_titles": ["Software Engineer"],
                   "decision": "AUTO_APPROVE", "approver_type": "NONE", "approver_id": None,
                   "temporary_allowed": False, "max_duration_days": 0, "permanent_allowed": True, "enabled": True}
        service.create_application("Linear", ["Read"], changes, "UDEMO009", service.revision())
        app.run()
        assert "Linear" in app.selectbox(key="application").options
        service.set_application_enabled("Linear", False, "UDEMO009", service.revision(), confirmed=True)
        app.run()
        assert "Linear" not in app.selectbox(key="application").options
        service.set_application_enabled("Linear", True, "UDEMO009", service.revision(), confirmed=True)
        app.run()
        assert "Linear" in app.selectbox(key="application").options
    finally:
        database.close()
