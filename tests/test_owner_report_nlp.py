"""Synthetic-only Milestone B tests; never process the restored complaint corpus."""

import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from howreliable.data.cleaning import CleanComplaintRecord
from howreliable.data.features.nhtsa_complaints import FeatureGenerationError
from howreliable.nlp import (
    ExtractionRow,
    ProcessingConfig,
    ProcessingError,
    owner_reports,
    process_owner_reports,
)
from howreliable.nlp.__main__ import main

TIME = datetime(2026, 10, 27, 12, tzinfo=UTC)


def record(number: int = 1, **changes: Any) -> dict[str, Any]:
    row = CleanComplaintRecord(
        event_id=f"event_{number}",
        source_type="nhtsa_odi_complaint",
        source_record_id=str(number),
        source_reference_id="900",
        broad_vehicle_id="cohort_1",
        known_configuration_id=None,
        source_make="MAKE",
        normalized_make="make",
        source_model="MODEL",
        normalized_model="model",
        source_model_year="2020",
        model_year=2020,
        component="engine",
        source_component="ENGINE",
        severity="low",
        death_count=0,
        injury_count=0,
        crash=False,
        fire=False,
        mileage=100,
        mileage_unit="miles",
        occurrence_date=date(2021, 1, 1),
        report_date=date(2022, 1, 1),
        narrative="Engine stopped. Café 🚗",
        quality_flags=(),
    ).as_dict()
    row.update(changes)
    return row


def inputs(tmp: Path, rows: list[dict[str, Any]], count: int | None = None) -> Path:
    p = tmp / "clean.jsonl"
    p.write_bytes(b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode() for row in rows))
    p.with_suffix(".jsonl.provenance.json").write_text(
        json.dumps(
            {
                "cleaned_count": len(rows) if count is None else count,
                "cleaning_version": "nhtsa-complaints-1.0",
                "mapping_version": "nhtsa-reliability-event-1.0",
            }
        ),
        encoding="utf-8",
    )
    return p


def run(p: Path, out: Path, **kwargs: Any) -> Any:
    return process_owner_reports(p, out, clock=lambda: TIME, **kwargs)


def test_stream_conservation_lineage_empty_arrays_and_provenance(tmp_path: Path) -> None:
    rows = [
        record(),
        record(2, narrative=None),
        record(3, narrative=""),
        record(4, narrative=" \t ", source_reference_id=None),
        record(5, narrative="Other text", quality_flags=["short_narrative"]),
    ]
    p = inputs(tmp_path, rows)
    before = p.read_bytes()
    out = tmp_path / "rows.jsonl"
    meta = run(p, out)
    values = [ExtractionRow.model_validate_json(line) for line in out.read_bytes().splitlines()]
    assert [r.event_id for r in values] == [r["event_id"] for r in rows]
    assert [r.processing_status for r in values] == [
        "processed",
        "missing_text",
        "empty_text",
        "empty_text",
        "processed",
    ]
    assert all(r.mentions == r.component_mentions for r in values)
    assert all(not r.symptom_mentions and not r.associations for r in values)
    assert values[0].component_mentions[0].code == "engine"
    assert all(not r.component_mentions for r in values[1:])
    assert values[0].narrative_sha256 == hashlib.sha256(rows[0]["narrative"].encode()).hexdigest()
    assert values[1].narrative_sha256 is None and values[3].report_group_fallback
    assert values[0].report_group_id == values[1].report_group_id
    assert values[0].structured_component == "engine" and values[0].source_component == "ENGINE"
    assert values[0].report_date == date(2022, 1, 1)
    assert values[0].occurrence_date == date(2021, 1, 1)
    assert values[4].quality_flags == ("short_narrative",)
    assert meta.input_record_count == meta.output_record_count == 5
    assert sum(meta.status_counts.values()) == 5
    assert meta.unique_report_count == 2 and meta.conflicting_report_group_count == 1
    assert meta.input_sha256 == hashlib.sha256(before).hexdigest()
    assert meta.output_sha256 == hashlib.sha256(out.read_bytes()).hexdigest()
    assert (
        meta.input_provenance_sha256
        == hashlib.sha256(p.with_suffix(".jsonl.provenance.json").read_bytes()).hexdigest()
    )
    assert meta.generation_utc == TIME and meta.extraction_implemented
    assert meta.symptom_extraction_implemented
    assert meta.component_lexicon_sha256 is not None and len(meta.component_lexicon_sha256) == 64
    assert len(meta.code_sha256) == len(meta.configuration_sha256) == 64
    assert b"\r\n" not in out.read_bytes() and not out.read_bytes().startswith(b"\xef\xbb\xbf")
    assert p.read_bytes() == before


