# Access Ops

Access Ops is a focused prototype for software access requests. It addresses the manual intake, routing, approval, provisioning, expiration, and audit work that can surround employee access requests.

## Scope and approach

The narrow scope is software access requests through a Slack-style structured workflow. The selected implementation approach is deterministic, traditional automation: trusted employee attributes and human-readable policy configuration drive repeatable validation, routing, approval, provisioning, and revocation decisions.

An agentic natural-language intake architecture is documented for comparison and possible future use. It is not implemented, and no AI API calls are part of the prototype.

## Status and behavior boundaries

The phase-by-phase notes below retain implementation history. The five-application catalog fix at the end supersedes earlier GitHub-only phase limits.

Phase 7 adds a thin Streamlit demo with Employee Request, Reviewer Inbox, and IT Operations tabs. See the local launch instructions and current backend limitations below.

### Implemented behavior

The configuration and data-model layer uses the Python standard library: immutable typed records, validated CSV loading, exact employee lookup, and deterministic policy selection. The shared workflow supports every granting policy in the five-application configuration, with SQLite request/audit state, a mocked Okta directory, and safe Slack-style feedback. A policy match alone does not authorize provisioning; the workflow enforces validation, revalidation, and the committed audit requirement.

Engineering GitHub Write uses one configured manager approval. Product GitHub Write enters exception review with one configured application owner, as described below.

### Planned behavior

The implementation contract calls for a local vertical slice supporting:

- Structured requests for GitHub, Figma, Notion, Salesforce, and Snowflake.
- Required-field validation, trusted employee lookup, and deterministic policy evaluation.
- Automatic approval, one normal human-approval path, one exception-review path, and safe rejection or escalation.
- SQLite request state, append-style audit events, idempotency, duplicate protection, and explicit failure simulation.
- Temporary-access expiration and controlled revocation.
- Slack-style employee and reviewer feedback, with a possible operations view and policy editor after the core workflow passes.

### Mocked behavior

Slack identity, forms, messages, approval actions, and alerts; employee-directory/HRIS data; Okta provisioning and removal; and scheduled expiration invocation are mocked where applicable. Mocked Okta operations still represent prototype access state changes. Production authentication, OAuth, real Slack/Okta integrations, hosting, and deployment are out of scope.

## Repository structure

```text
access-ops/
├── Planning/              Existing architecture and locked scope documents
├── config/
│   ├── employees.csv       Existing synthetic trusted directory
│   └── access_policies.csv Existing policy catalog
├── src/access_ops/
│   ├── __init__.py
│   ├── models.py           Data representations
│   ├── config.py           CSV loading and validation
│   ├── policy_engine.py    Deterministic policy evaluation
│   ├── workflow.py         UI-independent orchestration
│   ├── approvals.py        Single-reviewer authorization
│   ├── audit.py            Append-style audit events
│   ├── database.py         SQLite persistence
│   ├── notifications.py    Safe Slack-style messages
│   └── integrations/
│       ├── __init__.py
│       └── mock_okta.py    Mock provider boundary
├── tests/
│   ├── test_imports.py     Scaffold imports
│   ├── test_config.py      CSV loading and validation
│   └── test_policy_engine.py Exact policy selection
├── AGENTS.md               Repository instructions
├── .env.example            Safe local configuration template
├── .gitignore              Local and generated-file exclusions
├── pytest.ini             Test discovery and src import path
├── README.md              Project overview and setup
└── requirements.txt       pytest dependency
```

## Development and setup

### Demo configuration conventions

`config/employees.csv` is the trusted synthetic directory. All names, Slack IDs, and `example.com` email addresses are demo data, not Customer.io employee information. Department, title, manager, and `active`/`inactive` status must come from this file, never requester input. Olivia is the top-level manager and has no manager herself; future requests needing an unavailable manager must stop safely for IT review.

`config/access_policies.csv` contains the five-application catalog. The loader and matcher use the following conventions:

