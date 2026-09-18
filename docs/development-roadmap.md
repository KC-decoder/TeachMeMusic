# Development Roadmap

TeachMeMusic develops in four stages. Each stage's output is the input of
the next. This document is intentionally high-level; detailed designs are
produced stage by stage and recorded in the development journal and ADRs.

## Development Increments vs. Product Stages

The **product stages** (A–D below) describe *capabilities*. Development
happens in separately numbered **development increments** (`DEV-xxx`;
lifecycle and rules in [governance.md](governance.md)):

- DEV-001 — Project Foundation
- DEV-002 — Development Governance & Traceability
- DEV-003 — Reference Score Review and Ground Truth (Stage A)
- DEV-004 — Canonical ScoreRepresentation (Stage A)
- DEV-005 — Basic MusicXML Parser (Stage A)
- …

An increment serves a product stage but is not itself a stage; the two
numberings must never be conflated.

## Stage A — Read

**Question: what is written in the music?**

Accurately represent the musical score. MusicXML/MXL documents are ingested
through a parser (eventually built on `music21`) and converted into
TeachMeMusic's canonical score representation — the library-independent
data model of what is written.

Stage A deliberately stops at the factual: it does not determine difficulty,
motifs, phrase structure for teaching, learner ability, teaching strategy,
lesson boundaries, exercises, or performance quality.

Status: **DEV-003 is DONE. Its independent MusicXML/PDF inspections,
comparison, and authoritative ground-truth consolidation found no musical
discrepancy and were approved by the project owner. DEV-004 canonical-model
planning is next but has not started. The parser and canonical representation
are not implemented.**

## Stage B — Understand

**Question: what is happening musically and technically?**

Extract relevant musical and technical characteristics from the canonical
score representation: structure, harmony, motifs, phrase patterns, technical
demands, and difficulty-relevant features.

Status: not started.

## Stage C — Plan

**Question: how should someone at a specified proficiency level learn it?**

Generate a learning curriculum appropriate for the learner's selected level
(Beginner / Intermediate / Advanced). The same piece must produce different,
level-appropriate learning strategies.

Status: not started.

## Stage D — Evaluate

**Question: is the generated learning plan pedagogically sensible?**

Evaluate generated curricula for pedagogical soundness — the mechanisms and
criteria by which plans are judged and improved.

Status: not started.
