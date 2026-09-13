# Access Ops: Slack Software Access Automation

For local setup and demo instructions, see the [README](../README.md).

I chose software access requests because they connect an everyday employee frustration with consequential IT work: understanding the request, checking eligibility, finding the right reviewer, granting access, and knowing when that access should end. Compared with hardware requests or general FAQs, this category offered a clear, bounded transaction whose correctness I could demonstrate from intake through removal.

I implemented the traditional deterministic approach and designed an agentic alternative without building it. The scenario describes approximately 40-50 weekly Slack messages across several IT categories, not a measured software-access workload. With a small application catalog and explicit authorization rules, I judged structured intake and a deterministic workflow to be the better starting point. Conversational AI could improve intake, but it would not replace the need to establish who may receive access and who may approve it.

The prototype demonstrates structured requests, trusted employee lookup, configurable policy, automatic approval, one-reviewer approval, configured exceptions, policy-less manual review, mock provisioning, audit history, failure visibility, and temporary-access removal. A local interface also shows request aging against an illustrative 24-hour target. Later ownership features support bounded policy maintenance, application lifecycle controls, and inspection or manual removal of current mock access.

Slack, employee identity, authentication, Okta, and notifications are simulated. Provisioning changes a local mock directory, not real application access. The most important limitation is operational recovery: provider and workflow state live in separate SQLite stores, so a successful provider mutation followed by a failed completion write requires manual reconciliation. Production work should establish real identity, integration, governance, and recovery controls before expanding automation or adding conversational intake.

## 1. Questions I Would Ask Before Building

I would start by walking through a recent request with IT, from the employee's first message to confirmed access, then ask:

- How many requests concern software access, which applications dominate, and how often do incomplete requests require clarification or rework?
- What is the supported catalog, which access levels exist, and which applications or permissions are high risk? Are licensing or training prerequisites involved?
- Who owns each approval decision? Which requests may be automatic, which need a manager or application owner, and who can authorize an exception?
- When must access be temporary, how long may it last, and who owns removal, employee transfers, and offboarding?
- What are the expected response, approval, and provisioning SLAs? Should unanswered approvals expire, and who receives escalations?
- Which Okta capabilities are available for each application, including grant verification and removal? Where would manual fulfillment still be necessary?
- Which system establishes trusted employee identity, active status, department, manager, and reviewer authority?
- What audit retention and data-access requirements apply, who will maintain the workflow without engineering help, and which baseline measures would define a successful pilot?

These answers could change the first application selected, approval routing, integration scope, and whether intake friction warrants an AI layer.

## 2. Assumptions Made

I used synthetic employees and policy data because Customer.io-specific identity and access rules were unavailable. The shipped demo catalog contains GitHub, Figma, Notion, Salesforce, and Snowflake. Their permissions and eligibility rules are illustrative, not Customer.io policies.

I assumed employee identity maps to trusted directory attributes: active status, department, title, and manager. Employees provide application, access level, reason, and duration; they cannot supply their own eligibility attributes. Policy configuration is trusted prototype input. Validating a configured reviewer exists and is active does not independently establish that person's organizational authority.

I limited each request to zero or one human reviewer. The 24-hour aging target is an illustrative prototype assumption, explicitly **not a Customer.io SLA or policy**. It provides visibility without reminders, escalation, or authorization effects.

Slack-style interactions, Okta operations, authentication, and notifications are mocked. Employee and reviewer feedback is local; persisted mock IT deliveries cover manual review and revocation failure rather than every workflow event.

Temporary access begins when a new grant is confirmed, with duration constrained by policy. Standard temporary policies allow up to 30 days; GitHub Admin allows up to seven and prohibits permanent access. The configured GitHub Write exception caps temporary access at seven days but also permits permanent access. Expiration requires explicit invocation of `process_expired_access()`; no scheduler runs automatically. Production employee lifecycle and offboarding integration are excluded.

## 3. Scope and Success Criteria

The core is one vertical slice: structured Slack-style intake, validation, deterministic policy matching, auto-approval, one-reviewer approval, configured exception review, policy-less `MANUAL_REVIEW`, mock provisioning, audit/history, temporary access and revocation, and visible failure outcomes. Read-only aging visibility addresses the scenario's tracking problem without adding a full SLA engine.

After the core workflow passed, I added the Day 4 ownership extensions: local policy maintenance, application onboarding and soft disable/re-enable, and Active Access visibility with reasoned manual removal. These extensions help demonstrate handoff and ongoing ownership. They are separate from the core and are not required to understand the architecture decision.

