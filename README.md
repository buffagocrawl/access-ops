# Access Ops

## What this is

Access Ops is a local Customer.io interview take-home prototype for software access requests only. It addresses the manual intake, routing, approval, provisioning, expiration, and audit work that can surround employee access requests.

## Core vertical slice vs. post-core ownership extensions

**Core workflow:** structured software-access intake; trusted employee lookup; deterministic policy evaluation; auto-approval; one human approval; configured exception review; policy-less manual review; mock provisioning; audit history; temporary access and revocation; deterministic failure handling; and tests.

**Post-core / Day 4 ownership extensions:** local policy administration; application add/disable/re-enable; current-access view; reasoned manual access removal; and UI/usability polish. The core workflow was completed and tested first; these features were added afterward and are not necessary to understand the central architecture decision. They are narrow local operations, not a general IAM platform. Production authentication, lifecycle automation, offboarding, generalized IAM, and broad administration remain out of scope.

The shipped demo catalog starts with five applications: GitHub, Figma, Notion, Salesforce, and Snowflake. The later local lifecycle extension can add a catalog entry for demonstration or maintenance; this is a Day 4 amendment to the original “exactly five” core constraint, not a general-purpose catalog promise.

## Why deterministic automation

The narrow scope is software access requests through a Slack-style structured workflow. The selected implementation approach is deterministic, traditional automation: trusted employee attributes and human-readable policy configuration drive repeatable validation, routing, approval, provisioning, and revocation decisions.

Software access has predictable inputs and consequential outcomes. Explicit rules make authorization repeatable, testable, auditable, and maintainable within this take-home's scope. Natural-language interpretation does not resolve the core policy and approval requirements.

An agentic natural-language intake architecture is [documented separately](Planning/Access-Ops_Architecture.md) for comparison and possible future use. It is not implemented, and no AI API calls are part of the prototype. Natural-language AI is not part of the implemented authorization path. AI/LLM output must never independently authorize sensitive access; any future intake output would remain untrusted input to deterministic validation and approval controls.

## Architecture

The local Streamlit UI (`app.py`) passes structured requests and simulated reviewer actions to the UI-independent `Workflow`. Validated CSV employee data and the exact policy matcher determine eligibility and routing. The workflow obtains any configured approval, revalidates authorization, commits the pre-action audit event, and only then calls Mock Okta. Provider confirmation is required before recording successful access.

SQLite stores requests and append-style audit history in the workflow database; Mock Okta stores grants and completed operation keys in a separate SQLite database. Manual-review routing and revocation-failure notifications persist in the workflow database's mock inbox. Expiration processing is invoked explicitly through the service API.

See [Access Ops Architecture and Approach Comparison](Planning/Access-Ops_Architecture.md) for the detailed design and agentic alternative. The [Implementation Contract](Planning/Implementation_Contract.md), including Branden's Day 4 ownership amendment, governs build scope. Real authenticated identities, scheduling and delayed retries remain future-state. Local policy editing, reasoned reviewer rejection and manual access removal are implemented.

The handoff set includes the [non-technical maintenance guide](Planning/Maintenance_Guide.md), [project timeline](Planning/Project_Timeline.md), [AI Usage Log](Planning/AI_Usage_Log.md), and [13-area written-submission coverage](Planning/Written_Submission.md). The two architecture diagrams are in [Access Ops Architecture](Planning/Access-Ops_Architecture.md): the selected deterministic component architecture and the documented agentic alternative.

## Implemented vs mocked vs future-state

### Implemented behavior

The configuration and data-model layer uses the Python standard library: immutable typed records, validated CSV loading, exact employee lookup, and deterministic policy selection. The shared workflow supports every granting policy in the five-application configuration, with SQLite request/audit state, a mocked Okta directory, and safe Slack-style feedback. A policy match alone does not authorize provisioning; the workflow enforces validation, revalidation, and the committed audit requirement.

Engineering GitHub Write uses one configured manager approval. Product GitHub Write enters exception review with one configured application owner, as described below.

### Mocked integrations

Slack-style intake, employee feedback, and review actions are represented in the local UI and service responses. There is no Slack connection. IT notifications for manual review and revocation failure are persisted **mock deliveries**, visible in the IT Operations inbox, rather than real Slack messages. Ordinary employee responses and reviewer views are local feedback, not a delivery service for every workflow event.

Employee-directory/HRIS data is synthetic CSV data. Okta provisioning and removal use a local SQLite mock directory; confirmed operations change prototype access state, not real application access. Expiration is manually invoked, with an optional supplied clock, rather than run by a scheduler.

### Future-state architecture (not implemented)

Real Slack/Okta/HRIS integration, authenticated identity and administration, durable scheduling, production hosting, and an optional AI intake layer remain outside this implementation. The alternative architecture is a design comparison, not an available runtime mode. No production-readiness or measured efficiency gains are claimed.

## Repository structure

