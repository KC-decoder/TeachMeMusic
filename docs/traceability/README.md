# Traceability

TeachMeMusic maintains the conceptual chain from need to evidence:

```text
Business/Product Need
        ↓
Requirement            (docs/requirements/)
        ↓
Design / Architecture  (docs/architecture.md, docs/decisions/)
        ↓
Implementation         (src/)
        ↓
Verification           (tests/, experiments/, review evidence)
        ↓
Evidence / Result      (linked in the traceability matrix)
```

The working artifact is the
[traceability matrix](traceability-matrix.md).

## Rules

- If an artifact in the chain does not exist yet, write **`Pending`**.
- **Never write `Verified`** unless actual evidence exists in the
  repository (passing tests, experiment results, or documented review
  evidence), and link that evidence.
- Do not invent implementation or verification links.
- Update the matrix as part of the work that changes what it covers
  (Definition of Done).

## Identifier Conventions

Stable, namespaced identifiers are used so the chain can be referenced
from code, commits, and docs. IDs are unique, stable, and never silently
reused.

### Test identifiers

```text
TEST-SCORE-xxx    TEST-ANALYSIS-xxx    TEST-PED-xxx
TEST-CURR-xxx     TEST-PERF-xxx        TEST-NFR-xxx
```

Tests may reference their requirement(s) in a docstring, e.g.:

```python
def test_written_pitch_is_preserved() -> None:
    """TEST-SCORE-001 — verifies REQ-SCORE-001."""
```

Convention only for now: existing DEV-001 foundation tests are not renamed,
and no new tests are created until the functionality they verify exists.

### Defect identifiers

Consequential defects use:

```text
BUG-SCORE-xxx    BUG-ANALYSIS-xxx    BUG-PED-xxx
BUG-CURR-xxx     BUG-PERF-xxx        BUG-NFR-xxx
```

A meaningful defect record may include: Description, Affected
Requirement, Affected Version/Commit, Severity, Reproduction, Regression
Test, Fix Commit, Status (`Open`, `In Progress`, `Fixed`, `Verified`,
`Closed`, `Won't Fix`).

- Trivial typos and inconsequential edits do **not** require formal bug IDs.
- No bug database exists. GitHub Issues may become the primary bug tracker
  later; until then, consequential defects are recorded in the affected
  increment's development record with a BUG ID.

### Related conventions

- Requirement IDs and statuses: [../requirements/README.md](../requirements/README.md)
- Experiment IDs: [../experiments/README.md](../experiments/README.md)
- ADRs: [../decisions/README.md](../decisions/README.md)
