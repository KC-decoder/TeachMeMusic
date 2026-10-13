# Traceability Matrix

The working traceability artifact. Columns:

- **Requirement** — stable ID (see `docs/requirements/`).
- **Introduced** — increment that recorded the requirement.
- **Design/ADR** — the architecture/decision that shapes the work, or
  `Pending`.
- **Implementation** — where it is implemented, or `Pending`.
- **Verification** — test/experiment/review evidence, or `Pending`.
- **Status** — mirrors the requirement's status. `Verified` is only ever
  written when repository evidence exists and is linked.

## Product Requirements

| Requirement | Introduced | Design/ADR | Implementation | Verification | Status |
|---|---|---|---|---|---|
| REQ-PROD-001 — Learner-selected musical material | DEV-002 | Pending | Pending | Pending | Accepted |
| REQ-PROD-002 — Initial instrument: piano | DEV-002 | Pending | Pending | Pending | Accepted |
| REQ-PROD-003 — Structured, interactive learning experience | DEV-002 | Pending | Pending | Pending | Accepted |
| REQ-PROD-004 — Proficiency level selection | DEV-002 | Pending | Pending | Pending | Accepted |

## Non-Functional Requirements

| Requirement | Introduced | Design/ADR | Implementation | Verification | Status |
|---|---|---|---|---|---|
| REQ-NFR-001 — Architectural boundary adherence | DEV-002 | ADR-0001, ADR-0003 | `src/teachmemusic/score/` boundary (module structure only) | Architecture review each increment | Accepted |
| REQ-NFR-002 — Reproducibility | DEV-002 | ADR-0003 | `pyproject.toml`, `README.md` | Verification suite run in DEV-001/DEV-002 | Accepted |
| REQ-NFR-003 — Deliberate dependency management | DEV-002 | ADR-0002, ADR-0003 | `pyproject.toml` (zero runtime deps) | Review of dependency list each increment | Accepted |

## Functional Requirements

None yet. Detailed Stage A requirements (REQ-SCORE-xxx) begin in
**DEV-004 - Canonical ScoreRepresentation**, using the approved ground truth
from the closed DEV-003 increment.

## Reference Evidence

| Evidence ID | Introduced | Source material | Evidence record | Status |
|---|---|---|---|---|
| TMM-REF-CANDIDATE-001 — Hot Cross Buns | DEV-003 | `.mxl` and PDF fixture pair | [`tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/README.md`](../../tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/README.md) | Approved authoritative ground truth; no musical discrepancy found; DEV-003 DONE |

This evidence record does not implement or verify a product requirement. Its
purpose is to inform the future Stage A requirements and canonical score-model
design without prematurely declaring either complete.

## Defects

None recorded.

## Experiments

None recorded.