```text
access-ops/
|-- Planning/               Architecture, locked scope, and Phase 8 acceptance audit
|-- config/
|   |-- employees.csv       Synthetic trusted directory
|   |-- applications.csv    Application lifecycle catalog
|   `-- access_policies.csv Five-application policy catalog
|-- src/access_ops/
|   |-- models.py           Typed data records
|   |-- config.py           CSV loading and validation
|   |-- policy_engine.py    Exact policy matching
|   |-- workflow.py         UI-independent orchestration and expiration
|   |-- approvals.py        Single-reviewer authorization
|   |-- audit.py            Audit event construction
|   |-- database.py         SQLite request/audit persistence
|   |-- notifications.py    Local responses and persisted mock IT deliveries
|   |-- administration.py   Policy/application ownership operations
|   |-- sla.py              Derived request-aging display helper
|   `-- integrations/mock_okta.py  Mock grants, revocation, and operation keys
|-- tests/                  Configuration, policy, workflow, catalog, and UI tests
|-- app.py                  Local Streamlit entry point
|-- admin_ui.py             Operations ownership controls
|-- ui.py                   Shared presentation helpers
|-- data/                   Generated local SQLite files (gitignored)
|-- AGENTS.md               Repository instructions
|-- .env.example            Placeholder template; not loaded by the app
|-- .gitignore              Local and generated-file exclusions
|-- pytest.ini             Test discovery and src import path
|-- README.md              Project overview and setup
`-- requirements.txt       pytest and Streamlit dependencies
```

## Configuration

### Demo configuration conventions

`config/employees.csv` is the trusted synthetic directory. All names, Slack IDs, and `example.com` email addresses are demo data, not Customer.io employee information. Department, title, manager, and `active`/`inactive` status must come from this file, never requester input. Olivia is the top-level manager and has no manager herself; requests needing an unavailable manager must stop safely for IT review.

`config/access_policies.csv` contains the five-application catalog. Owners should use IT Operations → Configuration to validate and audit supported policy edits. CSV remains the persistent source; direct file edits bypass the UI audit trail and require careful administrative handling. The loader and matcher use the following conventions:

- Match enabled rows by exact application/access level and trusted department/title. Semicolons separate allowed values; `*` means any value in that field. Department and title conditions both apply. `eligible_departments` identifies which employees a row applies to, including exception and rejection rows; it does not itself grant eligibility. There is no row-order precedence. Zero matches on otherwise valid intake route to manual review; multiple matches fail configuration validation or reject intake with IT guidance. Neither authorizes access.
- `AUTO_APPROVE` and `REJECT` use `approver_type=NONE` and a blank ID. `MANAGER` uses a blank ID because the one reviewer comes from the requester's `manager_slack_id`. `APPLICATION_OWNER` and `IT_SECURITY` each identify exactly one reviewer through `approver_id`. The shared workflow resolves the configured manager, application owner, or IT/security reviewer and prohibits self-approval.
- Booleans are `true`/`false`. `max_duration_days` caps temporary access only; permanent access requires `permanent_allowed=true`. Rejection rows allow neither and use a zero-day limit. Standard temporary access is capped at 30 days, GitHub exceptions and Admin at 7 days. A 90-day request is not authorized by these rows. Duration failures must not fall through to a more permissive rule.
- `policy_version` must be positive and should increase when a row changes (the shipped GitHub exception is version `2`; other rows are version `1`). `eligible_titles` preserves the Blueprint's explicit Engineering-leadership restriction on GitHub Admin; other rows use `*`, so titles do not otherwise imply trust.
- Alice demonstrates Engineering GitHub Read auto-approval and Write manager approval. Paul and Sarah demonstrate temporary GitHub Write exception review directly by Grace. Mike demonstrates temporary GitHub Admin review by Ivan. Farah demonstrates an explicit GitHub Write rejection. Ian provides an inactive-employee negative case that must be blocked before policy evaluation.
- Figma View and Notion Standard are automatic for active employees; Figma Editor is automatic for Product/Design. Salesforce Standard requires the Sales/Customer Success employee's manager. Snowflake Read requires the Data/Engineering employee's manager; Write requires Dana and is temporary only. Non-rejection rows permit permanent access except Snowflake Write and GitHub Admin; the existing GitHub exception row permits permanent access.

These are prototype policy assumptions, not Customer.io policies. Design and Customer Success are configured for future synthetic records without requiring additional employees now. The Blueprint lists several admin roles and UI features; the locked scope limits this foundation to one elevated example (GitHub Admin), with the local Streamlit demo UI. Unmatched combinations remain manual-review cases, not implicit approvals or implicit exception grants.

### Configuration startup boundary

Call `load_configuration(config_directory)` from `access_ops.config` before using policies. The default directory is `config`, relative to the working directory; callers outside the repository root should supply an explicit path. It returns a complete immutable `Configuration` or raises `ConfigurationError`; it never returns partial configuration. The service does not load configuration at import time or read environment files. Streamlit reloads the CSV configuration on each rerun; an existing service instance requires an explicit reload, for example `workflow.configuration = load_configuration("config")`.

Validation rules:

- Both UTF-8 CSV files must exist, be readable, contain data, and have exactly the documented columns with no duplicate headers. Malformed CSV, incorrect cell counts, and blank required values fail. UTF-8 BOMs are accepted and surrounding cell whitespace is stripped.
- Only manager and approver IDs may be blank. Employee status must be `active` or `inactive`; Slack IDs and policy IDs must be unique. Nonblank managers must reference another directory employee; managers of active employees must be active. A blank manager is allowed for the documented top-level employee.
- The catalog must contain all five applications. Access levels are limited to the existing demo catalog, including only GitHub Admin as the elevated example. Applications may have disabled rows; disabling rules never creates fallback permission.
- Decisions and approver types must be recognized enum values. Boolean cells must be lowercase `true` or `false`. Policy versions must be positive integers and maximum durations nonnegative integers.
- Department/title selectors must be distinct semicolon-separated values or `*` alone. Empty list entries and mixed wildcard lists fail. Department/title names are not restricted to current employees, allowing the existing Design and Customer Success rules.
- Automatic and rejection decisions require `NONE` with no reviewer ID. Review decisions require a reviewer type. `MANAGER` leaves the ID blank; application-owner and IT/security rules require one active directory reviewer. The workflow enforces request-specific reviewer availability and self-approval checks.
- Temporary access requires a positive duration limit; disabling temporary access requires zero. Rejection allows neither temporary nor permanent access. Other rules must allow at least one duration form. Admin requires IT/security approval and temporary-only access capped at seven days. Other duration limits remain CSV-driven.
- Enabled rules with the same application/access cannot overlap in both department and title selectors, even if no current employee would match. Wildcards overlap every selector. Disabled rows still receive field and consistency validation, but do not participate in overlap detection. Errors identify the file and row or conflicting record IDs.

Use `configuration.employee(slack_user_id)` for exact lookup; unknown IDs return `None`. `match_policy(configuration, slack_user_id, application, access_level)` retrieves trusted employee attributes and refuses unknown or inactive employees. It matches enabled rules by case-sensitive application/access and both department/title selectors. There is no row-order priority or fuzzy matching. One match returns its `AccessPolicy`; zero returns `None`, meaning no policy permission; valid unmatched intake is persisted for manual review by the workflow. Multiple matches raise `ConfigurationError` defensively even if loading was bypassed.

The catalog/access choices are bounded in `config.py`, duration choices and the fixed three-attempt retry limit are in `workflow.py`; these are not CSV settings. `Configuration.it_operations_recipient` defaults to `#it-operations` and can be set by trusted calling code, not through the CSV files. Mock failure controls are constructor arguments described below.