- Match enabled rows by exact application/access level and trusted department/title. Semicolons separate allowed values; `*` means any value in that field. Department and title conditions both apply. `eligible_departments` identifies which employees a row applies to, including exception and rejection rows; it does not itself grant eligibility. There is no row-order precedence. Zero or multiple matches must authorize nothing and require IT review.
- `AUTO_APPROVE` and `REJECT` use `approver_type=NONE` and a blank ID. `MANAGER` uses a blank ID because the one reviewer comes from the requester's `manager_slack_id`. `APPLICATION_OWNER` and `IT_SECURITY` each identify exactly one reviewer through `approver_id`. The shared workflow resolves the configured manager, application owner, or IT/security reviewer and prohibits self-approval.
- Booleans are `true`/`false`. `max_duration_days` caps temporary access only; permanent access requires `permanent_allowed=true`. Rejection rows allow neither and use a zero-day limit. Standard temporary access is capped at 30 days, GitHub exceptions and Admin at 7 days. A 90-day request is not authorized by these rows. Duration failures must not fall through to a more permissive rule.
- `policy_version` starts at `1` and should increase when a row changes. `eligible_titles` preserves the Blueprint's explicit Engineering-leadership restriction on GitHub Admin; other rows use `*`, so titles do not otherwise imply trust.
- Alice demonstrates Engineering GitHub Read auto-approval and Write manager approval. Paul and Sarah demonstrate temporary GitHub Write exception review directly by Grace. Mike demonstrates temporary GitHub Admin review by Ivan. Farah demonstrates an explicit GitHub Write rejection. Ian provides an inactive-employee negative case that must be blocked before policy evaluation.
- Figma View and Notion Standard are automatic for active employees; Figma Editor is automatic for Product/Design. Salesforce Standard requires the Sales/Customer Success employee's manager. Snowflake Read requires the Data/Engineering employee's manager; Write requires Dana and is temporary only. Non-rejection rows permit permanent access except Snowflake Write and GitHub Admin; the existing GitHub exception row permits permanent access.

These are prototype policy assumptions, not Customer.io policies. Design and Customer Success are configured for future synthetic records without requiring additional employees now. The Blueprint lists several admin roles and UI features; the locked scope limits this foundation to one elevated example (GitHub Admin), with the simple Phase 7 demo UI. Unmatched combinations remain manual-review cases, not implicit approvals or implicit exception grants.

### Configuration startup boundary

Call `load_configuration(config_directory)` from `access_ops.config` before using policies. The default directory is `config`, relative to the working directory; callers outside the repository root should supply an explicit path. It returns a complete immutable `Configuration` or raises `ConfigurationError`; it never returns partial configuration. No import-time loading or environment-file loader is added.

Validation rules:

- Both UTF-8 CSV files must exist, be readable, contain data, and have exactly the documented columns with no duplicate headers. Malformed CSV, incorrect cell counts, and blank required values fail. UTF-8 BOMs are accepted and surrounding cell whitespace is stripped.
- Only manager and approver IDs may be blank. Employee status must be `active` or `inactive`; Slack IDs and policy IDs must be unique. Nonblank managers must reference another directory employee; managers of active employees must be active. A blank manager is allowed for the documented top-level employee.
- The catalog must contain all five applications. Access levels are limited to the existing demo catalog, including only GitHub Admin as the elevated example. Applications may have disabled rows; disabling rules never creates fallback permission.
- Decisions and approver types must be recognized enum values. Boolean cells must be lowercase `true` or `false`. Policy versions must be positive integers and maximum durations nonnegative integers.
- Department/title selectors must be distinct semicolon-separated values or `*` alone. Empty list entries and mixed wildcard lists fail. Department/title names are not restricted to current employees, allowing the existing Design and Customer Success rules.
- Automatic and rejection decisions require `NONE` with no reviewer ID. Review decisions require a reviewer type. `MANAGER` leaves the ID blank; application-owner and IT/security rules require one active directory reviewer. The Engineering GitHub Write workflow enforces request-specific manager availability and self-approval checks.
- Temporary access requires a positive duration limit; disabling temporary access requires zero. Rejection allows neither temporary nor permanent access. Other rules must allow at least one duration form. Admin requires IT/security approval and temporary-only access capped at seven days. Other duration limits remain CSV-driven.
- Enabled rules with the same application/access cannot overlap in both department and title selectors, even if no current employee would match. Wildcards overlap every selector. Disabled rows still receive field and consistency validation, but do not participate in overlap detection. Errors identify the file and row or conflicting record IDs.

Use `configuration.employee(slack_user_id)` for exact lookup; unknown IDs return `None`. `match_policy(configuration, slack_user_id, application, access_level)` retrieves trusted employee attributes and refuses unknown or inactive employees. It matches enabled rules by case-sensitive application/access and both department/title selectors. There is no row-order priority or fuzzy matching. One match returns its `AccessPolicy`; zero returns `None`, meaning no policy permission and a future manual-review case. Multiple matches raise `ConfigurationError` defensively even if loading was bypassed.

