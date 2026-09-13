# Phase 8 acceptance-test audit

Audit date: September 12, 2026. Scope: the 15 acceptance criteria under `Implementation_Contract.md`, including the two explicitly requested behavior fixes. No access policy CSV, dependency, or unrelated architecture was changed. Existing uncommitted Phase 8 tests were preserved and updated only where the requested behavior changed.

## Implemented corrections

1. Revocation failure commits its existing failed state and audit event, then sends an actionable notification using the extended local notification module. Mock delivery persists in SQLite and targets `Configuration.it_operations_recipient` (default `#it-operations`). The IT Operations tab exposes the inbox. Original approvals/access history remain unchanged and unremoved access is never reported revoked.
2. A known active employee requesting supported application/access and valid duration with no matching policy now creates a `MANUAL_REVIEW` request, a routing audit event, and a detailed mock IT inbox message. No policy is fabricated: the existing non-null request columns use empty policy ID/version zero, while the audit policy version is null. The configured IT channel receives manual investigation rather than an invented access approver. Unknown/inactive employees, unsupported applications/access, explicit reject policies, and ambiguous policy matches remain safely rejected.

Focused acceptance tests:

- `tests/test_workflow.py::test_injected_revoke_outcome_preserves_durable_history` (failure cases for both normal and exception approval): configured recipient, actionable delivery surviving database reopen, retained failure/access/history, and no repeated removal or notification.
- `tests/test_workflow.py::test_no_policy_match_requires_it_review_without_authorization`: shipped Product employee/GitHub Read no-match scenario, durable manual request and routing, requester/reviewer messaging, absent authorization, and blocked processing/approval.

Additional checks prove manual-routing audit failure creates neither a request nor delivery, and notification failure cannot undo a committed revocation failure. Existing safety tests were retained; assertions for no-match rejection were replaced with stricter routing/state/delivery assertions to reflect the requested change. No cases were removed.

## Final acceptance matrix

`W` means `tests/test_workflow.py`; `A` means `tests/test_app.py`. PASS evaluates implemented mock behavior, not real external delivery.

| Criterion | Test name | File | What the assertion proves | PASS/FAIL |
| --- | --- | --- | --- | --- |
| Valid auto-approval | `test_golden_path_and_committed_order` | W | Committed automatic authorization before provider entry; confirmed ACTIVE grant. | PASS |
| Valid human approval | `test_write_pending_survives_reopen_without_provisioning`; `test_manager_approval_commits_revalidation_before_mock_grant` | W | No access while pending; designated approval and revalidation commit before confirmed access. | PASS |
| Incorrect reviewer rejected | `test_unauthorized_approval_preserves_pending[UDEMO002]` | W | Wrong reviewer rejected and audited; no provider call. | PASS |
| Self-approval rejected | `test_unauthorized_approval_preserves_pending[UDEMO001]` | W | Requester rejected and audited; no provider call. | PASS |
| Inactive employee rejected | `test_invalid_intake_has_durable_deterministic_audit` (`employee_id=UDEMO004`) | W | Rejected before policy execution; durable audit, no request/grant. | PASS |
| Unsupported application handled safely | `test_invalid_intake_has_durable_deterministic_audit` (`application=Github`); `test_invalid_intake_never_calls_provider` (`application=Unknown`) | W | No fuzzy catalog correction, policy inference, or provider call. | PASS |
| Unsupported access level handled safely | `test_invalid_intake_has_durable_deterministic_audit` (`access_level=write`); `test_invalid_intake_never_calls_provider` (`access_level=Owner`) | W | Unsupported roles never become permission. | PASS |
| Exception request routed correctly | `test_exception_pending_and_reviewer_details_survive_reopen`; `test_exception_approval_commits_audit_before_mock_okta` | W | Configured single owner receives the exception; approved/audited path grants access. | PASS |
| Duplicate request does not create duplicate access | `test_existing_access_is_confirmed_without_second_grant` | W | Two submissions, one grant; second outcome ALREADY_EXISTS. | PASS |
| Duplicate approval is harmless | `test_duplicate_approval_preserves_outcome_and_history` (all four cases) | W | Outcome, lifecycle fields, prior approval/history, and grants survive replay; no reprovisioning. | PASS |
| Provisioning failure preserves approval | `test_injected_grant_outcome_and_committed_approval` (`fail_grant=True`, all three paths) | W | Approval remains durable alongside explicit provisioning failure and no grant. | PASS |
| Successful temporary expiration | `test_expiration_audit_removal_and_repeat_survive_reopen` | W | Removal occurs at expiry, is confirmed/audited/durable, and is not repeated. | PASS |
| Revocation failure alerts IT | `test_injected_revoke_outcome_preserves_durable_history` (`fail_revoke=True`, normal and exception paths) | W | Durable delivery to the configured mock IT channel includes employee/access, request/operation ID and verify/remove guidance; original history, failure state and grant survive reopening and repeat expiration. | PASS |
| No policy match goes to manual review | `test_no_policy_match_requires_it_review_without_authorization`; `test_missing_or_ambiguous_policy_is_audited_and_closed` | W | Valid unmatched requests persist as MANUAL_REVIEW and route details to the configured mock IT inbox; no policy is invented and process/approval cannot grant access. Removed/disabled/unmatched rules route; ambiguous rules still reject. | PASS |
| Audit failure prevents provisioning | `test_pre_audit_failure_rolls_back_and_blocks_provider`; `test_approval_audit_failure_blocks_grant`; `test_exception_audit_failure_blocks_provider`; `test_retry_audit_failure_blocks_next_provider_call` (`grant`) | W | Required pre-action audit failure blocks the initial or next provider action. | PASS |

