# Changes

## 3.0.0 — read-only role-bound execution

- Replaced directory-wide hot tool discovery with an explicit built-in registry.
- Added per-worker tool allowlists and a separate, default-off mutation opt-in.
- Added an execution-time write denial inside write_file.
- Bound each configured worker's role, model, system prompt, and tools to its
  OpenRouterAgent.
- Removed case-specific facts, legal conclusions, probabilities, automatic
  escalation paths, and claimed deadlines from runtime defaults and documentation.
- Added bounded HTTP, per-agent, and orchestration timeouts plus cancellation of
  pending futures.
- Classified generated results as model_inference / pending_review with source
  expectations.
- Required synthesis to preserve uncertainty, disagreements, and evidence gaps.
- Added standard-library policy tests that make no external API calls.