Matching does not filter by requested duration: the workflow checks the selected policy's `temporary_allowed`, `max_duration_days`, and `permanent_allowed` fields without falling through to another rule or substituting a duration. Returning an `AUTO_APPROVE` policy does not change request status. Typed request and audit records remain data containers; the workflow and database implement validation and persistence.

### Local checks (Python 3.12)

Reuse the existing `.venv`. If setting up a fresh checkout, create it with a Python 3.12 interpreter (`python -m venv .venv`). From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

`pytest.ini` makes `src/` importable during tests and collects tests from `tests/`; no package installation or activation is needed for these commands. SQLite (`sqlite3`) and CSV support use Python's standard library. Streamlit is deferred until the demo interface is built. All future business logic belongs in `src/access_ops/`, independently of Streamlit.

There is no UI or application entry point yet; the golden path is callable through the Python service below. Normal manager denial, retries, broad duplicate-submission handling, failure-simulation controls, dashboards, and configuration editing remain deferred. Real integrations, external APIs, AI runtime behavior, Docker, and ORM are not implemented. The `.env.example` paths match the existing configuration, but environment-file loading is not implemented.

Tests cover the existing configuration and policy engine plus the golden-path workflow, committed audit ordering, provider-confirmed activation, persistent idempotency, existing-access outcomes, invalid intake, revalidation, audit failures, and safe handling of unconfirmed provider results. Explicit revocation-failure simulation remains deferred; the full core prototype is not yet complete.

### Calling the first vertical slice

With `src` on the Python import path (pytest configures this automatically):

```python
from access_ops.config import load_configuration
from access_ops.database import Database
from access_ops.integrations.mock_okta import MockOkta
from access_ops.workflow import Workflow

database = Database("access_ops.db")
provider = MockOkta("mock_okta.db")
try:
    workflow = Workflow(load_configuration("config"), database, provider)
    response = workflow.submit(
        employee_id="UDEMO001", application="GitHub", access_level="Read",
        business_reason="Read engineering documentation", duration="Permanent",
    )
    print(response.message)
    print(provider.access_list())
    # Internal reprocessing uses the persisted request ID, not caller-supplied status.
    if response.request_id:
        print(workflow.process(response.request_id).message)
finally:
    provider.close()
    database.close()
```

Order of operations:

1. Look up the trusted employee and require active status; validate required fields and catalog values.
2. For the Read path below, use the existing exact policy engine and require `AUTO_APPROVE`. Both implemented paths require Engineering/GitHub and policy-permitted `Permanent` duration.
3. Generate a UUID-based `REQ-...` ID and atomically persist `APPROVED` with `REQUEST_AUTO_APPROVED`. This event records the approval timestamp, policy ID, and version.
4. Reload the stored request and revalidate against the service's current configuration; require the same policy ID/version.
5. Commit `PROVISIONING_STARTED` and `PROVISIONING` together. Any audit/transaction error exits before the provider call.
6. Call the injected `AccessProvider.grant` boundary with the workflow-authorized stored request. The mock only inserts into its local directory; it never evaluates policy or approval.
7. Only `GRANTED` or `ALREADY_EXISTS` confirms access. Atomically persist `ACTIVE`, the provider result, completion timestamp, and `PROVISIONING_SUCCEEDED`, then return the request ID and mock-access confirmation.

Idempotency has two layers: processing an `ACTIVE` request returns the saved outcome without a provider call or extra audit events; the mock uses a unique employee/application/access tuple and stable `<request_id>:grant` key. An existing tuple returns `ALREADY_EXISTS` without inserting another grant. SQLite preserves both layers across reopening. A new submission creates a new request; broader submission deduplication is deferred.

Assumptions and limits: identity is supplied by trusted local demo code, configuration is a validated in-memory snapshot (reload explicitly to adopt CSV edits), and processing is sequential in one local workflow service. The local SQLite files are trusted application state, not an authentication boundary. Permanent access is the only supported duration because expiration is deferred. Approval and provisioning times are retained in audit history. The combined creation/auto-approval event keeps this slice small.

