# Access Ops

Access Ops is a focused prototype for software access requests. It addresses the manual intake, routing, approval, provisioning, expiration, and audit work that can surround employee access requests.

## Scope and approach

The narrow scope is software access requests through a Slack-style structured workflow. The selected implementation approach is deterministic, traditional automation: trusted employee attributes and human-readable policy configuration drive repeatable validation, routing, approval, provisioning, and revocation decisions.

An agentic natural-language intake architecture is documented for comparison and possible future use. It is not implemented, and no AI API calls are part of the prototype.

## Status and behavior boundaries

### Implemented behavior

The initial configuration foundation contains synthetic employees and explicit access policies in `config/`. Application code, configuration loading/validation, and tests have not been started; these files do not enforce access decisions yet.

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
|-- config/         Synthetic trusted employees and access policies
├── Planning/       Architecture, scope, blueprint, and implementation decisions
├── .env.example    Safe local configuration template
├── .gitignore      Local and generated-file exclusions
├── README.md       Project overview and status
└── requirements.txt Dependency placeholder for future implementation
```

## Development and setup

### Demo configuration conventions

`config/employees.csv` is the trusted synthetic directory. All names, Slack IDs, and `example.com` email addresses are demo data, not Customer.io employee information. Department, title, manager, and `active`/`inactive` status must come from this file, never requester input. Olivia is the top-level manager and has no manager herself; future requests needing an unavailable manager must stop safely for IT review.

`config/access_policies.csv` contains the five-application catalog. The following conventions define data for the future generic evaluator; no evaluator is implemented yet:

- Match enabled rows by exact application/access level and trusted department/title. Semicolons separate allowed values; `*` means any value in that field. Department and title conditions both apply. `eligible_departments` identifies which employees a row applies to, including exception and rejection rows; it does not itself grant eligibility. There is no row-order precedence. Zero or multiple matches must authorize nothing and require IT review.
- `AUTO_APPROVE` and `REJECT` use `approver_type=NONE` and a blank ID. `MANAGER` uses a blank ID because the one reviewer comes from the requester's `manager_slack_id`. `APPLICATION_OWNER` and `IT_SECURITY` each identify exactly one reviewer through `approver_id`. Reviewer availability and self-approval checks remain required future workflow controls.
- Booleans are `true`/`false`. `max_duration_days` caps temporary access only; permanent access requires `permanent_allowed=true`. Rejection rows allow neither and use a zero-day limit. Standard temporary access is capped at 30 days, GitHub exceptions and Admin at 7 days. A 90-day request is not authorized by these rows. Duration failures must not fall through to a more permissive rule.
- `policy_version` starts at `1` and should increase when a row changes. `eligible_titles` preserves the Blueprint's explicit Engineering-leadership restriction on GitHub Admin; other rows use `*`, so titles do not otherwise imply trust.
- Alice demonstrates Engineering GitHub Read auto-approval and Write manager approval. Paul and Sarah demonstrate temporary GitHub Write exception review directly by Grace. Mike demonstrates temporary GitHub Admin review by Ivan. Farah demonstrates an explicit GitHub Write rejection. Ian provides an inactive-employee negative case that must be blocked before policy evaluation.
- Figma View and Notion Standard are automatic for active employees; Figma Editor is automatic for Product/Design. Salesforce Standard requires the Sales/Customer Success employee's manager. Snowflake Read requires the Data/Engineering employee's manager; Write requires Dana and is temporary only. Standard non-rejection rows permit permanent access except Snowflake Write and the GitHub exception/Admin rows.

These are prototype policy assumptions, not Customer.io policies. Design and Customer Success are configured for future synthetic records without requiring additional employees now. The Blueprint lists several admin roles and UI features; the locked scope limits this foundation to one elevated example (GitHub Admin), with no UI. Unmatched combinations remain manual-review cases, not implicit approvals or implicit exception grants.

Implementation setup instructions will be added when the application structure, dependencies, and runnable commands are established. Until then, there is no application command to run. Future local development is expected to use a Python virtual environment and synthetic/mock data defined by the implementation.

Do not commit credentials, tokens, passwords, API keys, or local `.env` files. The `.env` file is gitignored; use `.env.example` as the safe template.

## Planning references

The [`Planning/`](Planning/) directory is the source of truth for architecture, scope, implementation boundaries, assumptions, workflow states, and the deterministic-versus-agentic decision.