def test_date_filter_preserves_rows_and_never_uses_occurrence_date(tmp_path: Path) -> None:
    p = inputs(
        tmp_path,
        [
            record(),
            record(2, report_date="2023-01-01"),
            record(3, report_date=None, narrative=None),
        ],
    )
    out = tmp_path / "rows.jsonl"
    meta = run(p, out, config=ProcessingConfig(mode="as_of", cutoff=date(2022, 1, 1)))
    statuses = [json.loads(line)["processing_status"] for line in out.read_text().splitlines()]
    assert statuses == ["processed", "excluded_after_cutoff", "excluded_missing_report_date"]
    assert meta.output_record_count == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"narrative": 42},
        {"report_date": "not-a-date"},
        {"model_year": True},
        {"quality_flags": ["not-real"]},
        {"component": "not-real"},
        {"event_id": " "},
        {"source_record_id": ""},
        {"extra": "invalid"},
    ],
)
def test_invalid_fields_leave_no_output(tmp_path: Path, changes: dict[str, Any]) -> None:
    p = inputs(tmp_path, [record(), record(2, **changes)])
    out = tmp_path / "rows.jsonl"
    with pytest.raises((ProcessingError, FeatureGenerationError)):
        run(p, out)
    assert not out.exists() and not out.with_suffix(".jsonl.provenance.json").exists()


def test_missing_field_and_duplicate_id_fail(tmp_path: Path) -> None:
    row = record()
    del row["narrative"]
    p = inputs(tmp_path, [row])
    out = tmp_path / "rows.jsonl"
    with pytest.raises(FeatureGenerationError):
        run(p, out)
    p.unlink()
    p.with_suffix(".jsonl.provenance.json").unlink()
    p = inputs(tmp_path, [record(), record()])
    with pytest.raises(ProcessingError, match="duplicate"):
        run(p, out)
    assert not out.exists()


def test_count_mismatch_and_missing_provenance(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record()], count=2)
    out = tmp_path / "rows.jsonl"
    with pytest.raises(ProcessingError, match="conservation"):
        run(p, out)
    p.with_suffix(".jsonl.provenance.json").unlink()
    with pytest.raises(FileNotFoundError):
        run(p, out)
    assert not out.exists()


@pytest.mark.parametrize("target", ["rows", "metadata"])
def test_overwrite_refusal_preserves_existing(tmp_path: Path, target: str) -> None:
    p = inputs(tmp_path, [record()])
    out = tmp_path / "rows.jsonl"
    meta = out.with_suffix(".jsonl.provenance.json")
    existing = out if target == "rows" else meta
    existing.write_bytes(b"unchanged")
    with pytest.raises(FileExistsError):
        run(p, out)
    assert existing.read_bytes() == b"unchanged"


def test_paths_and_config_fail_before_processing(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record()])
    with pytest.raises(ProcessingError):
        run(p, p)
    with pytest.raises(ProcessingError):
        run(p, tmp_path / "same", provenance_path=tmp_path / "same")
    invalid_configs: list[dict[str, Any]] = [
        {"mode": "as_of"},
        {"cutoff": date(2022, 1, 1)},
        {"mode": "unknown"},
    ]
    for args in invalid_configs:
        with pytest.raises(ValidationError):
            ProcessingConfig(**args)
    with pytest.raises(ProcessingError, match="timezone"):
        process_owner_reports(p, tmp_path / "rows", clock=lambda: datetime(2022, 1, 1))


def test_interrupt_during_stream_leaves_no_completed_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = inputs(tmp_path, [record()])

    def interrupted(_path: Path) -> Any:
        yield record()
        raise KeyboardInterrupt

    monkeypatch.setattr(owner_reports, "iter_clean_records", interrupted)
    out = tmp_path / "rows.jsonl"
    with pytest.raises(KeyboardInterrupt):
        run(p, out)
    assert not out.exists() and not out.with_suffix(".jsonl.provenance.json").exists()


