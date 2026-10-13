# TeachMeMusic Documentation

## Where Things Live

Each artifact has one primary responsibility. Do not duplicate content
across artifacts — link to it.

| Artifact | Responsibility |
|----------|----------------|
| `README.md` (root) | What is TeachMeMusic? |
| `PROJECT_STATUS.md` (root) | Append-only chronological development log and cross-agent handoff |
| `docs/governance.md` | Development process: lifecycle, Definitions of Ready/Done, increment numbering, commit and Git conventions, versioning, tooling policy |
| `docs/architecture.md` | How is TeachMeMusic structurally designed? (layers, boundaries, modularity) |
| `docs/development-roadmap.md` | What capabilities exist conceptually, in what order? (Stages A–D) |
| `docs/score-schema.md` | Status of the canonical ScoreRepresentation (not yet designed) |
| `docs/requirements/` | What *must* TeachMeMusic do? (REQ-xxx) |
| `docs/traceability/` | How do requirements connect to design, implementation, and evidence? |
| `docs/decisions/` | Why were significant architectural decisions made? (ADRs) |
| `docs/experiments/` | What research hypotheses were tested, and what happened? (EXP-xxx) |
| `docs/development/` | What happened during each development increment? (DEV-xxx records) |
| `CHANGELOG.md` | What user/developer-visible changes accumulated? |
| Git history | Exactly what changed and when |
| Tests | Executable evidence that defined behavior works |

## Contents

- [governance.md](governance.md) — development governance (process rules)
- [architecture.md](architecture.md) — conceptual layers, the
  canonical-representation boundary, modularity principles.
- [development-roadmap.md](development-roadmap.md) — product Stages A–D
  and the increment/stage distinction.
- [score-schema.md](score-schema.md) — status of the canonical
  ScoreRepresentation (not yet designed; DEV-003 first establishes the
  reference-score ground truth, with design planned for DEV-004).
- [requirements/](requirements/README.md) — requirement conventions and
  the established requirements.
- [traceability/](traceability/README.md) — traceability conventions and
  the [matrix](traceability/traceability-matrix.md).
- [experiments/](experiments/README.md) — experiment framework.
- [decisions/](decisions/README.md) — Architecture Decision Records (ADRs).
- [development/](development/001-project-foundation.md) — the development
  journal: one record per significant increment, plus the
  [template](development/TEMPLATE.md).
- [DEV-003](development/003-reference-score-ground-truth.md) — reference score
  review and ground-truth development record.

## Conventions

Every significant development step produces a numbered journal entry in
`development/` (see [development/TEMPLATE.md](development/TEMPLATE.md)).
Architecture-level decisions are recorded as ADRs in `decisions/`.
Documentation must never describe functionality that does not exist.
