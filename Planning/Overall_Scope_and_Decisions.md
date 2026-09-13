# Customer.io Take-Home: Day 1 Scope and Decisions

## Human override / refinement: Day 4 extension

Branden reviewed the initial Day 4 UI and explicitly removed explanatory workflow-step content because architecture documentation already covers it. He prioritized concise demo paths and operational ownership: structured policy editing, current SQLite-backed access management, and human reasons for rejection/manual removal. This is human prioritization, not an invented AI disagreement.

The Day 4 amendment in `Implementation_Contract.md` supersedes the earlier policy-administration and non-expiration-removal exclusions. Policy configuration remains CSV-backed and deterministically validated; local administrative actions are audited and restricted to active mocked Operations Directors / IT Security Analysts in Operations. Production authentication, external API management, employee editing, general administration and AI decisions remain excluded.

**Decision date:** September 10, 2026  
**Status:** Locked foundation for architecture and implementation

## Objective

Build and defend a focused Slack-based IT access-request workflow that demonstrates technical and business judgment, intentional scope, authorization controls, auditability, maintainability, and an honest comparison of deterministic and agentic automation.

## Selected Category

**Software access requests** were selected because they provide a clear end-to-end workflow with structured intake, eligibility rules, approvals, provisioning, expiration, employee feedback, and audit history.

## Approach Decision

### Approach to build

Build a **traditional deterministic automation** using structured Slack-style intake and configurable policy rules.

Software access is a structured, consequential transaction with a limited set of valid applications, roles, approval paths, and outcomes. Deterministic automation provides stronger predictability, auditability, security, and maintainability than an LLM-driven workflow.

### Alternative architecture

Document an **agentic natural-language intake design**. An agent could interpret messages, identify the likely application, and gather missing information conversationally. However, all agent output would remain untrusted and would pass through the same deterministic eligibility, authorization, approval, and provisioning controls.

### AI boundary

- No AI API calls will be included in the implemented workflow.
- AI will not determine eligibility, authorize access, provision access, or take corrective action after errors.
- A possible future enhancement is read-only AI incident summarization after deterministic error handling has completed and sensitive information has been removed.

## Working Scope

An active employee requests access to one of five supported applications through a structured Slack-style form. Trusted employee attributes and configurable policies determine whether the request is automatically approved, routed to a manager, routed to an application owner, or routed to an IT/security reviewer. An authorized reviewer can approve or deny through a private Slack-style message. Approved access is provisioned in a test application directory through a mocked Okta adapter. Temporary access removal is explicitly invoked through the prototype expiration service after expiration. Every action is audited, and failures return useful employee feedback.

## Application Catalog

The prototype will use exactly five applications:

1. GitHub
2. Figma
3. Notion
4. Salesforce
5. Snowflake

This set demonstrates meaningfully different access-risk profiles while keeping the prototype bounded to five applications.

Example policy behaviors:

| Application/access | Example policy |
| --- | --- |
| GitHub read | Automatic for eligible Engineering employees |
| GitHub write | Manager approval for eligible Engineering employees |
| GitHub write exception | For an out-of-policy but plausible business need, route directly to the configured GitHub application owner or IT reviewer; one approval maximum |
| GitHub admin | IT/Security approval; temporary only |
| Figma editor | Automatic for Product/Design |
| Notion standard | Automatic for any active employee |
| Salesforce standard | Manager approval for eligible Sales/Customer Success employees |
| Snowflake read/write | Human approval for eligible Data/Engineering employees, with approver determined by access level |

These are prototype assumptions, not representations of Customer.io's actual access policies.

## Employee and Directory Data

The employee provides:

- Application
- Requested access option
- Business reason
- Requested duration

The system retrieves from a mocked trusted directory:

- Slack user identity
- Employee name
- Department
- Manager
- Employment status
- Job title or level for audit context

Employees cannot enter or modify their own trusted attributes. Department may determine eligibility or approval routing. Job title is retained for audit context and is not treated as a broad indicator of trust. Any title-based rule would require an explicit documented policy.

## Approval Model