Unconfirmed provider results use the existing `PROVISIONING_FAILED` state with a fixed safe audit description; no simulation controls or retries are added. If completion persistence fails after a provider grant, state remains `PROVISIONING` with the durable attempt event; the response asks IT to check access and does not claim completion. Reprocessing that state stops. Crash reconciliation, concurrent workers, and automatic recovery are deferred. Raw errors and business reasons are excluded from employee feedback and audit details.

### Human approval (Phase 6, Step 12)

Submit the same fields as above with `access_level="Write"`. The existing `GH-WRITE-ENG` policy requires manager approval. Alice's manager is already configured as Mike (`UDEMO005`); no CSV or model changes are needed.

Submission persists `PENDING_APPROVAL`, the assigned manager, the policy reference, and `REQUEST_SUBMITTED`, then returns a Slack-style pending message. Calling `process` while pending grants nothing. Trusted local demo code supplies the reviewer identity:

```python
response = workflow.submit(
    employee_id="UDEMO001", application="GitHub", access_level="Write",
    business_reason="Contribute engineering changes", duration="Permanent",
)
print(response.message)
print(workflow.approve(response.request_id, reviewer_id="UDEMO005").message)
```

`approve` audits the attempt and accepts only an active assigned reviewer on a pending request. Wrong reviewers, self-approval, and repeated approval are rejected without granting access. Successful approval atomically persists `APPROVED` and `REQUEST_APPROVED`, including the reviewer identity and timestamp. Processing then re-reads the requester from the service's current trusted configuration, repeats intake/policy validation, checks the saved policy ID/version, and verifies that the current manager matches the recorded approval. Failed revalidation records `REVALIDATION_FAILED` and `REJECTED`, retaining approval history and granting nothing. Successful revalidation is committed before the existing audited Mock Okta provisioning path. Access becomes `ACTIVE` only on provider confirmation.

Configuration remains an immutable in-memory snapshot: trusted calling code must explicitly assign `workflow.configuration = load_configuration("config")` to adopt CSV changes before approval. CSV files are not watched automatically. Reviewer identity is mocked, not authenticated by this service. Processing remains sequential. Existing SQLite databases gain one nullable `assigned_approver_id` column on opening; existing requests are preserved.

Tests cover pending persistence, no provisioning while pending, wrong/self reviewers, correct manager approval, approval audit ordering, revalidation both while pending and after approval, inactive/missing/ineligible requesters, changed policy/manager, unresolved reviewers, and audit failures. Step 12 adds normal permanent Engineering GitHub Write approval. Step 13 extends this machinery for exception review as described next. Step 15 adds temporary access/expiration/revocation below. Steps 16 and 17 below add failure injection, bounded retries, and provider-operation idempotency.

### Exception review (Phase 6, Step 13)

Product Manager Paul (`UDEMO002`) requesting GitHub Write matches `GH-WRITE-EXCEPTION` and enters `EXCEPTION_REVIEW`. The CSV assigns Grace, the GitHub owner (`UDEMO006`), directly. Paul's manager is not involved. This preserves the human decision to reject the earlier AI suggestion of a manager plus owner approval chain. The existing policy also covers Sales; no additional exception rules are introduced.

**Historical Step 13 duration assumption:** that slice enabled Permanent on the exception demo policy and incremented its version to 2. Step 15 now supports temporary durations as well, subject to its existing seven-day maximum. Planning documents are unchanged.

```python
from access_ops.notifications import exception_review

response = workflow.submit(
    employee_id="UDEMO002", application="GitHub", access_level="Write",
    business_reason="Update launch website documentation", duration="Permanent",
)
print(response.message)
# Private reviewer feedback in trusted local demo code; no real Slack delivery.
print(exception_review(database.get(response.request_id)).message)
print(workflow.approve(response.request_id, reviewer_id="UDEMO006").message)
# Alternatively, while still pending:
# workflow.reject(response.request_id, reviewer_id="UDEMO006")
```

The reviewer message uses the saved request's business reason and access level, and identifies the persisted requested duration. Approval/rejection requires the single assigned, active reviewer, who must still match the configured application owner or IT/Security reviewer. Self-approval, unauthorized decisions, and decisions after completion are rejected and audited. Rejection records `REJECTED` and grants nothing. No normal manager denial workflow is added.

An unresolved, inactive, or self-referencing exception reviewer leaves a saved `EXCEPTION_REVIEW` request with no assigned approver, records `EXCEPTION_ROUTING_FAILED`, and returns a blocked-review message with the request ID. There is no fallback reviewer or automatic rerouting. Startup CSV validation continues to reject invalid reviewer configuration; the workflow check also handles unavailable reviewers in the current in-memory configuration.

