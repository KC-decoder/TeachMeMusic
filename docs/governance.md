# Development Governance

Lightweight, repository-centered governance for TeachMeMusic.

> **Governing principle.** Documentation and traceability exist to help
> future developers understand, verify, reproduce, maintain, and audit
> meaningful work. They must not become paperwork for its own sake.

Do not create records for trivial changes that provide no lasting value.
Do create records for meaningful requirements, architectural decisions,
experiments, defects, and development increments.

## Development Increments vs. Product Stages

Two independent numbering systems are used and must never be confused:

- **Development increments** (`DEV-xxx`) — the sequence of development
  *steps*. Each has one record in `docs/development/`.
  - DEV-001 — Project Foundation
  - DEV-002 — Development Governance & Traceability
  - DEV-003 — Reference Score Review and Ground Truth
  - DEV-004 — Canonical ScoreRepresentation
  - DEV-005 — Basic MusicXML Parser
  - …
- **Product stages** (`Stage A–D`) — the conceptual *capabilities* of the
  product (see `development-roadmap.md`): A — Read, B — Understand,
  C — Plan, D — Evaluate.

An increment is labeled with the product stage it serves, e.g.:

```text
DEV-004
Product Stage: A — READ
Capability: Canonical ScoreRepresentation
```

"Prompt N" (task briefs) is a third, separate thing: prompts *request*
increments; they are not a project numbering system.

## Increment Lifecycle

```text
BACKLOG → READY → IN PROGRESS → REVIEW → DONE
                    ↘ BLOCKED (documented reason; re-enters when cleared)
```

| State | Meaning |
|-------|---------|
| **BACKLOG** | Identified, but not sufficiently prepared for implementation. |
| **READY** | Definition of Ready satisfied. |
| **IN PROGRESS** | Active implementation is occurring. |
| **REVIEW** | Implementation complete enough for verification and human review. |
| **DONE** | Definition of Done satisfied, including human review and commit. |
| **BLOCKED** | Progress cannot continue because of a documented dependency, decision, failure, or external constraint. |

## Chronological Development Log and Handoff

`PROJECT_STATUS.md` is an append-only chronological record shared by human
developers and coding agents. Its final entry is the current handoff.

- Append a dated entry after meaningful work or a lifecycle change.
- Never rewrite, reorder, or delete earlier entries.
- Correct earlier information with a new entry.
- State the active increment, resulting status, completed work, real evidence,
  blockers, exact next action, and the human or agent that performed the work.
- Link to detailed increment records rather than duplicating their full
  implementation history.

This provides continuity when work moves between humans, Qwen, Codex, or other
agents without treating an agent's memory as project state.

This current operating rule refines ADR-0003's original description of
`PROJECT_STATUS.md` as a snapshot dashboard; the repository-centered
governance decision itself remains in force.

### Work-in-Progress Rule

Only **one major development increment** should normally be IN PROGRESS at
a time. Exceptions must be deliberate and documented in `PROJECT_STATUS.md`.
Coding agents must not begin unrelated future capabilities simply because
they appear useful.

## Definition of Ready

Before implementation starts, an increment should have:

- [ ] Objective defined
- [ ] Business/product rationale defined
- [ ] Scope defined
- [ ] Non-goals defined
- [ ] Relevant requirements identified
- [ ] Acceptance criteria defined
- [ ] Dependencies understood
- [ ] Relevant architecture reviewed
- [ ] Testing/verification strategy defined
- [ ] Known unresolved decisions identified

An increment should not move BACKLOG → READY until these are reasonably
satisfied. The Definition of Ready exists to prevent coding agents from
filling major ambiguity with assumptions.

## Definition of Done

An implementation increment is DONE when:

- [ ] Requirements implemented
- [ ] Acceptance criteria satisfied
- [ ] Appropriate tests exist
- [ ] Tests pass
- [ ] Ruff lint passes
- [ ] Ruff formatting check passes
- [ ] mypy passes
- [ ] Documentation updated
- [ ] Traceability updated
- [ ] ADRs created/updated where required
- [ ] `PROJECT_STATUS.md` updated
- [ ] `CHANGELOG.md` updated when appropriate
- [ ] No known critical regression
- [ ] Git diff reviewed
- [ ] Human review completed
- [ ] Clean Git commit created

Research/documentation-only increments may have different applicable
verification (e.g. no new tests), but any exception must be stated
explicitly in the increment record. Never mark an item complete merely
because code was generated.

## Commit Conventions

Conventional Commit-style subjects: `chore:`, `docs:`, `feat:`, `fix:`,
`test:`, `refactor:`, `perf:`, `build:`, `ci:`. Scope the product area
where useful:

```text
chore: establish TeachMeMusic project foundation
docs: establish development governance and traceability
feat(score): add canonical score domain models
test(score): add tie regression coverage
```

Where useful, commit bodies may reference stable identifiers:

```text
Increment: DEV-004
Implements: REQ-SCORE-001
Verifies: TEST-SCORE-001
Experiment: EXP-SCORE-001
Fixes: BUG-SCORE-001
```

Do not require meaningless metadata on trivial commits.

## Git Workflow

A lightweight workflow for future work:

```text
feature branch → implementation → verification → human review → commit / pull request → main
```

Rules that hold now:

- Human review precedes every commit; commits are never made automatically.
- Nothing is pushed without explicit human approval; no remote exists yet.
- No GitHub remote, Actions, releases, or other GitHub automation yet.
- No heavyweight GitFlow.

## Versioning

TeachMeMusic intends to follow [Semantic Versioning](https://semver.org/)
(`MAJOR.MINOR.PATCH`) where appropriate. The current `0.0.0` is an
unreleased placeholder and is not a release. Pre-1.0 development may
evolve rapidly. Do not invent release milestones or version numbers that
have not been decided.

## Tooling Policy

Governance is repository-centered. The following are deliberately **not**
used and must not be introduced without a deliberate, documented decision:
Jira/Linear/Azure DevOps or other external project-management services,
GitHub Projects, GitHub Actions, release automation, coverage services,
telemetry, analytics, cloud infrastructure, or databases. Future tooling
can be mapped onto this repository-centered system later.
