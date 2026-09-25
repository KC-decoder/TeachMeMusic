"""Task 7H evidence for links, opuses, sound catalogs, and auxiliaries."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.score.musicxml.boundary import validate_musicxml_source
from teachmemusic.score.musicxml.standards import resource_root
from teachmemusic.score.parser import parse_musicxml_auxiliary, parse_musicxml_timeline
from teachmemusic.score.v2.auxiliary import OpusCatalog, SoundCatalog
from teachmemusic.score.v2.auxiliary_validation import validate_auxiliary_document
from teachmemusic.score.v2.links import ExternalLink
from teachmemusic.score.v2.temporal_codec import temporal_from_dict, temporal_to_dict
from teachmemusic.score.v2.temporal_validation import validate_temporal_score


def _linked_score() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <work><work-title>Linked</work-title><opus xlink:href="collection.xml"/></work>
  <credit page="1">
    <link xlink:href="https://example.test/credit" name="credit-link"/>
    <bookmark id="credit-target" name="Credit"/>
    <credit-words>Linked score</credit-words>
  </credit>
  <part-list>
    <score-part id="P1">
      <part-link xlink:href="parts/piano.musicxml">
        <instrument-link id="P1-I1"/><group-link>score</group-link>
      </part-link>
      <part-name>Piano</part-name>
      <score-instrument id="P1-I1"><instrument-name>Piano</instrument-name></score-instrument>
    </score-part>
  </part-list>
  <part id="P1"><measure number="1">
    <link xlink:href="#credit-target" element="credit" position="1"/>
    <bookmark id="measure-target" name="Measure"/>
  </measure></part>
</score-partwise>"""


def _opus(version: str) -> bytes:
    public_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version in {"1.0", "1.1"} else f' version="{public_version}"'
    return (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML {public_version} Opus//EN" '
        '"http://www.musicxml.org/dtds/opus.dtd">'
        f"<opus{version_attribute}><title>Collection</title></opus>"
    ).encode()


def test_score_links_bookmarks_and_linked_parts_are_typed() -> None:
    """TEST-MXML-AUXILIARY-001: score links keep targets, scope, and references."""

    result = parse_musicxml_timeline(_linked_score())
    score = result.score
    assert score.work_opus is not None
    assert score.work_opus.href == "collection.xml"
    assert score.links[0].context == "credit:1"
    assert score.links[0].link.href == "https://example.test/credit"
    assert score.bookmarks[0].bookmark.id == "credit-target"
    assert score.parts[0].part_links[0].instrument_ids == ("P1-I1",)
    assert score.parts[0].part_links[0].group_links == ("score",)
    assert score.parts[0].measures[0].links[0].position == 1
    assert score.parts[0].measures[0].bookmarks[0].id == "measure-target"
    assert not validate_temporal_score(score)
    assert temporal_from_dict(temporal_to_dict(score)) == score


@pytest.mark.parametrize(
    "version",
    ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"),
)
def test_every_native_opus_version_maps_to_canonical_content(version: str) -> None:
    """TEST-MXML-AUXILIARY-002: all pinned opus roots map without XML leakage."""

    result = parse_musicxml_auxiliary(_opus(version))
    assert isinstance(result, OpusCatalog)
    assert (result.version, result.title, result.items) == (version, "Collection", ())
    assert not validate_auxiliary_document(result)


def test_nested_opus_order_links_and_page_state_are_preserved() -> None:
    """TEST-MXML-AUXILIARY-006: recursive opus relationships stay explicit."""

    source = b"""<?xml version="1.0"?>
<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML 4.0 Opus//EN"
  "http://www.musicxml.org/dtds/opus.dtd">
<opus version="4.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <title>Collection</title>
  <score xlink:href="one.musicxml" new-page="yes"/>
  <opus><title>Nested</title><opus-link xlink:href="nested.xml"/></opus>
</opus>"""
    result = parse_musicxml_auxiliary(source)
    assert isinstance(result, OpusCatalog)
    assert result.items[0].kind == "score"
    assert result.items[0].link is not None
    assert result.items[0].link.href == "one.musicxml"
    assert result.items[0].new_page is True
    assert result.items[1].title == "Nested"
    assert result.items[1].children[0].link is not None
    assert result.items[1].children[0].link.href == "nested.xml"
    assert not validate_auxiliary_document(result)


@pytest.mark.parametrize(
    ("version", "expected_entries"),
    (("3.0", 886), ("3.1", 886), ("4.0", 894), ("4.1-draft", 908)),
)
def test_every_standard_sound_catalog_maps_completely(version: str, expected_entries: int) -> None:
    """TEST-MXML-AUXILIARY-003: pinned sound catalogs keep every mapping row."""

    path = resource_root() / version / "schema" / "sounds.xml"
    result = parse_musicxml_auxiliary(path.read_bytes(), logical_name=path.name)
    assert isinstance(result, SoundCatalog)
    assert len(result.entries) == expected_entries
    assert len({entry.id for entry in result.entries}) == expected_entries
    assert not validate_auxiliary_document(result)


def test_invalid_links_fail_closed_in_canonical_validation() -> None:
    """TEST-MXML-AUXILIARY-004: empty outgoing targets cannot become canonical."""

    score = parse_musicxml_timeline(_linked_score()).score
    invalid = replace(score, work_opus=ExternalLink(href=""))
    assert {issue.code for issue in validate_temporal_score(invalid)} == {"TEMPORAL_WORK_OPUS"}


def test_score_root_cannot_enter_auxiliary_mapper() -> None:
    """TEST-MXML-AUXILIARY-005: document-family dispatch fails closed."""

    validated = validate_musicxml_source(_linked_score())
    with pytest.raises(ValueError, match="not an auxiliary"):
        from teachmemusic.score.musicxml.auxiliary_mapping import map_auxiliary_document

        map_auxiliary_document(validated)
