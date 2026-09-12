\# Customer.io Access Ops - Implementation Contract



\*\*Status:\*\* Locked for Day 3 implementation

\*\*Purpose:\*\* Define exactly what will and will not be built for the take-home prototype.



This file is the implementation scope for the prototype. Do not add functionality outside this contract unless explicitly requested.



\## Goal



Build one narrow, reliable vertical slice for software access requests.



An authenticated mock employee submits a structured access request. The application validates the request, retrieves trusted employee attributes, evaluates deterministic policy rules, obtains at most one human approval when required, provisions access through a mocked Okta adapter, records state and audit history, returns Slack-style feedback, and removes temporary access when it expires.



\## Application Catalog



The prototype supports exactly five applications:



\* GitHub

\* Figma

\* Notion

\* Salesforce

\* Snowflake



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



\## Nice to Have — Only After Core Workflow Passes



These features may be added only after the required workflow and tests work reliably:



\* Simple operations page

\* Simple configuration viewing/editing UI

\* Metrics summary



Failure to build these features does not make the prototype incomplete.



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