- Each prototype request requires at most one approval.
- Approval types are automatic, manager, application owner, or IT/security reviewer.
- The reviewer receives a private Slack-style message with request details and Approve/Deny actions.
- Only the designated reviewer can act.
- Self-approval is prohibited.
- Requests must still be pending and unexpired when reviewed.
- Employee eligibility and policy are revalidated immediately before provisioning.
- Out-of-policy exceptions still use at most one approver. For the Product Manager → GitHub Write example, route directly to the configured GitHub application owner or IT reviewer rather than requiring sequential manager and application-owner approvals.
- Approval authorizes an attempt to provision; it does not by itself mark provisioning successful.

## Temporary and Elevated Access

Supported duration options:

- 1 day
- 7 days
- 30 days
- 90 days
- Permanent, only when policy permits

Temporary access records an access start, expiration, and deprovisioning status. A local expiration service finds expired access when explicitly invoked, removes it through the mocked Okta adapter, logs the result, and informs the employee. The demo may advance a mock clock or invoke the expiration process directly; no scheduler runs it automatically.

One narrowly defined elevated-access example will be included. It must be explicitly configured, approved by the configured privileged-access reviewer, time-limited, ineligible for self-approval, and fully audited.

## Provisioning Definition

A completed request means that the required policy and approval checks passed and the employee received access in the test application directory. This is a real state change inside the prototype. The external Okta API is mocked behind an adapter boundary.

The prototype must demonstrate that:

- The employee appears in the application's access list after successful provisioning.
- Approval and provisioning timestamps are recorded.
- Provisioning without required approval fails.
- Repeated processing does not create duplicate access.
- Temporary access is removed after expiration.

## Configuration and Maintainability

Use human-readable configuration files rather than building a policy-management web application.

- `employees.csv` contains mocked trusted directory/HRIS data.
- `access_policies.csv` contains applications, roles, eligibility conditions, decisions, approval types, approvers, duration rules, and enabled status.

A non-technical owner can edit the files in Excel or Google Sheets and export CSV. The application validates required columns, recognized values, fallback policies, and policy consistency before processing requests.

A production implementation would use a versioned policy database and an authenticated administrative interface with validation, preview/testing, change history, rollback, and restricted access.

## Employee Feedback and Failure Handling

Every outcome produces a Slack-style response explaining:

1. What happened
2. Whether anything was submitted, approved, provisioned, or removed
3. What the employee should do next
4. The request ID, when one exists

Employee responses do not expose stack traces, credentials, internal identifiers, or raw API errors.

Required failure cases include:

- Missing required information
- Unknown application
- Unsupported access level
- Unknown or inactive employee
- No matching policy
- Missing approver
- Unauthorized or self-approval attempt
- Denied request
- Duplicate request
- Provisioning failure after approval
- Temporary deprovisioning failure
- Unexpected internal error

Provisioning failures preserve approval, mark the request `PROVISIONING_FAILED`, and return local IT guidance. Only explicitly transient provider failures receive bounded immediate retry attempts; terminal failures have no automatic recovery workflow. Production recovery/reconciliation is future-state. Employees are not asked to submit a duplicate request.

## Deterministic Error Handling

| Error type | Corrective action |
| --- | --- |
| Temporary provider timeout | Retry up to a fixed configured limit |
| Invalid request data | Stop and tell the employee what to correct |
| Missing approver | Pause and route to IT |
| Authentication failure | Stop and alert IT; do not retry blindly |
| Duplicate submission | A separate request record may be created; provider idempotency prevents a duplicate access grant |
| Unknown error | Stop safely, preserve context, and alert IT |

AI will not select or perform corrective actions.

## Explicit Exclusions

- Service accounts
- Access removal unrelated to temporary-access expiration (superseded by the Day 4 amendment below; narrow reasoned manual removal is implemented)
- Employee offboarding
- License purchasing or capacity management
- Multiple sequential approvers
- More than one elevated-access example
- Real Slack, Okta, or HRIS integrations
- Production authentication, hosting, or deployment
- AI-based authorization, policy decisions, or error remediation
- Applications outside the five-item catalog
- A policy-administration web application

Unsupported application/access intake is rejected safely with an `INTAKE_STOPPED` audit outcome. Only otherwise-valid intake with no enabled policy match is persisted as `MANUAL_REVIEW` for IT investigation; it cannot authorize access.

## Discovery Questions

