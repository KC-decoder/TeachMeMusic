# Architecture Decision Records

This directory records significant architectural decisions as lightweight
ADRs.

## Conventions

- File names: `ADR-NNNN-short-description.md` (e.g. `ADR-0001-canonical-representation.md`).
- Numbering is sequential and never reused.
- An ADR is written **only when an actual architectural decision warrants
  one** — not to populate this directory.
- Decisions that change or supersede an existing ADR are recorded as a new
  ADR that references the old one.

## Recommended Format

```markdown
# ADR-NNNN: Decision title

## Status

## Context

## Decision

## Alternatives Considered

## Consequences
```

Statuses: `Proposed`, `Accepted`, `Superseded by ADR-NNNN`, `Deprecated`.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-0001](ADR-0001-canonical-score-representation-boundary.md) | TeachMeMusic owns a canonical score representation | Accepted |
| [ADR-0002](ADR-0002-defer-music21-dependency.md) | Defer the music21 dependency until ingestion is implemented | Accepted |