Approval records `EXCEPTION_APPROVED`, then revalidates the current requester, matched exception policy and version, duration permission, and reviewer authority before entering the existing Mock Okta provisioning flow. This validates the configured exception policy rather than requiring Engineering eligibility. Provider confirmation is still required for `ACTIVE`.

Audit history records `EXCEPTION_DETECTED`, `EXCEPTION_ROUTED` (or routing failure), approval attempts and rejected attempts, `EXCEPTION_APPROVED` or `EXCEPTION_REJECTED`, requester/policy/approval revalidation, and provisioning outcomes. Tests verify persistence, reviewer details, authorization, rejection, changed requester/policy/reviewer data, committed audit ordering, and audit failure safety. Configuration reload and sequential-processing limitations from Step 12 still apply.

Do not commit credentials, tokens, passwords, API keys, or local `.env` files. The `.env` file is gitignored; use `.env.example` as the safe template.

## Planning references

The [`Planning/`](Planning/) directory is the source of truth for architecture, scope, implementation boundaries, assumptions, workflow states, and the deterministic-versus-agentic decision.


### Missing and invalid requests (Phase 6, Step 14)

Intake checks trusted employee identity/status, required fields, and exact catalog values before policy execution. Missing business reason returns a correction message; unsupported applications and roles are never corrected or substituted. Unknown/inactive employees, missing or disabled matching policies, and ambiguous policy configuration grant nothing and return safe IT guidance.

Pre-policy failures receive a UUID request reference and a durable `INTAKE_STOPPED` event in the existing audit table: `NEEDS_INFORMATION` for missing fields, otherwise `REJECTED`. These are audit-only references, retrievable with `database.events(response.request_id)`; no request row is created because the existing request schema requires a matched policy. No synthetic employee or policy is created, and raw input is not copied into audit details. These references cannot be processed or approved. Corrected intake requires a new submission. If audit persistence fails, the response explicitly says recording failed and directs the employee to IT; no reference or successful recording is claimed.

Missing managers now preserve `PENDING_APPROVAL` with no assigned reviewer and `APPROVAL_ROUTING_FAILED`, matching the existing blocked `EXCEPTION_REVIEW` behavior for missing exception reviewers. Neither allows approval or provisioning, chooses a fallback, or automatically reroutes after configuration correction. IT must correct configuration; recovery/rerouting is deferred. Startup CSV validation remains strict; runtime checks also defend against unavailable reviewers in the in-memory configuration.

Revalidation failures now record `REVALIDATION_FAILED` and `REJECTED` for automatic as well as human-approved requests. Existing approval history is retained. Tests cover each invalid outcome, audit persistence and deterministic states, exact matching, blocked managers and exception reviewers, no provider calls, and safe messages on internal errors.

The existing GitHub Read/Write phase limits remain. Step 15 adds temporary access and expiration/revocation below. Steps 16 and 17 below add failure injection, bounded retries, and provider-operation idempotency. Blocked-request recovery remains deferred. Planning documents and configuration are unchanged.


### Phase 6, Step 15: temporary access

The existing GitHub Read/Write and exception paths accept exactly `1 day`, `7 days`, `30 days`, `90 days`, or `Permanent`. Each request must satisfy the matched policy's duration flags and maximum at intake and again before provisioning. No duration is shortened, extended, or substituted. The shipped policies do not permit 90 days; a trusted policy change is required to demonstrate that duration.

Requests persist `duration`, `temporary`, `starts_at`, `expires_at`, and `revocation_status`. Approval waiting time does not consume access time: `GRANTED` sets `starts_at` to the current workflow time, and temporary expiration is that time plus the requested number of 24-hour days. Permanent `ALREADY_EXISTS` confirms access and remains ACTIVE without assigning `starts_at` or `expires_at`. Permanent access has no expiration and `NOT_APPLICABLE` revocation status. Temporary requests begin `PENDING` and finish `REVOKED` after confirmed removal. Additive SQLite migration preserves earlier permanent requests and audit history; old start times remain null rather than being invented.

`Workflow(..., clock=callable)` accepts a timezone-aware clock. `process_expired_access(now=...)` also accepts a timezone-aware instant; both normalize to UTC. Manual processing finds expired ACTIVE temporary requests, validates their stored lifecycle and provisioning evidence, commits `ACCESS_EXPIRED` and `REVOCATION_STARTED`, and removes only the matching employee/application/access/request grant key through Mock Okta. Confirmed removal persists request status `REVOKED` and audits `REVOCATION_SUCCEEDED`. History and timestamps remain available. Later calls ignore the revoked request.