Prototype success means the intended paths work and unsafe paths stop. The automated suite covers normal access, pending and approved requests, exceptions, rejection, unauthorized actions, duplicate grants and review replays, provisioning failures, expiration, revocation failures, and persistence boundaries. These checks demonstrate behavior in the local environment; they do not establish production reliability or business savings.

For a real pilot, I would measure:

- Percentage resolved automatically, alongside request mix and exception frequency.
- Clarification rate, intake time, and employee completion or abandonment.
- Time from submission to approved access, separating approval latency from provisioning time.
- Provisioning success/failure and requests past the agreed SLA target.
- IT handling time per request compared with the current process.
- Unauthorized grants, with a target of zero.

I would establish the baseline before setting improvement targets. I have not measured actual time savings or an achieved automation rate.

## 4. Traditional Automation Architecture

The local Streamlit interface collects structured requests and passes them to a UI-independent Python workflow. CSV configuration supplies the synthetic employee directory, application catalog, and policy rules. SQLite stores request state and append-style audit history; a separate SQLite database represents Mock Okta grants and completed provider operations.

The workflow first validates identity and input, then matches enabled policy using the requested application/access and trusted employee attributes. Configuration is validated for malformed or conflicting rules. A matching rule can permit automatic approval, require one reviewer, route a configured exception, or reject the request. Request duration must satisfy the selected policy; it cannot fall through to a more permissive rule.

**No policy means no authority.** Otherwise-valid intake with no enabled policy match becomes `MANUAL_REVIEW` and reaches the mock IT inbox for investigation. That state cannot authorize provisioning. Unsupported application/access intake instead stops safely with an `INTAKE_STOPPED` audit outcome; it is not a manual-review request.

For human review, the backend checks the assigned reviewer, active identity, request state, and self-review prohibition. It rejects and audits invalid or replayed approval/rejection actions. Approval authorizes a provisioning attempt; it does not mean access exists.

Before calling the provider, the workflow revalidates employee eligibility, policy identity/version, and required approval evidence. It commits provisioning intent and state before the consequential action. Only a confirmed provider result followed by successful persistence of final state and audit allows a successful completion response.

