# Canonical Score Schema

> **TeachMeMusic's canonical ScoreRepresentation has NOT yet been designed.**
> DEV-003 established and closed the approved Hot Cross Buns reference ground
> truth. Schema design is planned for DEV-004 and must use that evidence;
> DEV-004 has not started.

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

## DEV-003 Evidence-Derived Design Inputs

The authoritative evidence record is the Hot Cross Buns sample
[`README.md`](../tests/fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/README.md),
especially its Part 4 ground truth. DEV-003 does not design the schema or
create functional requirements; it establishes the facts DEV-004 must address.

The future representation must be able to preserve or deliberately classify:

- score identity and textual metadata, including unknown and empty values;
- ordered part, staff, voice, and measure structure without inventing labels;
- clef, key signature, encoded mode, meter, and attribute carry-forward;
- ordered note/rest events with voice, measure, onset, normalized duration,
  written value, augmentation dots, pitch spelling, and octave;
- exact lyric text, lyric line/number, syllabic status, punctuation,
  capitalization, and event association;
- explicit barline style and score termination;
- explicit engraving/layout facts such as stem direction and system breaks,
  either in the canonical model or in a deliberately separate layout record;
- printed directions separately from playback-only metadata;
- source/provenance metadata separately from musical facts and inferences;
- empty/default states for absent features without fabricated events.

For this fixture specifically, the representation must be capable of
expressing eight complete 4/4 measures, 17 pitched notes, 3 quarter rests, 32
quarter-note beats, two lyric lines, a measure 7 system break, and a final
light-heavy barline, together with the exact event sequence recorded in the
fixture ground truth.

DEV-004 must decide whether numerical layout coordinates, page geometry,
fonts, and MIDI/playback settings belong in the canonical representation, a
separate source/layout record, or are intentionally excluded. These are design
questions, not decisions made by DEV-003.

## Open Questions for DEV-004

- What granularity of musical detail is required by Stages B–D?
- How to represent ensemble structure (parts/instruments) vs. a single
  piano score?
- How to represent tied notes, grace notes, ornaments, dynamics, and
  slurs?
- What is the serialization target for storage and debugging?
- What invariants must validation enforce?
