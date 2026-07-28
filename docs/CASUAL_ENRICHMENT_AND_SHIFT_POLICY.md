# Casual Enrichment and Shift Policy

## Purpose

This policy replaces passive read-only posture with non-destructive improvement.

If an agent, worker, or operator can clearly improve a repository without removing data, breaking behavior, hiding evidence, or inventing unsupported claims, it should improve it.

The default posture is not read-only.

The default posture is:

```text
inspect → understand → improve safely → preserve original context → record receipt
```

## Core Doctrine

Read-only review is useful only as a temporary diagnostic phase.

A mature repository-maintenance agent should move from observation to enrichment as soon as the improvement is clear, reversible, and scoped.

## Allowed Casual Enrichment

The agent may apply safe improvements such as:

- strengthening README clarity
- adding missing system-role sections
- adding integration maps
- adding truthful status notes
- improving examples
- improving headings and structure
- adding repository relationship metadata
- adding missing configuration documentation
- adding architecture notes
- adding non-destructive comments where useful
- moving obsolete or confusing material into a review folder
- creating audit receipts for changed files

## Non-Destructive Rule

Do not delete useful material outright.

If a file, section, workflow, script, or document appears obsolete, confusing, duplicated, or risky, move or copy it into a review location instead of destroying it.

Recommended destinations:

```text
shift/
shift/review/
shift/legacy-candidates/
shift/deprecated/
legacy/
legacy/<date-or-version>/
```

## Shift Folder Semantics

`shift/` means:

```text
preserved but no longer treated as the active canonical surface
```

A shifted item is not gone.

It is identified for review, consolidation, migration, or eventual legacy classification.

## Legacy Candidate Criteria

A file or repo can be marked as a legacy candidate when it is:

- superseded by a newer implementation
- mostly empty or skeletal
- duplicated by a stronger repo
- misleading in its README or project claim
- not connected to the current system graph
- not recently maintained
- missing install/use instructions
- unsafe to present as active
- useful only as historical context

## Best-of-All-Worlds Handling

When material is questionable but may contain value:

1. Keep the active repo working.
2. Preserve the questionable material in `shift/`.
3. Add a short note explaining why it was shifted.
4. Link any replacement or successor file.
5. Mark whether the item should be revived, merged, archived, or moved to legacy.

## README Swarm Behavior

README workers should not merely score documentation and stop.

They should:

1. Read the current README.
2. Identify the actual system role.
3. Improve the README when the improvement is clear.
4. Add a star-map section.
5. Add truthful status boundaries.
6. Add related repositories and integration targets.
7. Mark uncertain claims as unknown.
8. Route obsolete sections into `shift/` when needed.
9. Produce a receipt.

## Receipt Requirement

Every enrichment wave should record:

```yaml
repo: GlacierEQ/example-repo
branch: docs/readme-star-map
files_changed:
  - README.md
  - README.star-map.yml
  - shift/review/OLD_README.md
change_type: casual_enrichment
non_destructive: true
legacy_candidates:
  - path: old-script.sh
    reason: superseded by current worker flow
receipt_sha256: null
```

## Hard Boundaries

Casual enrichment does not authorize:

- deleting files without preservation
- removing secrets without recording the remediation path
- changing legal/evidentiary meaning without source support
- fabricating installation steps
- claiming tests pass when not verified
- inventing integrations
- silently changing public behavior
- destructive refactors without a migration path

## Operating Standard

The agent should leave every touched repo clearer, more truthful, more connected, and easier to operate than it found it.

If the change is safe and useful, do it.

If the change is uncertain, preserve and shift.

If the repo is superseded, mark it as a legacy candidate.

If the repo is active, make the README a star map.
