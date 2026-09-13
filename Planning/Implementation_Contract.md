\# Customer.io Access Ops - Implementation Contract

## Human-authorized Day 4 extension: September 13, 2026

This amendment supersedes earlier exclusions of local policy administration and access removal unrelated to expiration. Branden explicitly authorized these focused ownership features; the five-application catalog, deterministic workflow, single-reviewer constraint, and mock integration boundaries remain.

- IT Operations contains Operations, Active Access, and Configuration. Remove architecture/process-step guides from application pages; retain three primary experiences, concise scenario prefills, and operational results.
- Assigned, active reviewers may reject either normal pending approvals or configured exceptions with a human-entered, trimmed nonempty reason. Preserve authorization, self-review and request-state checks. Record reason, reviewer, timestamp and rejected outcome in the existing request audit history; retain the original request.
- Active Access reads current grants from the existing provider SQLite `mock_access` table, joined through its grant key to the originating workflow request. Approval history is not current access. Failed or overdue removal remains visible while the grant exists.
- Active mocked Operations Directors and IT Security Analysts in the Operations department act as prototype process owners. Backend checks this narrow role for policy saves and manual removal. Selecting an identity is not production authentication.
- Manual removal requires an explicit confirmation and trimmed nonempty human reason, verifies the exact source grant and recorded lifecycle, audits intent before the provider call, and uses existing request-specific mock revocation and bounded retries. Only provider confirmation permits REVOKED; failure retains the actual grant and auditable failure/reason. Historical request/audit records are never deleted.
- Configuration edits update existing policy rows only. Policy ID, application/access identity and automatic version are not user editable. Supported fields: department/title eligibility, decision, approver type/fixed reviewer, temporary/permanent permissions, maximum days, enabled state. No employee editing, new reviewer accounts, arbitrary SQL/JSON, bulk import, policy creation/deletion, rollback UI or AI policy generation.
- Edit → validate/review changes → explicit save. Validate the entire candidate catalog using the startup loader plus administrative checks for known selectors and valid exception/manager routing. Reject malformed, conflicting, stale or unauthorized changes. Increment the changed policy version automatically; persist to the existing CSV via a staged atomic file replacement.
- Append configuration audit records with actor, UTC time, policy, before/after values and intent/outcome. A durable intent must exist before replacement. CSV and SQLite are separate stores; an interrupted completion can require manual reconciliation and must not be reported as confirmed success.
- New policy versions affect future evaluation and revalidation of pending requests. They do not rewrite historical policy references, decisions, audit events or existing grants. No AI approves any configuration or access action.



\*\*Status:\*\* Locked for Day 3 implementation

\*\*Purpose:\*\* Define exactly what will and will not be built for the take-home prototype.



This file is the implementation scope for the prototype. Do not add functionality outside this contract unless explicitly requested.



\## Goal



Build one narrow, reliable vertical slice for software access requests.



An authenticated mock employee submits a structured access request. The application validates the request, retrieves trusted employee attributes, evaluates deterministic policy rules, obtains at most one human approval when required, provisions access through a mocked Okta adapter, records state and audit history, returns Slack-style feedback, and removes temporary access when it expires.



\## Application Catalog



The core prototype supports exactly five applications:



\* GitHub

\* Figma

\* Notion

\* Salesforce

\* Snowflake

The Day 4 human-authorized lifecycle amendment below supersedes this core-build restriction only for local application onboarding after the core workflow was complete. The shipped demo/test catalog remains these five applications; a later locally added entry does not turn the prototype into a general IAM platform.



Do not add additional applications during the core build.



\## Must Work



The completed core prototype must include:



\* Synthetic employees

\* Five supported applications

\* Structured access-request intake

\* Required-field validation

\* Trusted employee-directory lookup

\* Deterministic policy evaluation

\* Auto-approval

\* One normal human-approval path

\* One exception-review path

\* At most one human approver per request

\* Mock Okta provisioning

\* SQLite request state

\* Append-style audit events

\* Slack-style employee/reviewer responses

\* Temporary-access expiration

\* Mock access revocation

\* Idempotency and duplicate protection

\* Explicit deterministic failure simulation

\* Automated tests



\## Approval Constraint



A request may require \*\*zero or one human approver\*\*.



Sequential or multi-stage approvals are explicitly outside prototype scope.



