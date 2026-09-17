# ADR-0001: TeachMeMusic owns a canonical score representation

## Status

Accepted (2026-09-17, Prompt 001).

## Context

TeachMeMusic will ultimately parse MusicXML/MXL with an external library
(`music21` is the current candidate). If `music21` objects were passed
through the whole application, every downstream component (analysis,
pedagogy, curriculum, performance) would be coupled to that one external
library: its API shape, its bugs, its upgrade behavior, and its license.
Replacing or removing the parser would then require touching the entire
codebase.

## Decision

TeachMeMusic owns a canonical, library-independent internal representation
of music (the ScoreRepresentation). The parsing library's objects terminate
at the ingestion boundary in `src/teachmemusic/score/`:

```text
MusicXML / MXL → music21 → TeachMeMusic parser → ScoreRepresentation → rest of TeachMeMusic
```

No module outside `score/` may import or expose external parsing-library
objects. Downstream components consume the ScoreRepresentation only.

The concrete schema of the ScoreRepresentation is deliberately **not** part
of this decision; it is designed separately (see
[docs/score-schema.md](../score-schema.md)).

## Alternatives Considered

1. **Use `music21` objects end to end.** Rejected: couples the entire
   application to one external library and prevents independent development
   and testing of downstream layers.
2. **Reimplement MusicXML parsing natively.** Rejected for now: a large
   undertaking with no benefit over using a mature parser behind a boundary.
   Reconsider only if `music21` proves unsuitable.
3. **Adopt a different standard format (e.g. MusicXML) as the internal
   model.** Rejected: it would tie the domain model to the file format and
   leave no place for TeachMeMusic-specific structure later stages need.

## Consequences

- The parser must be written and tested at the boundary; the rest of the
  application can be developed and tested without any MusicXML or `music21`
  dependency.
- The canonical representation must be complete enough for Stages B–D;
  under-representing the score would force revisiting this boundary.
- A design task (Prompt 002) is required before any parsing implementation.
