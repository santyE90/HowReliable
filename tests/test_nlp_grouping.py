"""Synthetic duplicate membership, temporal eligibility and partition-isolation tests."""

import hashlib
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from howreliable.nlp import ExtractionRow, ProcessingConfig, ProcessingError
from howreliable.nlp.grouping import validate_partition_assignments
from test_owner_report_nlp import inputs, record, run


def values(path: Path) -> list[ExtractionRow]:
    return [ExtractionRow.model_validate_json(line) for line in path.read_bytes().splitlines()]


def index(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".membership.sqlite")


def test_reports_texts_conflicts_and_transitive_evaluation_groups(tmp_path: Path) -> None:
    # A-X, A-Y, B-Y, C-Z, C-Y is a transitive evaluation component. A/B/C stay reports.
    rows = [
        record(1, source_reference_id="A", narrative="Engine stalled"),
        record(2, source_reference_id="A", narrative="Brakes failed"),
        record(3, source_reference_id="B", narrative="Brakes failed"),
        record(4, source_reference_id="C", narrative="Battery leaked"),
        record(5, source_reference_id="C", narrative="Brakes failed"),
        record(6, source_reference_id="D", narrative=None),
        record(7, source_reference_id="E", narrative=" "),
    ]
    p = inputs(tmp_path, rows)
    out = tmp_path / "rows.jsonl"
    meta = run(p, out)
    result = values(out)
    assert [v.event_id for v in result] == [r["event_id"] for r in rows]
    assert len({v.report_group_id for v in result[:5]}) == 3
    assert len({v.evaluation_group_id for v in result[:5]}) == 1
    assert result[5].evaluation_group_id != result[6].evaluation_group_id
    assert [v.report_group_conflict for v in result] == [
        True,
        True,
        False,
        True,
        True,
        False,
        False,
    ]
    assert meta.input_record_count == 7 and meta.unique_report_count == 5
    assert meta.conflicting_report_group_count == 2
    assert meta.membership_counts is not None
    assert meta.membership_counts["exact_text_duplicate_count"] == 2
    assert meta.membership_counts["evaluation_group_count"] == 3
    assert meta.membership_sha256 == hashlib.sha256(index(out).read_bytes()).hexdigest()
    with closing(sqlite3.connect(index(out))) as db:
        assert db.execute("SELECT id FROM events ORDER BY sequence").fetchall() == [
            (r["event_id"],) for r in rows
        ]
        assert db.execute("SELECT count(*) FROM events").fetchone() == (7,)
    before = index(out).read_bytes()
    validate_partition_assignments(index(out), {"event_1": "dev", "event_5": "dev"})
    with pytest.raises(ValueError, match="crosses partitions"):
        validate_partition_assignments(index(out), {"event_1": "dev", "event_5": "held_out"})
    with pytest.raises(ValueError, match="unknown event"):
        validate_partition_assignments(index(out), {"missing": "dev"})
    assert index(out).read_bytes() == before


def test_fallback_namespaces_and_exact_not_normalized_text(tmp_path: Path) -> None:
    rows = [
        record(1, source_reference_id=None, narrative="Engine"),
        record(2, source_reference_id="", narrative="engine"),
        record(3, source_reference_id=" ", narrative="Engine "),
        record(4, source_reference_id="900", narrative="Engine"),
        record(5, source_reference_id="900", source_type="another_source", narrative="Unique"),
    ]
    p = inputs(tmp_path, rows)
    out = tmp_path / "rows.jsonl"
    meta = run(p, out)
    rows_out = values(out)
    assert all(v.report_group_fallback for v in rows_out[:3])
    assert len({v.report_group_id for v in rows_out}) == 5
    assert rows_out[0].evaluation_group_id == rows_out[3].evaluation_group_id
    assert len({v.evaluation_group_id for v in rows_out[:3]}) == 3
    assert meta.report_group_fallback_count == 3


def test_cutoff_counts_and_conflicting_dates_are_row_local(tmp_path: Path) -> None:
    rows = [
        record(1, report_date="2022-12-31", occurrence_date="2025-01-01"),
        record(2, report_date="2023-01-01", occurrence_date="2020-01-01"),
        record(3, report_date=None),
        record(4, source_reference_id="future", report_date="2025-01-01"),
    ]
    p = inputs(tmp_path, rows)
    out = tmp_path / "rows.jsonl"
    meta = run(p, out, config=ProcessingConfig(mode="as_of", cutoff=date(2022, 12, 31)))
    result = values(out)
    assert [r.eligible for r in result] == [True, False, False, False]
    assert result[0].mentions and all(not r.mentions for r in result[1:])
    assert [r.report_date_conflict for r in result] == [True, True, True, False]
    assert meta.membership_counts is not None
    assert meta.membership_counts["eligible_record_count"] == 1
    assert meta.membership_counts["eligible_unique_report_count"] == 1
    assert meta.membership_counts["eligible_exact_text_duplicate_count"] == 0
    assert meta.membership_counts["exact_text_duplicate_count"] == 3
    with pytest.raises(ValueError, match="date-excluded"):
        validate_partition_assignments(index(out), {"event_2": "dev"})


def test_full_corpus_keeps_missing_dates_and_group_keys_ignore_input_order(tmp_path: Path) -> None:
    original = [
        record(1, narrative="X", report_date=None),
        record(2, narrative="Y"),
        record(3, narrative="Y", source_reference_id="different"),
    ]
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    a, b = first / "rows.jsonl", second / "rows.jsonl"
    run(inputs(first, original), a)
    run(inputs(second, original[::-1]), b)
    x = {v.event_id: v.evaluation_group_id for v in values(a)}
    y = {v.event_id: v.evaluation_group_id for v in values(b)}
    assert x == y and all(v.eligible for v in values(a))


def test_membership_bytes_deterministic_and_no_overwrite(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record(), record(2)])
    a, b = tmp_path / "a/rows.jsonl", tmp_path / "b/rows.jsonl"
    run(p, a)
    run(p, b)
    assert a.read_bytes() == b.read_bytes()
    assert index(a).read_bytes() == index(b).read_bytes()
    assert (
        a.with_suffix(".jsonl.provenance.json").read_bytes()
        == b.with_suffix(".jsonl.provenance.json").read_bytes()
    )
    existing = tmp_path / "existing.jsonl"
    index(existing).write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        run(p, existing)
    assert not existing.exists() and index(existing).read_bytes() == b"preserve"
    with pytest.raises(ProcessingError, match="distinct"):
        run(p, tmp_path / "collision", provenance_path=tmp_path / "collision.membership.sqlite")


def test_invalid_date_fails_before_any_publication(tmp_path: Path) -> None:
    p = inputs(tmp_path, [record(), record(2, report_date="2022-02-30")])
    out = tmp_path / "rows.jsonl"
    from howreliable.data.features.nhtsa_complaints import FeatureGenerationError

    with pytest.raises(FeatureGenerationError, match="report_date"):
        run(p, out)
    assert not out.exists() and not index(out).exists()
    assert not out.with_suffix(".jsonl.provenance.json").exists()


def test_final_publication_failure_removes_index_and_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = inputs(tmp_path, [record()])
    out = tmp_path / "rows.jsonl"
    meta = out.with_suffix(".jsonl.provenance.json")
    original = Path.open

    def fail(path: Path, *args: object, **kwargs: object) -> object:
        if path == meta and args == ("xb",):
            raise OSError("final publication failed")
        return original(path, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(OSError, match="final publication"):
        run(p, out)
    assert not out.exists() and not meta.exists() and not index(out).exists()
