# Canonical Score Schema

> **TeachMeMusic's canonical ScoreRepresentation has NOT yet been designed.**
> Designing it is the next architectural task (Prompt 002).

This document intentionally does not define the schema. Prematurely fixing a
data model before the ingestion requirements are understood would cost more
to change later than it saves now.

## Why This Representation Matters

The canonical ScoreRepresentation is the single most important data
structure in TeachMeMusic. It is the contract at the center of the
architecture:

```text
score ingestion
       ↓
ScoreRepresentation        ← the contract
       ↓
all downstream systems (analysis, pedagogy, curriculum, performance)
```

- It is what the **ingestion** side must produce: a faithful, complete
  account of what is written in the score, independent of any particular
  parsing library.
- It is what **every downstream system** consumes. Once it exists, analysis,
  pedagogy, and curriculum work proceed against a stable, TeachMeMusic-owned
  type surface — never against external library objects (see
  [architecture.md](architecture.md) and ADR-0001).
- Its quality determines whether Stage B–D questions can be asked at all:
  the representation must capture at least everything later stages need
  (e.g. notes, durations, parts, keys, meters, articulations, dynamics)
  without being polluted by interpretations that belong to Stage B.

## Open Questions (to be resolved in the next architectural task)

- What granularity of musical detail is required by Stages B–D?
- How to represent ensemble structure (parts/instruments) vs. a single
  piano score?
- How to represent tied notes, grace notes, ornaments, dynamics, and
  slurs?
- What is the serialization target for storage and debugging?
- What invariants must validation enforce?
