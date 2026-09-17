"""Future MusicXML/MXL to TeachMeMusic score model conversion.

Intended responsibility
-----------------------
Parse MusicXML (``.xml``) and compressed MusicXML (``.mxl``) documents using
``music21`` as the external parsing engine, and convert the parsed content
into TeachMeMusic's canonical score-domain models.

Architectural constraint
------------------------
This module is the ingestion boundary (see ADR-0001): all external library
objects, e.g. ``music21`` objects, must terminate here. Everything
downstream of this module consumes the TeachMeMusic canonical score
representation only, never external library objects.

Status
------
Intentionally not implemented. The canonical score representation this
module would produce has not been designed yet (Prompt 002); see
``docs/score-schema.md`` and ``docs/development/001-project-foundation.md``.
"""
