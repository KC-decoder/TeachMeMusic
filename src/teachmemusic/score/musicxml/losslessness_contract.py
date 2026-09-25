"""Machine-readable declaration-level losslessness evidence contract."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

LOSSLESSNESS_INDEX_FORMAT = "teachmemusic.musicxml.losslessness-evidence/1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TEST_ID = re.compile(r"^TEST-MXML-[A-Z0-9-]+$")

type EvidenceValue = str | int | bool | None | tuple[EvidenceValue, ...]
type WitnessFacts = tuple[str, str, dict[str, EvidenceValue]]


class LosslessnessEvidenceError(ValueError):
    """Raised when declaration-level proof is incomplete or stale."""


@dataclass(frozen=True, slots=True)
class WitnessEvidence:
    """Identity of one generated input used by independent evidence."""

    witness_id: str
    family: str
    standard_version: str
    source_format: str
    source_sha256: str
    byte_length: int
    generator_id: str
    oracle_facts: tuple[tuple[str, EvidenceValue], ...]


@dataclass(frozen=True, slots=True)
class DeclarationEvidence:
    """One exact declaration-to-witness-to-canonical proof link."""

    component_key: str
    family: str
    disposition: str
    witness_id: str
    standard_version: str
    source_selector: str
    proof_basis: str
    fact_names: tuple[str, ...]
    source_fact_sha256: str
    canonical_locator: str
    canonical_fact_sha256: str
    positive_test_ids: tuple[str, ...]
    mutation_test_ids: tuple[str, ...]
    result: str


@dataclass(frozen=True, slots=True)
class LosslessnessEvidenceIndex:
    """Deterministic declaration-aware evidence for one bounded scope."""

    scope: str
    inventory_sha256: str
    registry_sha256: str
    generator_id: str
    oracle_id: str
    witnesses: tuple[WitnessEvidence, ...]
    declarations: tuple[DeclarationEvidence, ...]


def fact_digest(facts: dict[str, EvidenceValue], names: tuple[str, ...]) -> str:
    """Hash the exact ordered fact subset named by one declaration proof."""

    try:
        selected = [(name, facts[name]) for name in names]
    except KeyError as error:
        raise LosslessnessEvidenceError(f"proof names unavailable fact {error.args[0]}") from error
    encoded = json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def render_index(index: LosslessnessEvidenceIndex) -> str:
    """Render a stable JSON evidence artifact."""

    payload = {
        "format": LOSSLESSNESS_INDEX_FORMAT,
        "scope": index.scope,
        "inventory_sha256": index.inventory_sha256,
        "registry_sha256": index.registry_sha256,
        "generator_id": index.generator_id,
        "oracle_id": index.oracle_id,
        "summary": {
            "witnesses": len(index.witnesses),
            "declarations": len(index.declarations),
            "passed": sum(item.result == "passed" for item in index.declarations),
        },
        "witnesses": [asdict(item) for item in index.witnesses],
        "declarations": [asdict(item) for item in index.declarations],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load_losslessness_links(
    evidence_path: Path,
    inventory_path: Path,
    registry_path: Path,
    *,
    known_test_ids: frozenset[str],
) -> dict[str, frozenset[str]]:
    """Load only current, passed, declaration-specific independent links."""

    payload = _json_object(evidence_path.read_bytes(), "losslessness evidence")
    if payload.get("format") != LOSSLESSNESS_INDEX_FORMAT:
        raise LosslessnessEvidenceError("unsupported losslessness-evidence format")
    _required_text(payload, "scope")
    _required_text(payload, "generator_id")
    _required_text(payload, "oracle_id")
    _require_current_hash(payload, "inventory_sha256", inventory_path)
    _require_current_hash(payload, "registry_sha256", registry_path)

    inventory = _json_object(inventory_path.read_bytes(), "declaration inventory")
    registry = _json_object(registry_path.read_bytes(), "mapping registry")
    inventory_entries = _index_by_text_key(inventory, "components", "key")
    registry_entries = _registry_entries(registry)
    witness_facts = _witness_facts(payload)

    raw_declarations = payload.get("declarations")
    if not isinstance(raw_declarations, list):
        raise LosslessnessEvidenceError("losslessness evidence has no declaration proofs")
    links: dict[str, frozenset[str]] = {}
    for raw_proof in raw_declarations:
        if not isinstance(raw_proof, dict):
            raise LosslessnessEvidenceError("declaration proof is not an object")
        proof = cast(dict[str, object], raw_proof)
        key = _required_text(proof, "component_key")
        if key in links:
            raise LosslessnessEvidenceError(f"duplicate declaration proof: {key}")
        if key not in inventory_entries or key not in registry_entries:
            raise LosslessnessEvidenceError(f"proof names unknown declaration: {key}")
        component = inventory_entries[key]
        entry = registry_entries[key]
        if proof.get("family") != entry.get("family"):
            raise LosslessnessEvidenceError(f"proof family disagrees with registry: {key}")
        if proof.get("disposition") != entry.get("disposition"):
            raise LosslessnessEvidenceError(f"proof disposition disagrees with registry: {key}")
        witness_id = proof.get("witness_id")
        if witness_id not in witness_facts:
            raise LosslessnessEvidenceError(f"proof names unknown witness: {key}")
        witness_family, witness_version, facts = witness_facts[witness_id]
        proof_version = _required_text(proof, "standard_version")
        if proof_version != component.get("version") or proof_version != witness_version:
            raise LosslessnessEvidenceError(f"proof version disagrees with evidence: {key}")
        if proof.get("family") != witness_family:
            raise LosslessnessEvidenceError(f"proof family disagrees with witness: {key}")
        _required_text(proof, "source_selector")
        _required_text(proof, "proof_basis")
        _required_text(proof, "canonical_locator")
        fact_names = proof.get("fact_names")
        if (
            not isinstance(fact_names, list)
            or not fact_names
            or not all(isinstance(item, str) and item for item in fact_names)
        ):
            raise LosslessnessEvidenceError(f"proof has invalid fact_names: {key}")
        if proof.get("result") != "passed":
            raise LosslessnessEvidenceError(f"declaration proof did not pass: {key}")
        source_digest = _required_text(proof, "source_fact_sha256")
        canonical_digest = _required_text(proof, "canonical_fact_sha256")
        if not _SHA256.fullmatch(source_digest) or source_digest != canonical_digest:
            raise LosslessnessEvidenceError(f"source/canonical evidence differs: {key}")
        recomputed = fact_digest(
            facts,
            tuple(cast(list[str], fact_names)),
        )
        if source_digest != recomputed:
            raise LosslessnessEvidenceError(f"source fact digest is not reproducible: {key}")
        test_ids = _test_ids(proof, "positive_test_ids") | _test_ids(proof, "mutation_test_ids")
        if not test_ids or not test_ids <= known_test_ids:
            raise LosslessnessEvidenceError(f"proof cites unknown or empty tests: {key}")
        links[key] = frozenset(test_ids)
    return links


def _require_current_hash(payload: dict[str, object], key: str, path: Path) -> None:
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    if payload.get(key) != expected:
        raise LosslessnessEvidenceError(f"{key} does not match {path.name}")


def _json_object(data: bytes, label: str) -> dict[str, object]:
    value = json.loads(data)
    if not isinstance(value, dict):
        raise LosslessnessEvidenceError(f"{label} is not a JSON object")
    return cast(dict[str, object], value)


def _index_by_text_key(
    document: dict[str, object], list_key: str, key_name: str
) -> dict[str, dict[str, object]]:
    values = document.get(list_key)
    if not isinstance(values, list):
        raise LosslessnessEvidenceError(f"{list_key} is not a list")
    result: dict[str, dict[str, object]] = {}
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get(key_name), str):
            continue
        key = cast(str, item[key_name])
        if key in result:
            raise LosslessnessEvidenceError(f"{list_key} repeats {key_name}: {key}")
        result[key] = cast(dict[str, object], item)
    return result


def _registry_entries(document: dict[str, object]) -> dict[str, dict[str, object]]:
    values = document.get("entries")
    if not isinstance(values, list):
        raise LosslessnessEvidenceError("mapping registry has no entries")
    return {
        cast(str, item["component_key"]): cast(dict[str, object], item)
        for item in values
        if isinstance(item, dict) and isinstance(item.get("component_key"), str)
    }


def _witness_facts(payload: dict[str, object]) -> dict[str, WitnessFacts]:
    values = payload.get("witnesses")
    if not isinstance(values, list):
        raise LosslessnessEvidenceError("losslessness evidence has no witnesses")
    result: dict[str, WitnessFacts] = {}
    for raw_witness in values:
        if not isinstance(raw_witness, dict):
            raise LosslessnessEvidenceError("witness is not an object")
        witness = cast(dict[str, object], raw_witness)
        identifier = _required_text(witness, "witness_id")
        if identifier in result:
            raise LosslessnessEvidenceError("witness identity is duplicated")
        family = _required_text(witness, "family")
        version = _required_text(witness, "standard_version")
        _required_text(witness, "source_format")
        _required_text(witness, "generator_id")
        source_sha256 = _required_text(witness, "source_sha256")
        if not _SHA256.fullmatch(source_sha256):
            raise LosslessnessEvidenceError(f"witness has invalid source hash: {identifier}")
        byte_length = witness.get("byte_length")
        if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length <= 0:
            raise LosslessnessEvidenceError(f"witness has invalid byte length: {identifier}")
        raw_facts = witness.get("oracle_facts")
        if not isinstance(raw_facts, list):
            raise LosslessnessEvidenceError(f"witness has invalid oracle facts: {identifier}")
        facts: dict[str, EvidenceValue] = {}
        for raw_fact in raw_facts:
            if (
                not isinstance(raw_fact, list)
                or len(raw_fact) != 2
                or not isinstance(raw_fact[0], str)
            ):
                raise LosslessnessEvidenceError(f"witness has malformed oracle fact: {identifier}")
            name = raw_fact[0]
            if name in facts:
                raise LosslessnessEvidenceError(f"witness repeats oracle fact {name}: {identifier}")
            facts[name] = _evidence_value(raw_fact[1])
        result[identifier] = (family, version, facts)
    return result


def _evidence_value(value: object) -> EvidenceValue:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, list):
        return tuple(_evidence_value(item) for item in value)
    raise LosslessnessEvidenceError("oracle fact contains an unsupported value")


def _required_text(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise LosslessnessEvidenceError(f"proof has no {key}")
    return value


def _test_ids(document: dict[str, object], key: str) -> frozenset[str]:
    value = document.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and _TEST_ID.fullmatch(item) for item in value)
    ):
        raise LosslessnessEvidenceError(f"proof has invalid {key}")
    return frozenset(cast(list[str], value))
