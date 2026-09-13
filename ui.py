"""Presentation helpers only; recorded state is never an access decision."""
from html import escape
from datetime import datetime

import streamlit as st


def styles():
    st.html("""<style>
    .stApp {background:#f5f7fa;color:#192c3c}
    .stMainBlockContainer {max-width:1320px;padding-top:1.4rem;padding-bottom:3rem}
    [data-testid="stVerticalBlock"] {gap:.65rem}
    h1 {font-size:2rem!important;letter-spacing:-.04em}
    h2 {font-size:1.5rem!important;letter-spacing:-.025em}
    h3 {font-size:1.1rem!important}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#344b5f!important;opacity:1!important}
    [data-testid="stToolbar"] {display:none}
    /* The transparent Streamlit header stays fixed while scrolling. Let clicks pass through it. */
    [data-testid="stHeader"] {background:transparent;pointer-events:none}
    [data-baseweb="tab-list"] {gap:2rem;border-bottom:1px solid #d6dee6}
    [data-baseweb="tab"] {font-weight:600;color:#475b6b;padding:0 0 12px}
    [aria-selected="true"][data-baseweb="tab"] {color:#14665e}
    [data-baseweb="tab-highlight"] {background:#14665e}
    [role="tab"][aria-selected="true"] {color:#14665e!important;border-bottom-color:#14665e!important}
    [data-baseweb="tab-border"] {background:#d6dee6}
    [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {border-radius:6px}
    button[kind="primary"],button[kind="primaryFormSubmit"] {background:#176c61;border-color:#176c61;color:white}
    button[kind="primary"]:hover,button[kind="primary"]:focus,button[kind="primaryFormSubmit"]:hover {background:#10564d!important;border-color:#10564d!important;color:white!important}
    [data-testid="stForm"] {background:white;border:1px solid #dbe2e9;border-radius:8px}
    .eyebrow {color:#526374;font-size:11px;letter-spacing:.13em;font-weight:700;text-transform:uppercase;margin:8px 0}
    .guide-title {font-size:24px!important;margin:8px 0!important;padding:0!important}
    .guide-summary {font-size:15px;margin:0 0 12px;line-height:1.5}
    .guide {display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin:4px 0 2px}
    .guide section {border-top:2px solid #cbd8df;padding-top:10px;font-size:14px;color:#475b6b;line-height:1.5}
    .guide b {display:block;color:#192c3c;margin-bottom:4px}
    .shell-head {background:#273447;color:#fff;border-radius:9px 9px 0 0;padding:15px 20px;display:flex;justify-content:space-between;align-items:center}
    .shell-head small {color:#d3deea;font-size:12px}
    .shell-copy strong {color:#fff}.shell-copy small {display:block;color:#d3deea;font-size:12px;margin-top:3px}
    .st-key-request_shell_header,.st-key-review_shell_header {background:#273447;padding:10px 20px 2px;border-radius:9px 9px 0 0}
    .st-key-request_shell_header label,.st-key-review_shell_header label {color:#d3deea!important;font-size:12px!important}
    .workspace {background:#34263b;color:#e0d6e5;padding:20px 14px;border-radius:7px;min-height:380px;font-size:13px;line-height:2.2}
    .workspace b {display:block;color:#fff;font-size:15px;margin-bottom:18px}
    .workspace .selected {background:#594361;border-radius:4px;padding:2px 8px;color:#fff;margin:8px -5px}
    .workspace small {color:#cbbdd1}
    .message {display:flex;gap:12px;padding:4px 0 7px;align-items:flex-start;font-size:14px;line-height:1.5}
    .avatar {background:#e1eeeb;color:#185b50;border-radius:7px;min-width:36px;height:36px;display:grid;place-items:center;font-weight:700}
    .message small {color:#526374;margin-left:8px}
    .state {display:inline-block;padding:4px 9px;border-radius:5px;font-size:12px;font-weight:650;background:#e9eef4;color:#344b62}
    .state.success {background:#dff1e8;color:#1a6147}
    .state.pending {background:#e3edf9;color:#254f7a}
    .state.warning {background:#fff0d1;color:#77500a}
    .state.failed,.state.rejected {background:#fbe3e4;color:#92313b}
    .detail-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:8px 0;font-size:14px}
    .detail-grid small {display:block;color:#526374;font-size:12px;margin-bottom:3px}
    .detail-grid span {overflow-wrap:anywhere}
    .reason {border-left:3px solid #cbd8df;padding:8px 14px;background:#f5f7fa;font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}
    .st-key-request_workspace,.st-key-review_workspace,.st-key-operations_workspace {background:white;padding:20px;border:1px solid #dbe2e9;border-radius:0 0 9px 9px}
    @media(max-width:700px) {.guide,.detail-grid{grid-template-columns:1fr}.workspace{min-height:100px}.shell-head{gap:12px}}
    </style>""")


