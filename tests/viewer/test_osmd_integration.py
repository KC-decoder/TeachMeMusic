"""Opt-in browser proofs for canonical renderer payloads."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from teachmemusic.score import CanonicalMusicPackage, parse_musicxml_package
from teachmemusic.viewer import build_notation_bundle, viewer_bundle_to_json

_ROOT = Path(__file__).parents[2]
_WEB = _ROOT / "web"
_FIXTURE = (
    _ROOT
    / "tests"
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-001-Hot-Cross-Buns"
    / "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
)
_HAPPY_BIRTHDAY_FIXTURE = (
    _ROOT
    / "tests"
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-002-Happy-Birthday"
    / "happy-birthday-to-you-c-major.mxl"
)
_CLAIR_DE_LUNE_FIXTURE = (
    _ROOT
    / "tests"
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-003-Clair-de-Lune"
    / "clair-de-lune-debussy.mxl"
)
_MOONLIGHT_SONATA_FIXTURE = (
    _ROOT
    / "tests"
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-004-Moonlight-Sonata"
    / "beethoven-piano-sonata-no-14-moonlight.mxl"
)
_DEUX_ARABESQUES_FIXTURE = (
    _ROOT
    / "tests"
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-005-Deux-Arabesques"
    / "debussy-deux-arabesques.mxl"
)
_BROWSER_ENABLED = os.environ.get("TMM_RUN_BROWSER_TESTS") == "1"


def _render_package(package: CanonicalMusicPackage, tmp_path: Path) -> dict[str, Any]:
    npm = shutil.which("npm")
    assert npm is not None, "Node/npm is required for the opt-in OSMD proof"
    assert (_WEB / "node_modules" / "opensheetmusicdisplay").is_dir(), (
        "run npm ci --omit=optional in web/ before the OSMD proof"
    )
    bundle = build_notation_bundle(package)
    bundle_path = tmp_path / "viewer-bundle.json"
    bundle_path.write_text(viewer_bundle_to_json(bundle), encoding="utf-8")

    completed = subprocess.run(
        [npm, "run", "test:osmd-proof", "--", str(bundle_path)],
        cwd=_WEB,
        check=True,
        capture_output=True,
        text=True,
    )
    result: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])

    return result


def _render_fixture(fixture: Path, tmp_path: Path) -> dict[str, Any]:
    package = parse_musicxml_package(fixture.read_bytes(), logical_name=fixture.name)
    return _render_package(package, tmp_path)


def _rhythmic_notation_package() -> CanonicalMusicPackage:
    source = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<score-partwise version="4.0"><part-list><score-part id="P1">'
        b'<part-name>Piano</part-name></score-part></part-list><part id="P1">'
        b'<measure number="1"><attributes><divisions>6</divisions>'
        b"<time><beats>2</beats><beat-type>4</beat-type></time>"
        b'<clef><sign>G</sign><line>2</line></clef></attributes><sound tempo="60"/>'
        b"<note><pitch><step>B</step><octave>3</octave></pitch><duration>12</duration>"
        b"<voice>1</voice><type>half</type></note><backup><duration>12</duration></backup>"
        b"<note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>"
        b"<voice>2</voice><type>eighth</type><time-modification>"
        b"<actual-notes>3</actual-notes>"
        b"<normal-notes>2</normal-notes></time-modification><notations>"
        b'<tuplet type="start"/></notations></note><note><pitch><step>D</step>'
        b"<octave>5</octave></pitch><duration>2</duration><voice>2</voice><type>eighth</type>"
        b"<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        b"</time-modification></note><note><pitch><step>E</step><octave>5</octave></pitch>"
        b"<duration>2</duration><voice>2</voice><type>eighth</type><time-modification>"
        b"<actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        b'</time-modification><notations><tuplet type="stop"/></notations></note>'
        b"<attributes><clef><sign>F</sign><line>4</line></clef></attributes>"
        b'<note><grace slash="yes"/><pitch><step>F</step><octave>4</octave></pitch>'
        b"<voice>2</voice><type>16th</type></note><note><pitch><step>G</step>"
        b"<octave>3</octave></pitch><duration>6</duration><voice>2</voice>"
        b"<type>quarter</type></note></measure></part>"
        b"</score-partwise>"
    )
    return parse_musicxml_package(source, logical_name="rhythmic-notation.musicxml")


def _note_attachment_package() -> CanonicalMusicPackage:
    source = (
        b'<?xml version="1.0" encoding="utf-8"?><score-partwise version="4.0">'
        b'<part-list><score-part id="P1"><part-name>Attached notation</part-name>'
        b'</score-part></part-list><part id="P1"><measure number="1"><attributes>'
        b"<divisions>1</divisions></attributes><note><pitch><step>C</step><octave>4</octave>"
        b'</pitch><duration>1</duration><tie type="start"/><type>quarter</type><notations>'
        b'<tied type="start"/><slur type="start" number="1" placement="above"/>'
        b'<articulations><staccato/></articulations><fermata type="upright"/>'
        b"</notations></note><note><pitch><step>C</step><octave>4</octave></pitch>"
        b'<duration>1</duration><tie type="stop"/><type>quarter</type><notations>'
        b'<tied type="stop"/><slur type="stop" number="1"/><ornaments>'
        b'<tremolo type="start">2</tremolo></ornaments></notations></note>'
        b"<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>"
        b'<type>quarter</type><notations><ornaments><tremolo type="stop">2</tremolo>'
        b"</ornaments></notations></note></measure></part></score-partwise>"
    )
    return parse_musicxml_package(source, logical_name="note-attachment.musicxml")


def _direction_package() -> CanonicalMusicPackage:
    source = (
        b'<?xml version="1.0" encoding="utf-8"?><score-partwise version="4.0">'
        b'<part-list><score-part id="P1"><part-name>Directions</part-name>'
        b'</score-part></part-list><part id="P1"><measure number="1"><attributes>'
        b'<divisions>1</divisions></attributes><direction placement="above">'
        b"<direction-type><words>dolce</words></direction-type><staff>1</staff>"
        b'</direction><direction placement="below"><direction-type>'
        b"<dynamics><p/></dynamics></direction-type><staff>1</staff></direction>"
        b'<direction placement="below"><direction-type><wedge type="crescendo" '
        b'number="1"/></direction-type><staff>1</staff></direction>'
        b"<note><rest/><duration>4</duration><type>whole</type></note></measure>"
        b'<measure number="2"><direction placement="below"><direction-type>'
        b'<wedge type="stop" number="1"/></direction-type><staff>1</staff></direction>'
        b"<note><rest/><duration>4</duration><type>whole</type></note></measure>"
        b"</part></score-partwise>"
    )
    return parse_musicxml_package(source, logical_name="directions.musicxml")


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_hot_cross_buns_renders_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-001: OSMD renders only the verified canonical payload."""

    result = _render_fixture(_FIXTURE, tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_happy_birthday_renders_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-002: OSMD renders the verified two-staff chord payload."""

    result = _render_fixture(_HAPPY_BIRTHDAY_FIXTURE, tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_rhythmic_notation_renders_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-003: OSMD accepts tuplets, grace, and a clef change."""

    result = _render_package(_rhythmic_notation_package(), tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_note_attachments_render_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-004: OSMD accepts ties, slurs, marks, and tremolos."""

    result = _render_package(_note_attachment_package(), tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_directions_render_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-005: OSMD accepts words, dynamics, and hairpins."""

    result = _render_package(_direction_package(), tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_clair_de_lune_renders_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-006: OSMD renders the complete canonical Clair de Lune."""

    result = _render_fixture(_CLAIR_DE_LUNE_FIXTURE, tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_moonlight_sonata_renders_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-007: OSMD renders the complete canonical Moonlight Sonata."""

    result = _render_fixture(_MOONLIGHT_SONATA_FIXTURE, tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True


@pytest.mark.skipif(
    not _BROWSER_ENABLED,
    reason="set TMM_RUN_BROWSER_TESTS=1 after npm ci to run the OSMD browser proof",
)
def test_generated_deux_arabesques_renders_headlessly_in_osmd(tmp_path: Path) -> None:
    """TEST-VIEWER-OSMD-008: OSMD renders the complete canonical Deux arabesques."""

    result = _render_fixture(_DEUX_ARABESQUES_FIXTURE, tmp_path)

    assert result["rendered"] is True
    assert result["svg_count"] >= 1
    assert result["graphical_element_count"] >= 1
    assert result["title_present"] is True
