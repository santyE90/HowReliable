"""Synthetic bounded vehicle review; no real narratives or annotation materials."""

import json
from pathlib import Path

import pytest

from howreliable.demo.index import build_index
from howreliable.nlp.owner_reports import _hash
from howreliable.nlp.vehicle_review import build_review, review_records
from test_demo_history import TIME, record, source_file


def fixtures(tmp_path: Path, missing: bool = False) -> tuple[Path, Path]:
    texts = [
        "😀 Engine stalled.",
        "😀 Engine stalled.",
        "Engine did not stall.",
        "Possibly the engine stalled.",
        "Battery replaced.",
        "Grinding noise.",
        None,
    ]
    rows = [
        record(
            event_id=f"event_{i}" if not missing else " ",
            source_record_id=str(i),
            source_reference_id="900" if i < 3 else None,
            normalized_make="bmw",
            normalized_model="335i",
            model_year=2011,
            narrative=text,
            component="other" if i == 4 else "engine",
        )
        for i, text in enumerate(texts)
    ]
    rows.append(
        record(
            event_id="event_t",
            source_record_id="t",
            source_reference_id="901",
            normalized_make="toyota",
            normalized_model="corolla",
            model_year=2011,
            narrative="Smoke appeared.",
        )
    )
    source = source_file(tmp_path, rows)
    index = tmp_path / "history.sqlite"
    build_index(source, index, TIME)
    return source, index


def test_bounded_review_accounting_variants_assertions_and_determinism(tmp_path: Path) -> None:
    source, index = fixtures(tmp_path)
    before = (_hash(source), _hash(index))
    output = tmp_path / "one"
    build_review(source, index, output, TIME)
    build_review(source, index, tmp_path / "two", TIME)
    for path in output.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (tmp_path / "two" / path.relative_to(output)).read_bytes()
    review = json.loads((output / "2011-bmw-335i/review.json").read_bytes())
    assert len(review["reports"]) == 5
    multi = next(r for r in review["reports"] if len(r["source_rows"]) == 3)
    assert len(multi["variants"]) == 2
    assert multi["conflicting_narratives"]
    variants = [v for r in review["reports"] for v in r["variants"]]
    statuses = {m["assertion"] for v in variants for m in v["symptoms"]}
    assert {"affirmed", "negated", "uncertain"} <= statuses
    battery = next(v for v in variants if v["narrative"] == "Battery replaced.")
    assert battery["components"] and not battery["symptoms"]
    noise = next(v for v in variants if v["narrative"] == "Grinding noise.")
    assert noise["symptoms"] and not noise["associations"]
    assert any(v["processing_status"] == "missing_text" for v in variants)
    summary = json.loads((output / "2011-bmw-335i/summary.json").read_bytes())
    assert summary["denominators"]["total_source_rows"] == 7
    affirmed_stall = next(
        item for item in summary["symptoms"]
        if item["category"] == "stall_shutdown" and item["assertion"] == "affirmed"
    )
    assert affirmed_stall["unique_report_count"] == 1
    assert affirmed_stall["source_row_count"] == 2
    assert any("other" in r["structured_components"] for r in review["reports"])
    assert before == (_hash(source), _hash(index))
    with pytest.raises(FileExistsError):
        build_review(source, index, output, TIME)
    completion = json.loads((output / "completion.json").read_bytes())
    for name, digest in completion["files"].items():
        assert _hash(output / name) == digest


def test_missing_identifier_leaves_no_completed_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identifier"):
        fixtures(tmp_path, missing=True)
    assert not (tmp_path / "bad").exists()


def test_corrupt_offset_and_source_identity_are_rejected(tmp_path: Path) -> None:
    source, index = fixtures(tmp_path)
    output = tmp_path / "one"
    build_review(source, index, output, TIME)
    subset = output / "2011-bmw-335i/selected-clean.jsonl"
    rows = [json.loads(line) for line in subset.read_bytes().splitlines()]
    extraction = subset.parent / "extraction.jsonl"
    rows[0]["event_id"] = " "
    with pytest.raises(ValueError, match="identity"):
        review_records(rows, extraction)
    rows[0]["event_id"] = "event_0"
    rows[0]["narrative"] = "X" * len(rows[0]["narrative"])
    with pytest.raises(ValueError, match="offset"):
        review_records(rows, extraction)


def test_interruption_leaves_no_published_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = fixtures(tmp_path)

    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("howreliable.nlp.vehicle_review.process_owner_reports", interrupt)
    with pytest.raises(KeyboardInterrupt):
        build_review(source, index, tmp_path / "interrupted", TIME)
    assert not (tmp_path / "interrupted").exists()
    assert not list(tmp_path.glob(".p4b-*"))