def test_publication_failure_cleans_owned_rows_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = inputs(tmp_path, [record()])
    out = tmp_path / "rows.jsonl"
    meta = out.with_suffix(".jsonl.provenance.json")
    original = Path.open

    def fail(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == meta and args == ("xb",):
            raise OSError("simulated disk failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError, match="simulated"):
        run(p, out)
    assert not out.exists() and not meta.exists()


def test_deterministic_reruns_and_cli(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record()])
    a, b = tmp_path / "a/rows.jsonl", tmp_path / "b/rows.jsonl"
    run(p, a)
    assert main(["--input", str(p), "--output", str(b), "--generation-utc", TIME.isoformat()]) == 0
    assert a.read_bytes() == b.read_bytes()
    assert (
        a.with_suffix(".jsonl.provenance.json").read_bytes()
        == b.with_suffix(".jsonl.provenance.json").read_bytes()
    )


def test_empty_input_and_empty_only_schema(tmp_path: Path) -> None:
    p = inputs(tmp_path, [])
    out = tmp_path / "rows.jsonl"
    meta = run(p, out)
    assert meta.output_record_count == 0 and out.read_bytes() == b""
    p.unlink()
    p.with_suffix(".jsonl.provenance.json").unlink()
    p = inputs(tmp_path, [record()])
    out = tmp_path / "nonempty.jsonl"
    run(p, out)
    row = json.loads(out.read_bytes())
    row["component_mentions"] = [{"code": "engine"}]
    with pytest.raises(ValidationError):
        ExtractionRow.model_validate_json(json.dumps(row))


@pytest.mark.parametrize(
    "metadata",
    [
        [],
        {"cleaned_count": True},
        {"cleaned_count": -1},
        {"cleaned_count": 1, "cleaning_version": ""},
    ],
)
def test_invalid_provenance_fails_before_publication(tmp_path: Path, metadata: object) -> None:
    p = inputs(tmp_path, [record()])
    p.with_suffix(".jsonl.provenance.json").write_text(json.dumps(metadata), encoding="utf-8")
    out = tmp_path / "rows.jsonl"
    with pytest.raises(ProcessingError):
        run(p, out)
    assert not out.exists()


def test_mutating_input_during_read_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = inputs(tmp_path, [record()])

    def changed(_path: Path) -> Any:
        yield record()
        with p.open("ab") as handle:
            handle.write(b"\n")

    monkeypatch.setattr(owner_reports, "iter_clean_records", changed)
    out = tmp_path / "rows.jsonl"
    with pytest.raises(ProcessingError, match="changed"):
        run(p, out)
    assert not out.exists()


def test_interrupt_during_publication_removes_partial_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = inputs(tmp_path, [record()])
    out = tmp_path / "rows.jsonl"
    original = os.fsync

    def interrupt(fd: int) -> None:
        original(fd)
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "fsync", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(p, out)
    assert not out.exists() and not out.with_suffix(".jsonl.provenance.json").exists()


def test_frozen_repository_output_paths_are_rejected(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record()])
    root = Path(owner_reports.__file__).resolve().parents[3]
    with pytest.raises(ProcessingError, match="NLP artifact"):
        run(p, root / "artifacts/presentation/never-create.jsonl")


def test_component_extraction_ignores_structured_codes_and_excluded_rows(tmp_path: Path) -> None:
    rows = [
        record(narrative="Battery and brake pedal", component="engine"),
        record(2, narrative="Grinding noise only", component="transmission"),
        record(3, narrative="Engine", report_date="2024-01-01"),
        record(4, narrative="Engine", report_date=None),
        record(5, narrative=None),
    ]
    p = inputs(tmp_path, rows)
    original = p.read_bytes()
    out = tmp_path / "rows.jsonl"
    meta = run(p, out, config=ProcessingConfig(mode="as_of", cutoff=date(2022, 12, 31)))
    values = [ExtractionRow.model_validate_json(line) for line in out.read_bytes().splitlines()]
    assert [m.code for m in values[0].component_mentions] == ["electrical", "brakes"]
    assert all(not v.component_mentions for v in values[1:])
    assert all(
        len(v.mentions) == len(v.component_mentions) + len(v.symptom_mentions) for v in values
    )
    assert values[1].symptom_mentions[0].code == "noise"
    assert all(not v.associations for v in values)
    for source, value in zip(rows, values, strict=True):
        for m in value.mentions:
            assert source["narrative"][m.start : m.end] == m.evidence_text
    assert meta.input_record_count == meta.output_record_count == 5
    assert sum(meta.status_counts.values()) == 5
    assert meta.milestone == "E" and meta.symptom_extraction_implemented is True
    assert p.read_bytes() == original
