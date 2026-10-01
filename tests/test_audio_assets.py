from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_app_audio_001_local_piano_assets_match_the_licensed_manifest() -> None:
    """TEST-APP-AUDIO-001: every shipped sample is attributed and hash-locked."""

    sample_dir = Path(__file__).parents[1] / "web" / "public" / "audio" / "salamander"
    manifest = json.loads((sample_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["instrument"] == "Salamander Grand Piano V3"
    assert manifest["creator"] == "Alexander Holm"
    assert manifest["license"] == "CC-BY-3.0"
    assert len(manifest["files"]) == 30
    assert set(manifest["files"]) == {path.name for path in sample_dir.glob("*.mp3")}
    for filename, expected in manifest["files"].items():
        assert hashlib.sha256((sample_dir / filename).read_bytes()).hexdigest() == expected
