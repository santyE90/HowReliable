"""Synthetic descriptive summaries; no historical corpus processing."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from howreliable.nlp import ProcessingConfig
from howreliable.nlp.summaries import main, summarize_reports
from test_owner_report_nlp import TIME, inputs, record, run


def prepare(tmp: Path, rows: list[dict[str, Any]], **kwargs: Any) -> Path:
    extraction = tmp / "rows.jsonl"
    run(inputs(tmp, rows), extraction, **kwargs)
    return extraction


def summary(source: Path, output: Path) -> dict[str, Any]:
    summarize_reports(source, output, clock=lambda: TIME)
    return json.loads(output.read_bytes())  # type: ignore[no-any-return]


def test_report_deduplication_assertions_and_explicit_links(tmp_path: Path) -> None:
    source = prepare(
        tmp_path,
        [
            record(1, source_reference_id="A", narrative="Engine stalled. Engine stalled."),
            record(2, source_reference_id="A", narrative="Engine stalled."),
            record(3, source_reference_id="B", narrative="Engine stalled."),
            record(4, source_reference_id="C", narrative="Engine did not stall."),
            record(5, source_reference_id="D", narrative="Battery replaced; vehicle stalled."),
        ],
    )
    result = summary(source, tmp_path / "summary.json")
    engine = next(x for x in result["components"] if x["category"] == "engine")
    assert engine["source_row_count"] == 4
    assert engine["unique_report_count"] == 3
    assert engine["occurrence_count"] == 5
    affirmed = next(x for x in result["symptoms"] if x["assertion"] == "affirmed")
    assert affirmed["source_row_count"] == 4
    assert affirmed["unique_report_count"] == 3
    assert any(x["assertion"] == "negated" for x in result["symptoms"])
    assert all(x["component"] != "electrical" for x in result["associations"])
    assert any(x["primary_pattern"] for x in result["associations"])
    assert b"Engine stalled" not in (tmp_path / "summary.json").read_bytes()
    assert b"event_1" not in (tmp_path / "summary.json").read_bytes()


def test_temporal_denominators_and_empty_narratives(tmp_path: Path) -> None:
    source = prepare(
        tmp_path,
        [
            record(1, source_reference_id="A", narrative="Engine stalled."),
            record(2, source_reference_id="A", narrative="Engine stalled."),
            record(3, source_reference_id="B", narrative=None),
            record(4, source_reference_id="C", narrative=" "),
            record(
                5, source_reference_id="D", narrative="Brakes failed.", report_date="2023-01-01"
            ),
            record(6, source_reference_id="E", narrative="Brakes failed.", report_date=None),
            record(7, source_reference_id="F", narrative="Nothing recognized here."),
        ],
        config=ProcessingConfig(mode="as_of", cutoff=date(2022, 12, 31)),
    )
    result = summary(source, tmp_path / "summary.json")
    assert result["denominators"] == {
        "total_source_rows": 7,
        "total_unique_reports": 6,
        "eligible_source_rows": 5,
        "eligible_unique_reports": 4,
        "processable_source_rows": 3,
        "processable_unique_reports": 2,
    }
    assert all(x["category"] != "brakes" for x in result["components"])
    assert result["eligible_processed_without_mentions"] == {
        "source_row_count": 1,
        "unique_report_count": 1,
    }
    assert sum(x["source_row_count"] for x in result["processing_statuses"]) == 7


def test_unresolved_uncertain_diagnostics_and_stable_order(tmp_path: Path) -> None:
    source = prepare(
        tmp_path,
        [
            record(
                1,
                source_reference_id="A",
                narrative="Check engine light. Dealer suspects fuel pump.",
            ),
            record(2, source_reference_id="B", narrative="Brakes. Steering."),
        ],
    )
    result = summary(source, tmp_path / "summary.json")
    assert result["unresolved_mentions"]["components"]
    assert any(x["assertion"] == "uncertain" for x in result["assertions"])
    for section in ("components", "symptoms"):
        assert result[section] == sorted(
            result[section],
            key=lambda x: (
                -x["unique_report_count"],
                -x["source_row_count"],
                x["category"],
                x["assertion"],
            ),
        )


def test_determinism_provenance_and_read_only_sources(tmp_path: Path) -> None:
    source = prepare(tmp_path, [record()])
    originals = {p: p.read_bytes() for p in tmp_path.iterdir()}
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    summary(source, a)
    summary(source, b)
    assert a.read_bytes() == b.read_bytes()
    pa, pb = a.with_suffix(".json.provenance.json"), b.with_suffix(".json.provenance.json")
    assert pa.read_bytes() == pb.read_bytes()
    meta = json.loads(pa.read_bytes())
    assert meta["output_sha256"] == hashlib.sha256(a.read_bytes()).hexdigest()
    assert meta["source_extraction_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert meta["complete"] and meta["generation_utc"] == "2026-10-27T12:00:00Z"
    assert meta["source_schema_version"].endswith("1.3")
    assert all(p.read_bytes() == value for p, value in originals.items())


@pytest.mark.parametrize("existing", ["summary.json", "summary.json.provenance.json"])
def test_overwrite_refusal(tmp_path: Path, existing: str) -> None:
    source = prepare(tmp_path, [record()])
    target = tmp_path / existing
    target.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        summary(source, tmp_path / "summary.json")
    assert target.read_bytes() == b"preserve"


@pytest.mark.parametrize("suffix", ["", ".membership.sqlite"])
def test_checksum_mismatch_publishes_nothing(tmp_path: Path, suffix: str) -> None:
    source = prepare(tmp_path, [record()])
    changed = Path(str(source) + suffix)
    with changed.open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        summary(source, tmp_path / "summary.json")
    assert not (tmp_path / "summary.json").exists()


def test_interrupt_cleans_published_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = prepare(tmp_path, [record()])
    original = Path.open

    def interrupted(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if path.name == "summary.json.provenance.json" and mode == "xb":
            raise KeyboardInterrupt
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", interrupted)
    with pytest.raises(KeyboardInterrupt):
        summary(source, tmp_path / "summary.json")
    assert not (tmp_path / "summary.json").exists()
    assert not (tmp_path / "summary.json.provenance.json").exists()


def test_cli_empty_run(tmp_path: Path) -> None:
    source = prepare(tmp_path, [])
    output = tmp_path / "summary.json"
    assert (
        main(
            [
                "--extraction",
                str(source),
                "--output",
                str(output),
                "--generation-utc",
                TIME.isoformat(),
            ]
        )
        == 0
    )
    result = json.loads(output.read_bytes())
    assert result["denominators"]["total_unique_reports"] == 0
    assert result["components"] == result["symptoms"] == result["associations"] == []


def test_same_category_multiple_statuses_counts_report_once(tmp_path: Path) -> None:
    source = prepare(
        tmp_path,
        [
            record(1, source_reference_id="A", narrative="Engine stalled. Engine did not stall."),
            record(2, source_reference_id="A", narrative="Engine might stall."),
        ],
    )
    result = summary(source, tmp_path / "summary.json")
    totals = result["category_totals_all_assertions"]["symptom"]
    assert len(totals) == 1
    assert totals[0]["unique_report_count"] == 1
    assert totals[0]["source_row_count"] == 2
    assert {x["assertion"] for x in result["symptoms"]} == {
        "affirmed",
        "negated",
        "uncertain",
    }


def test_membership_disagreement_rejected_even_with_updated_hash(tmp_path: Path) -> None:
    source = prepare(tmp_path, [record()])
    member = source.with_suffix(".jsonl.membership.sqlite")
    with closing(sqlite3.connect(member)) as db:
        db.execute("UPDATE events SET sequence=99")
        db.commit()
    marker = source.with_suffix(".jsonl.provenance.json")
    meta = json.loads(marker.read_bytes())
    meta["membership_sha256"] = hashlib.sha256(member.read_bytes()).hexdigest()
    marker.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees with membership"):
        summary(source, tmp_path / "summary.json")
    assert not (tmp_path / "summary.json").exists()


def test_missing_completion_marker_and_input_collision(tmp_path: Path) -> None:
    source = prepare(tmp_path, [record()])
    with pytest.raises(ValueError, match="distinct"):
        summary(source, source)
    source.with_suffix(".jsonl.provenance.json").unlink()
    with pytest.raises(FileNotFoundError):
        summary(source, tmp_path / "summary.json")
    assert not (tmp_path / "summary.json").exists()
