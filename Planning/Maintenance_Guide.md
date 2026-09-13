# Non-Technical Maintenance Guide

## What this guide covers

This is a local prototype. It uses mock Slack feedback, synthetic employee data, CSV configuration, and a mocked Okta directory stored in SQLite. It does not connect to production Slack, Okta, HRIS, or company SSO.

## Daily operations

Open **IT Operations** to review manual-review requests, provisioning failures, revocation failures, current mock access, and audit history.

- A `MANUAL_REVIEW` request means the request was valid but no enabled policy matched it. It is delivered to the mock IT Operations inbox for investigation. It cannot be approved or provisioned from that state. Establish or correct the policy, then have the employee submit a new request.
- A `PROVISIONING_FAILED` request has an approval or automatic path but the mocked provider did not confirm access. Do not claim access was granted. Use its request history to investigate.
- A `REVOCATION_FAILED` request may still have access. Verify the current grant under **Active Access** before taking another action.

## Review a request

In **Reviewer Inbox**, select the appropriate simulated reviewer and the assigned request.

- Approve only when the request is assigned to that reviewer.
- Reject only with a clear, nonempty human reason.
- A requester cannot approve their own request.
- An approval authorizes a provider attempt. It does not mean access is active until the mock provider confirms it.

## Change an existing policy

Only active mocked Operations Directors or IT Security Analysts in Operations can save policy changes through the application.

1. Open **IT Operations > Configuration**.
2. Select an existing policy row. Policy ID, application, and access level are fixed.
3. Update only the supported eligibility, decision, reviewer, duration, or enabled fields.
4. Select **Validate changes** and read the before/after summary and any validation errors.
5. Select **Save reviewed changes** only after the result is correct.

The application validates the complete catalog, checks reviewer routing, rejects stale reviews, increments the changed policy version, and records before/after audit history. Direct CSV editing bypasses that audit history and should be avoided for routine changes.

Policy changes affect future evaluation and revalidation. They do not rewrite historical requests, audit events, or existing grants.

## Maintain applications

The application catalog is stored in `config/applications.csv`. The supported local Configuration experience can onboard an application and soft-disable or re-enable one. Disabling prevents new requests only. It does not remove existing grants or delete history. Hard deletion is not supported.

## Remove current access

Use **IT Operations > Active Access** only after confirming the actual grant shown there.

1. Select the grant.
2. Enter a specific nonempty removal reason.
3. Check the explicit confirmation.
4. Select **Remove access**.

The removal intent is audited before the mock provider call. Only provider confirmation marks the source request revoked. If removal fails, the grant may remain and stays visible for investigation. A process owner can explicitly retry a failed manual removal after verifying current access; each attempt is audited.

## Retry behavior and duplicates

Only transient provider failures receive immediate bounded retries: at most three provider attempts total. There is no delayed retry queue, sleep, increasing delay, or exponential backoff.

Two identical submissions can create two request records. This is expected in the prototype. The safeguard is the mock provider's stable request operation keys and unique grant identity, which prevent duplicate access grants. Do not rely on request-level deduplication.

## When to escalate

Escalate to an engineer before changing code or files when:

- a policy change cannot validate;
- the requested outcome needs a new application, access level, approval model, or workflow state;
- an audit or completion result is uncertain after a configuration save;
- current access does not match the source request or provider grant;
- a provider failure or database error needs recovery beyond the documented UI/service action; or
- production authentication, real integrations, scheduled processing, or concurrent operation is required.

## Safe boundaries

Do not edit SQLite databases to change a request outcome. Do not delete historical request, grant, or audit data. Do not present mocked local feedback as a real Slack or Okta action. Keep the configuration directory and local data directory backed up before manual experimentation.
