"""Task 9O.4 production integration tests for the DEV-009 curriculum."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from teachmemusic.app import create_app
from teachmemusic.app.curriculum_runs import default_curriculum_store
from teachmemusic.app.sessions import SessionStore

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-002-Happy-Birthday"
    / "happy-birthday-to-you-c-major.mxl"
)
_TOKEN = "task-9o4-token"
_HEADERS = {"X-TeachMeMusic-Token": _TOKEN}


def _upload(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/viewer-sessions",
        headers=_HEADERS,
        files={
            "score": (
                _FIXTURE.name,
                _FIXTURE.read_bytes(),
                "application/vnd.recordare.musicxml",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _perfect_attempt(
    presentation: dict[str, object],
    *,
    score_id: str,
    support_id: str,
) -> dict[str, object]:
    playback = presentation["demonstration"]
    assert isinstance(playback, dict)
    notes = playback["notes"]
    assert isinstance(notes, list) and notes
    start = 1_000_000
    normalized: list[dict[str, object]] = []
    for index, note in enumerate(notes):
        assert isinstance(note, dict)
        onset = int(note["start_microseconds"])
        end = int(note["end_microseconds"])
        pitch = int(note["midi_pitch"])
        normalized.extend(
            (
                {
                    "id": f"midi:{index}:on",
                    "raw_message_id": None,
                    "kind": "note-on",
                    "timestamp_microseconds": start + onset + index,
                    "channel": 1,
                    "note": pitch,
                    "velocity": 80,
                    "controller": None,
                    "value": None,
                    "detail": None,
                },
                {
                    "id": f"midi:{index}:off",
                    "raw_message_id": None,
                    "kind": "note-off",
                    "timestamp_microseconds": start + end + index,
                    "channel": 1,
                    "note": pitch,
                    "velocity": 0,
                    "controller": None,
                    "value": None,
                    "detail": None,
                },
            )
        )
    normalized.sort(key=lambda item: (int(item["timestamp_microseconds"]), str(item["id"])))
    tempo = presentation["aid_state"]
    assert isinstance(tempo, dict)
    fraction = tempo["tempo_bpm"]
    assert isinstance(fraction, dict)
    return {
        "score_id": score_id,
        "plan_id": presentation["plan_id"],
        "exercise_id": presentation["exercise_id"],
        "practice_mode": presentation["practice_modes"][0],
        "support_state_id": support_id,
        "tempo_bpm": int(fraction["numerator"]) / int(fraction["denominator"]),
        "count_in_enabled": True,
        "started_at_utc": "2026-10-13T12:00:00Z",
        "start_microseconds": start,
        "end_microseconds": int(normalized[-1]["timestamp_microseconds"]) + 1_000,
        "completion": "completed",
        "calibration": {
            "version": "casio-browser-calibration-v1",
            "device_id": "device:test-px770",
            "input_name": "Test PX-770",
            "timestamp_origin": "monotonic-microseconds",
            "pitch_numbering_confirmed": True,
            "sustain_available": True,
            "clock_offset_microseconds": 0,
            "clock_jitter_microseconds": 1_000,
            "timing_window_microseconds": 50_000,
            "chord_window_microseconds": 50_000,
            "limitations": [],
            "approved": True,
            "approved_at_utc": "2026-10-13T11:59:00Z",
        },
        "raw_messages": [],
        "normalized_events": normalized,
        "diagnostics": [],
        "unsafe_condition": None,
    }


def test_curriculum_production_route_uses_dev009_for_a_real_attempt(tmp_path: Path) -> None:
    """TEST-CURR-PRODUCTION-001: browser route reaches DEV-009 evidence and reward."""

    sessions = SessionStore(
        max_sessions=1,
        ttl_seconds=1_800,
        id_factory=lambda: "session:production-happy-birthday",
    )
    curriculum = default_curriculum_store(tmp_path / "evidence")
    app = create_app(
        launch_token=_TOKEN,
        store=sessions,
        curriculum_store=curriculum,
    )
    with TestClient(app) as client:
        upload = _upload(client)
        session_id = str(upload["session_id"])
        score = upload["scores"][0]
        assert isinstance(score, dict)
        score_id = str(score["score_id"])
        plan_response = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-plans",
            headers=_HEADERS,
            json={"score_id": score_id},
        )
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()["plan"]
        assert plan["policy_identity"] == "TMM-DETERMINISTIC-POLICY-0.2"
        assert [item["boundary_reason"] for item in plan["exercises"]] == [
            "tempo-diagnostic for upper-layer",
            "tempo-diagnostic for lower-layer",
            "tempo-diagnostic for combined",
        ]
        first = plan["exercises"][0]
        projection_response = client.post(
            (
                f"/api/v1/viewer-sessions/{session_id}/curriculum-plans/"
                f"{plan['id']}/exercises/{first['id']}"
            ),
            headers=_HEADERS,
            json={"score_id": score_id},
        )
        assert projection_response.status_code == 200, projection_response.text
        presentation = projection_response.json()["presentation"]
        assert presentation["curriculum"]["stage"]["kind"] == "tempo-diagnostic"
        assert presentation["curriculum"]["presentation"]["notation_condition"] == ("upper-layer")

        run_response = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-runs",
            headers=_HEADERS,
            json={
                "score_id": score_id,
                "plan_id": plan["id"],
                "authorization_approved": True,
                "capture_midi": True,
                "capture_self_report": False,
                "allow_export": False,
                "audit_outcome": "pass-no-change",
                "source_faithful": True,
                "musically_coherent": True,
                "safe": True,
                "executable": True,
                "reviewer": "Project owner",
            },
        )
        assert run_response.status_code == 200, run_response.text
        run_id = run_response.json()["run_id"]
        submission = _perfect_attempt(
            presentation,
            score_id=score_id,
            support_id=first["initial_support"]["id"],
        )
        attempt_response = client.post(
            f"/api/v1/curriculum-runs/{run_id}/attempts",
            headers=_HEADERS,
            json=submission,
        )
        assert attempt_response.status_code == 200, attempt_response.text
        result = attempt_response.json()
        assert result["curriculum"]["mastery"]["status"] == "mastered"
        assert result["curriculum"]["research_reward"]["components"]
        assert result["inspection"]["attempt_count"] == 1
        assert result["inspection"]["curriculum"]["storage"]["chunk_count"] >= 1
        assert result["presentation"]["curriculum"]["stage"]["order"] == 1
        denied = client.post(
            f"/api/v1/curriculum-runs/{run_id}/exports",
            headers=_HEADERS,
        )
        assert denied.status_code == 422
        assert denied.json()["diagnostics"][0]["code"] == ("TMM-STORE-AUTHORIZATION-REQUIRED")


def test_curriculum_production_export_is_explicit_and_integrity_checked(tmp_path: Path) -> None:
    """TEST-CURR-PRODUCTION-002: export remains an independent opt-in capability."""

    sessions = SessionStore(
        max_sessions=1,
        ttl_seconds=1_800,
        id_factory=lambda: "session:curriculum-export",
    )
    curriculum = default_curriculum_store(tmp_path / "evidence")
    with TestClient(
        create_app(
            launch_token=_TOKEN,
            store=sessions,
            curriculum_store=curriculum,
        )
    ) as client:
        upload = _upload(client)
        session_id = str(upload["session_id"])
        score = upload["scores"][0]
        assert isinstance(score, dict)
        score_id = str(score["score_id"])
        plan = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-plans",
            headers=_HEADERS,
            json={"score_id": score_id},
        ).json()["plan"]
        run = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-runs",
            headers=_HEADERS,
            json={
                "score_id": score_id,
                "plan_id": plan["id"],
                "authorization_approved": True,
                "capture_midi": True,
                "capture_self_report": False,
                "allow_export": True,
                "audit_outcome": "pass-no-change",
                "source_faithful": True,
                "musically_coherent": True,
                "safe": True,
                "executable": True,
                "reviewer": "Project owner",
            },
        ).json()
        exported = client.post(
            f"/api/v1/curriculum-runs/{run['run_id']}/exports",
            headers=_HEADERS,
        )
        assert exported.status_code == 200, exported.text
        assert exported.json()["type"] == "curriculum-evidence-store-export"
        assert exported.json()["manifest"]["authorization"] == {
            "allow_export": True,
            "approved": True,
            "capture_midi": True,
            "capture_self_report": False,
        }


def test_curriculum_tempo_diagnostics_unlock_the_real_acquisition_graph(tmp_path: Path) -> None:
    """TEST-CURR-PRODUCTION-003: real probes replace diagnostics with seven stages."""

    sessions = SessionStore(
        max_sessions=1,
        ttl_seconds=1_800,
        id_factory=lambda: "session:curriculum-tempo-probes",
    )
    with TestClient(
        create_app(
            launch_token=_TOKEN,
            store=sessions,
            curriculum_store=default_curriculum_store(tmp_path / "evidence"),
        )
    ) as client:
        upload = _upload(client)
        session_id = str(upload["session_id"])
        score = upload["scores"][0]
        assert isinstance(score, dict)
        score_id = str(score["score_id"])
        plan = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-plans",
            headers=_HEADERS,
            json={"score_id": score_id},
        ).json()["plan"]
        first = plan["exercises"][0]
        presentation = client.post(
            (
                f"/api/v1/viewer-sessions/{session_id}/curriculum-plans/"
                f"{plan['id']}/exercises/{first['id']}"
            ),
            headers=_HEADERS,
            json={"score_id": score_id},
        ).json()["presentation"]
        run = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-runs",
            headers=_HEADERS,
            json={
                "score_id": score_id,
                "plan_id": plan["id"],
                "authorization_approved": True,
                "capture_midi": True,
                "capture_self_report": False,
                "allow_export": True,
                "audit_outcome": "pass-no-change",
                "source_faithful": True,
                "musically_coherent": True,
                "safe": True,
                "executable": True,
                "reviewer": "Project owner",
            },
        ).json()

        result: dict[str, object] = {}
        for index in range(3):
            support = presentation["curriculum"]["support"]
            submission = _perfect_attempt(
                presentation,
                score_id=score_id,
                support_id=support["id"],
            )
            submission["normalized_events"] = [
                {**item, "id": f"{item['id']}:{index}"} for item in submission["normalized_events"]
            ]
            response = client.post(
                f"/api/v1/curriculum-runs/{run['run_id']}/attempts",
                headers=_HEADERS,
                json=submission,
            )
            assert response.status_code == 200, f"attempt {index}: {response.text}"
            result = response.json()
            presentation = result["presentation"]

        assert result["inspection"]["curriculum"]["tempo_diagnostic_count"] == 3
        assert len(result["plan"]["exercises"]) == 7
        assert presentation["curriculum"]["stage"]["kind"] == "component-acquisition"
        assert presentation["curriculum"]["presentation"]["notation_condition"] == ("upper-layer")


def test_curriculum_attempt_offsets_remain_monotonic_across_exercises(tmp_path: Path) -> None:
    """TEST-CURR-PRODUCTION-004: shorter exercises retain monotonic evidence time."""

    sessions = SessionStore(
        max_sessions=1,
        ttl_seconds=1_800,
        id_factory=lambda: "session:curriculum-offsets",
    )
    curriculum = default_curriculum_store(tmp_path / "evidence")
    with TestClient(
        create_app(
            launch_token=_TOKEN,
            store=sessions,
            curriculum_store=curriculum,
        )
    ) as client:
        upload = _upload(client)
        session_id = str(upload["session_id"])
        score = upload["scores"][0]
        assert isinstance(score, dict)
        score_id = str(score["score_id"])
        plan = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-plans",
            headers=_HEADERS,
            json={"score_id": score_id},
        ).json()["plan"]
        presentation = client.post(
            (
                f"/api/v1/viewer-sessions/{session_id}/curriculum-plans/"
                f"{plan['id']}/exercises/{plan['exercises'][0]['id']}"
            ),
            headers=_HEADERS,
            json={"score_id": score_id},
        ).json()["presentation"]
        run = client.post(
            f"/api/v1/viewer-sessions/{session_id}/curriculum-runs",
            headers=_HEADERS,
            json={
                "score_id": score_id,
                "plan_id": plan["id"],
                "authorization_approved": True,
                "capture_midi": True,
                "capture_self_report": False,
                "allow_export": True,
                "audit_outcome": "pass-no-change",
                "source_faithful": True,
                "musically_coherent": True,
                "safe": True,
                "executable": True,
                "reviewer": "Project owner",
            },
        ).json()

        result: dict[str, object] = {}
        for index in range(3):
            support = presentation["curriculum"]["support"]
            submission = _perfect_attempt(
                presentation,
                score_id=score_id,
                support_id=support["id"],
            )
            submission["normalized_events"] = [
                {**item, "id": f"{item['id']}:{index}"} for item in submission["normalized_events"]
            ]
            response = client.post(
                f"/api/v1/curriculum-runs/{run['run_id']}/attempts",
                headers=_HEADERS,
                json=submission,
            )
            assert response.status_code == 200, f"progression attempt {index}: {response.text}"
            result = response.json()
            presentation = result["presentation"]
        assert result["inspection"]["attempt_count"] == 3
        assert result["inspection"]["curriculum"]["storage"]["record_count"] > 3