Matching does not filter by requested duration: the workflow checks the selected policy's `temporary_allowed`, `max_duration_days`, and `permanent_allowed` fields without falling through to another rule or substituting a duration. Returning an `AUTO_APPROVE` policy does not change request status. Typed request and audit records remain data containers; the workflow and database implement validation and persistence.

## Setup

Use Python 3.12 (verified locally with 3.12.10). From the repository root in PowerShell:

```powershell
# Only needed if .venv does not exist:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Dependencies are pytest and Streamlit; SQLite and CSV support use Python's standard library. No external credentials are required. `.env.example` is a safe local template showing the current configuration paths; the application and service do not load `.env`.

## Run instructions

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open http://localhost:8501. Stop with Ctrl+C. See [Local Streamlit demo](#local-streamlit-demo) for state paths and tab behavior.

### Calling the workflow directly

For the service examples below, start a Python shell from the repository root with `src` on its import path:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
.\.venv\Scripts\python.exe
```

The first example is standalone. For each later workflow snippet, reuse its imports and database/provider setup, and replace the original submission/processing lines inside the `try` block with that snippet. Keep the `finally` cleanup. Use fresh database filenames for each independent scenario, especially temporary access; do not first submit the permanent example for the same access.

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
2. Match the configured application/access and trusted employee attributes, validate duration, and either auto-approve, wait for the single configured human approval, reject, or route a policy-less request to manual review. This example follows auto-approval.
3. Generate a UUID-based `REQ-...` ID and atomically persist `APPROVED` with `REQUEST_AUTO_APPROVED`. This event records the approval timestamp, policy ID, and version.
4. Reload the stored request and revalidate against the service's current configuration; require the same policy ID/version.
5. Commit `PROVISIONING_STARTED` and `PROVISIONING` together. Any audit/transaction error exits before the provider call.
6. Call the injected `AccessProvider.grant` boundary with the workflow-authorized stored request. The mock only inserts into its local directory; it never evaluates policy or approval.
7. Only `GRANTED` or, for permanent requests, `ALREADY_EXISTS` confirms access. Atomically persist `ACTIVE`, the provider result, completion timestamp, and `PROVISIONING_SUCCEEDED`, then return the request ID and mock-access confirmation.

Idempotency has two layers: processing an `ACTIVE` request returns the saved outcome without a provider call or extra audit events; the mock uses a unique employee/application/access tuple and stable `<request_id>:grant` key. An existing tuple returns `ALREADY_EXISTS` without inserting another grant. SQLite preserves both layers across reopening. Duplicate submissions can create separate request rows, but not duplicate directory grants. Repeated approval is rejected and audited without reprovisioning; submission deduplication is not implemented.

Assumptions and limits: identity is supplied by trusted local demo code, configuration is a validated in-memory snapshot (reload explicitly to adopt CSV edits), and processing is sequential in one local workflow service. The local SQLite files are trusted application state, not an authentication boundary. Temporary access and explicitly invoked expiration are supported as described below. Approval and provisioning times are retained in audit history. The combined creation/auto-approval event keeps this slice small.

