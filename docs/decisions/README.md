# Architecture Decision Records

This directory records significant architectural decisions as lightweight
ADRs.

## When an ADR Is Required

Create an ADR when a decision:

- is difficult or costly to reverse,
- affects multiple components,
- changes architectural boundaries,
- introduces a significant dependency,
- establishes a long-lived project convention, or
- involves meaningful trade-offs.

Do **not** create ADRs for trivial implementation details.

## Conventions

- File names: `ADR-NNNN-short-description.md`.
- Numbering is sequential and **never reused**.
- **Never delete a historical ADR.** When a later decision supersedes an
  earlier one, record the new ADR and mark the old one `Superseded by
  ADR-NNNN` (and link both ways).

## Statuses

`Proposed`, `Accepted`, `Superseded (by ADR-NNNN)`, `Deprecated`,
`Rejected`.

## Recommended Format

```markdown
# ADR-NNNN: Decision title

## Status

## Context

## Decision

## Alternatives Considered

## Consequences
```

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-0001](ADR-0001-canonical-score-representation-boundary.md) | TeachMeMusic owns a canonical score representation | Accepted |
| [ADR-0002](ADR-0002-defer-music21-dependency.md) | Defer the music21 dependency until ingestion is implemented | Accepted |
| [ADR-0003](ADR-0003-development-governance-and-traceability.md) | Lightweight, repository-centered development governance | Accepted |