Temporary grants record start and expiration timestamps. Explicit expiration processing audits the removal attempt and calls the mock provider; confirmed removal permits a revoked state. Failed removal remains visible and produces a persisted mock IT notification. The [architecture document](Access-Ops_Architecture.md#3-traditional-deterministic-architecture-selected-build) contains the Mermaid component and lifecycle diagrams.

## 5. Agentic Automation Architecture

The alternative I designed would accept a free-form Slack request such as “I need to update our GitHub integration for the launch.” An intake agent could interpret intent, identify likely application/access choices, and ask whether the employee needs read or write access and for how long. It would gather missing information using approved catalog and policy context, then present a structured request for employee confirmation.

The agent would return the proposed fields and a confidence assessment. Ambiguous, unsupported, or conflicting interpretations would require clarification or human intake assistance. Confidence would describe extraction uncertainty, never permission to grant access. I would evaluate its calibration against representative examples rather than assume a model's confidence score is reliable.

The strongest hybrid keeps the same deterministic workflow behind this conversational interface. Schema validation, supported values, trusted identity lookup, policy matching, reviewer assignment, and pre-action checks remain mandatory. The agent never independently decides eligibility, assigns itself authority, approves access, provisions, revokes, or changes policy. A plausible business reason cannot bypass those controls.

This design could reduce clarification work while preserving authorization boundaries. It also needs evaluation data, prompt-injection defenses, data-handling rules, model/version records, and a structured fallback during outages. I would build it only if measured intake problems justify that additional operating responsibility. The [agentic architecture](Access-Ops_Architecture.md#4-agentic-architecture-documented-alternative) documents the proposed flow; it is not a runtime feature.

## 6. Traditional vs Agentic Comparison

| Consideration | Implemented deterministic workflow | Proposed hybrid with agentic intake |
| --- | --- | --- |
| Risk/authorization | Explicit policy and reviewer checks | Same checks, plus protection against misleading intake output |
| Ambiguity | Requires listed choices or human clarification | Can interpret wording and ask contextual questions |
| Predictability | Repeatable policy and state behavior | Authorization stays repeatable; extraction may vary |
| Auditability | Identity, policy version, decisions, and actions | Adds model, context, output, and validation records |
| Employee experience | Direct form with clear required fields | Natural conversation, potentially fewer corrections |
| Maintenance | Policies, directory, workflow, and integrations | Also prompts, approved knowledge, and evaluations |
| Implementation time | Smaller bounded build | Additional integration and assessment work |
| Volume | Fits a modest, stable catalog | More attractive when varied intake creates substantial work |
| Cost | No runtime model expense | Model usage plus evaluation and monitoring effort |
| Operational value | Automates routing and validated fulfillment | Could additionally reduce intake clarification |

I chose the deterministic workflow because the assumed volume and bounded catalog support predictable structured data at low operational cost. That is a working judgment, not measured evidence that “40-50 requests per week means a form is sufficient.” The scenario's figure spans IT categories, and volume alone cannot reveal employee friction.

I would revisit the choice after measuring incomplete submissions, clarification messages, employee abandonment, intake time, and request variety. If people struggle to select the right access despite good form design, a hybrid could be valuable even at modest volume. Conversely, a conversational layer would add little if approval ownership or provider failures cause most delays.

## 7. What I Built and Why

An employee selects an application and access level, supplies a business reason, and chooses a duration. The trusted directory supplies department, title, manager, and employment status. For example, an eligible Engineering employee's GitHub Read request follows an automatic policy; GitHub Write requires the configured manager.

The policy determines whether to auto-approve, wait for one reviewer, enter a configured exception, or stop. A Product Manager's GitHub Write request follows the configured exception path to one application owner. Valid intake without a matching policy becomes `MANUAL_REVIEW`; explicit rejection and unsupported intake grant nothing.

When authorization is available, the workflow revalidates it and persists audit intent before invoking Mock Okta. Stable operation keys and unique grant identity prevent duplicate grants. The provider result and successful completion persistence determine whether the request becomes `ACTIVE`. Employee feedback explains the outcome and next step, while IT can inspect request history and supported mock inbox deliveries.

If the provider reports an explicitly transient failure, the workflow makes at most three immediate attempts total. Other failures stop without blind retries. Failed provisioning preserves approval history and directs the employee to IT with the existing request ID.

Operations derives request age from persisted timestamps and compares it with the illustrative 24-hour target. This display is read-only: it does not change authorization, approval, expiration, or workflow state. I included it to expose waiting work without implying an implemented SLA enforcement system.

## 8. Priorities and Explicit Exclusions

I prioritized authorization correctness, safe failure behavior, auditability, clear employee feedback, maintainability, and demo reliability, in that order. The decisive tests ask whether access can occur without authority, whether failures are represented honestly, and whether someone can reconstruct what happened.

I intentionally excluded production Slack and Okta connections, SSO/authentication, offboarding automation, and general IAM. Those require real organizational identity, integration contracts, and lifecycle ownership that synthetic data cannot establish.

I also excluded multiple approval chains, request-level deduplication, automated approval expiry, a scheduler, retry queues, distributed transactions, concurrency guarantees, and a full SLA engine. The local prototype assumes serial processing. These boundaries kept the implementation small enough to inspect and explain while exercising consequential failure cases.

AI is excluded from the authorization path. Its absence does not prevent a later intake experiment because the workflow accepts structured requests independently of how those fields were collected.

## 9. Tradeoffs and Limitations

**Intake and aging.** A structured form may create more friction than conversation. The 24-hour target is illustrative, and pending approvals have no age-based TTL. These were acceptable demonstration boundaries because the prototype establishes workflow behavior without inventing company policy. Production should measure completion and clarification, agree response and approval targets, and implement approved reminder, escalation, and expiry rules.

**Recovery.** Terminal `PROVISIONING_FAILED` requests have no automatic recovery workflow. Bounded immediate retries apply only to explicitly transient provider failures. If a provider mutation succeeds but the final local write fails, the request can remain `PROVISIONING`; the system does not report successful completion. Manual reconciliation is required. Production should verify actual provider state and recover through durable, audited operations rather than ask employees to submit duplicates.

**Persistence and concurrency.** Workflow and provider SQLite stores are not distributed transaction-safe. Their separate transactions make the failure boundary visible, which is useful for this local exercise, but cannot guarantee atomic completion across systems. Production needs reconciliation, durable work coordination, and tested concurrency behavior. A generic notification retry would not resolve an uncertain grant; no such delivery retry mechanism exists here.

**Authority and administration.** Reviewer authority is trusted configuration, and local authentication/admin identity is simulated. This lets the prototype demonstrate backend restrictions without claiming real authentication. Production should source privileged authority from approved RBAC or application ownership and restrict who can change it.

**Manual review and duplicates.** A `MANUAL_REVIEW` request requires policy investigation/correction and resubmission; it cannot be approved in place. Separate submissions may create duplicate request records even though duplicate grants are prevented. These choices keep policy authority explicit and the local implementation understandable. A pilot could justify a governed resolution flow and request deduplication after defining their semantics.

**Data and lifecycle.** Business reasons have guidance but no automated sensitive-data redaction. There is no offboarding integration, and expiration runs only on explicit invocation. Synthetic data and supervised local use make these acceptable prototype boundaries. Production would require access-controlled retention, appropriate redaction, reliable scheduling, and assigned lifecycle ownership. Failed removals need operational follow-up because the actual grant may remain.

## 10. What I Would Change With More Time

I would prioritize the next work in this order, validating each investment with IT and Security:

1. Replace Slack, trusted identity, and Okta mocks with authenticated integrations for one pilot application, including confirmation of actual grant and removal behavior.
2. Agree real SLA and approval TTL policy, then add the required aging, reminders, escalation, and reliable expiration scheduling.
3. Source privileged reviewer authority from authoritative RBAC/application ownership and govern administrative changes.
4. Add reconciliation and recovery for uncertain provider/workflow outcomes, including interrupted completion writes and terminal failures.
5. Measure intake friction, clarification rate, and employee completion against the existing process.
6. If those results justify it, test conversational AI intake while preserving every deterministic authorization boundary.
7. Complete production observability, retention, and security controls, with launch-critical controls brought forward before any real pilot.

This is a prioritization framework, not a commitment to build every feature. Actual integration gaps or security requirements could change the order; intake AI should compete on demonstrated value.

## 11. Non-Technical Maintenance and Handoff

A nontechnical owner can use the bounded local Configuration experience to maintain applications, choose supported access levels during onboarding, edit existing policies, and assign configured reviewers. Existing policy application/access identity stays fixed. Supported edits include eligibility, decision, reviewer routing, duration limits, and enabled status, with validation and review before save.

Policy changes increment versions and retain audit history. They affect future evaluation and pending-request revalidation without rewriting historical decisions or existing grants. Application disable stops new intake; it does not revoke access. Active Access reads actual mock grants and supports confirmed manual removal with a human reason.

Privileged reviewer assignment, elevated-access policy, and application lifecycle changes are security decisions. I would establish ownership and escalation rules before handing them over, rather than describe them as casual configuration. The [Maintenance Guide](Maintenance_Guide.md) provides procedures, failure guidance, and engineering escalation boundaries. The local role checks are demonstrations, not substitutes for production administrative authentication.

## 12. AI Tools Used

I used Codex / ChatGPT for brainstorming, architecture critique, implementation scaffolding, test generation and review, documentation, UI iteration, and QA/repository review. Those are the tool names supported by the project record; I am not attributing work to an unverified model version.

AI does not run in the application and did not independently authorize any access. I reviewed the generated work and retained responsibility for architecture, implementation, security boundaries, and final decisions. The [AI Usage Log](AI_Usage_Log.md) records the assistance and limitations in more detail without claiming line-by-line authorship that repository history cannot prove.

## 13. Where AI Helped, Where It Fell Short, and One Overrule

### Where AI helped

AI accelerated repetitive implementation, tests, and documentation. It helped surface edge cases around reviewer identity, duplicate operations, expiration, and persistence failures, and provided a useful challenge to architecture and failure-state assumptions. Its greatest value was helping turn explicit decisions into inspectable code and test scenarios.

### Where it fell short

Suggestions needed scope control because additional features or complexity could distract from the vertical slice. Generated tests and documentation still needed comparison with actual behavior. Development artifacts also required manual inspection: I found and removed an unrelated file containing captured terminal/diff output. The record does not establish which tool created it, so I would not attribute that artifact more specifically.

### One overrule

AI initially leaned toward rigid department eligibility that would reject an out-of-department request. I challenged that with a Product Manager who could legitimately need GitHub Write. I chose a controlled, configured exception-review path with exactly one authorized human reviewer. The requester does not gain authority by describing a business need, and AI does not decide the exception. This is the decision supported by the final AI Usage Log: preserve a legitimate human exception path without relaxing deterministic authorization.

## 14. Final Result

The prototype proves the highest-risk part of this workflow first: whether access actions follow explicit policy, reviewer boundaries, provider confirmation, and durable history. It provides structured requests, policy enforcement, approval and exception paths, mock provisioning, failure visibility, auditability, temporary-access handling, and basic aging visibility.

I intentionally kept consequential access decisions deterministic. AI remains a plausible future improvement to intake, not an authorization authority. Moving beyond this local demonstration would require real identity and integrations, governed ownership, reliable lifecycle processing, and recovery controls for uncertain outcomes. Those are the foundations I would validate before claiming operational savings or expanding scope.

## Supporting documentation

- [README: setup and demo](../README.md)
- [Architecture and approach comparison](Access-Ops_Architecture.md)
- [Non-Technical Maintenance Guide](Maintenance_Guide.md)
- [AI Usage Log](AI_Usage_Log.md)
