"""Structured owner controls; all consequential work belongs to services."""
import streamlit as st
import ui

from access_ops.administration import policy_values
from access_ops.models import ApproverType, Decision


def active_access(workflow, actor, name):
    ui.shell("Active Access", "Current grants · mock Okta")
    if "removal_feedback" in st.session_state:
        st.info(st.session_state["removal_feedback"])
    grants = workflow.active_access()
    search = st.text_input("Find employee or application", key="access_search")
    grants = [g for g in grants if search.lower() in f'{name(g["employee_id"])} {g["application"]}'.lower()]
    if not grants:
        st.info("No current access grants match this view.")
        return
    st.caption("Select a row to choose the access to remove. Grants remain listed until mock Okta confirms removal, including overdue access and failed removals.")
    rows = [{
        "Employee": name(g["employee_id"]), "Application": g["application"], "Access": g["access_level"],
        "Granted by": (name(g["request"].assigned_approver_id) if g["request"] and g["request"].assigned_approver_id
                       else "Deterministic policy (auto-approved)"),
        "Granted": g["request"].starts_at.strftime("%b %d, %Y %H:%M UTC") if g["request"] and g["request"].starts_at else "Unknown",
        "Duration": g["request"].duration if g["request"] else "Unknown",
        "Expiration": g["request"].expires_at.isoformat() if g["request"] and g["request"].expires_at else "None recorded",
        "Reference": g["request_id"][-8:],
        "State": "Grant present · " + (ui.status_label(g["request"].status) if g["request"] else "Reconciliation required")
    } for g in grants]
    selection = st.dataframe(rows, hide_index=True, use_container_width=True, key="active_access_grid",
                             on_select="rerun", selection_mode="single-row")
    by_id = {g["request_id"]: g for g in grants}
    selected_rows = selection.selection.rows
    if selected_rows:
        st.session_state["remove_grant"] = grants[selected_rows[0]]["request_id"]
    elif st.session_state.get("remove_grant") not in by_id:
        st.session_state.pop("remove_grant", None)
    selected = st.selectbox("Remove this access", list(by_id), key="remove_grant",
                            format_func=lambda value: f'{name(by_id[value]["employee_id"])} · {by_id[value]["application"]} {by_id[value]["access_level"]} ({value[-8:]})')
    with st.form(f"remove_{selected}"):
        reason = st.text_area("Removal reason", key=f"remove_reason_{selected}")
        confirmed = st.checkbox("I confirm removal of this access", key=f"remove_confirm_{selected}")
        submit = st.form_submit_button("Remove this access", type="primary")
    if submit:
        if not reason.strip() or not confirmed:
            st.warning("Enter a removal reason and confirm this access removal.")
        else:
            response = workflow.remove_access(selected, actor, reason, confirmed=confirmed)
            st.session_state["removal_feedback"] = response.message
            st.rerun()


