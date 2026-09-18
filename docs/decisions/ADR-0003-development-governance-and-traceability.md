# ADR-0003: Lightweight, repository-centered development governance

## Status

Accepted (2026-09-17, DEV-002).

## Context

TeachMeMusic is a serious research/software project with the possibility of
becoming a future commercial consumer application (e.g. distributed through
the Apple App Store). Development will be done by humans and coding agents,
over a long timeline, and may eventually need to be audited. The project
must remain modular, understandable, testable, reproducible, traceable,
maintainable, and auditable — without becoming bureaucratic: the
governance must help future developers, not burden them with paperwork for
its own sake.

## Decision

Adopt a lightweight, **repository-centered** Agile governance system:

1. **Incremental development** with stable `DEV-xxx` increment numbering,
   distinct from product-stage numbering (A–D) and from task-prompt
   numbering.
2. A documented **increment lifecycle** (BACKLOG → READY → IN PROGRESS →
   REVIEW → DONE, plus BLOCKED) with a **Definition of Ready**, a
   **Definition of Done**, and a **work-in-progress rule** (one major
   increment in progress).
3. **Stable, namespaced identifiers** for requirements (`REQ-…`), tests
   (`TEST-…`), experiments (`EXP-…`), and defects (`BUG-…`), never reused
   silently.
4. A **traceability chain** (need → requirement → design/ADR →
   implementation → verification → evidence) maintained in
   `docs/traceability/`.
5. **Development journals** (`docs/development/`) — one record per
   meaningful increment.
6. **Human review before commits**; no automatic commits or pushes.
7. **Lightweight documentation**: `PROJECT_STATUS.md` as a snapshot
   dashboard, ADRs for significant decisions, requirement/traceability
   records for meaningful work — and no records for trivial changes.

The full rules live in `docs/governance.md`; agent operating rules live in
`AGENTS.md`.

## Alternatives Considered

1. **Informal development with Git history only.** Rejected: commits
   record *what* changed, not *why*; a project involving coding agents,
   research, and possible future audit needs explicit requirements,
   decisions, and status.
2. **Heavyweight Scrum/Jira-style governance** (external tracker, sprints,
   ceremonies, role requirements). Rejected: disproportionate for a single
   active developer plus agents; introduces tool lock-in and duplicated
   state outside the repository. External tools may later *map onto* this
   system, not replace it.
3. **The selected lightweight repository-centered approach.** Chosen: all
   state lives in versioned files that are themselves auditable,
   reproducible, and readable by both humans and agents with zero external
   dependencies.

## Consequences

- Every meaningful increment carries a small documentation overhead
  (status update, record, traceability update); trivial changes do not.
- Coding agents are constrained by `AGENTS.md` (active increment only, no
  invented requirements, no unverified "Verified" claims, human review
  before commit).
- If the project outgrows the repository-centered system, tools can be
  introduced later and mapped onto the existing identifiers; the
  identifiers and records remain stable.
- This ADR governs *process*; it does not change any product architecture
  (ADR-0001/0002 remain in force).