## Remaining boundaries and ambiguities

- Manual review means a durable request routed to the configured IT Operations channel for investigation/configuration correction. It is not a new exception authorization policy. No in-place approve/provision or completion action was added for policy-less requests; after IT establishes valid policy, a new request uses the existing workflow. This keeps eligibility deterministic and avoids inventing an approver. This interpretation is explicit in requester and reviewer messaging.
- Notifications are actual persisted **mock** deliveries, visible locally; real Slack remains out of scope. Notification delivery errors do not roll back committed request/audit state; no new delivery retry mechanism was added.
- Duplicate submissions still create separate request rows with one directory grant. Duplicate approval remains rejected/audited without reprovisioning; activity timestamps may change.
- Audit failure before a consequential action blocks that action. A completion-write failure after a provider action cannot undo the provider operation; cross-database atomicity and crash recovery remain out of scope.
- No ambiguity remains about either original gap: mock IT delivery and persistent manual routing are now implemented. Manual review resolution and production notification delivery remain the explicit boundaries above.

## Verification and changed files

Final full suite: `.\.venv\Scripts\python.exe -m pytest -q` ? **334 passed, 0 failed** in 42.30 seconds. No skipped or expected-failure cases. The first implementation run had 331 passed/1 failed because a test incorrectly expected manual review for an explicit reject policy; that expectation was corrected without changing rejection behavior.

Focused acceptance rerun: **60 passed, 0 failed, 135 deselected** in 9.94 seconds. All **15/15 criteria PASS**. The full suite additionally covers normal denial, exception denial, notification-failure durability, and manual-review audit failure.

Reproduction command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_workflow.py -k 'golden_path_and_committed_order or write_pending_survives_reopen or manager_approval_commits or unauthorized_approval_preserves_pending or invalid_intake_has_durable or invalid_intake_never or exception_pending_and_reviewer or exception_approval_commits or existing_access_is_confirmed or duplicate_approval_preserves or injected_grant_outcome or expiration_audit_removal or injected_revoke_outcome or no_policy_match_requires or missing_or_ambiguous or pre_audit_failure or approval_audit_failure or exception_audit_failure or retry_audit_failure'
```

`git diff --check` passed.

Production files changed in this fix:

- `app.py`
- `src/access_ops/config.py`
- `src/access_ops/database.py`
- `src/access_ops/models.py`
- `src/access_ops/notifications.py`
- `src/access_ops/workflow.py`

Test files changed: `tests/test_workflow.py` only.

Documentation: `README.md`, `Planning/Phase_8_Acceptance_Audit.md`.

No commits or pushes were made.
