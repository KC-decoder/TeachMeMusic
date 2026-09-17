"""Stage A — score ingestion and canonical score representation.

This package will read MusicXML (``.xml``) and compressed MusicXML (``.mxl``)
documents and convert them into TeachMeMusic's canonical,
library-independent score representation — the contract between ingestion
and every downstream system (analysis, pedagogy, curriculum, performance).

Architectural constraint: external parsing-library objects (eventually
``music21``) terminate inside this package; they must not leak into the rest
of TeachMeMusic. See ``docs/architecture.md`` and ADR-0001.

Status: intentionally not implemented. The canonical representation this
package will define is the next architectural task — see
``docs/score-schema.md``.
"""
