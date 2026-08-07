# Make-It-Heavy

Make-It-Heavy is a write-capable, policy-bound multi-agent swarm runner for heavy analysis, repository improvement, and README star-map maintenance.

It distributes a request across role-bound workers, gathers independent outputs, synthesizes the result, and can write local UTF-8 artifacts when mutation is enabled in configuration.

## System Role

Make-It-Heavy is the parallel reasoning and artifact-drafting node in the GlacierEQ operator ecosystem.

It receives a mission, decomposes it into worker lanes, runs multiple model-backed agents, and produces reviewable artifacts such as analysis reports, README upgrades, repository maps, integration notes, and action plans.

It is designed to connect with:

- GitHub repositories
- README maintenance workflows
- Notion control-plane queues
- Smithery / MCP tool surfaces
- document automation systems
- browser automation systems
- repository graph indexes
- future worker-swarm dispatch layers

## Status

**ACTIVE / WRITE-CAPABLE LOCAL ARTIFACT MODE**

Current verified capability:

- multi-agent task decomposition
- parallel worker execution
- synthesis
- web search tool
- calculator tool
- local file read tool
- local file write tool
- persistent local swarm memory
- policy-bound tool allowlisting
- bounded request, worker, and connector timeouts
- built-in Smithery MCP connector with fail-closed transport/protocol handling

Current boundary:

- local file writes are supported through `write_file`
- swarm memory is available through `memory`
- the base configuration deliberately does **not** activate `smithery_mcp`
- Smithery requires exact `smithery.allowed_connections`, global and role tool allowlisting, and mutation opt-in before it can execute
- GitHub, Notion, Drive, Smithery, browser, or other external mutations are not performed merely because connector code exists; deployment policy must explicitly enable the relevant capability

## Star Map

```text
Repository Mission
        │
        ▼
Make-It-Heavy
        │
        ├── decompose mission
        ├── run parallel workers
        ├── preserve contradictions
        ├── synthesize findings
        ├── write local artifacts
        ├── recall/store local swarm memory
        └── produce integration-ready output
        │
        ▼
README Star Maps / Reports / Plans / Draft Artifacts
        │
        ├── GitHub library maintenance
        ├── Notion worker queues
        ├── opt-in Smithery MCP execution
        ├── MegaPDF / document pipelines
        ├── browser automation runners
        └── repository graph control plane
```

## Why This Exists

A single agent can miss context, flatten contradictions, or overfit to one interpretation.

Make-It-Heavy uses multiple role-bound workers so a mission can be split into source review, claim audit, counter-analysis, implementation planning, and artifact drafting.

For README maintenance, that means one repo can be analyzed as part of the larger system instead of being rewritten as an isolated project.

## Quick Start

Use Python 3.9 or newer.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_API_KEY="..."
python make_it_heavy.py
```

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Configuration

Primary configuration lives in `config.yaml`.

The base profile enables local artifact writes and memory but leaves the privileged Smithery connector disabled:

```yaml
smithery:
  api_key: ""
  namespace_url: "https://mcp.smithery.run/GlacierEQ"
  allowed_connections: []
  request_timeout: 60

tools:
  allowlist:
    - search_web
    - calculate
    - read_file
    - write_file
    - mark_task_complete
    - memory
  mutation_enabled: true
```

`write_file` writes local UTF-8 files atomically. It does not create external GitHub commits, send messages, publish documents, delete resources, purchase anything, or mutate connected systems.

To enable Smithery for a deployment, configure exact connection IDs in `smithery.allowed_connections`, add `smithery_mcp` to the global allowlist, and add it only to worker roles that need the capability. The connector is treated as privileged even when a particular remote operation is intended to be read-only because connected MCP servers may expose writes.

## Worker Configuration

Each `apex_agents` entry must include:

- `role`
- `model`
- `system_prompt`
- `allowed_tools`

The included workers are tuned for:

- source-backed research
- claim auditing
- counter-analysis
- review planning and artifact drafting

## Tool Policy

The built-in registry contains:

- `search_web`
- `calculate`
- `read_file`
- `write_file`
- `mark_task_complete`
- `memory`
- `smithery_mcp`

Tools are explicit. Directory scanning and hot loading are not used.

The built-in registry is not the same thing as the active tool set. A tool must still pass configuration and worker policy. Mutating or privileged capabilities are controlled by:

1. the global `tools.mutation_enabled` setting,
2. the global tool allowlist,
3. each worker's `allowed_tools` list, and
4. connector-specific boundaries such as `smithery.allowed_connections`.

The repository's base profile intentionally leaves `smithery_mcp` out of both the global and worker allowlists.

## README Swarm Use Case

Make-It-Heavy can be used as the reasoning engine for a README maintenance swarm:

```text
GitHub repo inventory
        │
        ▼
