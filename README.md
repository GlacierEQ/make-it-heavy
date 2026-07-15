# Make-It-Heavy

Make-It-Heavy is a bounded, read-only multi-agent research runner using
OpenRouter-compatible models. It distributes a question across role-bound
workers and returns source-oriented model inference for human review.

It is not an autonomous legal operator. It does not file, publish, message,
purchase, delete, or modify external systems. Its output is not a verified fact,
court finding, legal conclusion, probability assessment, or deadline calculation.

## Safety and correctness model

- Every worker receives its configured role, model, system prompt, and tool allowlist.
- Tools come from an explicit built-in registry. Directory scanning and hot loading
  are not used.
- File mutation is disabled by default. Enabling write access requires both
  listing write_file and setting tools.mutation_enabled to true.
- OpenRouter requests, each agent run, and the overall worker pool have separate
  bounded timeouts. Pending futures are cancelled where Python permits cancellation.
- Results are labeled model_inference and pending_review.
- Factual assertions are expected to carry a URL or precise document citation.
- Synthesis must preserve contradictions, missing evidence, and uncertainty.

## Setup

Use Python 3.9 or newer, install the small runtime dependency set, and provide
the API credential through the environment:

    python -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    export OPENROUTER_API_KEY="..."

Run one worker:

    python main.py

Run the bounded four-worker orchestrator:

    python make_it_heavy.py

## Worker configuration

Each apex_agents entry in config.yaml must include:

- role
- model
- system_prompt
- allowed_tools

The included configuration defines source research, claim auditing,
counter-analysis, and review planning. These are research roles, not authority to
act.

## Tool policy

The built-in registry contains search_web, calculate, read_file, write_file, and
mark_task_complete. Each worker sees only its allowlisted subset.

write_file is denied unless the operator makes both changes below:

    tools:
      allowlist: [write_file]
      mutation_enabled: true

That opt-in permits local UTF-8 file writes only. It does not authorize external
actions.

## Validation

Run the dependency-minimal policy tests with:

    python -m unittest discover -s tests -v

The tests use the standard library test runner and make no external API calls.