With the workflow/database/provider setup shown above, use a fresh mock directory:

```python
from datetime import timedelta

response = workflow.submit(
    employee_id="UDEMO001", application="GitHub", access_level="Read",
    business_reason="Short documentation review", duration="1 day",
)
request = database.get(response.request_id)
print(request.starts_at, request.expires_at)
print(provider.access_list())
print(workflow.process_expired_access(now=request.expires_at + timedelta(seconds=1)))
print(provider.access_list())
print(database.get(request.request_id).revocation_status)
print(database.events(request.request_id))
```

Assumptions: invoke this local workflow serially. A temporary request receiving `ALREADY_EXISTS` fails closed without a start or expiration, because it did not create its own expiring grant. Expiration uses the stored grant rather than current eligibility policy, so later employee/configuration changes do not prevent removing the original access. An unconfirmed removal now persists REVOCATION_FAILED with revocation_status PENDING for inspection and is not automatically retried (Step 16 below). Crash recovery across provider and workflow databases is not implemented.

Tests cover all five durations, disallowed/unsupported durations, pending approvals and exceptions, execution-time revalidation, expiration boundaries, durable lifecycle/audit records, exact grant targeting, pre-action audit failure, and repeated processing. Step 16 adds explicit failure injection and revocation-failure handling below; Step 17 adds bounded provider retries and operation idempotency below. No scheduler infrastructure is added.


### Phase 6, Step 16: deterministic failure injection

Construct `MockOkta("provider.db", fail_grant=True)` to fail every grant attempt, or `MockOkta("provider.db", fail_revoke=True)` to fail every removal attempt. Both keyword flags default to `False` and can be combined. They are local demo/test settings, returning the existing `GrantResult.FAILED` or `False` before changing the mock directory. No environment settings or random behavior are involved.

Grant failure follows the usual validation, policy, approval, revalidation, and committed `PROVISIONING_STARTED` path. It creates no grant and persists `PROVISIONING_FAILED`, preserving any manager or exception approval. Feedback says: "Approval succeeded, but provisioning failed." It asks the employee to contact IT with the request ID and not resubmit; raw provider errors are never included.

For a removal-failure demo, construct the provider with only `fail_revoke=True`, obtain temporary access normally, then call `workflow.process_expired_access(now=request.expires_at)`. `ACCESS_EXPIRED` and `REVOCATION_STARTED` commit before removal is attempted. A false/unconfirmed result or provider exception persists request status `REVOCATION_FAILED` and the matching audit event. The injected failure leaves the grant present. `revocation_status` remains `PENDING`, meaning removal is unconfirmed; the request status explicitly records failure. Start/expiration timestamps and all earlier approval/provisioning events remain intact. Feedback directs IT to verify and remove the grant and states that no automatic retry will occur.

Later expiration calls skip failed requests and return no result for them; they do not retry, change failure state, or claim removal. Permanent access is unaffected. This step assumes the existing serial local invocation model and uses returned Slack-style feedback for employee/admin follow-up. Step 17 below adds bounded transient retries and provider-operation idempotency. Backoff infrastructure and automatic recovery remain deferred.


### Phase 6, Step 17: retry and provider-operation idempotency

Only `TransientProviderError` raised by a provider call is retryable. It explicitly represents a timeout or temporary provider unavailability. `GrantResult.FAILED`, unconfirmed revoke results, malformed results, and all other exceptions are non-retryable, including authentication, authorization, invalid input, and configuration errors. Grant success remains `GRANTED` or `ALREADY_EXISTS`; revoke `True` confirms either removal now or a previously completed removal. An absent grant without a recorded successful revoke is still unconfirmed (`False`).

The workflow makes at most **three provider attempts total**, with no sleeps or delays. Validation, approval, revalidation, and expiration checks happen before this loop. Initial `PROVISIONING_STARTED` / `REVOCATION_STARTED` events commit before attempt 1. Each failure records `PROVIDER_ATTEMPT_FAILED` with operation ID, verb, attempt number, and transient/non-retryable classification. `PROVIDER_RETRYING` commits before each additional attempt. Any audit persistence failure stops processing without another provider call. The final lifecycle event includes the operation ID and final attempt number. Approval and earlier provisioning history remain intact; success is persisted once, only after confirmation.

