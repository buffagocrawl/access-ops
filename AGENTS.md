\# Access Ops — Codex Instructions



This repository is a focused Customer.io interview take-home project.



Before making architectural or implementation decisions, read:



1\. `Planning/Overall\_Scope\_and\_Decisions`

2\. `Planning/Blueprint.md`

3\. `Planning/Implementation\_Contract.md`



`Planning/Implementation\_Contract.md` defines the locked implementation scope.



If documentation appears inconsistent, do not silently choose or expand scope. Prefer the Implementation Contract for build scope and flag material conflicts.



\## Core principles



\* Build the smallest understandable solution that satisfies the implementation contract.

\* Prefer deterministic behavior over unnecessary abstraction.

\* Do not add frameworks, infrastructure, integrations, or AI features merely to make the project appear sophisticated.

\* Consequential access actions must be deterministically validated.

\* A request may have at most one human approver.

\* Treat mocked integrations clearly as mocks.

\* Keep code simple enough for the project owner to explain line by line.

\* Make routine policy behavior configuration-driven where practical.

\* Fail safely and preserve auditability.

\* Never mark provisioning successful unless the mocked provider confirms success.



\## Before considering work complete



\* Run the automated test suite.

\* Fix failures rather than weakening tests.

\* Verify normal, approval, exception, unauthorized, duplicate, provisioning-failure, expiration, and revocation-failure scenarios.

\* Keep documentation synchronized with any intentional implementation changes.

\* Do not implement items explicitly listed as out of scope.



