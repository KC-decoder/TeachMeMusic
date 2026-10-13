"""Task 5C local application boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from teachmemusic.app import AppBudgets, create_app
from teachmemusic.app.sessions import SessionStore

FIXTURE = (
    Path(__file__).parents[1] / "fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/"
    "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
)
TOKEN = "test-launch-token"
TOKEN_HEADER = {"X-TeachMeMusic-Token": TOKEN}


def _upload(client: TestClient) -> object:
    return client.post(
        "/api/v1/viewer-sessions",
        headers=TOKEN_HEADER,
        files={"score": (FIXTURE.name, FIXTURE.read_bytes(), "application/vnd.recordare.musicxml")},
    )


def test_app_001_health_config_auth_and_origin() -> None:
    """TEST-APP-001: reads are public; every mutation needs token and same origin."""

    with TestClient(create_app(launch_token=TOKEN)) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
        assert client.get("/api/v1/config").json()["launch_token"] == TOKEN
        assert client.post("/api/v1/viewer-sessions").status_code == 403
        response = client.post(
            "/api/v1/viewer-sessions",
            headers={**TOKEN_HEADER, "Origin": "https://attacker.example"},
        )
        assert response.status_code == 403
        assert response.json()["diagnostics"][0]["code"] == "APP_ORIGIN_REJECTED"
        assert "access-control-allow-origin" not in response.headers


def test_app_002_ingests_and_projects_only_the_canonical_session() -> None:
    """TEST-APP-002: valid upload creates a canonical-only projected bundle."""

    store = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        response = _upload(client)
        assert response.status_code == 201
        manifest = response.json()
        assert manifest["session_id"] == "session-1"
        assert manifest["scores"][0]["title"] == "Hot Cross Buns"

        retained = store.get("session-1")
        assert not hasattr(retained, "source_bytes")
        assert not hasattr(retained, "upload")
        bundle = client.post(
            "/api/v1/viewer-sessions/session-1/bundles",
            headers=TOKEN_HEADER,
            json={
                "score_id": manifest["scores"][0]["score_id"],
                "fallback_tempo_qpm": 120,
            },
        )
        assert bundle.status_code == 200
        result = bundle.json()
        assert result["notation"]["title"] == "Hot Cross Buns"
        assert len(result["notation"]["renderer"]["anchors"]) == 30
        assert len(result["playback"]["notes"]) == 17
        assert FIXTURE.read_bytes() not in bundle.content


def test_app_003_failed_upload_preserves_last_valid_session() -> None:
    """TEST-APP-003: invalid replacement input cannot damage valid state."""

    store = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        assert _upload(client).status_code == 201
        failed = client.post(
            "/api/v1/viewer-sessions",
            headers=TOKEN_HEADER,
            files={"score": ("broken.musicxml", b"not XML", "application/xml")},
        )
        assert failed.status_code == 422
        assert len(store) == 1
        assert store.get("session-1").package.id.value.startswith("package:")


def test_app_004_rejects_unbounded_or_unsupported_input() -> None:
    """TEST-APP-004: request, upload, filename, and type budgets fail closed."""

    budgets = AppBudgets(max_upload_bytes=8, max_request_bytes=1_024)
    with TestClient(create_app(launch_token=TOKEN, budgets=budgets)) as client:
        oversized = client.post(
            "/api/v1/viewer-sessions",
            headers=TOKEN_HEADER,
            files={"score": ("score.musicxml", b"123456789", "application/xml")},
        )
        assert oversized.status_code == 413
        assert oversized.json()["diagnostics"][0]["code"] == "APP_UPLOAD_TOO_LARGE"
        unsupported = client.post(
            "/api/v1/viewer-sessions",
            headers=TOKEN_HEADER,
            files={"score": ("score.pdf", b"small", "application/pdf")},
        )
        assert unsupported.status_code == 415


def test_app_005_enforces_session_expiry_capacity_and_deletion() -> None:
    """TEST-APP-005: storage is finite, expiring, and explicitly erasable."""

    now = [0.0]
    ids = iter(("one", "two"))
    store = SessionStore(
        max_sessions=1,
        ttl_seconds=10,
        clock=lambda: now[0],
        id_factory=lambda: next(ids),
    )
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        first = _upload(client)
        assert first.status_code == 201
        assert _upload(client).status_code == 429
        assert client.delete("/api/v1/viewer-sessions/one", headers=TOKEN_HEADER).status_code == 204
        assert len(store) == 0
        assert _upload(client).status_code == 201
        now[0] = 10.0
        response = client.post(
            "/api/v1/viewer-sessions/two/bundles",
            headers=TOKEN_HEADER,
            json={"score_id": "irrelevant"},
        )
        assert response.status_code == 404
        assert len(store) == 0


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"max_anchors": 1}, "APP_ANCHOR_LIMIT"),
        ({"max_notes": 1}, "APP_NOTE_LIMIT"),
        ({"max_response_bytes": 100}, "APP_RESPONSE_LIMIT"),
    ],
)
def test_app_006_enforces_projection_budgets(overrides: dict[str, int], expected_code: str) -> None:
    """TEST-APP-006: generated output cannot exceed declared process budgets."""

    budgets = AppBudgets(**overrides)
    with TestClient(create_app(launch_token=TOKEN, budgets=budgets)) as client:
        manifest = _upload(client).json()
        response = client.post(
            f"/api/v1/viewer-sessions/{manifest['session_id']}/bundles",
            headers=TOKEN_HEADER,
            json={
                "score_id": manifest["scores"][0]["score_id"],
                "fallback_tempo_qpm": 120,
            },
        )
        assert response.status_code == 413
        assert response.json()["diagnostics"][0]["code"] == expected_code


def test_app_007_serves_the_compiled_same_origin_shell(tmp_path: Path) -> None:
    """TEST-APP-007: the browser shell is served from the API origin."""

    (tmp_path / "index.html").write_text("<main>TeachMeMusic shell</main>", encoding="utf-8")
    with TestClient(create_app(launch_token=TOKEN, static_directory=tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "TeachMeMusic shell" in response.text


def test_app_008_generates_and_projects_an_exact_beginner_exercise() -> None:
    """TEST-APP-008: lesson and exercise endpoints remain canonical and bounded."""

    store = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        manifest = _upload(client).json()
        score_id = manifest["scores"][0]["score_id"]
        plan_response = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-plans",
            headers=TOKEN_HEADER,
            json={"score_id": score_id},
        )
        assert plan_response.status_code == 200
        plan = plan_response.json()["plan"]
        assert len(plan["nodes"]) == len(plan["exercises"]) == 16
        assert plan["track"] == "beginner"

        exercise_id = plan["exercises"][2]["id"]
        projected = client.post(
            f"/api/v1/viewer-sessions/session-1/teaching-plans/{plan['id']}"
            f"/exercises/{exercise_id}",
            headers=TOKEN_HEADER,
            json={"score_id": score_id, "tempo_bpm": 48, "count_in_enabled": True},
        )
        assert projected.status_code == 200
        presentation = projected.json()["presentation"]
        assert presentation["exercise_id"] == exercise_id
        assert presentation["measure_numbers"] == ["1", "2"]
        assert presentation["aid_state"]["tempo_bpm"] == {"numerator": 48, "denominator": 1}
        assert presentation["aid_state"]["count_in_beats"] == 4
        assert presentation["demonstration"]["notes"]
        assert {
            source["event_id"]
            for note in presentation["demonstration"]["notes"]
            for source in note["source_events"]
        } <= set(presentation["event_ids"])

        changed = client.post(
            f"/api/v1/viewer-sessions/session-1/teaching-plans/lesson-plan:changed"
            f"/exercises/{exercise_id}",
            headers=TOKEN_HEADER,
            json={"score_id": score_id},
        )
        assert changed.status_code == 409
        assert changed.json()["diagnostics"][0]["code"] == "APP_TEACHING_PLAN_CHANGED"


def test_app_009_runs_exports_resumes_and_continues_the_closed_loop() -> None:
    """TEST-APP-009: a no-learning rehearsal crosses every authoritative boundary."""

    store = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        manifest = _upload(client).json()
        score_id = manifest["scores"][0]["score_id"]
        plan = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-plans",
            headers=TOKEN_HEADER,
            json={"score_id": score_id},
        ).json()["plan"]
        exercise = plan["exercises"][2]
        projected = client.post(
            f"/api/v1/viewer-sessions/session-1/teaching-plans/{plan['id']}"
            f"/exercises/{exercise['id']}",
            headers=TOKEN_HEADER,
            json={"score_id": score_id},
        ).json()["presentation"]

        started = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-runs",
            headers=TOKEN_HEADER,
            json={
                "score_id": score_id,
                "plan_id": plan["id"],
                "authorization_approved": True,
                "capture_midi": True,
                "capture_self_report": True,
                "allow_export": True,
                "audit_outcome": "pass-no-change",
                "source_faithful": True,
                "musically_coherent": True,
                "safe": True,
                "executable": True,
                "reviewer": "project-owner",
            },
        )
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        assert started.json()["inspection"]["event_count"] == 4

        events: list[dict[str, object]] = []
        attempt_start = 1_000_000
        serial = 0
        for note in projected["demonstration"]["notes"]:
            for kind, timestamp, velocity in (
                ("note-on", attempt_start + note["start_microseconds"], 80),
                ("note-off", attempt_start + note["end_microseconds"], 0),
            ):
                serial += 1
                events.append(
                    {
                        "id": f"midi-event:{serial:04d}",
                        "raw_message_id": None,
                        "kind": kind,
                        "timestamp_microseconds": timestamp,
                        "channel": 1,
                        "note": note["midi_pitch"],
                        "velocity": velocity,
                        "controller": None,
                        "value": None,
                        "detail": None,
                    }
                )
        events.sort(key=lambda item: (item["timestamp_microseconds"], item["id"]))
        attempt_end = max(int(item["timestamp_microseconds"]) for item in events) + 1
        submission = {
            "score_id": score_id,
            "plan_id": plan["id"],
            "exercise_id": exercise["id"],
            "practice_mode": "follow-pitch",
            "support_state_id": exercise["initial_support"]["id"],
            "started_at_utc": "2026-10-02T12:00:00Z",
            "start_microseconds": attempt_start,
            "end_microseconds": attempt_end,
            "completion": "completed",
            "calibration": {
                "version": "casio-browser-calibration-v1",
                "device_id": "casio-px-770",
                "input_name": "CASIO USB-MIDI",
                "timestamp_origin": "browser-monotonic-microseconds",
                "pitch_numbering_confirmed": True,
                "sustain_available": True,
                "clock_offset_microseconds": 0,
                "clock_jitter_microseconds": 3_400,
                "timing_window_microseconds": None,
                "chord_window_microseconds": None,
                "limitations": ["No physical or acoustic latency was measured."],
                "approved": True,
                "approved_at_utc": "2026-10-02T11:59:00Z",
            },
            "raw_messages": [],
            "normalized_events": events,
            "diagnostics": [],
        }
        first = client.post(
            f"/api/v1/teaching-runs/{run_id}/attempts",
            headers=TOKEN_HEADER,
            json=submission,
        )
        assert first.status_code == 200, first.text
        assert first.json()["decision"]["action"] == "integrate"
        assert first.json()["mastery"]["action"] == "exercise-complete"
        assert first.json()["mastery"]["green_percent"] == 100
        assert first.json()["feedback"]["action"]
        assert first.json()["inspection"]["attempt_count"] == 1

        exported = client.post(
            f"/api/v1/teaching-runs/{run_id}/exports",
            headers=TOKEN_HEADER,
        )
        assert exported.status_code == 200
        assert exported.json()["evidence"]["manifest"]["score_id"] == score_id
        assert "score-partwise" not in exported.text

        assert (
            client.delete(f"/api/v1/teaching-runs/{run_id}", headers=TOKEN_HEADER).status_code
            == 204
        )
        resumed = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-runs/import",
            headers=TOKEN_HEADER,
            json={"score_id": score_id, "archive": exported.json()},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["inspection"]["attempt_count"] == 1

        second = client.post(
            f"/api/v1/teaching-runs/{run_id}/attempts",
            headers=TOKEN_HEADER,
            json={**submission, "started_at_utc": "2026-10-02T12:01:00Z"},
        )
        assert second.status_code == 200, second.text
        assert second.json()["decision"]["action"] == "integrate"
        assert second.json()["mastery"]["action"] == "exercise-complete"
        assert second.json()["next_support"] is None


def test_app_010_rejects_partial_gate_zero_approval() -> None:
    """TEST-APP-010: a run cannot start with any owner precondition omitted."""

    store = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        manifest = _upload(client).json()
        score_id = manifest["scores"][0]["score_id"]
        plan = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-plans",
            headers=TOKEN_HEADER,
            json={"score_id": score_id},
        ).json()["plan"]
        response = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-runs",
            headers=TOKEN_HEADER,
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
                "safe": False,
                "executable": True,
                "reviewer": "project-owner",
            },
        )
        assert response.status_code == 422
        assert response.json()["diagnostics"][0]["code"] == "APP_GATE_ZERO_PRECONDITION"


def test_app_011_keeps_capture_and_export_authorization_granular() -> None:
    """TEST-APP-011: MIDI-only local capture can start while export remains declined."""

    store = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    with TestClient(create_app(launch_token=TOKEN, store=store)) as client:
        manifest = _upload(client).json()
        score_id = manifest["scores"][0]["score_id"]
        plan = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-plans",
            headers=TOKEN_HEADER,
            json={"score_id": score_id},
        ).json()["plan"]
        response = client.post(
            "/api/v1/viewer-sessions/session-1/teaching-runs",
            headers=TOKEN_HEADER,
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
                "reviewer": "project-owner",
            },
        )

        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        evidence = client.app.state.teaching_run_store.evidence(run_id)
        assert evidence.data_authorization.capture_midi is True
        assert evidence.data_authorization.capture_self_report is False
        assert evidence.data_authorization.allow_export is False
        exported = client.post(
            f"/api/v1/teaching-runs/{run_id}/exports",
            headers=TOKEN_HEADER,
        )
        assert exported.status_code == 422
        assert exported.json()["diagnostics"][0]["code"] == "EVIDENCE_EXPORT_DECLINED"
