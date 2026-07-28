# README Swarm Automation Design

This document defines how Make-It-Heavy can participate in a repository-wide README maintenance swarm.

## Mission

Turn every README in the GitHub library into a truthful star map:

- clear project identity
- explicit system role
- integration map
- setup path
- maintenance status
- related repositories
- machine-readable metadata
- audit receipt

## Core Flow

```text
GitHub repository inventory
        │
        ▼
README audit queue
        │
        ▼
Make-It-Heavy analysis swarm
        │
        ├── identity worker
        ├── integration-map worker
        ├── setup / usage worker
        ├── truth-status worker
        └── patch-plan worker
        │
        ▼
Patch package
        │
        ├── README.md replacement or targeted diff
        ├── README.star-map.yml
        ├── INTEGRATIONS.md when needed
        ├── ARCHITECTURE.md when needed
        └── audit receipt
        │
        ▼
GitHub worker branch + PR
        │
        ▼
Notion queue status + memory sync
```

## Division of Labor

Make-It-Heavy should not become the entire control plane.

It should be the reasoning and patch-drafting engine.

| Component | Role |
|---|---|
| GitHub inventory worker | Lists repositories and fetches README/content metadata |
| Notion queue | Stores mission rows, status, priority, owner, and review state |
| Make-It-Heavy | Audits README quality and drafts patch artifacts |
| GitHub worker | Creates branches, commits files, opens PRs, stores receipts |
| Memory layer | Captures repository role, category, integration map, and decisions |
| README spec repo | Defines required sections, schemas, and scoring rules |

## README Score

Each README should receive a score from 0 to 100.

```text
Identity clarity               10
Purpose clarity                10
System role                    10
Quick start                    10
Architecture / star map        15
Integration map                15
Configuration                  10
Examples                       10
Truth / maintenance status      5
Related repositories            5
```

## Queue Record

```yaml
repo: GlacierEQ/example-repo
default_branch: main
category: document-automation
priority: high
status: queued
readme_score_before: 42
readme_score_after: null
worker_batch: readme-swarm-001
branch: docs/readme-star-map
pr: null
receipt_sha256: null
```

## Mutation Rules

The swarm is write-capable. It is not blind.

Required behavior:

1. Work on a branch.
2. Preserve repository-specific truth.
3. Do not invent install steps, badges, passing CI, integrations, or production status.
4. Mark unknowns as unknown.
5. Prefer targeted edits when the README is mostly sound.
6. Use full replacement when the README is skeletal, misleading, or integration-hostile.
7. Write an audit receipt for each repo touched.
8. Open a PR with score delta and missing follow-up work.

## Gatling / Tsunami Mode

A repository-wide wave should be batched, not chaotic.

Suggested modes:

```text
wave 0: spec + schema + auditor
wave 1: top 10 core repos
wave 2: category index repos
wave 3: document automation repos
wave 4: MCP / connector repos
wave 5: browser automation repos
wave 6: legal/document pipeline repos
wave 7: remaining public repos
wave 8: private/internal repos
```

Each wave should produce:

- repository list
- before score
- after score
- changed files
- PR links
- failed repos
- blocked repos
- next wave recommendations

## Output Artifact Contract

Make-It-Heavy should write local artifacts like:

```text
out/readme-audit/<repo>/README_PROPOSED.md
out/readme-audit/<repo>/README.star-map.yml
out/readme-audit/<repo>/AUDIT_RECEIPT.json
out/readme-audit/<repo>/PATCH_PLAN.md
```

The GitHub worker then converts those artifacts into branch commits and PRs.

## Near-Term Build Plan

1. Add a `readme_auditor` worker profile.
2. Add a `star_map_writer` worker profile.
3. Add a `truth_guard` worker profile.
4. Add an output directory convention.
5. Hand drafted artifacts to the GitHub worker for branch and PR creation.
6. Sync status back to Notion and memory.