def configuration_editor(service, config, actor, name, workflow=None):
    ui.shell("Configuration", "Validated local policies · changes are audited")
    if "config_feedback" in st.session_state:
        st.info(st.session_state["config_feedback"])
    by_id = {p.policy_id: p for p in config.policies}
    selected = st.selectbox("Policy", list(by_id), key="edit_policy",
                            format_func=lambda value: f'{by_id[value].application} {by_id[value].access_level} · {value}')
    policy = by_id[selected]
    current = policy_values(policy)
    # A new version or identity creates a fresh form. Reviewed drafts bind actor + revision.
    prefix = f"policy_{selected}_{policy.policy_version}"
    st.caption(f"Version {policy.policy_version} · application/access identity is fixed. Saving increments the version; existing grants and request history remain intact.")
    with st.form(prefix):
        changes = {}
        for key, label, employee_field in (("eligible_departments", "Eligible departments", "department"),
                                           ("eligible_titles", "Eligible titles", "title")):
            choices = sorted({"*"} | {getattr(e, employee_field) for e in config.employees}
                             | {v for p in config.policies for v in getattr(p, key)})
            changes[key] = st.multiselect(label, choices, default=current[key], key=prefix + key,
                                          help="Use * alone to mean any configured value.")
        decisions = [d.value for d in Decision]
        approvers = [a.value for a in ApproverType]
        changes["decision"] = st.selectbox("Decision", decisions, index=decisions.index(policy.decision), key=prefix + "decision",
                                          format_func=lambda value: value.replace("_", " ").capitalize())
        changes["approver_type"] = st.selectbox("Reviewer type", approvers, index=approvers.index(policy.approver_type), key=prefix + "approver_type",
                                               format_func=lambda value: value.replace("_", " ").capitalize())
        reviewer_ids = [None] + [e.slack_user_id for e in config.employees if e.status == "active"]
        changes["approver_id"] = st.selectbox("Fixed reviewer", reviewer_ids, index=reviewer_ids.index(policy.approver_id),
                                            format_func=lambda value: name(value) if value else "None (automatic or manager lookup)", key=prefix + "approver_id")
        a, b, c = st.columns(3)
        changes["temporary_allowed"] = a.checkbox("Temporary allowed", value=policy.temporary_allowed, key=prefix + "temporary_allowed")
        changes["permanent_allowed"] = b.checkbox("Permanent allowed", value=policy.permanent_allowed, key=prefix + "permanent_allowed")
        changes["enabled"] = c.checkbox("Enabled", value=policy.enabled, key=prefix + "enabled")
        changes["max_duration_days"] = st.number_input("Maximum temporary days", min_value=0, value=policy.max_duration_days, step=1, key=prefix + "max_duration_days")
        reviewed = st.form_submit_button("Validate changes")
    if reviewed:
        st.session_state.pop("config_review", None)
        try:
            revision = service.revision()
            before, after = service.preview(selected, changes, actor, revision)
            st.session_state["config_review"] = (selected, actor, revision, changes, before, after)
        except Exception as error:
            st.error(f"Changes not accepted: {error}")
    draft = st.session_state.get("config_review")
    if draft and draft[0] == selected and draft[1] == actor:
        _, _, revision, reviewed_changes, before, after = draft
        st.markdown("**Reviewed changes**")
        st.caption("Save applies this reviewed snapshot. If you edit the form again, choose Validate changes to replace it.")
        st.dataframe([{"Field": key, "Before": str(before[key]), "After": str(after[key])}
                      for key in after if before[key] != after[key]], hide_index=True, use_container_width=True)
        if st.button("Save reviewed changes", type="primary"):
            try:
                service.save(selected, reviewed_changes, actor, revision)
                st.session_state["config_feedback"] = "Policy saved and audited. Future evaluations use the new version."
                st.session_state.pop("config_review", None)
                st.rerun()
            except Exception:
                st.error("Save was not confirmed. Reload and inspect configuration history; the file may have changed if completion auditing failed.")

    st.divider()
    st.markdown("**Application lifecycle**")
    applications = {item.application: item for item in config.applications}
    lifecycle = st.selectbox("Application", list(applications), key="lifecycle_application")
    item = applications[lifecycle]
    st.caption("Disabled applications stay visible here for audit history. Disabling blocks new requests and never revokes current access.")
    if item.enabled:
        active_count = sum(g["application"] == lifecycle for g in workflow.active_access()) if workflow else 0
        if active_count:
            st.warning(f"This application currently has {active_count} active access grant(s). Disabling it prevents new requests but does not revoke existing access.")
        else:
            st.warning("Disabling prevents new requests. Existing active access is not removed.")
        confirm_disable = st.checkbox("I confirm disabling this application", key=f"disable_{lifecycle}")
        if st.button("Disable application"):
            try:
                service.set_application_enabled(lifecycle, False, actor, service.revision(), confirmed=confirm_disable, active_grants=active_count)
                st.rerun()
            except Exception as error:
                st.error(f"Application was not disabled: {error}")
    else:
        if st.button("Re-enable application"):
            try:
                service.set_application_enabled(lifecycle, True, actor, service.revision(), confirmed=True)
                st.rerun()
            except Exception as error:
                st.error(f"Application was not re-enabled: {error}")

    with st.expander("Add application"):
        st.caption("Create one deterministic policy shape for one or more supported access levels. Validate before saving.")
        with st.form("add_application"):
            new_name = st.text_input("Application name")
            levels = st.multiselect("Supported access levels", ["Read", "Write", "Admin", "View", "Editor", "Standard"])
            departments = st.multiselect("Eligible departments", sorted({"*"} | {e.department for e in config.employees}), default=["*"])
            titles = st.multiselect("Eligible titles", sorted({"*"} | {e.title for e in config.employees}), default=["*"])
            decision = st.selectbox("New application decision", [d.value for d in Decision])
            approver_type = st.selectbox("New application reviewer type", [a.value for a in ApproverType])
            reviewer_ids = [None] + [e.slack_user_id for e in config.employees if e.status == "active"]
            approver_id = st.selectbox("New application fixed reviewer", reviewer_ids, format_func=lambda value: name(value) if value else "None")
            temporary = st.checkbox("New application temporary access allowed")
            max_days = st.number_input("New application maximum temporary days", min_value=0, value=0, step=1)
            permanent = st.checkbox("New application permanent access allowed", value=True)
            new_enabled = st.checkbox("Enable for new requests", value=True)
            create_validate = st.form_submit_button("Validate new application")
        if create_validate:
            changes = {"eligible_departments": departments, "eligible_titles": titles, "decision": decision,
                       "approver_type": approver_type, "approver_id": approver_id, "temporary_allowed": temporary,
                       "max_duration_days": max_days, "permanent_allowed": permanent, "enabled": True}
            try:
                service.preview_application(new_name, levels, changes, actor, service.revision(), enabled=new_enabled)
                st.session_state["application_review"] = (new_name, levels, changes, actor, service.revision(), new_enabled)
                st.success("Validation passed. Review the details below, then save.")
            except Exception as error:
                st.error(f"Application was not accepted: {error}")
        draft = st.session_state.get("application_review")
        if draft and draft[3] == actor:
            name_value, levels_value, changes_value, _, revision, enabled_value = draft
            st.caption(f"Ready to add {name_value}: {', '.join(levels_value)}. Save makes it available for future requests.")
            if st.button("Save new application", type="primary"):
                try:
                    service.create_application(name_value, levels_value, changes_value, actor, revision, enabled=enabled_value)
                    st.session_state.pop("application_review", None)
                    st.rerun()
                except Exception as error:
                    st.error(f"Application was not created: {error}")

    with st.expander("Configuration history"):
        for event in service.database.configuration_history():
            st.markdown(f'**{event["policy_id"]} · {event["outcome"]}**')
            st.caption(f'{event["timestamp"]} · {name(event["actor"])}')
            st.text(f'Before: {event["before_json"]}\nAfter: {event["after_json"]}')
