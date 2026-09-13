# AI Usage Log

## Summary

Codex / ChatGPT assisted development of this local prototype across architecture discussion, scaffolding, implementation help, tests, documentation, and UI review. The running prototype has no runtime AI dependency. Branden retained final judgment and responsibility for scope, security boundaries, review, and submission decisions.

This log records the work at a task level. Repository history can show that changes occurred, but it cannot prove which person or tool authored individual lines. Attribution below is therefore intentionally conservative.

| Tool used | Task | Useful result | Limitation or bad suggestion | Branden review/modification | Final decision |
| --- | --- | --- | --- | --- | --- |
| Codex / ChatGPT | Architecture and scope discussion | Clarified the deterministic control plane and documented an agentic intake alternative. | AI initially leaned toward rigid department eligibility that would simply reject an out-of-department request. | Branden challenged that with the Product Manager → GitHub Write example and chose a controlled, configured exception-review path. | The exception reviewer may approve one configured exception; the LLM does not authorize the request. |
| Codex / ChatGPT | Scaffolding and implementation assistance | Helped build the small Python package, CSV configuration, SQLite persistence, policy engine, workflow, mock provider, and Streamlit UI. | Generated work still required execution, inspection, and correction; mock integrations do not prove production integration behavior. | Branden kept the implementation bounded to the contract and reviewed behavior against the source code and tests. | Keep authorization, approval, provisioning, revocation, policy changes, and retries deterministic. |
| Codex / ChatGPT | Tests and failure-path work | Helped develop tests for normal approval, exception review, rejection, unauthorized actions, duplicates, provider failures, expiration, revocation failure, persistence, and UI/admin paths. | Test expectations and generated assertions can be wrong; acceptance work identified an incorrect expectation about explicit rejection and it was corrected while preserving rejection behavior. | Branden used the test suite and acceptance matrix as evidence, not as a substitute for code review. | Fail safely, preserve audit history, and require provider confirmation before claiming success. |
| Codex / ChatGPT | Documentation and handoff | Helped draft the README, architecture comparison, technical design, maintenance guide, and scope records. | Documentation can lag implementation and can overstate historical attribution or performance. | Branden’s final pass reconciles claims with the current implementation, labels mocks and future state, and keeps unsupported metrics as targets or measurement plans. | Documentation describes a local prototype, not a production system or measured outcome. |
| Codex / ChatGPT | UI review | Suggested presentation improvements, concise scenario guidance, and clearer mocked boundaries. | Visual scores are subjective advisory feedback; suggestions that expanded scope or altered deterministic workflow behavior were not adopted. | Branden retained the final UI and scope decisions. | UI remains a thin local demonstration interface over the backend workflow. |

## Secondary review example: generated artifact

During early scaffold work, an accidental file named `t` containing captured `git diff`/terminal output entered repository history. Branden later noticed the unexplained artifact during review, inspected it, confirmed it was unrelated to application behavior and contained no needed project content, and removed it from the current tree. This is evidence that generated development output required manual inspection. Git history does not independently prove which tool created the file, and removing it from the current tree did not remove it from history.

## Boundaries

AI assisted development and review only. No LLM authorizes, approves, rejects, provisions, revokes, changes policy, selects a consequential remediation, or participates in the running authorization path. The prototype uses no AI API at runtime.
