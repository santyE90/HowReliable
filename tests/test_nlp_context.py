"""Synthetic-only symptom, assertion and explicit association tests."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from howreliable.nlp.context import extract_report
from howreliable.nlp.schemas import ExtractionRow, ProcessingConfig, RunProvenance
from howreliable.nlp.symptoms import extract_symptoms, symptom_lexicon_sha256
from test_owner_report_nlp import inputs, record, run


@pytest.mark.parametrize(
    "phrase,code",
    [
        ("stalled", "stall_shutdown"),
        ("shut down", "stall_shutdown"),
        ("would not start", "no_start"),
        ("hesitation", "hesitation_power_loss"),
        ("reduced power", "hesitation_power_loss"),
        ("unintended acceleration", "unintended_acceleration"),
        ("noise", "noise"),
        ("vibration", "vibration"),
        ("harsh engagement", "shift_engagement"),
        ("leaking", "leak"),
        ("burning odor", "odor"),
        ("smoke", "smoke"),
        ("overheating", "overheating"),
        ("warning light", "warning_indicator"),
        ("loss of braking", "braking_difficulty"),
        ("loss of steering assistance", "steering_difficulty"),
        ("lights cut out", "electrical_interruption"),
        ("cuts in and out", "intermittent_operation"),
        ("stopped working", "operation_loss"),
    ],
)
def test_affirmed_explicit_symptoms(phrase: str, code: str) -> None:
    _, symptoms, _ = extract_report(f"Vehicle {phrase}.")
    assert len(symptoms) == 1 and symptoms[0].code == code
    assert symptoms[0].assertion == "affirmed"


@pytest.mark.parametrize(
    "text,code,status",
    [
        ("Engine did not stall", "stall_shutdown", "negated"),
        ("No vibration", "vibration", "negated"),
        ("Without smoke", "smoke", "negated"),
        ("Engine never stalled", "stall_shutdown", "negated"),
        ("Engine isn't overheating", "overheating", "negated"),
        ("Engine will stall", "stall_shutdown", "uncertain"),
        ("Not without noise", "noise", "unresolved"),
        ("Noise was not present", "noise", "negated"),
        ("Engine might stall", "stall_shutdown", "uncertain"),
        ("Dealer suspects overheating", "overheating", "uncertain"),
        ("If engine stalls", "stall_shutdown", "uncertain"),
        ("Overheating is suspected", "overheating", "uncertain"),
        ("Engine may not stall", "stall_shutdown", "unresolved"),
        ("Replaced battery and engine stalled", "stall_shutdown", "unresolved"),
        ("I deliberately shut off the engine", "stall_shutdown", "unresolved"),
        ("Stopped working", "operation_loss", "unresolved"),
    ],
)
def test_assertions_and_cue_offsets(text: str, code: str, status: str) -> None:
    _, symptoms, _ = extract_report(text)
    m = next(m for m in symptoms if m.code == code)
    assert m.assertion == status
    for cue in m.assertion_cue_spans:
        assert text[cue.start : cue.end] == cue.evidence_text
    if status in {"negated", "uncertain"}:
        assert m.assertion_cue_spans


def test_contrast_punctuation_and_component_referent_semantics() -> None:
    c, s, a = extract_report("Engine did not stall, but brakes failed; no vibration.")
    assert [m.assertion for m in c] == ["affirmed", "affirmed"]
    assert [(m.code, m.assertion) for m in s] == [
        ("stall_shutdown", "negated"),
        ("braking_difficulty", "affirmed"),
        ("vibration", "negated"),
    ]
    assert len(a) == 2
    assert extract_report("Not only noise but vibration")[1][0].assertion == "affirmed"


@pytest.mark.parametrize(
    "text",
    [
        "Engine stalled",
        "Engine did not stall",
        "Transmission had harsh engagement",
        "Steering wheel shook",
        "Brakes failed",
        "Loss of steering assistance",
    ],
)
def test_explicit_associations(text: str) -> None:
    c, s, associations = extract_report(text)
    assert len(associations) == 1
    a = associations[0]
    assert a.component_mention_id in {m.mention_id for m in c}
    assert a.symptom_mention_id in {m.mention_id for m in s}
    assert text[a.start : a.end] == a.evidence_text and a.rule_id.startswith("association-v1.")


@pytest.mark.parametrize(
    "text",
    [
        "Battery replaced; vehicle stalled",
        "Battery was replaced and vehicle stalled",
        "Engine and transmission stalled",
        "Battery was inspected while vehicle stalled",
        "Engine inspected. It stalled",
        "Engine light came on",
        "Wheel was shaking",
        "The engine was inspected and it stalled",
        "Perhaps the wheel had vibration",
    ],
)
def test_unsupported_relations_abstain(text: str) -> None:
    assert extract_report(text)[2] == ()


def test_repair_history_warning_indication_and_suspicion() -> None:
    c, s, a = extract_report(
        "Battery replaced. Check engine light illuminated. Dealer suspects fuel pump."
    )
    assert c[0].code == "electrical" and c[0].assertion == "affirmed"
    assert c[1].assertion == "unresolved" and c[2].assertion == "uncertain"
    assert [(m.code, m.assertion) for m in s] == [("warning_indicator", "affirmed")]
    assert not a


def test_unicode_offsets_longest_overlap_and_repeatability() -> None:
    text = (
        "🚗 Café: \uff25\uff2e\uff27\uff29\uff2e\uff25 stalled; "
        "no vibration, but warning\u00a0light appeared."
    )
    one, two = extract_report(text), extract_report(text)
    assert one == two
    for mentions in one:
        for m in mentions:
            assert text[m.start : m.end] == m.evidence_text
    assert [m.code for m in one[1]] == ["stall_shutdown", "vibration", "warning_indicator"]
    assert len(extract_symptoms("grinding noise; intermittently stopped working")) == 2
    assert not extract_symptoms("smokeless, noisyword, stalledness")
    assert len(symptom_lexicon_sha256()) == 64


def test_streaming_invariants_and_schema_references(tmp_path: Path) -> None:
    rows = [
        record(narrative="Engine stalled"),
        record(2, narrative=None),
        record(3, narrative="Brakes failed", report_date="2025-01-01"),
    ]
    p = inputs(tmp_path, rows)
    before = p.read_bytes()
    out = tmp_path / "rows.jsonl"
    meta = run(p, out, config=ProcessingConfig(mode="as_of", cutoff=date(2022, 12, 31)))
    values = [ExtractionRow.model_validate_json(line) for line in out.read_bytes().splitlines()]
    assert meta.input_record_count == meta.output_record_count == 3
    assert sum(meta.status_counts.values()) == 3 and meta.milestone == "E"
    assert meta.assertion_rules_version and meta.symptom_lexicon_sha256
    assert len(values[0].associations) == 1
    assert not values[1].mentions and not values[2].mentions
    assert p.read_bytes() == before
    value = values[0].model_dump(mode="json")
    value["associations"][0]["symptom_mention_id"] = "absent"
    with pytest.raises(ValidationError):
        ExtractionRow.model_validate_json(json.dumps(value))


def test_legacy_component_only_rows_and_provenance_remain_readable(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record(narrative="Engine")])
    out = tmp_path / "rows.jsonl"
    meta = run(p, out)
    row: dict[str, Any] = json.loads(out.read_bytes())
    row["schema_version"] = "howreliable-owner-report-extraction-1.1"
    assert ExtractionRow.model_validate_json(json.dumps(row)).schema_version.endswith("1.1")
    old = meta.model_dump(mode="json")
    old.update(
        schema_version="howreliable-owner-report-extraction-1.1",
        milestone="C",
        symptom_extraction_implemented=False,
    )
    for key in [
        "symptom_lexicon_version",
        "symptom_lexicon_sha256",
        "assertion_rules_version",
        "association_rules_version",
    ]:
        del old[key]
    assert RunProvenance.model_validate_json(json.dumps(old)).milestone == "C"
    row.update(
        schema_version="howreliable-owner-report-extraction-1.0", mentions=[], component_mentions=[]
    )
    assert not ExtractionRow.model_validate_json(json.dumps(row)).mentions
    old.update(
        schema_version="howreliable-owner-report-extraction-1.0",
        milestone="B",
        extraction_implemented=False,
    )
    for key in [
        "component_lexicon_version",
        "component_lexicon_sha256",
        "component_matcher_version",
        "symptom_extraction_implemented",
    ]:
        del old[key]
    assert RunProvenance.model_validate_json(json.dumps(old)).milestone == "B"
