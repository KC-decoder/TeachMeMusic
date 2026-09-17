# ADR-0002: Defer the music21 dependency until ingestion is implemented

## Status

Accepted (2026-09-17, Prompt 001).

## Context

`music21` is the planned external parsing engine for Stage A. It is a large
dependency with its own dependency tree. At the project-foundation stage,
nothing imports it.

## Decision

`music21` is **not** declared in `pyproject.toml` yet. The project has zero
runtime dependencies at the foundation stage. `music21` (or a replacement)
will be added to the project's runtime dependencies at the same time the
parser implementation begins, after the canonical ScoreRepresentation has
been designed (Prompt 002 and following).

## Alternatives Considered

1. **Declare `music21` now** so the dependency is "known" to the environment.
   Rejected: pulls a heavy, unused dependency into every install before any
   code justifies it, and fixes the tooling choice before the
   representation design is known to fit it.
2. **Defer (chosen).** Keeps the foundation minimal; the addition of
   `music21` will be a deliberate, documented change alongside the parser
   work.

## Consequences

- The foundation install stays light and has no external musical-analysis
  coupling.
- When ingestion work starts, the dependency addition and its version
  constraints are part of that step's journal entry and verified then.
