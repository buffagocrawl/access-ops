# Written Submission Coverage

This map covers the 13 requested written-submission areas. The implementation and tests are the source of truth for implemented behavior; the Implementation Contract controls scope.

| Area | Submission coverage | Primary evidence |
| --- | --- | --- |
| 1. Problem | Manual software access intake, routing, approval, provisioning, expiration, and audit work are the focused problem. | `Overall_Scope_and_Decisions.md` |
| 2. Scope | The core demonstrated/tested catalog has five software applications; narrow Day 4 local ownership extensions do not make this a general IAM platform. Hardware, FAQs, real integrations, and production authentication are excluded. | `Implementation_Contract.md`, `README.md` |
| 3. Request-category choice | Software access was selected after comparison with hardware and FAQs. | `Project_Timeline.md`, `Overall_Scope_and_Decisions.md` |
| 4. Traditional architecture | Structured intake, deterministic policy, workflow state, audit, and mock provider form the implemented control plane. | `Access-Ops_Architecture.md` |
| 5. Agentic alternative | AI may improve future intake only; all consequential decisions remain deterministic. No runtime AI is implemented. | `Access-Ops_Architecture.md` |
| 6. Decision rationale | Deterministic automation fits bounded, consequential access requests and is more testable and auditable for this scope. | `Access-Ops_Architecture.md` |
| 7. Trust and authorization | Trusted directory attributes, exact policy matching, one reviewer maximum, self-review prevention, revalidation, and pre-action audit writes protect access actions. | `Technical_Design.md`, tests |
| 8. Workflow and exceptions | Automatic, normal approval, configured exception review, rejection, manual review, provisioning, expiration, and revocation paths are explicit. | `README.md`, workflow tests |
| 9. Failure and recovery | Valid no-policy intake persists as `MANUAL_REVIEW`; provider success is required for active/revoked states; only transient failures receive immediate bounded retries. | `README.md`, `Phase_8_Acceptance_Audit.md` |
| 10. Data, audit, and integrations | CSV provides trusted local configuration; separate SQLite stores hold workflow/audit data and mock provider grants; integrations are clearly mocked. | `Technical_Design.md`, `README.md` |
| 11. Testing and evidence | Automated tests cover normal, approval, exception, unauthorized, duplicate-grant, failure, expiration, revocation, UI, and administration behavior. | `Phase_8_Acceptance_Audit.md`, `tests/` |
| 12. Operations and maintenance | IT Operations supports inspection, policy maintenance, current-access removal, and configuration audit history within narrow mocked owner rules. | `Maintenance_Guide.md`, `Implementation_Contract.md` |
| 13. AI disclosure and delivery process | The AI Usage Log distinguishes verified assistance, known limitations, and Branden's actual design decision; the timeline records the Thursday through Sunday work. | `AI_Usage_Log.md`, `Project_Timeline.md` |

The scenario explicitly identified lack of SLA visibility. I added a minimal derived 24-hour demo aging indicator in the existing Operations view. It is read-only, based on persisted timestamps, and does not alter workflow behavior. The 24-hour target is illustrative, not a Customer.io policy; production SLA definitions, reminders, escalation, expiration, and reporting remain future work.

## Implementation truth statements

- A valid request with no matching enabled policy is persisted as `MANUAL_REVIEW`, routed to the mock IT Operations inbox, and cannot authorize or provision access.
- Separate duplicate submissions may create separate request records. Duplicate access grants are prevented by provider idempotency and unique grant identity.
- Only transient provider failures receive at most three immediate attempts total. No delay, backoff, scheduler, or automatic terminal-failure recovery is implemented.