The existing request-based adapter interface derives stable IDs with `operation_id(request, "grant")` or `operation_id(request, "revoke")`: for example `REQ-1042:grant` and `REQ-1042:revoke`. Every attempt uses the same persisted request ID; IDs do not authorize access. Mock Okta stores completed operation IDs and the employee/application/access tuple in `mock_operations`, in the same SQLite transaction as the directory change. This additive table preserves existing directory data. Replaying a completed grant returns `ALREADY_EXISTS` while access exists, and never recreates revoked access (returns `FAILED` if absent). Replaying a completed revoke returns `True` without deleting anything, including a newer replacement grant. Reusing a completed key with different access is rejected. Revoke still targets only the original `:grant` key.

Deterministic demo construction:

```python
# Fail the first two attempts of each operation, then succeed on attempt three.
provider = MockOkta("provider.db", transient_grant_failures=2,
                    transient_revoke_failures=2)
# Exhaust the three-attempt workflow limit for grants.
provider = MockOkta("provider.db", transient_grant_failures=3)
# Non-retryable failure: one call only (existing Step 16 flags).
provider = MockOkta("provider.db", fail_grant=True, fail_revoke=True)
```

Counts default to zero and must be nonnegative integers. They apply independently per operation ID within a mock instance; reopening resets simulated attempt counts but preserves completed operations. Completed-operation checks precede failure injection; permanent failure flags take precedence over transient injection for new operations. A count of three or more exhausts the workflow limit. After terminal `PROVISIONING_FAILED` or `REVOCATION_FAILED`, subsequent workflow processing does not start another attempt budget. Revocation failure retains `PENDING` removal status and safe IT guidance. No failure classification or raw exception text is exposed to employees.

Assumptions remain serial local execution and mocked identity/provider calls. Production concerns left out include concurrent/distributed coordination, crash reconciliation between workflow and provider databases, durable scheduling/backoff, real provider error mapping, and operational alert delivery. Existing temporary `ALREADY_EXISTS` handling remains conservative: it does not infer a new start time or expiration. This step does not add broad duplicate-submission detection or recovery for blocked approvals.

## Phase 7: local Streamlit demo

From PowerShell in the repository root (Python 3.11+):

