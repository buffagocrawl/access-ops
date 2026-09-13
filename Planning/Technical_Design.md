# Access Ops Technical Design

## Day 4 operational ownership extension

The human-approved contract amendment adds a small administrative service and UI without a parallel access-state model. `mock_access` in provider SQLite is authoritative for currently present grants. Its `grant_key` identifies the original request; join that exact request for grant time, temporary duration, expiry and history. Do not infer current access from approval status or duplicate `ALREADY_EXISTS` requests. A passed expiration date does not itself prove removal.

Rejection supports normal and exception pending states and requires a trimmed nonempty reason in service logic. Existing request audit event details persist that reason together with actor, timestamp and outcome; no separate rejection-reason column is needed.

Manual removal validates active mocked process-owner authority, explicit confirmation, reason, allowed source request state, exact provider grant ownership and successful provisioning evidence. Commit a reason-bearing intent before calling the existing `_provider_operation(..., 'revoke')`. Success records REVOKED; failure records REVOCATION_FAILED, keeps the actual grant visible and delivers local IT feedback. Existing request/audit and provider operation histories are retained. No new grant table is introduced.

Policy administration edits existing rows in `access_policies.csv` using structured controls. Identity fields (policy ID, application/access) are fixed. Editable eligibility, decision, reviewer, duration and enabled fields are validated by staging a complete candidate and calling `load_configuration`; additional administration checks reject unknown selectors, invalid exception routing and unresolved manager review. Versions increment automatically. A digest of both directory and policy files protects against stale review/save. Each save reloads authority from current directory data.

One additive `configuration_audit` SQLite table records attempted/rejected/succeeded/failed changes with before/after JSON, actor and UTC timestamp. JSON is internal audit serialization, not an editing interface. Durable intent precedes atomic CSV replacement; completion follows it. This is not a cross-resource transaction or version-control system. An interrupted completion remains visible as intent requiring investigation; no confirmed success is returned without completion audit. Historical requests retain their original policy references and are subject to existing revalidation when provisioning is attempted.

The UI retains Employee Request, Reviewer Inbox and IT Operations at top level. IT Operations uses a simple Operations / Active Access / Configuration selector. Mock labels and concise scenario controls remain; process-step cards are removed. Production RBAC, real Okta APIs, dual control, centralized configuration and rollback remain future-state.

**Status:** Implementation design for the locked prototype contract  
**Project:** Customer.io IT access-request take-home project

## Purpose

This document translates the existing scope and implementation contract into a deliberately simple technical design. It does not add application behavior or change the decisions in the other planning documents.

## Technology

The prototype will use:

- **Python** for the application and workflow logic.
- **SQLite** for local request, access, and audit state.
- **pytest** for deterministic automated tests.
- **Streamlit** for the demo and presentation interface only.

`app.py` is an interface layer. Authorization, policy evaluation, workflow transitions, provisioning logic, persistence, and audit behavior must be implemented in the `src/access_ops/` modules and called by the interface. The UI must not decide whether access is permitted or directly mutate workflow state.

There is no runtime LLM or AI API dependency in the core workflow. Any future AI intake would produce untrusted structured input that must pass the same deterministic validation and authorization boundaries.

## Planned repository structure

```text
access-ops/
├── Planning/
├── config/
│   ├── employees.csv
│   └── access_policies.csv
├── src/
│   └── access_ops/
│       ├── models.py
│       ├── config.py
│       ├── policy_engine.py
│       ├── workflow.py
│       ├── approvals.py
│       ├── audit.py
│       ├── database.py
│       ├── notifications.py
│       └── integrations/
│           └── mock_okta.py
├── tests/
│   ├── test_policy_engine.py
│   ├── test_workflow.py
│   ├── test_approvals.py
│   └── test_expiration.py
├── app.py
├── seed.py
├── requirements.txt
├── README.md
├── .env.example
└── .gitignore
```

This is the intended design. Creating empty source, test, configuration, or entry-point files is outside this documentation task.

## Responsibilities and boundaries

| Module or boundary | Responsibility | Boundary |
| --- | --- | --- |
| `app.py` | Render Streamlit forms, demo controls, status, and safe messages | Does not authorize, evaluate policy, or perform direct state transitions |
| `models.py` | Define request, employee, policy, approval, access, and audit representations | Does not make policy decisions |
| `config.py` | Load and validate the CSV configuration | Does not provision access |
| `policy_engine.py` | Deterministically match policy and produce the required decision/routing result | Does not mutate access or bypass approval |
| `workflow.py` | Orchestrate validation, state transitions, revalidation, provisioning, expiration, and idempotency | Owns workflow rules independently of the UI |
| `approvals.py` | Assign the single authorized reviewer and validate approve/deny actions | Blocks unauthorized and self-approval |
| `audit.py` | Append audit events before and after consequential actions | Does not silently discard audit failures |
| `database.py` | Persist SQLite request, access, and audit state | Provides durable state used by the workflow |
| `notifications.py` | Produce Slack-style employee, reviewer, and IT messages | Does not expose secrets, stack traces, or raw provider errors |
| `integrations/mock_okta.py` | Simulate external grants and removals, including explicit failures | Does not decide whether an action is authorized |
| `seed.py` | Prepare synthetic demo data and local prototype state | Does not replace workflow validation |

## Request status model

The workflow uses this intentionally small set of statuses:

```text
NEEDS_INFORMATION
PENDING_APPROVAL
EXCEPTION_REVIEW
APPROVED
PROVISIONING
ACTIVE
REJECTED
PROVISIONING_FAILED
EXPIRED
REVOKED
REVOCATION_FAILED
```