For the Product Manager → GitHub Write exception example, route the request directly to the configured GitHub application owner / IT reviewer.



A production implementation could require additional approval stages, but they will not be implemented here.



\## Nice to Have: Only After Core Workflow Passes



These features may be added only after the required workflow and tests work reliably:



\* Simple operations page

\* Simple configuration viewing/editing UI

\* Metrics summary



Failure to build these features does not make the prototype incomplete. The Day 4 amendment above supersedes the earlier “nice to have” framing for the implemented local ownership features; it does not expand the core workflow or add production administration.



\## Explicitly Out of Scope



Do not implement:



\* Real Slack integration

\* Real Okta integration

\* OAuth

\* Docker

\* Cloud deployment

\* LLM or AI API calls

\* AI-based authorization or remediation

\* Multi-approver workflows

\* Production authentication

\* Production SSO

\* Fancy frontend

\* Hardware/equipment workflows

\* General IT FAQ workflows

\* General-purpose identity-management functionality

The earlier exclusions of local policy administration and unrelated manual access removal are superseded by the Day 4 amendment above. All other exclusions remain effective.



\## Architectural Boundaries



\### AI



There is no runtime AI dependency in the implemented prototype.



AI may be discussed in the documented alternative architecture, but it must not:



\* Determine access eligibility

\* Authorize access

\* Approve exceptions

\* Select unauthorized approvers

\* Provision or revoke access

\* Determine corrective actions after failures



\### Policy



Access decisions must come from deterministic configuration rather than application-specific hard-coded branching where practical.



\### Identity



Employees cannot provide or modify their own trusted attributes such as:



\* Department

\* Manager

\* Employment status

\* Job title



Those values come from mocked trusted employee data.



\### Provisioning



Provisioning occurs only after:



1\. Employee validation

2\. Request validation

3\. Policy evaluation

4\. Required approval, if applicable

5\. Revalidation

6\. Successful pre-provisioning audit write



Approval means permission to \*\*attempt provisioning\*\*. It does not mean provisioning succeeded.



\### Auditability



Requests, approvals, denials, provisioning attempts, failures, expiration, and revocation must produce audit events.



If the required audit write fails before a consequential action, the action must stop.



\## Failure Philosophy



Fail safely.



Never guess:



\* Employee identity

\* Application

\* Access level

\* Policy

\* Approver

\* Provisioning outcome



Expected failures must result in a controlled request state, useful employee feedback, and enough internal information for troubleshooting.



Do not expose secrets, stack traces, credentials, or raw provider errors in employee-facing responses.



\## Implementation Priority



Build in this order:



1\. Synthetic employee/config data

2\. Structured request model

3\. Validation

4\. Deterministic policy engine

5\. Auto-approved happy path

6\. Mock provisioning

7\. Persistence and audit trail

8\. Human approval path

9\. Exception-review path

10\. Failure handling

11\. Idempotency / duplicate protection

12\. Temporary access expiration and revocation

13\. Automated tests

14\. Nice-to-have UI/metrics only if time remains



\## Definition of Core Done



The core build is complete when automated tests and/or deterministic demo scenarios prove that:



\* An eligible request can auto-approve and provision.

\* A request requiring approval cannot provision beforehand.

\* Only the configured reviewer can approve.

\* Self-approval is blocked.

\* An approved request provisions successfully.

\* A denied request does not provision.

\* An out-of-policy but legitimate request can enter the single-reviewer exception path.

\* Duplicate processing does not duplicate access.

\* Provisioning failure preserves the approval but records failure.

\* Temporary access expires and is revoked.

\* Revocation failure is visible and auditable.

\* Every consequential state change has an audit trail.



Prefer a small implementation that satisfies these behaviors over additional features.




## Human-authorized application lifecycle refinement: September 13, 2026

Branden authorized non-technical application onboarding and application soft disable/re-enable in IT Operations. Applications are retained in a validated `applications.csv` catalog with an enabled flag; policies remain separate configuration rows. Hard deletion is excluded: history, audit references and active grants remain readable. Disabling stops new requests only and never revokes existing access. Creation, disable and re-enable use deterministic validation, mocked owner authorization, review/save confirmation and the existing configuration audit history. Production would add authenticated RBAC and stronger change approval.