Unconfirmed provider results use `PROVISIONING_FAILED` with a fixed safe audit description. Deterministic failure injection and bounded transient retries are described below. If completion persistence fails after a provider grant, state remains `PROVISIONING` with the durable attempt event; the response asks IT to check access and does not claim completion. Reprocessing that state stops. Crash reconciliation, concurrent workers, and automatic recovery are deferred. Raw provider errors and business reasons are excluded from these employee responses and audit details; business reasons remain stored in requests and appear in reviewer views and manual-review mock deliveries.

### Human approval

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

Tests cover pending persistence, no provisioning while pending, wrong/self reviewers, correct manager approval, approval audit ordering, revalidation both while pending and after approval, inactive/missing/ineligible requesters, changed policy/manager, unresolved reviewers, and audit failures. The same configured-reviewer checks apply across the five-application catalog.

### Exception review

Product Manager Paul (`UDEMO002`) requesting GitHub Write matches `GH-WRITE-EXCEPTION` and enters `EXCEPTION_REVIEW`. The CSV assigns Grace, the GitHub owner (`UDEMO006`), directly. Paul's manager is not involved. The existing policy also covers Sales; no additional exception rules are introduced.

The shipped exception policy permits Permanent or temporary access up to seven days.

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
# workflow.reject(response.request_id, reviewer_id="UDEMO006", reason="Launch work was cancelled")
```

The reviewer message uses the saved business reason, access level and duration. Approval/rejection requires the single assigned, active reviewer. Self-review, unauthorized decisions and decisions after completion are rejected and audited. Both normal and exception requests now support rejection with a trimmed nonempty human reason. Rejection rechecks current reviewer authority, records `REJECTED` with reason/actor/timestamp in audit history, and grants nothing.

An unresolved, inactive, or self-referencing exception reviewer leaves a saved `EXCEPTION_REVIEW` request with no assigned approver, records `EXCEPTION_ROUTING_FAILED`, and returns a blocked-review message with the request ID. There is no fallback reviewer or automatic rerouting. Startup CSV validation continues to reject invalid reviewer configuration; the workflow check also handles unavailable reviewers in the current in-memory configuration.

Approval records `EXCEPTION_APPROVED`, then revalidates the current requester, matched exception policy and version, duration permission, and reviewer authority before entering the existing Mock Okta provisioning flow. This validates the configured exception policy rather than requiring Engineering eligibility. Provider confirmation is still required for `ACTIVE`.

Audit history records `EXCEPTION_DETECTED`, `EXCEPTION_ROUTED` (or routing failure), approval attempts and rejected attempts, `EXCEPTION_APPROVED` or `EXCEPTION_REJECTED`, requester/policy/approval revalidation, and provisioning outcomes. Tests verify persistence, reviewer details, authorization, rejection, changed requester/policy/reviewer data, committed audit ordering, and audit failure safety. Configuration reload and sequential-processing limitations still apply.

### Missing and invalid requests

Intake checks trusted employee identity/status, required fields, and exact catalog values before policy execution. Missing business reason returns a correction message; unsupported applications and roles are never corrected or substituted. Unknown/inactive employees and ambiguous policy configuration retain safe rejection and IT guidance. A valid request with no enabled matching policy is saved as `MANUAL_REVIEW` and delivered to the mock IT Operations inbox; it grants nothing.

Pre-policy failures receive a UUID request reference and a durable `INTAKE_STOPPED` event in the existing audit table: `NEEDS_INFORMATION` for missing fields, otherwise `REJECTED`. These are audit-only references, retrievable with `database.events(response.request_id)`; no request row is created for these invalid inputs. No synthetic employee or policy is created, and raw input is not copied into audit details. These references cannot be processed or approved. Corrected intake requires a new submission. If audit persistence fails, the response explicitly says recording failed and directs the employee to IT; no reference or successful recording is claimed.

Missing managers now preserve `PENDING_APPROVAL` with no assigned reviewer and `APPROVAL_ROUTING_FAILED`, matching the existing blocked `EXCEPTION_REVIEW` behavior for missing exception reviewers. Neither allows approval or provisioning, chooses a fallback, or automatically reroutes after configuration correction. IT must correct configuration; recovery/rerouting is deferred. Startup CSV validation remains strict; runtime checks also defend against unavailable reviewers in the in-memory configuration.

Revalidation failures now record `REVALIDATION_FAILED` and `REJECTED` for automatic as well as human-approved requests. Existing approval history is retained. Tests cover each invalid outcome, audit persistence and deterministic states, exact matching, blocked managers and exception reviewers, no provider calls, and safe messages on internal errors.

### Temporary access and revocation

The configured catalog workflow recognizes exactly `1 day`, `7 days`, `30 days`, `90 days`, or `Permanent`. Each request must satisfy the matched policy's duration flags and maximum at intake and again before provisioning. No duration is shortened, extended, or substituted. The shipped policies do not permit 90 days; a trusted policy change is required to demonstrate that duration.

Requests persist `duration`, `temporary`, `starts_at`, `expires_at`, and `revocation_status`. Approval waiting time does not consume access time: `GRANTED` sets `starts_at` to the current workflow time, and temporary expiration is that time plus the requested number of 24-hour days. Permanent `ALREADY_EXISTS` confirms access and remains ACTIVE without assigning `starts_at` or `expires_at`. Permanent access has no expiration and `NOT_APPLICABLE` revocation status. Policy-backed temporary requests begin with `revocation_status=PENDING` and finish with `revocation_status=REVOKED` after confirmed removal; these are distinct from request statuses such as `PENDING_APPROVAL` and `ACTIVE`. Additive SQLite migration preserves earlier permanent requests and audit history; old start times remain null rather than being invented.

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

Assumptions: invoke this local workflow serially. A temporary request receiving `ALREADY_EXISTS` fails closed without a start or expiration, because it did not create its own expiring grant. Expiration uses the stored grant rather than current eligibility policy, so later employee/configuration changes do not prevent removing the original access. An unconfirmed removal now persists REVOCATION_FAILED with revocation_status PENDING for inspection and is not automatically retried (see failure handling below). Crash recovery across provider and workflow databases is not implemented.

Tests cover all five durations, disallowed/unsupported durations, pending approvals and exceptions, execution-time revalidation, expiration boundaries, durable lifecycle/audit records, exact grant targeting, pre-action audit failure, and repeated processing. Failure injection, bounded provider retries, and operation idempotency are described below. No scheduler infrastructure is added.

### Deterministic failure injection

Construct `MockOkta("provider.db", fail_grant=True)` to fail new grant operations, or `MockOkta("provider.db", fail_revoke=True)` to fail new removal operations. Replays of completed operations are checked before failure injection. Both keyword flags default to `False` and can be combined. They are local demo/test settings, returning the existing `GrantResult.FAILED` or `False` before changing the mock directory. No environment settings or random behavior are involved.

Grant failure follows the usual validation, policy, approval, revalidation, and committed `PROVISIONING_STARTED` path. It creates no grant and persists `PROVISIONING_FAILED`, preserving any manager or exception approval. Feedback says: "Approval succeeded, but provisioning failed." It asks the employee to contact IT with the request ID and not resubmit; raw provider errors are never included.

For a removal-failure demo, construct the provider with only `fail_revoke=True`, obtain temporary access normally, then call `workflow.process_expired_access(now=request.expires_at)`. `ACCESS_EXPIRED` and `REVOCATION_STARTED` commit before removal is attempted. After any bounded transient retries, a false/unconfirmed result or provider exception persists request status `REVOCATION_FAILED` and the matching audit event. The injected failure leaves the grant present. `revocation_status` remains `PENDING`, meaning removal is unconfirmed; the request status explicitly records failure. Start/expiration timestamps and all earlier approval/provisioning events remain intact. Feedback directs IT to verify and remove the grant and states that no automatic retry will occur.

Later expiration calls skip failed requests and return no result for them; they do not retry, change failure state, or claim removal. Permanent access is unaffected. This assumes serial local invocation. Revocation failure also persists an actionable notification in the mock IT inbox; provisioning failure returns local feedback but does not send an IT inbox notification. Bounded transient retries and provider-operation idempotency are described below. Backoff infrastructure and automatic recovery remain deferred.

### Retry and provider-operation idempotency

Only `TransientProviderError` raised by a provider call is retryable. It explicitly represents a timeout or temporary provider unavailability. `GrantResult.FAILED`, unconfirmed revoke results, malformed results, and all other exceptions are non-retryable, including authentication, authorization, invalid input, and configuration errors. Provider grant confirmation is `GRANTED` or `ALREADY_EXISTS` (the workflow rejects `ALREADY_EXISTS` for temporary requests); revoke `True` confirms either removal now or a previously completed removal. An absent grant without a recorded successful revoke is still unconfirmed (`False`).

The workflow makes at most **three provider attempts total**, with no sleeps or delays. Validation, approval, revalidation, and expiration checks happen before this loop. Initial `PROVISIONING_STARTED` / `REVOCATION_STARTED` events commit before attempt 1. Each failure records `PROVIDER_ATTEMPT_FAILED` with operation ID, verb, attempt number, and transient/non-retryable classification. `PROVIDER_RETRYING` commits before each additional attempt. Any audit persistence failure stops processing without another provider call. The final lifecycle event includes the operation ID and final attempt number. Approval and earlier provisioning history remain intact; success is persisted once, only after confirmation.

The existing request-based adapter interface derives stable IDs with `operation_id(request, "grant")` or `operation_id(request, "revoke")`: for example `REQ-1042:grant` and `REQ-1042:revoke`. Every attempt uses the same persisted request ID; IDs do not authorize access. Mock Okta stores completed operation IDs and the employee/application/access tuple in `mock_operations`, in the same SQLite transaction as the directory change. This additive table preserves existing directory data. Replaying a completed grant returns `ALREADY_EXISTS` while access exists, and never recreates revoked access (returns `FAILED` if absent). Replaying a completed revoke returns `True` without deleting anything, including a newer replacement grant. Reusing a completed key with different access is rejected. Revoke still targets only the original `:grant` key.

Deterministic demo construction (choose one constructor to replace the provider setup above):

```python
# Fail the first two attempts of each operation, then succeed on attempt three.
provider = MockOkta("provider.db", transient_grant_failures=2,
                    transient_revoke_failures=2)
