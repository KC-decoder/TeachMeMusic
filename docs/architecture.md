# TeachMeMusic Architecture

## Conceptual Layers

TeachMeMusic is organized around a pipeline of conceptual layers, each
answering a distinct question:

```text
Score ingestion          (A — Read)
      ↓
Musical analysis         (B — Understand)
      ↓
Pedagogical reasoning    (C — Plan, 1)
      ↓
Curriculum generation    (C — Plan, 2)
      ↓
Performance/adaptation
```

| Layer | Question | Responsibility |
|-------|----------|----------------|
| **Score ingestion** | What is written? | Read MusicXML/MXL and produce TeachMeMusic's canonical representation of the score: notes, rhythms, parts, keys, meters, dynamics, articulations — faithfully, without interpretation. |
| **Musical analysis** | What is happening musically and technically? | Derive meaning from the written score: motifs, phrase structure, harmony, technical demands, difficulty characteristics. |
| **Pedagogical reasoning** | How should it be learned? | Decide, for a given proficiency level (Beginner/Intermediate/Advanced), how the material should be taught. |
| **Curriculum generation** | What sequence of lessons? | Turn the pedagogical plan into a concrete, ordered sequence of lessons and exercises. |
| **Performance/adaptation** | How did the learner perform? | Assess learner performance and adapt the learning experience. |

## The Fundamental Distinction

The separation between these three questions is fundamental to
TeachMeMusic and must never be blurred:

1. **What is written?** — A factual statement about the score. The same for
   every learner.
2. **What does it mean musically/technically?** — Interpretation of the
   written material: structure, demands, difficulty.
3. **How should it be learned?** — A learner-dependent decision. The *same
   piece* must yield *different* learning strategies for Beginner,
   Intermediate, and Advanced learners.

Collapsing these layers (e.g. inferring difficulty during parsing, or
embedding lesson logic in the data model) would make the system impossible
to test, reuse, or improve layer by layer.

## The Canonical-Representation Boundary

TeachMeMusic must **own its canonical internal representation of music**.
The intended boundary is:

```text
MusicXML / MXL
      ↓
music21 (external parsing engine)
      ↓
TeachMeMusic parser          ← ingestion boundary
      ↓
TeachMeMusic domain models   ← canonical ScoreRepresentation
      ↓
Rest of TeachMeMusic (analysis, pedagogy, curriculum, performance)
```

Rules:

- External library objects (e.g. `music21` objects) **terminate at the
  ingestion boundary** (`src/teachmemusic/score/`). They must not appear in
  the signatures or data of any other TeachMeMusic module.
- Every downstream component consumes the TeachMeMusic canonical score
  representation, never an external library object.
- This prevents the entire application from becoming tightly coupled to one
  external library: the parser is replaceable, but the domain model is
  stable and owned by TeachMeMusic.

The shape of the canonical ScoreRepresentation itself is **not yet designed**;
that is the next architectural task (see [score-schema.md](score-schema.md)).

## Current State

Only the **score ingestion** layer's module boundaries exist
(`src/teachmemusic/score/`), documented but not implemented. The layers
analysis, pedagogy, curriculum, and performance do not exist in this
repository yet and must not be created speculatively.
