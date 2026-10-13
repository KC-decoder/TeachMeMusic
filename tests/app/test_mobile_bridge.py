"""DEV-007 secure mobile bridge and integrated teaching-flow tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from teachmemusic.app import (
    BridgeMessage,
    MobileBridgeError,
    MobileBridgeStore,
    MobileNetworkPolicy,
    create_app,
    create_mobile_companion_app,
)
from teachmemusic.app.mobile_server import (
    companion_origin,
    create_private_network_socket,
    private_interface_address,
    require_tls_file,
)
from teachmemusic.app.sessions import SessionStore
from teachmemusic.app.teaching_runs import TeachingRunStore

TOKEN = "owner-launch-token"
TOKEN_HEADER = {"X-TeachMeMusic-Token": TOKEN}
ORIGIN = "https://192.168.1.44:8443"
FIXTURE = (
    Path(__file__).parents[1] / "fixtures/scores/TMM-REF-CANDIDATE-001-Hot-Cross-Buns/"
    "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
)


def _secrets() -> Iterator[str]:
    for name in (
        "phone-capability",
        "bridge-capability",
        "bridge-token",
        "phone-token",
        "spare-token",
    ):
        yield f"{name}-0123456789-abcdefghijklmnopqrstuvwxyz"


def _store(*, clock: list[float] | None = None) -> MobileBridgeStore:
    values = _secrets()
    current = clock if clock is not None else [100.0]
    return MobileBridgeStore(
        clock=lambda: current[0],
        id_factory=lambda: "pairing-one",
        secret_factory=lambda: next(values),
    )


def _clients(
    bridge: MobileBridgeStore,
) -> tuple[TestClient, TestClient]:
    owner = TestClient(
        create_app(
            launch_token=TOKEN,
            mobile_bridge=bridge,
            mobile_companion_origin=ORIGIN,
        )
    )
    phone = TestClient(
        create_mobile_companion_app(
            bridge=bridge,
            policy=MobileNetworkPolicy(public_origin=ORIGIN),
        ),
        base_url=ORIGIN,
    )
    return owner, phone


def _pair(owner: TestClient, phone: TestClient) -> tuple[str, str]:
    created = owner.post(
        "/api/v1/mobile-pairings",
        headers=TOKEN_HEADER,
        json={"ttl_seconds": 60},
    )
    assert created.status_code == 200
    offer = created.json()
    bridge_claim = owner.post(
        "/api/v1/mobile-pairings/pairing-one/bridge-claims",
        headers=TOKEN_HEADER,
        json={"capability": offer["bridge_capability"]},
    )
    assert bridge_claim.status_code == 200
    phone_claim = phone.post(
        "/api/v1/mobile/pairings/pairing-one/phone-claims",
        headers={"Origin": ORIGIN},
        json={"capability": offer["phone_capability"]},
    )
    assert phone_claim.status_code == 200
    return bridge_claim.json()["bridge_token"], phone_claim.json()["phone_token"]


def test_mobile_004_store_is_role_bounded_ordered_expiring_and_stale_safe() -> None:
    """TEST-APP-MOBILE-004: the pure store fails closed and clears stale notes."""

    clock = [100.0]
    bridge = _store(clock=clock)
    offer = bridge.create(ttl_seconds=60)
    bridge_token = bridge.claim(offer.id, role="midi-bridge", capability=offer.bridge_capability)
    phone_token = bridge.claim(offer.id, role="phone", capability=offer.phone_capability)
    bridge.publish(
        offer.id,
        token=bridge_token,
        message=BridgeMessage(
            sequence=1,
            sent_at_microseconds=1_000_000,
            connection="connected",
            active_notes=(60, 64),
        ),
    )
    assert bridge.snapshot(offer.id, phone_token=phone_token).active_notes == (60, 64)

    with pytest.raises(MobileBridgeError, match="duplicated") as duplicate:
        bridge.publish(
            offer.id,
            token=bridge_token,
            message=BridgeMessage(1, 1_000_001, "connected", (60,)),
        )
    assert duplicate.value.code == "MOBILE_SEQUENCE_REJECTED"
    with pytest.raises(MobileBridgeError) as wrong_role:
        bridge.publish(
            offer.id,
            token=phone_token,
            message=BridgeMessage(2, 1_000_002, "connected", (60,)),
        )
    assert wrong_role.value.code == "MOBILE_BRIDGE_TOKEN_INVALID"

    bridge.publish(
        offer.id,
        token=bridge_token,
        message=BridgeMessage(2, 1_000_002, "disconnected", ()),
    )
    disconnected = bridge.snapshot(offer.id, phone_token=phone_token)
    assert disconnected.availability == "disconnected"
    assert disconnected.active_notes == ()
    bridge.publish(
        offer.id,
        token=bridge_token,
        message=BridgeMessage(3, 1_000_003, "connected", (60, 64)),
    )

    clock[0] = 103.0
    stale = bridge.snapshot(offer.id, phone_token=phone_token)
    assert stale.availability == "stale"
    assert stale.active_notes == ()
    clock[0] = 160.0
    with pytest.raises(MobileBridgeError) as expired:
        bridge.snapshot(offer.id, phone_token=phone_token)
    assert expired.value.code == "MOBILE_PAIRING_EXPIRED"


def test_mobile_005_owner_and_phone_complete_one_sanitized_pairing() -> None:
    """TEST-APP-MOBILE-005: separate loopback and phone APIs exchange only live state."""

    bridge = _store()
    owner, phone = _clients(bridge)
    with owner, phone:
        bridge_token, phone_token = _pair(owner, phone)
        published = owner.post(
            "/api/v1/mobile-pairings/pairing-one/bridge-messages",
            headers={
                "Authorization": f"Bearer {bridge_token}",
                "Origin": "http://testserver",
            },
            json={
                "contract_version": "0.2.0",
                "kind": "midi-state",
                "sequence": 1,
                "sent_at_microseconds": 1_000_000,
                "connection": "connected",
                "active_notes": [60, 64],
                "capture": "idle",
                "capture_purpose": None,
                "calibration_approved": True,
            },
        )
        assert published.status_code == 204
        state = phone.get(
            "/api/v1/mobile/pairings/pairing-one/state",
            headers={"Authorization": f"Bearer {phone_token}"},
        )
        assert state.status_code == 200
        assert state.json() == {
            "mobile_contract_version": "0.2.0",
            "pairing_id": "pairing-one",
            "availability": "live",
            "sequence": 1,
            "active_notes": [60, 64],
            "age_microseconds": 0,
            "expires_in_seconds": 60,
            "capture": "idle",
            "capture_purpose": None,
            "calibration_approved": True,
        }
        assert state.headers["cache-control"] == "no-store"
        assert "default-src 'self'" in state.headers["content-security-policy"]
        assert phone.get("/api/v1/config").status_code == 404
        assert phone.post("/api/v1/viewer-sessions").status_code == 404


def test_mobile_006_host_origin_role_and_capacity_violations_fail_closed() -> None:
    """TEST-APP-MOBILE-006: host, origin, role, and one-client limits are enforced."""

    bridge = _store()
    owner, phone = _clients(bridge)
    with owner, phone:
        created = owner.post(
            "/api/v1/mobile-pairings",
            headers=TOKEN_HEADER,
            json={"ttl_seconds": 60},
        ).json()
        assert (
            owner.post(
                "/api/v1/mobile-pairings",
                headers=TOKEN_HEADER,
                json={"ttl_seconds": 60},
            ).json()["diagnostics"][0]["code"]
            == "MOBILE_PAIRING_CAPACITY"
        )
        missing_origin = phone.post(
            "/api/v1/mobile/pairings/pairing-one/phone-claims",
            json={"capability": created["phone_capability"]},
        )
        assert missing_origin.json()["diagnostics"][0]["code"] == "MOBILE_ORIGIN_REQUIRED"
        wrong_host = phone.post(
            "/api/v1/mobile/pairings/pairing-one/phone-claims",
            headers={"Host": "attacker.example", "Origin": ORIGIN},
            json={"capability": created["phone_capability"]},
        )
        assert wrong_host.json()["diagnostics"][0]["code"] == "MOBILE_HOST_REJECTED"
        cross_site = phone.post(
            "/api/v1/mobile/pairings/pairing-one/phone-claims",
            headers={"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
            json={"capability": created["phone_capability"]},
        )
        assert cross_site.json()["diagnostics"][0]["code"] == "MOBILE_FETCH_SITE_REJECTED"
        claimed = phone.post(
            "/api/v1/mobile/pairings/pairing-one/phone-claims",
            headers={"Origin": ORIGIN},
            json={"capability": created["phone_capability"]},
        )
        assert claimed.status_code == 200
        repeated = phone.post(
            "/api/v1/mobile/pairings/pairing-one/phone-claims",
            headers={"Origin": ORIGIN},
            json={"capability": created["phone_capability"]},
        )
        assert repeated.json()["diagnostics"][0]["code"] == "MOBILE_ROLE_OCCUPIED"


def test_mobile_007_messages_are_bounded_strict_and_revocable() -> None:
    """TEST-APP-MOBILE-007: malformed, reordered, oversized, and revoked traffic stops."""

    bridge = _store()
    owner, phone = _clients(bridge)
    with owner, phone:
        bridge_token, phone_token = _pair(owner, phone)
        path = "/api/v1/mobile-pairings/pairing-one/bridge-messages"
        headers = {"Authorization": f"Bearer {bridge_token}"}
        malformed = owner.post(path, headers=headers, content=b"not-json")
        assert malformed.json()["diagnostics"][0]["code"] == "MOBILE_MESSAGE_INVALID"
        oversized = owner.post(path, headers=headers, content=b"x" * 4_097)
        assert oversized.json()["diagnostics"][0]["code"] == "MOBILE_MESSAGE_TOO_LARGE"
        invalid_notes = owner.post(
            path,
            headers=headers,
            json={
                "contract_version": "0.2.0",
                "kind": "midi-state",
                "sequence": 1,
                "sent_at_microseconds": 1,
                "connection": "connected",
                "active_notes": [64, 60],
                "capture": "idle",
                "capture_purpose": None,
                "calibration_approved": True,
            },
        )
        assert invalid_notes.json()["diagnostics"][0]["code"] == "MOBILE_ACTIVE_NOTES_INVALID"
        wrong_sequence = owner.post(
            path,
            headers=headers,
            json={
                "contract_version": "0.2.0",
                "kind": "midi-state",
                "sequence": 2,
                "sent_at_microseconds": 2,
                "connection": "disconnected",
                "active_notes": [],
                "capture": "idle",
                "capture_purpose": None,
                "calibration_approved": False,
            },
        )
        assert wrong_sequence.json()["diagnostics"][0]["code"] == "MOBILE_SEQUENCE_REJECTED"
        assert (
            owner.delete("/api/v1/mobile-pairings/pairing-one", headers=TOKEN_HEADER).status_code
            == 204
        )
        revoked = phone.get(
            "/api/v1/mobile/pairings/pairing-one/state",
            headers={"Authorization": f"Bearer {phone_token}"},
        )
        assert revoked.json()["diagnostics"][0]["code"] == "MOBILE_PAIRING_REVOKED"


def test_mobile_008_launcher_requires_private_interface_and_explicit_tls(tmp_path: Path) -> None:
    """TEST-APP-MOBILE-008: network launch cannot wildcard, use public IP, or omit TLS files."""

    assert str(private_interface_address("192.168.1.44")) == "192.168.1.44"
    assert str(private_interface_address("fd00::44")) == "fd00::44"
    assert companion_origin("192.168.1.44", 8443) == ORIGIN
    for rejected in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "::"):
        with pytest.raises(ValueError):
            private_interface_address(rejected)
        with pytest.raises(ValueError):
            create_private_network_socket(rejected, 8443)
    certificate = tmp_path / "cert.pem"
    certificate.write_text("test certificate", encoding="utf-8")
    assert require_tls_file(str(certificate), label="--certfile") == certificate
    with pytest.raises(ValueError, match="readable file"):
        require_tls_file(str(tmp_path / "missing.pem"), label="--keyfile")


def test_mobile_011_phone_commands_are_single_role_bounded_and_acknowledged() -> None:
    """TEST-APP-MOBILE-011: one phone command crosses to one bridge and back."""

    bridge = _store()
    offer = bridge.create(ttl_seconds=60)
    bridge_token = bridge.claim(
        offer.id,
        role="midi-bridge",
        capability=offer.bridge_capability,
    )
    phone_token = bridge.claim(offer.id, role="phone", capability=offer.phone_capability)
    queued = bridge.request_command(
        offer.id,
        phone_token=phone_token,
        kind="start-attempt",
    )
    assert queued.sequence == 1
    assert queued.status == "pending"
    with pytest.raises(MobileBridgeError) as busy:
        bridge.request_command(
            offer.id,
            phone_token=phone_token,
            kind="pause-attempt",
        )
    assert busy.value.code == "MOBILE_COMMAND_BUSY"

    delivered = bridge.bridge_command(offer.id, bridge_token=bridge_token)
    assert delivered is not None
    assert delivered.status == "processing"
    completed = bridge.complete_command(
        offer.id,
        bridge_token=bridge_token,
        sequence=1,
        result={"capture": "recording"},
    )
    assert completed.status == "completed"
    assert bridge.command_status(offer.id, phone_token=phone_token, sequence=1) == completed


def test_mobile_012_command_api_relays_context_and_authoritative_result_only() -> None:
    """TEST-APP-MOBILE-012: strict APIs relay controls, not raw evidence or grading."""

    bridge = _store()
    owner, phone = _clients(bridge)
    with owner, phone:
        bridge_token, phone_token = _pair(owner, phone)
        phone_headers = {"Authorization": f"Bearer {phone_token}"}
        command = phone.post(
            "/api/v1/mobile/pairings/pairing-one/commands",
            headers=phone_headers,
            json={
                "mobile_contract_version": "0.2.0",
                "kind": "submit-attempt",
                "context": {
                    "run_id": "run:one",
                    "score_id": "score:one",
                    "plan_id": "plan:one",
                    "exercise_id": "exercise:one",
                    "practice_mode": "follow-pitch",
                    "support_state_id": "support:one",
                    "tempo_bpm": 60,
                    "count_in_enabled": True,
                },
            },
        )
        assert command.status_code == 200
        assert command.json()["status"] == "pending"
        delivered = owner.get(
            "/api/v1/mobile-pairings/pairing-one/bridge-command",
            headers={"Authorization": f"Bearer {bridge_token}"},
        )
        assert delivered.status_code == 200
        assert delivered.json()["context"]["run_id"] == "run:one"
        acknowledged = owner.post(
            "/api/v1/mobile-pairings/pairing-one/bridge-command-acks",
            headers={"Authorization": f"Bearer {bridge_token}"},
            json={
                "mobile_contract_version": "0.2.0",
                "sequence": 1,
                "result": {"attempt_id": "attempt:one", "decision": {"action": "repeat"}},
            },
        )
        assert acknowledged.status_code == 200
        result = phone.get(
            "/api/v1/mobile/pairings/pairing-one/commands/1",
            headers=phone_headers,
        )
        assert result.json()["result"]["attempt_id"] == "attempt:one"

        rejected = phone.post(
            "/api/v1/mobile/pairings/pairing-one/commands",
            headers=phone_headers,
            json={
                "mobile_contract_version": "0.2.0",
                "kind": "start-attempt",
                "raw_messages": [{"data": [144, 60, 70]}],
            },
        )
        assert rejected.json()["diagnostics"][0]["code"] == "MOBILE_COMMAND_INVALID"


def test_mobile_013_paired_phone_gate_wraps_separate_authority_token() -> None:
    """TEST-APP-MOBILE-013: only a paired phone reaches the shared authority edge."""

    bridge = _store()
    owner = TestClient(
        create_app(
            launch_token=TOKEN,
            mobile_bridge=bridge,
            mobile_companion_origin=ORIGIN,
        )
    )
    phone_authority = create_app(launch_token="companion-only-launch-token")
    phone = TestClient(
        create_mobile_companion_app(
            bridge=bridge,
            policy=MobileNetworkPolicy(public_origin=ORIGIN),
            authority_app=phone_authority,
        ),
        base_url=ORIGIN,
    )
    with owner, phone:
        _, phone_token = _pair(owner, phone)
        assert phone.get("/api/v1/config").status_code == 403
        authorized = phone.get(
            "/api/v1/config",
            headers={
                "Authorization": f"Bearer {phone_token}",
                "X-TeachMeMusic-Mobile-Pairing": "pairing-one",
            },
        )
        assert authorized.status_code == 200
        assert authorized.json()["launch_token"] == "companion-only-launch-token"
        assert authorized.json()["launch_token"] != TOKEN
        assert (
            owner.delete("/api/v1/mobile-pairings/pairing-one", headers=TOKEN_HEADER).status_code
            == 204
        )
        revoked = phone.get(
            "/api/v1/config",
            headers={
                "Authorization": f"Bearer {phone_token}",
                "X-TeachMeMusic-Mobile-Pairing": "pairing-one",
            },
        )
        assert revoked.status_code == 410
        assert revoked.json()["diagnostics"][0]["code"] == "MOBILE_PAIRING_REVOKED"


def test_mobile_017_phone_controls_one_authoritative_teaching_cycle() -> None:
    """TEST-APP-MOBILE-017: phone control returns the desktop-submitted policy result."""

    bridge = _store()
    sessions = SessionStore(max_sessions=4, ttl_seconds=1_800, id_factory=lambda: "session-1")
    teaching_runs = TeachingRunStore(max_runs=4)
    owner = TestClient(
        create_app(
            launch_token=TOKEN,
            store=sessions,
            teaching_store=teaching_runs,
            mobile_bridge=bridge,
            mobile_companion_origin=ORIGIN,
        )
    )
    companion_token = "companion-only-launch-token"
    phone_authority = create_app(
        launch_token=companion_token,
        store=sessions,
        teaching_store=teaching_runs,
    )
    phone = TestClient(
        create_mobile_companion_app(
            bridge=bridge,
            policy=MobileNetworkPolicy(public_origin=ORIGIN),
            authority_app=phone_authority,
        ),
        base_url=ORIGIN,
    )
    with owner, phone:
        bridge_token, phone_token = _pair(owner, phone)
        phone_headers = {
            "Authorization": f"Bearer {phone_token}",
            "X-TeachMeMusic-Mobile-Pairing": "pairing-one",
            "X-TeachMeMusic-Token": companion_token,
        }
        manifest_response = phone.post(
            "/api/v1/viewer-sessions",
            headers=phone_headers,
            files={
                "score": (
                    FIXTURE.name,
                    FIXTURE.read_bytes(),
                    "application/vnd.recordare.musicxml",
                )
            },
        )
        assert manifest_response.status_code == 201, manifest_response.text
        manifest = manifest_response.json()
        score_id = manifest["scores"][0]["score_id"]
        plan_response = phone.post(
            "/api/v1/viewer-sessions/session-1/teaching-plans",
            headers=phone_headers,
            json={"score_id": score_id},
        )
        assert plan_response.status_code == 200, plan_response.text
        plan = plan_response.json()["plan"]
        exercise = plan["exercises"][2]
        presentation = phone.post(
            f"/api/v1/viewer-sessions/session-1/teaching-plans/{plan['id']}"
            f"/exercises/{exercise['id']}",
            headers=phone_headers,
            json={"score_id": score_id},
        ).json()["presentation"]
        started = phone.post(
            "/api/v1/viewer-sessions/session-1/teaching-runs",
            headers=phone_headers,
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
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        command = phone.post(
            "/api/v1/mobile/pairings/pairing-one/commands",
            headers=phone_headers,
            json={
                "mobile_contract_version": "0.2.0",
                "kind": "submit-attempt",
                "context": {
                    "run_id": run_id,
                    "score_id": score_id,
                    "plan_id": plan["id"],
                    "exercise_id": exercise["id"],
                    "practice_mode": "follow-pitch",
                    "support_state_id": exercise["initial_support"]["id"],
                    "tempo_bpm": 60,
                    "count_in_enabled": True,
                },
            },
        )
        assert command.status_code == 200, command.text
        delivered = owner.get(
            "/api/v1/mobile-pairings/pairing-one/bridge-command",
            headers={"Authorization": f"Bearer {bridge_token}"},
        )
        assert delivered.json()["kind"] == "submit-attempt"
        assert delivered.json()["context"]["run_id"] == run_id

        attempt_start = 1_000_000
        events: list[dict[str, object]] = []
        for index, note in enumerate(presentation["demonstration"]["notes"], start=1):
            events.extend(
                (
                    {
                        "id": f"midi-event:{index:04d}:on",
                        "raw_message_id": None,
                        "kind": "note-on",
                        "timestamp_microseconds": attempt_start + note["start_microseconds"],
                        "channel": 1,
                        "note": note["midi_pitch"],
                        "velocity": 80,
                        "controller": None,
                        "value": None,
                        "detail": None,
                    },
                    {
                        "id": f"midi-event:{index:04d}:off",
                        "raw_message_id": None,
                        "kind": "note-off",
                        "timestamp_microseconds": attempt_start + note["end_microseconds"],
                        "channel": 1,
                        "note": note["midi_pitch"],
                        "velocity": 0,
                        "controller": None,
                        "value": None,
                        "detail": None,
                    },
                )
            )
        events.sort(key=lambda item: (item["timestamp_microseconds"], item["id"]))
        attempt_end = max(int(item["timestamp_microseconds"]) for item in events) + 1
        submission = owner.post(
            f"/api/v1/teaching-runs/{run_id}/attempts",
            headers=TOKEN_HEADER,
            json={
                "score_id": score_id,
                "plan_id": plan["id"],
                "exercise_id": exercise["id"],
                "practice_mode": "follow-pitch",
                "support_state_id": exercise["initial_support"]["id"],
                "tempo_bpm": 60,
                "count_in_enabled": True,
                "started_at_utc": "2026-10-05T12:00:00Z",
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
                    "approved_at_utc": "2026-10-05T11:59:00Z",
                },
                "raw_messages": [],
                "normalized_events": events,
                "diagnostics": [],
            },
        )
        assert submission.status_code == 200, submission.text
        authoritative_result = submission.json()
        rejected = owner.post(
            "/api/v1/mobile-pairings/pairing-one/bridge-command-acks",
            headers={"Authorization": f"Bearer {bridge_token}"},
            json={
                "mobile_contract_version": "0.2.0",
                "sequence": 1,
                "result": {"nested": {"normalized_events": []}},
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["diagnostics"][0]["code"] == "MOBILE_RESULT_CONTENT_REJECTED"
        acknowledged = owner.post(
            "/api/v1/mobile-pairings/pairing-one/bridge-command-acks",
            headers={"Authorization": f"Bearer {bridge_token}"},
            json={
                "mobile_contract_version": "0.2.0",
                "sequence": 1,
                "result": authoritative_result,
            },
        )
        assert acknowledged.status_code == 200, acknowledged.text
        received = phone.get(
            "/api/v1/mobile/pairings/pairing-one/commands/1",
            headers=phone_headers,
        )
        assert received.status_code == 200, received.text
        assert received.json()["result"] == authoritative_result
        assert received.json()["result"]["feedback"]["action"]
        exported = phone.post(
            f"/api/v1/teaching-runs/{run_id}/exports",
            headers=phone_headers,
        )
        assert exported.status_code == 200, exported.text
        assert exported.json()["evidence"]["manifest"]["score_id"] == score_id
        inspection = phone.get(
            f"/api/v1/teaching-runs/{run_id}",
            headers=phone_headers,
        )
        assert inspection.status_code == 200, inspection.text
        assert inspection.json()["inspection"]["attempt_count"] == 1
