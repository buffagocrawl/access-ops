# Day 4 UI review

## Starting observations

The baseline Streamlit app rendered all three tabs, but relied on long native form rows, raw database-oriented operations tables, sparse reviewer context, and no concise demonstration guide. Baseline screenshots were captured at 1440px wide after a representative auto-approved request. The initial full suite passed: **334 passed in 59.47s**.

The review used actual local screenshots of all three tabs at a 1440px presentation viewport. Scores are advisory assessments from three independent review perspectives, not test evidence or a release criterion.

| Round | CFO | AI / Tech Ops | Product / Design | Overall composite |
| --- | ---: | ---: | ---: | ---: |
| 1 | 88.0 | 90.4 | 88.0 | 88.8 |
| 2 | 92.2 | 94.6 | 93.2 | 93.3 |
| 3 | 95.4 | 96.2 | 95.8 | 95.8 |
| 4 | 96.4 | 96.2 | 96.6 | 96.4 |
| 5 | 96.0 | 96.0 | 96.0 | 96.0 |

## Material improvements

- Added a small shared visual system with a restrained navy, teal, slate, and semantic-state palette.
- Added concise guide sections on all three screens and a clear `Mock Slack UI` boundary.
- Added safe Employee scenario prefills. They only fill the existing form; submission still invokes the unchanged workflow.
- Distinguished configured exception review from policy-less manual IT review in both copy and persisted-status feedback.
- Made acting reviewer, authorized reviewer, self-approval protection, revalidation, mock identity, mock provider, and no-runtime-AI boundaries explicit.
- Replaced raw operations status presentation with readable, color-coded states; added request references, focused follow-up counts, failure consequences, formatted expiration, and expandable audit/history detail.
- Made the existing unsupported normal-denial limitation explicit on the action itself. Exception denial remains supported by the unchanged backend.
- Added UI tests proving prefills do not submit and manual review is rendered as a policy hold rather than a generic system error.

## Recommendations intentionally rejected

- Implementing normal approval denial: rejected because it changes frozen approval workflow behavior.
- Disabling or hiding the unsupported normal-denial control: rejected because the local demo must retain the existing capability and honestly expose its backend limitation.
- Adding click-only failure injection, expiration scheduling, or resolution tooling: rejected because those would alter the application surface and workflow scope. Existing harness mechanisms are documented as such.
- Replacing native Streamlit controls and tables with a custom front end: rejected because the additional machinery would not improve the deterministic workflow and would undermine the requested focused pass.

## Final limitations

- The final review did not reach the aspirational 98 target. Reviewers consistently cited the frozen ordinary-denial limitation, native Streamlit widgets, and desktop scrolling for the long employee/operations experiences.
- Failure injection and expiration processing remain existing local test/service-harness mechanisms, not click-only UI controls or a scheduler.
- Screenshots show presentation; authorization and audit guarantees are evidenced by the automated workflow tests and final logic-guardian review.
