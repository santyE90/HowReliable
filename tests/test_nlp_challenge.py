"""Synthetic-only blinded challenge preparation and isolation checks."""

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from howreliable.nlp.annotation_review import ReviewStore, read_source, validate_working
from howreliable.nlp.challenge import prepare, rule_hashes
from howreliable.nlp.development_predictions import DevelopmentPacket
from howreliable.nlp.owner_reports import _hash, _json
from howreliable.nlp.schemas import ComponentMention, SymptomMention
from test_owner_report_nlp import TIME, inputs, record, run


def fixture(tmp: Path) -> tuple[Path, Path, Path]:
    phrases = [
        "Engine stalled.",
        "No noise from the engine.",
        "Possibly an engine problem.",
        "If this happens the engine could fail.",
        "Garage door was shut.",
        "The remote start command failed.",
        "A warning appeared on the dashboard.",
        "Automatic stop and restart did not work.",
        "The brakes failed.",
    ]
    rows = [
        record(i, source_reference_id=str(i), narrative=phrases[(i - 1) % 9] + f" Case {i}.")
        for i in range(1, 61)
    ]
    # A duplicate relative outside the bounded sample must exclude report 3.
    corpus_rows = [*rows, record(61, source_reference_id="61", narrative=rows[2]["narrative"])]
    # Extra component row for report 4; must be preserved as one annotation unit.
    corpus_rows.append(record(62, source_reference_id="4", narrative=rows[3]["narrative"]))
    corpus_dir = tmp / "corpus"
    corpus_dir.mkdir()
    corpus = inputs(corpus_dir, corpus_rows)
    extraction = corpus_dir / "rows.jsonl"
    run(corpus, extraction)
    frozen = tmp / "original"
    frozen.mkdir()
    index = frozen / "global.sqlite"
    shutil.copyfile(extraction.with_suffix(".jsonl.membership.sqlite"), index)
    with closing(sqlite3.connect(index)) as db:
        reserved = [
            {
                "evaluation_group_id": db.execute(
                    "SELECT g.evaluation_group_id FROM events e "
                    "JOIN report_groups g ON e.report_id=g.id WHERE e.id=?",
                    (f"event_{n}",),
                ).fetchone()[0],
                "partition": p,
            }
            for n, p in ((1, "development"), (2, "held_out"))
        ]
    manifest = frozen / "partition-manifest.json"
    manifest.write_bytes(
        _json({"memberships": reserved, "partition_counts": {"development": 1, "held_out": 1}})
    )
    (frozen / "provenance.json").write_bytes(
        _json(
            {
                "complete": True,
                "inputs_sha256": {"complaints-clean.jsonl": _hash(corpus)},
                "outputs": {p.name: {"sha256": _hash(p)} for p in (manifest, index)},
            }
        )
    )
    sample = tmp / "sample.jsonl"
    sample.write_bytes(b"".join(_json(r) for r in [*rows, corpus_rows[-1]]))
    sample.with_suffix(".jsonl.provenance.json").write_bytes(
        _json(
            {
                "cleaned_count": 61,
                "sample_sha256": _hash(sample),
                "source_clean_sha256": _hash(corpus),
            }
        )
    )
    return sample, manifest, index


def test_fresh_blank_isolated_and_editor_compatible(tmp_path: Path) -> None:
    sample, manifest, index = fixture(tmp_path)
    before = {p: _hash(p) for p in (sample, manifest, index)}
    frozen_rules = rule_hashes()
    out = tmp_path / "challenge"
    result = prepare(sample, manifest, index, out, generation_utc=TIME)
    assert result["report_count"] == 20
    assert result["excluded"]["reserved_source_rows"] == 2
    assert result["excluded"]["multi_report_evaluation_groups"] == 1
    worksheet = out / "frozen/development/worksheet.jsonl"
    units = read_source(worksheet)
    assert len(units) == len({u.annotation_id for u in units}) == 20
    assert all(
        u.status == "pending"
        and all(
            not v.component_annotations
            and not v.symptom_annotations
            and not v.association_annotations
            for v in u.variants
        )
        for u in units
    )
    store = ReviewStore(worksheet, out / "annotation-work/review.json")
    validate_working(worksheet, store.read())
    assert not store.working.exists()
    packets = [
        DevelopmentPacket.model_validate_json(line)
        for line in (out / "private/development-predictions.jsonl").read_bytes().splitlines()
    ]
    assert {p.annotation_id for p in packets} == {u.annotation_id for u in units}
    originals = {u.annotation_id: u for u in units}
    for packet in packets:
        for prediction, v in zip(
            packet.predictions, originals[packet.annotation_id].variants, strict=True
        ):
            mentions: tuple[ComponentMention | SymptomMention, ...] = (
                *prediction.component_mentions,
                *prediction.symptom_mentions,
            )
            for m in mentions:
                assert (v.narrative or "")[m.start : m.end] == m.evidence_text
    mappings = [
        json.loads(line) for line in (out / "private/mapping.jsonl").read_bytes().splitlines()
    ]
    with closing(sqlite3.connect(index)) as db:
        for mapping in mappings:
            assert {
                r[0]
                for r in db.execute(
                    "SELECT id FROM events WHERE report_id=?", (mapping["report_group_id"],)
                )
            } == {r["event_id"] for r in mapping["source_records"]}
    assert all(_hash(p) == digest for p, digest in before.items()) and rule_hashes() == frozen_rules
    provenance = json.loads((out / "provenance.json").read_bytes())
    assert all(_hash(out / name) == spec["sha256"] for name, spec in provenance["outputs"].items())


def test_reproducible_and_overwrite_refusal(tmp_path: Path) -> None:
    args = fixture(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    assert prepare(*args, a, generation_utc=TIME) == prepare(*args, b, generation_utc=TIME)
    assert all(
        p.read_bytes() == (b / p.relative_to(a)).read_bytes() for p in a.rglob("*") if p.is_file()
    )
    with pytest.raises(FileExistsError):
        prepare(*args, a, generation_utc=TIME)


def test_tampering_and_bounded_limit_refused(tmp_path: Path) -> None:
    sample, manifest, index = fixture(tmp_path)
    with pytest.raises(ValueError, match="bounded_sample"):
        prepare(sample, manifest, index, tmp_path / "a", generation_utc=TIME, max_rows=30)
    with sample.open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(ValueError, match="checksum"):
        prepare(sample, manifest, index, tmp_path / "b", generation_utc=TIME)
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


def test_interrupt_does_not_publish_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    args = fixture(tmp_path)

    def interrupt(text: str) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr("howreliable.nlp.challenge.extract_report", interrupt)
    with pytest.raises(KeyboardInterrupt):
        prepare(*args, tmp_path / "challenge", generation_utc=TIME)
    assert not (tmp_path / "challenge").exists()
    assert not list(tmp_path.glob("challenge-stage-*"))


def test_missing_screen_coverage_refused_before_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import howreliable.nlp.challenge as implementation

    args = fixture(tmp_path)
    screens = {**implementation.SCREENS, "nonvehicle_objects": r"\babsent_fixture_phrase\b"}
    monkeypatch.setattr(implementation, "SCREENS", screens)

    def forbidden(text: str) -> Any:
        raise AssertionError("Extraction must not run for an incomplete mixture")

    monkeypatch.setattr(implementation, "extract_report", forbidden)
    with pytest.raises(ValueError, match="mixture_incomplete"):
        prepare(*args, tmp_path / "challenge", generation_utc=TIME)
    assert not (tmp_path / "challenge").exists()
