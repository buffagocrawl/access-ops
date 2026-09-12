# Access Ops

Access Ops is a focused prototype for software access requests. It addresses the manual intake, routing, approval, provisioning, expiration, and audit work that can surround employee access requests.

## Scope and approach

The narrow scope is software access requests through a Slack-style structured workflow. The selected implementation approach is deterministic, traditional automation: trusted employee attributes and human-readable policy configuration drive repeatable validation, routing, approval, provisioning, and revocation decisions.

An agentic natural-language intake architecture is documented for comparison and possible future use. It is not implemented, and no AI API calls are part of the prototype.

## Status and behavior boundaries

### Implemented behavior

None yet. This repository currently contains the planning documents and initial repository-hygiene files; application code and tests have not been started.

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
├── Planning/       Architecture, scope, blueprint, and implementation decisions
├── .env.example    Safe local configuration template
├── .gitignore      Local and generated-file exclusions
├── README.md       Project overview and status
└── requirements.txt Dependency placeholder for future implementation
```

## Development and setup

Implementation setup instructions will be added when the application structure, dependencies, and runnable commands are established. Until then, there is no application command to run. Future local development is expected to use a Python virtual environment and synthetic/mock data defined by the implementation.

Do not commit credentials, tokens, passwords, API keys, or local `.env` files. The `.env` file is gitignored; use `.env.example` as the safe template.

## Planning references

The [`Planning/`](Planning/) directory is the source of truth for architecture, scope, implementation boundaries, assumptions, workflow states, and the deterministic-versus-agentic decision.