1. Which applications generate the most access requests?
2. What roles and permission levels exist for each application?
3. What currently determines employee eligibility?
4. Who may approve each application and access level?
5. Which low-risk requests may be automatically approved?
6. Which elevated requests may be automated after approval, and which must remain manual?
7. When should temporary access be required, and what durations are permitted?
8. Which employee attributes can be trusted from Slack, the HR system, and Okta?
9. How should provisioning and deprovisioning failures be retried and escalated?
10. What audit records and retention periods are required?
11. What are the current request volume, completion time, and approval-time baselines?
12. Who will own the catalog and policies after handoff?

Preferred opening question to the stakeholder:

> Before we discuss tooling, can you walk me through one recent access request from the employee's first Slack message through approval and provisioning, including where it slowed down or went wrong?

## Assumptions

- The prototype uses synthetic employee and request data.
- Slack identity can be mapped to one trusted employee-directory record.
- Employment status, department, manager, and configured approvers are available from trusted sources.
- The five demo applications and their rules are representative examples only.
- Each request has at most one approver in the prototype.
- Some low-risk standard requests may be automatically approved.
- The selected elevated example requires an explicitly configured privileged reviewer and temporary duration.
- Slack interactions, Okta provisioning, HRIS lookup, and supported IT notifications are mocked. Expiration requires explicit invocation of `process_expired_access()`; production scheduling is future-state.
- An approved request may still fail provisioning and must preserve that distinction.
- Configuration is maintained in validated CSV files for the prototype.
- Production policy targets would be established after baseline measurement and a limited pilot.
- Current volume is approximately 40–50 Slack messages per week across the scenario's IT request categories.

## Success Measurements

### Prototype acceptance criteria

- Every request receives an immediate response.
- No request is provisioned without satisfying its policy.
- Only the designated reviewer can approve or deny.
- Self-approval is blocked.
- Approved requests create access in the test directory.
- Denied requests create no access.
- Temporary access is removed after expiration.
- Duplicate submissions do not create duplicate access.
- Every request, decision, provisioning attempt, and removal is audited.
- Failures stop safely and return useful employee feedback.

### Production metrics

- Percentage completed without IT involvement
- Median submission-to-access time
- Median approver response time
- Provisioning success rate
- Automatic deprovisioning success rate
- Requests missing required information
- Incorrectly routed requests
- Employee satisfaction after completion
- IT hours saved
- Security exceptions or unauthorized provisioning events

No unsupported percentage-improvement targets will be claimed without baseline data. Targets would be established after measuring the current process and running a controlled pilot.

## Major Risks and Controls

| Risk | Control |
| --- | --- |
| Employee falsifies identity attributes | Retrieve them from the mocked trusted directory |
| Wrong reviewer acts | Match Slack reviewer identity to configured approver |
| Requester self-approves | Explicitly block self-approval |
| Privileged request gets insufficient review | Require configured privileged reviewer and expiration |
| Invalid configuration | Validate configuration at startup and fail safely |
| Approval is replayed | Accept decisions only while a request is pending |
| Provisioning runs twice | Check existing access and use idempotent operations |
| Provisioning fails after approval | Preserve approval, mark failure, and return local IT guidance; only explicitly transient provider failures receive bounded immediate attempts, with no automatic terminal-failure recovery |
| Temporary access is not removed | Log failure, notify IT, and use fixed retry rules |
| Slack response exposes sensitive data | Separate safe employee messages from internal technical logs |
| No policy matches | Never guess; route to manual IT review |
| Audit write fails | Stop before provisioning |
| Employee status changes while pending | Revalidate immediately before provisioning |
| Prototype scope expands | Keep five applications, one approver, and one elevated example |

## Required Order of Operations

1. Validate employee identity and active status.
2. Validate the request fields.
3. Match exactly one policy.
4. Auto-approve or obtain the configured approval.
5. Revalidate the employee and current policy.
6. Write the pre-provisioning audit event.
7. Provision through the mocked Okta adapter.
8. Confirm and log the outcome.
9. Remove temporary access at expiration and audit the result.

## Next Session

Use these locked decisions to produce:

1. Traditional architecture
2. Agentic architecture
3. Workflow state model
4. Approval and authorization boundaries
5. Data and configuration model
6. Mock-integration plan
7. Test scenarios

## Application lifecycle refinement

The Configuration surface supports human-directed onboarding plus soft disable/re-enable. A disabled application remains in the local catalog and audit history; disable prevents new intake but does not revoke grants. Hard delete, bulk import, production RBAC and AI configuration decisions remain out of scope.
