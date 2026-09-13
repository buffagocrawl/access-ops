# Project Timeline

## Thursday: scope and problem selection

- Understood the problem and compared the three request categories: software access, hardware/equipment, and general IT FAQs.
- Brainstormed possible approaches and narrowed the scope to one small, explainable vertical slice.
- Selected software access requests because they make authorization, approval, provisioning, expiration, and auditability concrete.

## Friday: architecture and trust boundaries

- Fully designed both the deterministic/traditional and agentic architectures.
- Defined the authorization and trust boundaries: trusted directory data, deterministic policy, one human approver at most, pre-action audit persistence, and provider confirmation before success.
- Selected the deterministic workflow for implementation because access actions are consequential and the request shape is bounded.

## Saturday: implementation and tests

- Built the focused end-to-end vertical slice.
- Added configuration loading, policy matching, request and audit persistence, mocked provisioning and revocation, approval and exception paths, expiration, failure simulation, and the local UI.
- Added automated tests for normal, approval, exception, unauthorized, duplicate-grant, provider-failure, expiration, and revocation-failure behavior.

## Sunday: QA and handoff

- Performed QA and UI/usability polish.
- Completed documentation, both architecture diagrams, the non-technical maintenance guide, and the AI Usage Log.
- Performed the documentation consistency pass, including corrections for manual-review routing, duplicate submissions, and immediate bounded provider retries.
- Completed final README and cross-document verification.
