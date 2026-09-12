# Access Ops

Access Ops is a focused prototype for software access requests. It addresses the manual intake, routing, approval, provisioning, expiration, and audit work that can surround employee access requests.

## Scope and approach

The narrow scope is software access requests through a Slack-style structured workflow. The selected implementation approach is deterministic, traditional automation: trusted employee attributes and human-readable policy configuration drive repeatable validation, routing, approval, provisioning, and revocation decisions.

An agentic natural-language intake architecture is documented for comparison and possible future use. It is not implemented, and no AI API calls are part of the prototype.

## Status and behavior boundaries

### Implemented behavior

The configuration and data-model layer uses the Python standard library: immutable typed records, validated CSV loading, exact employee lookup, and deterministic policy selection. The first end-to-end workflow now supports an active Engineering employee requesting permanent GitHub Read access under the configured `AUTO_APPROVE` policy, with SQLite request/audit state, a mocked Okta directory, and safe Slack-style feedback. A policy match alone does not authorize provisioning; the workflow enforces validation, revalidation, and the committed audit requirement.

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
- `AUTO_APPROVE` and `REJECT` use `approver_type=NONE` and a blank ID. `MANAGER` uses a blank ID because the one reviewer comes from the requester's `manager_slack_id`. `APPLICATION_OWNER` and `IT_SECURITY` each identify exactly one reviewer through `approver_id`. The Engineering GitHub Write workflow checks manager availability and prohibits self-approval; other review paths remain deferred.
- Booleans are `true`/`false`. `max_duration_days` caps temporary access only; permanent access requires `permanent_allowed=true`. Rejection rows allow neither and use a zero-day limit. Standard temporary access is capped at 30 days, GitHub exceptions and Admin at 7 days. A 90-day request is not authorized by these rows. Duration failures must not fall through to a more permissive rule.
- `policy_version` starts at `1` and should increase when a row changes. `eligible_titles` preserves the Blueprint's explicit Engineering-leadership restriction on GitHub Admin; other rows use `*`, so titles do not otherwise imply trust.
- Alice demonstrates Engineering GitHub Read auto-approval and Write manager approval. Paul and Sarah demonstrate temporary GitHub Write exception review directly by Grace. Mike demonstrates temporary GitHub Admin review by Ivan. Farah demonstrates an explicit GitHub Write rejection. Ian provides an inactive-employee negative case that must be blocked before policy evaluation.
- Figma View and Notion Standard are automatic for active employees; Figma Editor is automatic for Product/Design. Salesforce Standard requires the Sales/Customer Success employee's manager. Snowflake Read requires the Data/Engineering employee's manager; Write requires Dana and is temporary only. Standard non-rejection rows permit permanent access except Snowflake Write and the GitHub exception/Admin rows.

These are prototype policy assumptions, not Customer.io policies. Design and Customer Success are configured for future synthetic records without requiring additional employees now. The Blueprint lists several admin roles and UI features; the locked scope limits this foundation to one elevated example (GitHub Admin), with no UI. Unmatched combinations remain manual-review cases, not implicit approvals or implicit exception grants.

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

Matching does not filter by requested duration: the workflow checks the selected policy's `permanent_allowed` flag without falling through to another rule. Temporary durations remain deferred. Returning an `AUTO_APPROVE` policy does not change request status. Typed request and audit records remain data containers; the workflow and database implement validation and persistence.

### Local checks (Python 3.12)

Reuse the existing `.venv`. If setting up a fresh checkout, create it with a Python 3.12 interpreter (`python -m venv .venv`). From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

`pytest.ini` makes `src/` importable during tests and collects tests from `tests/`; no package installation or activation is needed for these commands. SQLite (`sqlite3`) and CSV support use Python's standard library. Streamlit is deferred until the demo interface is built. All future business logic belongs in `src/access_ops/`, independently of Streamlit.