# Exhaust the three-attempt workflow limit for grants.
provider = MockOkta("provider.db", transient_grant_failures=3)
# Non-retryable failure: one call only (permanent failure flags).
provider = MockOkta("provider.db", fail_grant=True, fail_revoke=True)
```

Counts default to zero and must be nonnegative integers. They apply independently per operation ID within a mock instance; reopening resets simulated attempt counts but preserves completed operations. Completed-operation checks precede failure injection; permanent failure flags take precedence over transient injection for new operations. A count of three or more exhausts the workflow limit. After terminal `PROVISIONING_FAILED` or `REVOCATION_FAILED`, subsequent workflow processing does not start another attempt budget. Revocation failure retains `PENDING` removal status and safe IT guidance. No failure classification or raw exception text is exposed to employees.

Assumptions remain serial local execution and mocked identity/provider calls. Production concerns left out include concurrent/distributed coordination, crash reconciliation between workflow and provider databases, durable scheduling/backoff, real provider error mapping, and real operational alert delivery. Existing temporary `ALREADY_EXISTS` handling remains conservative: it does not infer a new start time or expiration. Broad duplicate-submission detection and recovery for blocked approvals are not implemented.

## Local Streamlit demo

The app creates `data/workflow.db` and `data/provider.db` by default. Both are gitignored SQLite files and survive reruns and server restarts. Existing `manual_workflow.db` / `manual_okta.db` files are not modified or imported. For isolated demo state, set `$env:ACCESS_OPS_DATA_DIR = "C:\path\to\demo-data"` before starting; the directory uses the same `workflow.db` and `provider.db` filenames. The app reads this environment variable directly; it does not load `.env`.

- **Employee Request:** four scenario buttons prefill Alice's auto/manager paths, Paul's exception, or Ian's inactive identity above the Mock Slack UI; none submits. Review the fields, then click Submit request. Architecture/process instructions remain in documentation. Submit calls `Workflow.submit`; status feedback comes from persisted requests/audit outcomes.
- **Reviewer Inbox:** the simulated acting-reviewer list includes only active people with current configured approval authority; it excludes ordinary requesters such as Alice. The inbox then shows only requests assigned to that reviewer. Inspect the request context, then choose Approve or enter a human rejection reason and choose Reject. Backend checks apply to both actions. The action snapshot and reason remain visible after refresh; IT can inspect the durable audit history.
- **IT Operations:** a read-only console separates manual-review, provisioning-failure, revocation-failure, and unresolved requests past the illustrative 24-hour target. Each request shows derived age and SLA status from its persisted UTC creation timestamp. This is visibility only; the app does not inject failures, run a scheduler, or process expiration on reruns.

### Reset local demo state

Stop Streamlit first, then delete only the generated SQLite files below. Never delete configuration, source, or test files. The app recreates these files on restart.

```powershell
Remove-Item .\data\workflow.db -ErrorAction SilentlyContinue
Remove-Item .\data\provider.db -ErrorAction SilentlyContinue

