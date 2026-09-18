# Non-Functional Requirements

Categories that will matter for TeachMeMusic, including for its possible
future life as a commercial consumer application, plus the non-functional
requirements established so far. Conventions: [README.md](README.md).

> **No numeric performance or security targets are set yet.** Undecided
> targets are marked `TBD` — values will be decided deliberately, not
> invented.

## Requirements Established So Far

## REQ-NFR-001 — Architectural boundary adherence

Status:
Accepted

Introduced:
DEV-002

Requirement:
TeachMeMusic shall maintain the documented conceptual layer boundaries
and the canonical-representation boundary (ADR-0001): external
parsing-library objects terminate at score ingestion, and layers
communicate through contracts rather than implementation details.

Rationale:
ADR-0001; long-term maintainability, testability, and the ability to
replace the parsing engine without touching the rest of the system.

Acceptance Criteria:
- Architecture review during each increment's review.
- (Future) automated architecture conformance checks, when modules exist.

Verification:
Pending

## REQ-NFR-002 — Reproducibility

Status:
Accepted

Introduced:
DEV-002

Requirement:
Building, installing, and verifying the project shall be reproducible
from the repository alone, without undocumented manual steps.

Rationale:
Research and auditability: any developer or agent must be able to rebuild
the same verifiable state.

Acceptance Criteria:
- Documented setup in `CONTRIBUTING.md` works on a clean machine with the
  stated Python version.
- The verification suite (`pytest`, Ruff, mypy) can be run from the
  documented commands.

Verification:
Pending (the documented procedure exists and was used in DEV-001/002;
cross-machine verification remains)

## REQ-NFR-003 — Deliberate dependency management

Status:
Accepted

Introduced:
DEV-002

Requirement:
New runtime dependencies shall be added only with documented justification
(increment record, and an ADR when the dependency is architectural).

Rationale:
ADR-0002 deferred `music21` on exactly this principle; dependency
proliferation is a common cause of unmaintainable research projects and a
licensing risk for a future commercial app.

Acceptance Criteria:
- Every runtime dependency in `pyproject.toml` is traceable to a decision
  in the development journal or an ADR.

Verification:
Pending (currently trivially true: zero runtime dependencies)

## Future Categories (targets TBD)

These categories are established so future work has a home. Do not add
numeric targets or legal conclusions until they are deliberately decided.

- **Correctness** — fidelity of score representation and of any
  generated learning content. Target: TBD.
- **Reliability** — dependable behavior on real-world scores and inputs.
  Target: TBD.
- **Performance** — parsing/analysis responsiveness (eventually
  device-appropriate for a consumer app). Target: TBD.
- **Security** — handling of files and data, safe defaults. Target: TBD.
- **Privacy** — treatment of user-uploaded musical material and
  learner/performance data. Target: TBD.
- **Accessibility** — usable by learners with disabilities. Target: TBD.
- **Platform compatibility** — target platforms for a future consumer
  application. Target: TBD.
- **Data integrity** — integrity of stored scores, plans, and progress.
  Target: TBD.
- **Licensing & copyright** — project license (pending decision),
  dependency licensing, and rights in learner-provided musical material.
  Status: pending deliberate decision; no legal conclusions recorded.
- **Release & reproducibility** — signed, reproducible releases for a
  future consumer application. Target: TBD.
