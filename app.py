"""Local Streamlit presentation; all access actions go through Workflow."""
import os
from pathlib import Path
import sys

import streamlit as st
import ui

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import MockOkta
from access_ops.workflow import DURATION_DAYS, Workflow
from access_ops.administration import PolicyAdministration, require_owner
from access_ops.approvals import configured_reviewer_ids
from access_ops.sla import DEMO_SLA_HOURS, UNRESOLVED_SLA_STATUSES, format_age, request_age, sla_status
import admin_ui
from datetime import datetime, timezone


def show_response(response, request, events, *, review=False):
    """Display backend feedback and recorded outcomes; never infer authorization."""
    last = events[-1].event_type if events else None
    if last == "INTAKE_STOPPED":
        st.error("Validation failure / request not accepted")
    elif last == "APPROVAL_REJECTED":
        st.error("Review action rejected by the backend")
    elif last in ("EXCEPTION_REJECTED", "REQUEST_REJECTED"):
        st.success("Request rejected; no access granted")
    elif last == "REJECTION_REASON_REQUIRED":
        st.warning("Enter a rejection reason; the request remains pending.")
    elif last == "PROVISIONING_SUCCEEDED":
        automatic = any(e.event_type == "REQUEST_AUTO_APPROVED" for e in events)
        st.success("Auto-approved — access confirmed" if automatic else "Approved — access confirmed")
    elif not review and request and request.status == "PENDING_APPROVAL":
        st.info("Pending approval")
    elif not review and request and request.status == "EXCEPTION_REVIEW":
        st.warning("Exception review")
    elif not review and request and request.status == "MANUAL_REVIEW":
        st.warning("Manual IT review — no matching policy; no access authorized")
    elif last == "REVALIDATION_FAILED":
        st.error("Backend revalidation failed; provisioning stopped")
    else:
        st.error("System failure / action stopped — follow the backend guidance below")
    st.write(response.message)
    with st.expander("Response reference & recorded state"):
        if response.request_id:
            st.code(response.request_id, language=None)
        if request:
            st.caption(f"Persisted status at response: {request.status}")


def table(title, rows):
    st.subheader(title)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.caption("No records yet.")


