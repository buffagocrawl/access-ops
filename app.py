"""Local Streamlit presentation; all access actions go through Workflow."""
import os
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import MockOkta
from access_ops.workflow import DURATION_DAYS, Workflow


def show_response(response, request, events, *, review=False):
    """Display backend feedback and recorded outcomes; never infer authorization."""
    st.write(response.message)
    if response.request_id:
        st.code(response.request_id, language=None)
    last = events[-1].event_type if events else None
    if request:
        st.caption(f"Persisted status at response: {request.status}")
    if last == "INTAKE_STOPPED":
        st.error("Validation failure / request not accepted")
    elif last == "APPROVAL_REJECTED":
        st.error("Review action rejected by the backend")
    elif last == "EXCEPTION_REJECTED":
        st.success("Exception denied; no access granted")
    elif last == "PROVISIONING_SUCCEEDED":
        automatic = any(e.event_type == "REQUEST_AUTO_APPROVED" for e in events)
        st.success("Auto-approved — access confirmed" if automatic else "Approved — access confirmed")
    elif not review and request and request.status == "PENDING_APPROVAL":
        st.info("Pending approval")
    elif not review and request and request.status == "EXCEPTION_REVIEW":
        st.warning("Exception review")
    elif last == "REVALIDATION_FAILED":
        st.error("Backend revalidation failed; provisioning stopped")
    else:
        st.error("System failure / action stopped — follow the backend guidance above")


def table(title, rows):
    st.subheader(title)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.caption("No records yet.")


def render(configuration, database, provider):
    workflow = Workflow(configuration, database, provider)
    employees = {e.slack_user_id: e for e in configuration.employees}

    def person(employee_id):
        employee = employees.get(employee_id)
        return f"{employee.name} ({employee_id}, {employee.status})" if employee else employee_id or "Unassigned"

    employee_tab, reviewer_tab, operations_tab = st.tabs(
        ["Employee Request", "Reviewer Inbox", "IT Operations"]
    )
    with employee_tab:
        employee_id = st.selectbox("Simulated employee", list(employees), format_func=person, key="employee")
        applications = list(dict.fromkeys(p.application for p in configuration.policies))
        application = st.selectbox("Application", applications, key="application")
        # Outside the form so changing application refreshes the role choices.
        levels = list(dict.fromkeys(p.access_level for p in configuration.policies if p.application == application))
        access_level = st.selectbox("Access level", levels, key=f"access_{application}")
        with st.form("request_form"):
            reason = st.text_area("Business reason", key="reason")
            duration = st.selectbox("Duration", list(DURATION_DAYS), key="duration")
            st.caption("Day-based durations request temporary access. The backend checks policy limits.")
            submitted = st.form_submit_button("Submit request")
        if submitted:
            response = workflow.submit(employee_id, application, access_level, reason, duration)
            show_response(response, database.get(response.request_id), database.events(response.request_id))

    with reviewer_tab:
        reviewer = st.selectbox("Simulated reviewer", list(employees), format_func=person, key="reviewer")
        st.caption("All pending requests are visible for this local demo. The backend checks each review action.")
        st.caption("Current backend limitation: Deny succeeds only for exception review; normal approval denial is rejected.")
        pending = [r for r in database.request_rows() if r["status"] in ("PENDING_APPROVAL", "EXCEPTION_REVIEW")]
        table("Awaiting review", [
            {"request_id": r["request_id"], "requester": person(r["requester_slack_id"]),
             "application": r["application"], "access_level": r["access_level"],
             "business_reason": r["business_reason"], "duration": r["duration"],
             "review_type": r["status"], "assigned_reviewer": person(r["assigned_approver_id"])}
            for r in pending
        ])
        if pending:
            request_id = st.selectbox("Request to review", [r["request_id"] for r in pending], key="review_request")
            approve, deny = st.columns(2)
            action = None
            if approve.button("Approve"):
                action = workflow.approve
            if deny.button("Deny"):
                action = workflow.reject
            if action:
                response = action(request_id, reviewer)
                # Keep the action's feedback snapshot across the inbox refresh.
                st.session_state["review_feedback"] = (
                    response, database.get(response.request_id), database.events(response.request_id)
                )
                st.rerun()
        if "review_feedback" in st.session_state:
            st.caption("Last review response")
            show_response(*st.session_state["review_feedback"], review=True)

    with operations_tab:
        st.button("Refresh persisted state")
        rows = database.request_rows()
        table("Requests and statuses", rows)
        table("Active access in mock Okta", [
            {"employee": person(employee), "application": app, "access_level": level}
            for employee, app, level in provider.access_list()
        ])
        st.caption("Mock directory grants may remain after a revocation failure. All timestamps are UTC.")
        table("Temporary access and expiration", [r for r in rows if r["temporary"]])
        table("Failures and exception requests", [r for r in rows if r["status"] in (
            "EXCEPTION_REVIEW", "REJECTED", "PROVISIONING_FAILED", "REVOCATION_FAILED", "PROVISIONING", "EXPIRED"
        ) or (r["status"] == "PENDING_APPROVAL" and not r["assigned_approver_id"])])
        audit = database.recent_audit_rows()
        table("Intake failures (within recent audit events)", [r for r in audit if r["event_type"] == "INTAKE_STOPPED"])
        table("Recent audit events (latest 100)", audit)


def main():
    st.set_page_config(page_title="Access Ops", layout="wide")
    st.title("Access Ops")
    st.caption("Local demo • synthetic identities • mocked Slack and Okta • no authentication")
    st.info("Requests for the configured catalog follow deterministic eligibility, duration, and approval policies.")
    database = provider = None
    try:
        configuration = load_configuration(ROOT / "config")
        data_dir = Path(os.environ.get("ACCESS_OPS_DATA_DIR", str(ROOT / "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        # Reopen per rerun: do not share thread-bound SQLite connections in caches.
        database = Database(data_dir / "workflow.db")
        provider = MockOkta(data_dir / "provider.db")
        render(configuration, database, provider)
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
