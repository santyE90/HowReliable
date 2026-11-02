"""Synthetic development-only generation, provenance and evaluator compatibility."""

import json
from pathlib import Path
from typing import Any

import pytest

from howreliable.nlp.annotation_review import ReviewError
from howreliable.nlp.development_evaluation import evaluate
from howreliable.nlp.development_predictions import DevelopmentPacket, generate
from howreliable.nlp.owner_reports import _hash, _json
from test_development_evaluation import fixture, freeze
from test_owner_report_nlp import TIME


def test_generation_is_deterministic_read_only_and_matches_legacy_scoring(tmp_path: Path) -> None:
    source, working, legacy = fixture(tmp_path)
    before = source.read_bytes(), working.read_bytes()
    a, b = tmp_path / "new-a", tmp_path / "new-b"
    meta = generate(source, working, a, generation_utc=TIME, expected_reports=1)
    generate(source, working, b, generation_utc=TIME, expected_reports=1)
    assert (source.read_bytes(), working.read_bytes()) == before
    assert all(p.read_bytes() == (b / p.name).read_bytes() for p in a.iterdir())
    file = a / "development-predictions.jsonl"
    packet = DevelopmentPacket.model_validate_json(file.read_bytes())
    assert packet.partition == "development" and len(packet.predictions) == 1
    assert packet.predictions[0].source_row_count == 2
    assert meta["prediction_sha256"] == _hash(file)
    # Compare the same new evidence represented by the original row-based schema.
    old = json.loads(legacy.read_bytes())
    v = packet.predictions[0].model_dump(mode="json")
    for row in old["predictions"]:
        for name in ("component_mentions", "symptom_mentions", "associations"):
            row[name] = v[name]
        row["mentions"] = sorted(
            [*v["component_mentions"], *v["symptom_mentions"]],
            key=lambda m: (m["start"], m["end"], m["kind"], m["code"]),
        )
    legacy.write_bytes(_json(old))
    freeze(source, legacy)
    original = evaluate(source, working, legacy, tmp_path / "legacy-results", generation_utc=TIME)
    updated = evaluate(source, working, file, tmp_path / "variant-results", generation_utc=TIME)
    assert original == updated
    with pytest.raises(FileExistsError):
        generate(source, working, a, generation_utc=TIME)


def test_gold_values_are_not_extraction_inputs(tmp_path: Path) -> None:
    source, working, _ = fixture(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    generate(source, working, a, generation_utc=TIME)
    raw = json.loads(working.read_bytes())
    raw["reports"][0]["annotation"]["variants"][0]["component_annotations"][0]["code"] = (
        "transmission"
    )
    working.write_bytes(_json(raw))
    generate(source, working, b, generation_utc=TIME)
    assert (a / "development-predictions.jsonl").read_bytes() == (
        b / "development-predictions.jsonl"
    ).read_bytes()


def test_generation_failures_publish_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, working, _ = fixture(tmp_path)

    def failed(text: str) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr("howreliable.nlp.development_predictions.extract_report", failed)
    out = tmp_path / "new"
    with pytest.raises(KeyboardInterrupt):
        generate(source, working, out, generation_utc=TIME)
    assert not out.exists()


def test_provenance_bound_to_exact_working_snapshot(tmp_path: Path) -> None:
    source, working, _ = fixture(tmp_path)
    out = tmp_path / "new"
    generate(source, working, out, generation_utc=TIME)
    with working.open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(ReviewError, match="provenance_mismatch"):
        evaluate(
            source,
            working,
            out / "development-predictions.jsonl",
            tmp_path / "results",
            generation_utc=TIME,
        )


def test_reject_wrong_partition_and_offset_before_scoring(tmp_path: Path) -> None:
    source, working, _ = fixture(tmp_path)
    out = tmp_path / "new"
    generate(source, working, out, generation_utc=TIME)
    file = out / "development-predictions.jsonl"
    packet = json.loads(file.read_bytes())
    bad = json.loads(file.read_bytes())
    bad["partition"] = "held_out"
    with pytest.raises(ValueError):
        DevelopmentPacket.model_validate_json(_json(bad))
    mention = packet["predictions"][0]["component_mentions"][0]
    mention["start"] += 1
    mention["end"] += 1
    file.write_bytes(_json(packet))
    meta = json.loads((out / "provenance.json").read_bytes())
    meta["prediction_sha256"] = _hash(file)
    (out / "provenance.json").write_bytes(_json(meta))
    with pytest.raises(ReviewError, match="offset_mismatch"):
        evaluate(source, working, file, tmp_path / "results", generation_utc=TIME)


def test_incomplete_report_is_not_generated(tmp_path: Path) -> None:
    source, working, _ = fixture(tmp_path, completed=False)
    with pytest.raises(ReviewError, match="unexpected_completed"):
        generate(source, working, tmp_path / "new", generation_utc=TIME)