def render(configuration, database, provider, config_dir=ROOT / "config"):
    workflow = Workflow(configuration, database, provider)
    employees = {e.slack_user_id: e for e in configuration.employees}

    def person(employee_id):
        employee = employees.get(employee_id)
        return f"{employee.name} · {employee.department} · {employee.status}" if employee else employee_id or "Unassigned"

    def name(employee_id):
        employee = employees.get(employee_id)
        return employee.name if employee else employee_id or "None assigned"

    def context(employee_id):
        employee = employees.get(employee_id)
        return f"{employee.title} · {employee.department}" if employee else "Not in directory"

    def prefill(employee, level, duration, reason):
        # Presentation only. The form still submits through the unchanged workflow.
        st.session_state.update(employee=employee, application="GitHub", access_GitHub=level,
                                duration=duration, reason=reason)

    def request_label(row):
        return f'{name(row["requester_slack_id"])} · {row["application"]} {row["access_level"]} · {row["request_id"][-8:]}'

    def request_card(row):
        ui.status(row["status"])
        st.subheader(f'{name(row["requester_slack_id"])} → {row["application"]} {row["access_level"]}')
        ui.details([("Employee context", context(row["requester_slack_id"])),
                    ("Requested duration", row["duration"]),
                    ("Authorized reviewer", name(row["assigned_approver_id"]))])
        st.caption("Business reason")
        ui.reason(row["business_reason"])

    employee_tab, reviewer_tab, operations_tab = st.tabs(
        ["Employee Request", "Reviewer Inbox", "IT Operations"]
    )
    with employee_tab:
        st.markdown("**Try a scenario** · Prefills only. Review the fields, then submit.")
        scenarios = [
            ("1 · Auto-approval", "UDEMO001", "Read", "Permanent", "Review engineering documentation"),
            ("2 · Manager approval", "UDEMO001", "Write", "Permanent", "Contribute code to the engineering repository"),
            ("3 · Configured exception", "UDEMO002", "Write", "7 days", "Support the product website launch"),
            ("4 · Inactive employee", "UDEMO004", "Read", "1 day", "Review engineering documentation"),
        ]
        for column, (label, *values) in zip(st.columns(4), scenarios):
            column.button(label, on_click=prefill, args=values, use_container_width=True)
        with st.container(key="request_shell_header"):
            title, actor = st.columns([3, 2], gap="large", vertical_alignment="center")
            with title:
                ui.shell_copy("Mock Slack UI", "Employee request · Slack integration is future-state")
            with actor:
                employee_id = st.selectbox("Acting employee (simulated identity)", list(employees),
                                           format_func=person, key="employee")
        with st.container(key="request_workspace"):
            rail, content = st.columns([1, 4], gap="large")
            with rail:
                ui.workspace("access-requests")
            with content:
                st.markdown("**# access-requests**")
                ui.message(name(employee_id), "I need application access.", tag="request preview")
                ui.message("Access Ops", "Choose the application and access level, then tell us why and for how long.", tag="APP · mock")
                app_column, level_column = st.columns(2)
                applications = [a.application for a in configuration.applications if a.enabled and any(p.enabled and p.application == a.application for p in configuration.policies)]
                application = app_column.selectbox("Application", applications, key="application")
                # Outside the form so changing application refreshes the role choices.
                levels = list(dict.fromkeys(p.access_level for p in configuration.policies if p.enabled and p.application == application))
                access_level = level_column.selectbox("Access level", levels, key=f"access_{application}")
                with st.form("request_form"):
                    reason = st.text_area("Business reason", key="reason", height=80, placeholder="What work will this access support?")
                    duration = st.selectbox("Duration", list(DURATION_DAYS), key="duration")
                    st.caption("Temporary access starts when granted. Policy checks the duration. Do not include secrets or customer data.")
                    submitted = st.form_submit_button("Submit request", type="primary")
                if submitted:
                    response = workflow.submit(employee_id, application, access_level, reason, duration)
                    show_response(response, database.get(response.request_id), database.events(response.request_id))

    with reviewer_tab:
        st.caption("Demo: Alice → GitHub Write waits for Mike Manager. Paul’s configured exception goes to Grace GitHubOwner.")
        with st.container(key="review_shell_header"):
            title, actor = st.columns([3, 2], gap="large", vertical_alignment="center")
            with title:
                ui.shell_copy("Mock Slack UI", "Simulated reviewer inbox · assigned requests only in this local demo")
            with actor:
                reviewer = st.selectbox("Acting reviewer (simulated authority)", configured_reviewer_ids(configuration),
                                        format_func=person, key="reviewer")
        pending = [r for r in database.request_rows() if r["status"] in ("PENDING_APPROVAL", "EXCEPTION_REVIEW")]
        with st.container(key="review_workspace"):
            rail, content = st.columns([1, 4], gap="large")
            with rail:
                ui.workspace("approvals")
            with content:
                assigned = [row for row in pending if row["assigned_approver_id"] == reviewer]
                st.markdown(f"**Access Ops · approval inbox** · {len(assigned)} assigned to you")
                st.caption("This identity is who clicks. Only requests assigned to it are actionable. No production authentication.")
                if "review_feedback" in st.session_state:
                    st.caption("Last review response · snapshot at time of action")
                    feedback_request = st.session_state["review_feedback"][1]
                    if feedback_request:
                        st.markdown(f'**{name(feedback_request.requester_slack_id)} · {feedback_request.application} {feedback_request.access_level}**')
                        ui.status(feedback_request.status)
                    show_response(*st.session_state["review_feedback"], review=True)
                    st.divider()
                if assigned:
                    by_id = {r["request_id"]: r for r in assigned}
                    request_id = st.selectbox("Request to review", list(by_id), format_func=lambda value: request_label(by_id[value]), key="review_request")
                    row = by_id[request_id]
                    request_card(row)
                    policy_reason = ("Outside normal eligibility: one configured exception reviewer must decide." if row["status"] == "EXCEPTION_REVIEW"
                                     else "Configured policy requires human approval before provisioning.")
                    st.info(f'{policy_reason} Policy: {row["policy_id"]} · v{row["policy_version"]}.')
                    if reviewer != row["assigned_approver_id"]:
                        st.warning(f'Acting as {name(reviewer)}; this request requires {name(row["assigned_approver_id"])}. The backend checks every attempt.')
                    rejection_reason = st.text_area("Rejection reason", key=f"rejection_reason_{request_id}",
                                                    placeholder="Required to reject. Explain the decision; do not include secrets.")
                    approve, deny = st.columns(2)
                    action = None
                    if approve.button("Approve", type="primary", use_container_width=True):
                        action = workflow.approve
                    if deny.button("Reject", use_container_width=True):
                        if not rejection_reason.strip():
                            st.warning("Enter a rejection reason; the request remains pending.")
                        else:
                            action = workflow.reject
                    if action:
                        response = (action(request_id, reviewer, rejection_reason)
                                    if action == workflow.reject else action(request_id, reviewer))
                        # Keep the action's feedback snapshot across the inbox refresh.
                        st.session_state["review_feedback"] = (
                            response, database.get(response.request_id), database.events(response.request_id)
                        )
                        st.rerun()
                else:
                    ui.message("Access Ops", f"No approval requests are assigned to {name(reviewer)}.", tag="APP · mock")

    with operations_tab:
        # Fixed local demo owner; employee/reviewer selectors do not set IT authority.
        actor = "UDEMO009"
        try:
            require_owner(configuration, actor)
        except ValueError:
            st.error("You do not have access to IT Operations.")
            return
        st.caption(f"Viewing as {name(actor)}")
        section = st.radio("IT workspace", ["Operations", "Active Access", "Configuration"], horizontal=True, key="it_section")
        if section != "Operations":
            if section == "Active Access":
                admin_ui.active_access(workflow, actor, name)
            else:
                admin_ui.configuration_editor(PolicyAdministration(config_dir, database), configuration, actor, name, workflow)
            return
        st.caption("Demo: Alice → Figma Editor shows manual review. Failure and expiration harness examples are in README.")
        ui.shell("Operations console", "Local request store + mock Okta · timestamps in UTC")
        rows = database.request_rows()
        with st.container(key="operations_workspace"):
            heading, refresh = st.columns([3, 1])
            heading.subheader("Requests & follow-up")
            refresh.button("Refresh requests", use_container_width=True)
            for column, value, label in zip(st.columns(3), ["MANUAL_REVIEW", "PROVISIONING_FAILED", "REVOCATION_FAILED"],
                                             ["Manual IT review", "Provisioning failed", "Revocation failed"]):
                with column:
                    st.metric(label, sum(r["status"] == value for r in rows))
            now = datetime.now(timezone.utc)
            past_target = sum(
                r["status"] in UNRESOLVED_SLA_STATUSES
                and sla_status(datetime.fromisoformat(r["created_at"]), now) == "Past target"
                for r in rows
            )
            st.metric("Past 24h target", past_target)
            focus = st.selectbox("Show requests", ["All requests", "Needs follow-up", "Awaiting reviewer", "Temporary access"], key="ops_filter")
            attention = {"MANUAL_REVIEW", "PROVISIONING_FAILED", "REVOCATION_FAILED", "PROVISIONING", "EXPIRED", "REJECTED"}
            visible = [r for r in rows if focus == "All requests"
                       or (focus == "Needs follow-up" and (r["status"] in attention or (r["status"] in ("PENDING_APPROVAL", "EXCEPTION_REVIEW") and not r["assigned_approver_id"])))
                       or (focus == "Awaiting reviewer" and r["status"] in ("PENDING_APPROVAL", "EXCEPTION_REVIEW"))
                       or (focus == "Temporary access" and r["temporary"])]
            st.caption(f"{len(visible)} matching requests · scroll the table to see all. Counters above cover all {len(rows)} stored requests.")
            selected_index = ui.register([{"status": r["status"], "Employee": name(r["requester_slack_id"]),
                                           "Application": r["application"], "Access": r["access_level"],
                                           "Duration": r["duration"], "Reviewer": name(r["assigned_approver_id"]),
                                           "Reference": r["request_id"][-8:]} for r in visible])
            if visible:
                by_id = {r["request_id"]: r for r in visible}
                if selected_index is not None and selected_index < len(visible):
                    st.session_state["ops_request"] = visible[selected_index]["request_id"]
                st.caption("Select a row to inspect it, or choose by employee, application, and reference.")
                selected = st.selectbox("Inspect request", list(by_id), format_func=lambda value: request_label(by_id[value]), key="ops_request")
                row = by_id[selected]
                ui.status(row["status"])
                st.subheader(f'{name(row["requester_slack_id"])} → {row["application"]} {row["access_level"]}')
                age = request_age(datetime.fromisoformat(row["created_at"]), now)
                st.caption(f"Age: {format_age(age)} · SLA: {sla_status(datetime.fromisoformat(row['created_at']), now)} {DEMO_SLA_HOURS}h demo target")
                if row["status"] in attention or row["status"] == "EXCEPTION_REVIEW":
                    guidance = {"MANUAL_REVIEW":"No matching policy. IT must investigate eligibility and configuration; this request cannot authorize a grant.",
                                "PROVISIONING_FAILED":"Grant not confirmed. Investigate the recorded provider result; do not treat approval as successful access.",
                                "REVOCATION_FAILED":"Removal not confirmed. Access may remain in mock Okta; IT follow-up is required.",
                                "EXCEPTION_REVIEW":"Outside normal eligibility. Await the configured exception reviewer; no access granted by this request."}
                    notice = st.error if row["status"] in ("PROVISIONING_FAILED", "REVOCATION_FAILED", "REJECTED") else st.warning
                    notice(guidance.get(row["status"], "Review the recorded state and history before taking further action."))
                ui.details([("Recorded grant result", {"GRANTED":"Grant confirmed", "ALREADY_EXISTS":"Access already existed", "FAILED":"Grant not confirmed"}.get(row["provisioning_result"], row["provisioning_result"] or "Not confirmed")),
                            ("Expiration", ui.timestamp(row["expires_at"]) if row["temporary"] else "Permanent"),
                            ("Removal tracking", row["revocation_status"].replace("_", " ").title())])
                if row["status"] == "REVOCATION_FAILED":
                    st.caption("Removal remains pending in storage because the attempt failed. The request status records that failure; a past grant confirmation does not confirm removal.")
                events = database.events(selected)
                with st.expander("Request history & reference", expanded=False):
                    ui.details([("Employee context", context(row["requester_slack_id"])),
                                ("Requested duration", row["duration"]),
                                ("Authorized reviewer", name(row["assigned_approver_id"])),
                                ("Policy reference", f'{row["policy_id"] or "No matching policy"} / v{row["policy_version"]}'),
                                ("Created (UTC)", row["created_at"]), ("Updated (UTC)", row["updated_at"])])
                    st.caption(f'Exact expiration: {row["expires_at"] or "None recorded"}')
                    st.caption("Business reason")
                    ui.reason(row["business_reason"])
                    st.code(selected, language=None)
                    for event in events:
                        st.markdown(f'**{event.event_type.replace("_", " ").title()}** · {event.timestamp:%Y-%m-%d %H:%M:%S} UTC')
                        st.text(event.details)
                        st.caption(f'Actor: {name(event.actor)} · {event.previous_status or "Intake"} → {event.new_status or "—"} · policy v{event.policy_version}')
            with st.expander("Mock access directory"):
                table("Active access in mock Okta", [
                    {"employee": person(employee), "application": app, "access_level": level}
                    for employee, app, level in provider.access_list()
                ])
                st.caption("Actual local mock grants. Access may remain after a revocation failure.")
            audit = database.recent_audit_rows()
            intake = [r for r in audit if r["event_type"] == "INTAKE_STOPPED"]
            with st.expander(f"Stopped intake · {len(intake)} in latest 100 events"):
                st.caption("Unknown/inactive identities and invalid inputs retain audit references, not request rows.")
                table("Intake failures", [{"Outcome": r["new_status"], "Reason": r["details"], "UTC": r["timestamp"], "Reference": r["request_id"]} for r in intake])
            with st.expander("Recent audit events & mock IT inbox"):
                table("Recent audit events (latest 100)", audit)
                st.caption("Local deliveries cover supported notification paths; this is not a universal alerting service.")
                table("Mock IT Operations inbox", workflow.notifications.deliveries())


def main():
    st.set_page_config(page_title="Access Ops", layout="wide")
    ui.styles()
    st.title("Access Ops")
    st.caption("ACCESS REQUESTS, UNDER CONTROL  /  Local demo · synthetic identities · mocked Slack, directory & Okta · no authentication")
    database = provider = None
    try:
        config_dir = Path(os.environ.get("ACCESS_OPS_CONFIG_DIR", str(ROOT / "config")))
        configuration = load_configuration(config_dir)
        data_dir = Path(os.environ.get("ACCESS_OPS_DATA_DIR", str(ROOT / "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        # Reopen per rerun: do not share thread-bound SQLite connections in caches.
        database = Database(data_dir / "workflow.db")
        provider = MockOkta(data_dir / "provider.db")
        render(configuration, database, provider, config_dir)
    except Exception:
        st.error("System failure: the demo could not load or complete safely. Contact IT to check configuration "
                 "and local persisted state before retrying. Access state may need verification.")
    finally:
        if provider is not None:
            provider.close()
        if database is not None:
            database.close()


if __name__ == "__main__":
    main()