There is no UI or application entry point yet; the golden path is callable through the Python service below. Exception review, denial workflows, temporary access, expiration, revocation, retries, broad duplicate-submission handling, failure-simulation controls, dashboards, and configuration editing remain deferred. Real integrations, external APIs, AI runtime behavior, Docker, and ORM are not implemented. The `.env.example` paths match the existing configuration, but environment-file loading is not implemented.

Tests cover the existing configuration and policy engine plus the golden-path workflow, committed audit ordering, provider-confirmed activation, persistent idempotency, existing-access outcomes, invalid intake, revalidation, audit failures, and safe handling of unconfirmed provider results. Expiration and revocation-failure workflows remain deferred; the full core prototype is not yet complete.

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

Tests cover pending persistence, no provisioning while pending, wrong/self reviewers, correct manager approval, approval audit ordering, revalidation both while pending and after approval, inactive/missing/ineligible requesters, changed policy/manager, unresolved reviewers, and audit failures. Step 12 adds normal permanent Engineering GitHub Write approval. Step 13 extends this machinery for exception review as described next. Temporary access/expiration/revocation, broader invalid-input handling, failure injection, retries, and generalized idempotency remain later work.

### Exception review (Phase 6, Step 13)

Product Manager Paul (`UDEMO002`) requesting GitHub Write matches `GH-WRITE-EXCEPTION` and enters `EXCEPTION_REVIEW`. The CSV assigns Grace, the GitHub owner (`UDEMO006`), directly. Paul's manager is not involved. This preserves the human decision to reject the earlier AI suggestion of a manager plus owner approval chain. The existing policy also covers Sales; no additional exception rules are introduced.

**Duration assumption for this step:** the previous exception CSV row allowed only temporary access, which conflicts with demonstrating provisioning before temporary access is implemented. This step explicitly permits Permanent access on that demo policy and increments its version to 2. Permanent remains the only accepted duration; no duration checks are bypassed. The existing permanent-only SQLite representation reloads requests with `temporary=False` and `expires_at=None`. Temporary duration storage, expiration, and revocation are deferred. Planning documents are unchanged.

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

The reviewer message uses the saved request's business reason and access level, and identifies the supported Permanent duration. Approval/rejection requires the single assigned, active reviewer, who must still match the configured application owner or IT/Security reviewer. Self-approval, unauthorized decisions, and decisions after completion are rejected and audited. Rejection records `REJECTED` and grants nothing. No normal manager denial workflow is added.

An unresolved, inactive, or self-referencing exception reviewer leaves a saved `EXCEPTION_REVIEW` request with no assigned approver, records `EXCEPTION_ROUTING_FAILED`, and returns a blocked-review message with the request ID. There is no fallback reviewer or automatic rerouting. Startup CSV validation continues to reject invalid reviewer configuration; the workflow check also handles unavailable reviewers in the current in-memory configuration.

Approval records `EXCEPTION_APPROVED`, then revalidates the current requester, matched exception policy and version, duration permission, and reviewer authority before entering the existing Mock Okta provisioning flow. This validates the configured exception policy rather than requiring Engineering eligibility. Provider confirmation is still required for `ACTIVE`.

Audit history records `EXCEPTION_DETECTED`, `EXCEPTION_ROUTED` (or routing failure), approval attempts and rejected attempts, `EXCEPTION_APPROVED` or `EXCEPTION_REJECTED`, requester/policy/approval revalidation, and provisioning outcomes. Tests verify persistence, reviewer details, authorization, rejection, changed requester/policy/reviewer data, committed audit ordering, and audit failure safety. Configuration reload and sequential-processing limitations from Step 12 still apply.

Do not commit credentials, tokens, passwords, API keys, or local `.env` files. The `.env` file is gitignored; use `.env.example` as the safe template.

## Planning references

The [`Planning/`](Planning/) directory is the source of truth for architecture, scope, implementation boundaries, assumptions, workflow states, and the deterministic-versus-agentic decision.