.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Quick demo: Alice Engineer + GitHub Read auto-approves; Alice + GitHub Write waits for Mike Manager; Paul Product + GitHub Write enters exception review for Grace GitHubOwner. Use Ian FormerEmployee or an empty business reason for validation feedback. For temporary access choose 1 day, 7 days, or 30 days as permitted by policy. All choices remain subject to backend validation.

## Security and authorization boundaries

### Owner tasks in IT Operations

IT Operations displays **Viewing as Olivia Operations** across Operations, Active Access and Configuration, with no identity selector. Olivia is the fixed local demo owner; employee and reviewer selections do not change IT authority. The workspace checks owner eligibility before displaying operational data or controls, and backend actions still require an active Operations Director or IT Security Analyst in Operations. This is a local demonstration, not production authentication.

**Maintain a policy:** open Configuration, select an existing policy, and edit the supported eligibility, decision, reviewer, duration or enabled fields. Application, access level and policy ID stay fixed. Use `*` alone for any department/title. Click **Validate changes**, inspect the before/after summary, then **Save reviewed changes**. Changing the form requires another validation to replace the reviewed snapshot. Validation errors identify unsupported values, conflicting enabled rules, missing reviewers or inconsistent durations. Save revalidates authority and the complete catalog, rejects stale reviews, and increments the edited policy version. Existing grants and historical request/audit records are not rewritten. Pending provisioning may stop at revalidation after a policy version changes; review it through Operations.

**Remove access:** open Active Access and locate the employee/application. This view reads actual current grants in provider SQLite, joined to the exact original request; it does not list historical approvals as current grants. Overdue access and failed removals remain visible while the provider grant exists. Select the grant, enter a human **Removal reason**, check the explicit confirmation and click **Remove access**. Blank reasons and unconfirmed actions stop. Success removes the grant through mock Okta while retaining request and audit history. Failure remains visible in Operations and records the reason; verify current grants before an explicit retry. Use Request history & reference in Operations to inspect actor, reason, timestamp and outcome.