The workflow service, rather than Streamlit, controls valid transitions. Every transition should record the actor, timestamp, previous status, new status, request ID, and non-sensitive details as an append-style audit event. A request may have zero or one human approver; sequential approval chains are excluded.

### High-level lifecycle

1. An authenticated mock employee submits structured application, access, reason, and duration fields.
2. The workflow validates the employee identity and active status, then validates required request fields.
3. A deterministic policy is matched. Incomplete input uses `NEEDS_INFORMATION`; a required normal approval uses `PENDING_APPROVAL`; a plausible out-of-policy request uses `EXCEPTION_REVIEW`; prohibited or unsafe requests use `REJECTED` or controlled IT escalation as defined by policy.
4. Automatic decisions move to `APPROVED`. An assigned reviewer may move a pending request to `APPROVED` or `REJECTED` only while the request is reviewable, only once, and only when authorized.
5. The workflow revalidates employee status, current policy, approval authority, request expiry, and duplicate state. It writes the required pre-provisioning audit event before moving to `PROVISIONING`.
6. The mocked Okta adapter attempts the grant. A confirmed grant moves the request to `ACTIVE`; a simulated or actual adapter failure moves it to `PROVISIONING_FAILED` while preserving valid approval and audit context.
7. Temporary active access moves to `EXPIRED` when its end time is reached. The expiration processor requests deterministic removal through the same integration boundary. Successful removal moves to `REVOKED`; an unsuccessful removal moves to `REVOCATION_FAILED` and alerts IT.

Repeated submissions and processing use stable request/access identifiers and must return the existing result without duplicate provisioning. Failure states are explicit and auditable rather than silently swallowed.

## Synthetic demo employees

These are synthetic demo records and are not representations of Customer.io employees.

| Persona | Department | Title | Status | Demonstration purpose |
| --- | --- | --- | --- | --- |
| Alice Engineer | Engineering | Software Engineer | Active | Eligible happy-path, auto-approved request |
| Paul Product | Product | Product Manager | Active | Legitimate request requiring human approval |
| Sarah Sales | Sales | Account Executive | Active | Access-policy exception requiring review |
| Ian FormerEmployee | Engineering | Software Engineer | Inactive | Rejection based on trusted employee status |

The exact application/access combinations and policy rows remain in editable synthetic configuration. They must demonstrate the scenarios above without expanding the five-application catalog.

## Synthetic reviewers

The demo reviewer records are:

- **Mike Manager** — manager approval
- **Grace GitHubOwner** — application-owner approval
- **Ivan ITSecurity** — security and exception review
- **Dana DataOwner** — sensitive-data application approval

These are synthetic demo records, not representations of Customer.io employees. Reviewer identity and authority are looked up from trusted demo configuration; they are not supplied by the requester or selected by the UI.

## Deterministic workflow controls

The workflow must enforce these boundaries:

- Treat employee identity and employment status as trusted demo configuration.
- Validate employee status before access-policy evaluation.
- Make policy decisions deterministic and configuration-driven.
- Never provision from arbitrary UI input; provisioning accepts an authorized request reference.
- Revalidate identity/status, current policy, reviewer authority, approval state, and request expiry immediately before provisioning.
- Treat approval as authorization to attempt provisioning, not proof that provisioning succeeded.
- Persist the pre-provisioning audit event successfully before a consequential provider call.
- Permit only the assigned reviewer to decide, prohibit self-approval, and reject replayed decisions.
- Keep duplicate processing idempotent.
- Use explicit adapter outcomes and bounded deterministic retry behavior for simulated failures.
- Return safe employee-facing feedback while retaining useful non-sensitive internal audit context.

## Configuration and persistence

`config/employees.csv` is the synthetic trusted directory. It should contain the Slack identity, name, email, department, title, manager, and active/inactive status needed by the workflow and audit context.

`config/access_policies.csv` is the editable policy catalog. It should represent the five supported applications—GitHub, Figma, Notion, Salesforce, and Snowflake—along with access level, eligibility, decision type, approver role, temporary-access rules, maximum duration, enabled status, and policy version as required by the existing contract.

SQLite stores the current request/access state and append-style audit events. The current record answers where a request is now; audit history records how it reached that state. Configuration loading must validate required columns, recognized values, enabled policies, approver availability, and policy consistency before processing requests.

## Mock integration behavior

Slack-style intake, messages, reviewer actions, alerts, employee-directory data, and expiration invocation are local demo behavior. The Okta adapter is explicitly mocked but must behave like an external dependency: it can confirm a grant/removal, return an existing idempotent result, or simulate a controlled failure. The workflow must never mark access active or revoked without a confirming adapter result.

## Architectural principles

- Treat employee identity/status data as trusted configuration for the demo.
- Validate employee status before access-policy evaluation.
- Policy decisions must be deterministic.
- An LLM must never independently authorize software access.
- AI output, if introduced later, is untrusted until deterministic validation occurs.
- Provisioning is isolated behind an integration boundary.
- Mock Okta should behave like an external dependency, including simulated failures.
- Every consequential action should create an audit event.
- Configuration should be editable without changing workflow logic.
- Temporary access must support expiration and deterministic revocation.
- Duplicate/idempotent requests must not result in duplicate provisioning.
- Failure states must be explicit rather than silently swallowed.

## Explicit exclusions

The implementation does not include:

- Real Slack integration
- Real Okta integration
- OAuth
- Docker
- Cloud deployment
- LLM/API calls in the core workflow
- Multi-approver workflows

These exclusions preserve the existing scope and architecture decisions. Additional exclusions in the locked planning documents remain in force.

## Application lifecycle

`applications.csv` is the validated local application catalog. It carries the application-level enabled state, while `access_policies.csv` keeps policy-level rules. Local owners create, disable and re-enable through staged, audited configuration actions. Disabling never calls the provider revocation path.