README audit queue
        │
        ▼
Make-It-Heavy worker lanes
        │
        ├── identity clarity audit
        ├── architecture / integration map audit
        ├── install / usage verification
        ├── truth and maintenance review
        └── rewrite plan / patch draft
        │
        ▼
README patch artifacts
        │
        ├── branch / PR creation by GitHub worker
        ├── Notion status update
        ├── repository graph update
        └── audit receipt
```

## Integration Targets

Available integration primitive:

- Smithery MCP gateway — implemented as a privileged connector and disabled by the base configuration until exact connections and worker policy are supplied

Planned or adjacent integration targets:

- GitHub repository scanner
- GitHub branch / PR writer
- Notion worker queue
- Google Drive archive layer
- MegaPDF document-output layer
- Doclet / DocuMind document intelligence
- Playwright / Stagehand browser automation
- Comet / computer-use operators
- repository graph visualizer

## Repository Map

```text
agent.py              OpenRouter agent runtime and tool-call loop
orchestrator.py       parallel task decomposition, execution, and synthesis
make_it_heavy.py      interactive CLI dashboard
tools/                explicit tool registry and built-in tools
config.yaml           worker, model, timeout, connector, and tool policy configuration
requirements.txt      Python dependency set
tests/                policy, security, and runtime tests
receipts/             verified run and maintenance receipts
SECURITY.md           supported-code and security-reporting boundaries
```

## Truth & Maintenance Notes

This repository is write-capable for local artifacts today and has persistent local swarm memory.

Smithery connector code is present, but presence is not authorization. The base configuration is fail-closed for Smithery and requires deployment-specific connection and worker policy before use.

A successful local or CI test proves the tested code path, not the health or authorization state of a connected external system. External state requires connector-specific read-back verification.

## Related System Categories

- `readme-system` — canonical README specification and audit rules
- `repo-graph` — repository relationship and category index
- `notion-worker-swarm` — task queue, control plane, status, and review layer
- `github-worker` — branch, commit, PR, and audit receipt layer
- `document-intelligence` — MegaPDF, Doclet, DocuMind, Overleaf, Word, Google Docs
- `browser-automation` — Playwright, Stagehand, Comet, computer-use operators

## CI Deploy Fleet

Batch deploy self-hosted CI to multiple repositories with one command.

### Features

- batch deployment to multiple repos
- language detection for Python, TypeScript, and Go
- dry-run mode for previewing changes
- upgrade mode to replace existing CI
- organization-wide deployment modes
- verbose logging
- workflow validation before deployment
- automatic backups of existing CI files
- retry logic with configurable attempts

### Usage

```bash
./ci-deploy-fleet.sh Pro-xAI colossus-gateway mastermind --lang python
./ci-deploy-fleet.sh Pro-* --lang python
./ci-deploy-fleet.sh Pro-xAI apex-alpha --dry-run
./ci-deploy-fleet.sh Pro-xAI Pro-Colossus --upgrade
./ci-deploy-fleet.sh --validate-only --upgrade Pro-xAI
./ci-deploy-fleet.sh --all-python
./ci-deploy-fleet.sh --all-typescript
```

### Options

- `--lang LANG` — force language for all repos: `python`, `typescript`, or `go`
- `--dry-run` — show planned changes without applying them
- `--upgrade` — replace existing CI with the new version
- `--verbose` — show detailed output
- `--validate-only` — only validate workflow syntax
- `--all-python` — deploy to all Python repos
- `--all-typescript` — deploy to all TypeScript repos
- `--help` — show usage information

See `ci-deploy-fleet-summary.md` for the detailed fleet documentation and its recorded test results.

## License

See `LICENSE` for the repository's license terms, including its additional large-scale commercial attribution requirement.