**Reject a request:** in Reviewer Inbox, choose the authorized acting reviewer, enter a human **Rejection reason**, and click **Reject**. Whitespace-only reasons do not complete rejection. Both normal and exception rejection are supported. Unauthorized reviewers and self-review remain blocked. The response and durable request history include the reason.

Configuration saves append before/after values and outcomes to `configuration_audit` in workflow SQLite. Save intent is durable before replacing the CSV; completion is recorded afterward. Configuration history exposes these records. A completion-audit error can occur after the CSV changed: the UI reports uncertainty, and the owner must inspect current values and history. CSV and SQLite are not one atomic transaction. Use this prototype serially with one operator; revision checks are stale-edit protection, not concurrent-writer locking. Direct CSV edits bypass administrative auditing.

For isolated practice, set both `ACCESS_OPS_DATA_DIR` (new SQLite directory) and `ACCESS_OPS_CONFIG_DIR` (a copied configuration directory) before launching Streamlit. Defaults remain `data/` and `config/`. Practice a harmless duration edit and restore it through the same Validate/Save flow; restoration increments the version again and preserves both audit records. Do not restore by erasing history.

Implemented: local structured policy administration, SQLite-backed current access, deterministic validation and audited reasoned rejection/removal. Mocked: Slack, directory, Okta and acting admin identity. Future-state: production RBAC, real APIs, dual-control change approval where appropriate, and a centralized durable configuration store. Employee editing, policy creation/deletion, arbitrary SQL/JSON editing, bulk import and rollback UI are excluded.

Employee identity and eligibility attributes come from trusted configured employee data. The UI simulates identity by letting the local operator choose an employee or reviewer; there is no authenticated Slack or Okta identity. Requesters cannot supply their own department, manager, employment status, or title through the form.

Deterministic policy configuration controls decisions. Each request has at most one human approver. The backend checks pending state, the assigned reviewer, active reviewer status, and self-approval restrictions before accepting approval, then revalidates employee eligibility, policy ID/version, duration, and current reviewer authority before provisioning. A policy match or request ID alone is not authorization. Missing reviewers block the request; unsupported values and ambiguous policies never authorize access.

Required pre-action audit writes must commit before provider calls, including retries and revocation. Approval authorizes an attempt; only provider confirmation permits success. Employee-facing failure responses omit raw provider errors and stack traces. Business reasons are stored and visible in review/operations views and manual-review mock deliveries; there is no general content-redaction system.

CSV files, local caller identities, and SQLite files are trusted local inputs, not protected security boundaries. The UI exposes shared requests and audit data to the local operator, with no role-based visibility or authenticated administration. The mock provider performs operations and relies on the workflow for authorization. Audit events are append-style through application code, not tamper-proof against local database edits.

## Known limitations

- Mock Slack and mock Okta only; synthetic employees, local SQLite, and a local Streamlit UI. No OAuth/SSO, production authentication, cloud deployment, or real approval identities from Slack/Okta.
- No LLM implementation or natural-language authorization path. The policy catalog is limited to five applications and the configured roles; GitHub Admin is the only elevated example. No hardware, FAQ, offboarding, license purchasing, or general identity-management workflows.
- Normal and exception rejection require the assigned, currently authorized active reviewer and a nonempty reason. There is no AI-generated rejection or removal reason.
- Duplicate submissions may create distinct request rows; protection prevents duplicate access. Temporary requests that find existing access fail closed rather than invent a new expiration.
- No approval-wait timeout, expiration scheduler, UI failure injection, or in-place resolution of manual-review/blocked requests. Manual review requires configuration correction and a new request. Policy editing and manual removal are available under IT Operations; expiry processing remains an explicitly invoked service operation.
- Serial local processing is assumed. No concurrent/distributed coordination, cross-database atomicity, crash reconciliation, delayed backoff, automatic recovery after terminal provisioning/revocation failure, or provisioning recovery. A process owner may explicitly retry a failed manual revocation through Active Access after verifying current access; every attempt remains audited. A failed completion write after a provider action cannot undo that action.
- Persisted mock IT deliveries cover manual review and revocation failure, not every failure or approval event. Delivery errors do not undo committed state; there is no delivery retry mechanism.
- Manual review has a distinct warning and operations filter. Employee feedback describes the immediate submission; reviewer feedback is explicitly a snapshot of the last action. Use IT Operations for current persisted state.
- Pending approvals do not currently have an age-based expiration or SLA deadline. Revalidation protects against changed employee, policy, or reviewer state, but an unchanged request may remain pending indefinitely. The Operations view provides read-only aging against a single illustrative 24-hour demo target; it does not enforce that target. Production should define an approval TTL with IT stakeholders, re-confirm or expire stale business context, and surface aging/SLA alerts.
- The prototype stores business reasons and displays them to reviewers and mock IT workflows. It does not classify or redact sensitive content automatically. Use only the minimum operational context; never include secrets, credentials, API tokens, customer data, or unnecessary personal information. Production needs data classification, access controls, retention, and deletion rules.
- Reviewer IDs are trusted prototype policy configuration. The prototype verifies that a configured reviewer exists and is active, but does not independently prove organizational application ownership or security authority. Changing a privileged reviewer, especially the GitHub Admin `IT_SECURITY` reviewer, is security-sensitive; production should use authoritative ownership/RBAC data and stronger change governance such as restricted admin roles, review/dual control, version history, and rollback.

