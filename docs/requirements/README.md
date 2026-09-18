# Requirements

This directory states **what** TeachMeMusic must do. It deliberately does
not state **how** it is implemented (that belongs to architecture, ADRs,
and code).

## Namespaces

| Namespace | Area |
|-----------|------|
| `REQ-PROD-xxx` | Product-level behavior |
| `REQ-SCORE-xxx` | Score ingestion and canonical score representation |
| `REQ-ANALYSIS-xxx` | Musical/technical analysis |
| `REQ-PED-xxx` | Pedagogical reasoning |
| `REQ-CURR-xxx` | Curriculum generation |
| `REQ-PERF-xxx` | Learner performance |
| `REQ-NFR-xxx` | Non-functional requirements |

Numbers are sequential within a namespace.

## ID Rules

- Requirement IDs are **unique, stable, and never silently reused** for
  another meaning.
- If a requirement becomes obsolete, its historical identity is preserved
  and its status is set to `Deprecated` (with a note) — it is not deleted
  or renumbered.
- Requirements are introduced deliberately: each must arise from an
  established product need, a documented decision, or a design task. No
  speculative requirements.

## Statuses

| Status | Meaning |
|--------|---------|
| `Proposed` | Drafted, not yet accepted. |
| `Accepted` | Agreed as something TeachMeMusic shall do; not yet built. |
| `Implemented` | Code exists that satisfies it; verification still pending. |
| `Verified` | Implemented **and** verification evidence exists in the repository (tests, experiment results, or review evidence — linked in the traceability matrix). Never set without that evidence. |
| `Deprecated` | No longer intended; identity preserved. |
| `Rejected` | Considered and declined; identity preserved. |

## Requirement Format

```markdown
## REQ-XXX-000 — Short title

Status: Proposed

Introduced: DEV-xxx

Requirement:
TeachMeMusic shall …

Rationale:
Why this is needed.

Acceptance Criteria:
- …

Verification:
Pending | TEST-XXX-xxx (link) | review evidence
```

## Files

- [product.md](product.md) — stable, high-level product requirements.
- [functional.md](functional.md) — functional requirements by capability
  (conventions; detailed Stage A requirements are planned for DEV-004 after
  DEV-003 establishes the reference-score ground truth).
- [non-functional.md](non-functional.md) — non-functional requirement
  categories and the requirements established so far.

## Related Conventions

- Test identifiers: see [../traceability/README.md](../traceability/README.md).
- Requirement → design → implementation → evidence chain: see
  [../traceability/README.md](../traceability/README.md) and the
  [traceability matrix](../traceability/traceability-matrix.md).