```powershell
# Only needed if .venv does not exist:
python -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open http://localhost:8501. Stop the server with Ctrl+C.

The app creates `data/workflow.db` and `data/provider.db` by default. Both are gitignored SQLite files and survive reruns and server restarts. Existing `manual_workflow.db` / `manual_okta.db` files are not modified or imported. For isolated demo state, set `$env:ACCESS_OPS_DATA_DIR = "C:\path\to\demo-data"` before starting; the directory uses the same `workflow.db` and `provider.db` filenames. The app reads this environment variable directly; it does not load `.env` or use the older placeholder path variables in `.env.example`.

- **Employee Request:** select a synthetic identity, catalog application/access level, business reason, and duration. Day-based durations mean temporary access. Submit calls `Workflow.submit`; the backend supplies the request reference and safe message. Status labels come from persisted requests/audit outcomes, including audit-only intake failures.
- **Reviewer Inbox:** all pending approvals and exceptions are visible. Select any synthetic identity to demonstrate authorized, wrong-reviewer, inactive-reviewer, and self-approval attempts. Approve calls `Workflow.approve`; Deny calls `Workflow.reject`. After an action, the inbox refreshes and preserves that action's feedback snapshot.
- **IT Operations:** read-only tables show requests, actual mock-directory grants, temporary lifecycle fields, failed/exception requests, audit-only intake failures, and the latest 100 audit events. Use Refresh persisted state after external workflow operations. Timestamps are UTC. The app does not run a scheduler or process expiration on reruns; use the existing expiration workflow example above with these database paths.

Quick demo: Alice Engineer + GitHub Read auto-approves; Alice + GitHub Write waits for Mike Manager; Paul Product + GitHub Write enters exception review for Grace GitHubOwner. Use Ian FormerEmployee or an empty business reason for validation feedback. For temporary access choose 1 day, 7 days, or 30 days as permitted by policy. All choices remain subject to backend validation.

### Preserved limitations and assumptions

This UI assumes one local operator invoking workflows serially, synthetic identities without authentication, and shared persistent state across tabs/sessions. Connections open and close per Streamlit rerun rather than caching thread-bound SQLite connections. The UI database additions are read-only snapshot methods. The catalog fix below generalizes workflow routing using the existing policies; policy data, audit-writing guarantees, and provider behavior are unchanged.

Material gaps against the broader planning documents remain explicit:

- The GitHub-only phase gate has been removed. All five applications use their configured policies; missing or rejecting policies still grant nothing.
- Normal manager requests can be approved, but the current backend rejects their Deny action. Only exception denial is implemented. Both buttons delegate to the backend; the UI does not implement a denial transition or bypass this restriction.
- Duplicate submissions can create distinct request rows; existing provider idempotency prevents duplicate access. The UI adds no submission deduplication.
- Approval-wait expiration, blocked-request recovery, and failure recovery remain existing backend limitations. Expiration processing and failure injection remain available through the service interfaces; no UI controls or scheduler are added for them.

The older Blueprint describes a policy editor and broader catalog/admin workflows. This phase follows the locked Implementation Contract and the explicit Phase 7 request: no policy editor or new business rules.

Run all tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

`tests/test_app.py` uses Streamlit AppTest with temporary database directories to verify actual UI/service wiring, auto-approval, review authorization and denial behavior, validation/system feedback, persistence, duplicate access protection, and operational expiration/failure visibility. Existing GitHub control tests remain in place. The obsolete Notion rejection case now tests an unsupported Notion access level; Notion Standard success is covered by catalog and UI tests.


## Five-application catalog correction

The original `Workflow._validate` phase gate rejected non-GitHub requests after successful policy matching. It also assumed Read meant automatic approval and Write meant manager approval. `Workflow.process` used the access-level name to decide whether human approval evidence was required. These assumptions are now replaced by the matched policy's decision and approver type. Normal approvals resolve one manager, application owner, or IT/security reviewer from trusted configuration and revalidate that reviewer and approval evidence before provisioning. Existing GitHub exceptions retain their configured single reviewer.

Mock Okta was already application-neutral and is unchanged: it records the authorized employee/application/access tuple under the same idempotent grant contract. No configuration rows, application names, policies, database schema, or provider rules changed. Application and role choices in Streamlit come from the loaded policy records. The fixed catalog validation in `config.py` continues to reject unsupported applications and access levels.

### Manual Streamlit QA

Use a nonempty business reason such as "Project documentation and collaboration" and choose **Permanent** for each scenario below. For human approval, select the generated request ID and the listed reviewer in Reviewer Inbox, then click Approve. Each completed request should show ACTIVE in IT Operations and its grant in Active access in mock Okta.

| Employee | Application | Access level | Approval |
| --- | --- | --- | --- |
| Alice Engineer (`UDEMO001`) | GitHub | Read | Automatic |
| Alice Engineer (`UDEMO001`) | Figma | View | Automatic |
| Alice Engineer (`UDEMO001`) | Notion | Standard | Automatic |
| Sarah Sales (`UDEMO003`) | Salesforce | Standard | Sam SalesManager (`UDEMO010`) |
| Alice Engineer (`UDEMO001`) | Snowflake | Read | Mike Manager (`UDEMO005`) |

Additional existing configured paths also work: Paul / Figma Editor (automatic), Alice / Snowflake Write / 1 day (Dana DataOwner approval), and Mike / GitHub Admin / 1 day (Ivan ITSecurity approval). GitHub Write still requires Mike for Alice and exception review by Grace for Paul or Sarah. GitHub Admin remains restricted to the configured Engineering Manager title, IT/security approval, and a maximum seven-day temporary duration.

`tests/test_catalog_workflow.py` derives its cases from every enabled, non-reject policy in the actual CSV. It checks committed authorization before provider invocation, pending requests granting nothing, required approval evidence, durable ACTIVE state and directory grants, lifecycle timestamps, audit events, post-approval revalidation, and provider failures. AppTest verifies an end-to-end UI path and the IT Operations grant table for every configured application. Unsupported application/access, missing-policy, employee-validation, and all existing GitHub authorization, exception, duration, expiration, retry, idempotency, and failure coverage remain.

Assumptions remain serial local execution, trusted synthetic CSV configuration, and mock identities/providers. Restart or refresh Streamlit to load the updated code. Existing pending requests can be reviewed normally; old audit-only rejected intake records remain history and require a new valid submission. Normal approval denial and broader recovery remain deferred as documented above.