### SLA visibility boundary

Implemented: persisted request timestamps, read-only request aging, and one illustrative 24-hour target in IT Operations. Not implemented: stakeholder-approved SLA policy, request-type targets, business-hours calculations, reminders, automated escalation, approval expiration, SLA enforcement, or historical SLA analytics. The 24-hour target is a prototype assumption for demonstrating SLA visibility. It is not a Customer.io policy.

## Demo scenarios

Use a nonempty business reason and a fresh data directory for an independent run. Unless specified otherwise, choose Permanent. In Reviewer Inbox select the generated request ID and the named reviewer; confirm successful requests in IT Operations and the mock access table.

| Scenario | Request/action | Expected outcome |
| --- | --- | --- |
| Auto-approved access | Alice / GitHub Read | ACTIVE with a confirmed mock grant |
| Manager approval | Alice / GitHub Write; approve as Mike | PENDING_APPROVAL with no grant, then ACTIVE |
| Unauthorized/self-approval | On Alice's pending Write request, try Paul or Alice | Action rejected and audited; no grant |
| Exception review | Paul / GitHub Write / 7 days; review as Grace | EXCEPTION_REVIEW; Grace alone can approve or deny |
| Policy-less manual review | Paul / GitHub Read | MANUAL_REVIEW and persisted mock IT delivery; cannot be approved/provisioned |
| Rejected or invalid | Farah / GitHub Write; or Ian / GitHub Read; or leave reason blank | No grant; rejected/invalid intake appears in audit history without a request row |
| Duplicate access | Submit Alice / GitHub Read / Permanent twice | Separate requests, one mock directory grant |
| Temporary access and revocation | Fresh Alice / GitHub Read / 1 day; invoke the expiration snippet at/after expiry | ACTIVE becomes REVOKED and its grant is removed |
| Simulated integration failure | In the service setup use `MockOkta("fresh-provider.db", fail_grant=True)` | PROVISIONING_FAILED, retained approval, no grant |
| Revocation failure | Fresh provider with `fail_revoke=True`; grant 1-day access and invoke expiration | REVOCATION_FAILED, grant retained, persisted actionable mock IT notification |

Expiration and failure simulation use the service snippets above. To inspect service-created state in Streamlit, use its `workflow.db` and `provider.db` paths, run operations serially, and click Refresh requests. Active Access also permits explicit reasoned manual removal. Use fresh files for temporary examples so existing permanent access does not block the scenario.

### Five-application demo

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

### Manual-review routing and mock IT notifications

Valid employee/catalog/access/duration requests with no matching policy persist as `MANUAL_REVIEW`, with a `MANUAL_REVIEW_ROUTED` audit event and a detailed message in the mock IT Operations inbox. Empty policy ID and version zero denote absence of a policy; no eligibility or permission is invented. The channel handles manual investigation, rather than assigning an access approver without policy authority. Approve/process cannot provision these requests. IT must establish valid configuration before a new request can follow the normal policy workflow; in-place recovery remains deferred. Explicit reject policies, ambiguous matches, unsupported catalog values, and unknown/inactive employees retain their safe behavior.

Revocation failure first commits `REVOCATION_FAILED` and its audit event, preserving the original approval, grant history, and unremoved access. It then sends an actionable mock IT notification identifying the employee, access, request, operation, and verify/remove action. Delivery failure cannot undo the committed failure state.

Both notifications use `Configuration.it_operations_recipient` (default `#it-operations`). `workflow.notifications.deliveries()` reads the durable local `mock_notifications` inbox, also shown in the IT Operations tab. This is mocked delivery only; no Slack API, credentials, or new access policies are involved.

## Tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

`pytest.ini` adds `src/` to the test import path and collects `tests/`. Final documentation QA on September 13, 2026 passed: **408 passed, 0 failed**.

[Phase 8 acceptance testing](Planning/Phase_8_Acceptance_Audit.md) passed all **15/15 criteria** in its recorded run. The final documentation-QA suite passed 408 tests. Those criteria evaluate the implemented prototype and mocked boundaries, not production integrations or every broader planning proposal.

Coverage includes normal automatic and human approval, reasoned normal/exception rejection, invalid and policy-less intake, unauthorized/self-review, duplicate access and approval replay, provisioning failure, expiration, revocation failure, committed audit ordering, bounded retries, and persistence across database reopening. `test_administration.py` adds owner authorization, exact grant ownership, reasoned manual removal, configuration validation/versioning/audit, and unchanged historical-request checks. `test_app.py` verifies UI/service wiring, prefills and owner workflows.

### Application lifecycle

In **IT Operations > Configuration**, an authorized mocked process owner can validate and save a new application with supported access levels and deterministic policy fields. The local `applications.csv` catalog controls whether an application accepts new requests. Disable requires confirmation, preserves configuration/audit history and never revokes existing access; re-enable validates the stored catalog again. Hard delete, production RBAC, bulk imports and AI-generated configuration remain out of scope.
