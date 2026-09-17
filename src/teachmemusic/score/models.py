"""Future canonical TeachMeMusic score-domain models.

Intended responsibility
-----------------------
Define the canonical, library-independent data models representing **what is
written in a musical score** — the TeachMeMusic ScoreRepresentation: the
contract between score ingestion and every downstream TeachMeMusic system
(analysis, pedagogy, curriculum, performance).

These models must not expose or depend on objects from external parsing
libraries such as ``music21`` (see ADR-0001).

Status
------
Intentionally not implemented. The schema will be designed as the next
architectural task (Prompt 002); see ``docs/score-schema.md``.
"""