def guide(number, title, summary, controls):
    st.html(f'<div class="eyebrow">Demo guide / {escape(number)}</div>'
            f'<h2 class="guide-title">{escape(title)}</h2><p class="guide-summary">{escape(summary)}</p>'
            '<div class="guide">' + ''.join(
        f'<section><b>{escape(label)}</b>{escape(text)}</section>' for label, text in controls
    ) + '</div>')


def shell(title, subtitle):
    st.html(f'<div class="shell-head"><strong>{escape(title)}</strong><small>{escape(subtitle)}</small></div>')


def shell_copy(title, subtitle):
    """Header copy for a Streamlit-native selector placed beside the mock shell title."""
    st.html(f'<div class="shell-copy"><strong>{escape(title)}</strong><small>{escape(subtitle)}</small></div>')


def workspace(channel):
    st.html(f'<div class="workspace"><b>Acme workspace</b><small>CHANNELS</small>'
            f'<div># general</div><div class="selected"># {escape(channel)}</div>'
            '<div># team-updates</div><br><small>APPS</small><div>Access Ops</div>'
            '<br><small>Local demonstration<br>No Slack connection</small></div>')


def message(name, text, *, tag=""):
    st.html(f'<div class="message"><div class="avatar">{escape(name[:1])}</div>'
            f'<div><b>{escape(name)}</b><small>{escape(tag)}</small><br>{escape(text)}</div></div>')


def status(value):
    tone = {"ACTIVE":"success", "REVOKED":"success", "APPROVED":"pending",
            "PENDING_APPROVAL":"pending", "EXCEPTION_REVIEW":"warning", "MANUAL_REVIEW":"warning",
            "REJECTED":"rejected", "PROVISIONING_FAILED":"failed", "REVOCATION_FAILED":"failed",
            "EXPIRED":"warning", "NEEDS_INFORMATION":"warning"}.get(value, "pending")
    st.html(f'<span class="state {tone}">{escape(status_label(value))}</span>')


def status_label(value):
    return {"ACTIVE":"Active · mock access", "PENDING_APPROVAL":"Approval required",
            "REVOKED":"Revoked · mock access", "MANUAL_REVIEW":"Manual IT review"}.get(value, value.replace("_", " ").capitalize())


def timestamp(value):
    return datetime.fromisoformat(value).strftime("%b %d, %Y · %H:%M UTC") if value else "Not started"


def register(rows):
    """Render the request register and return its selected row, if any."""
    import pandas as pd

    def color(value):
        if value in ("PROVISIONING_FAILED", "REVOCATION_FAILED", "REJECTED"):
            return "background-color: #fbe3e4; color: #92313b"
        if value in ("MANUAL_REVIEW", "EXCEPTION_REVIEW", "EXPIRED"):
            return "background-color: #fff0d1; color: #77500a"
        if value in ("ACTIVE", "REVOKED"):
            return "background-color: #dff1e8; color: #1a6147"
        return "background-color: #e3edf9; color: #254f7a"

    if rows:
        styled = pd.DataFrame(rows).style.format({"status": status_label}).map(color, subset=["status"])
        event = st.dataframe(
            styled, hide_index=True, use_container_width=True, height=min(245, 36 * (len(rows) + 1)),
            column_config={"status": st.column_config.TextColumn("Status")}, key="ops_register",
            on_select="rerun", selection_mode="single-row",
        )
        selected_rows = event.selection.rows
        return selected_rows[0] if selected_rows else None
    else:
        st.caption("No requests match this view.")
    return None


def details(items):
    st.html('<div class="detail-grid">' + ''.join(
        f'<span><small>{escape(label)}</small>{escape(str(value or "—"))}</span>' for label, value in items
    ) + '</div>')


def reason(text):
    st.html(f'<div class="reason">{escape(text)}</div>')
