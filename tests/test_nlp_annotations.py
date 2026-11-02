"""Synthetic annotation preparation only; never create gold labels."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from howreliable.nlp.annotations import AnnotationUnit, prepare_annotations
from howreliable.nlp.grouping import validate_partition_assignments
from test_owner_report_nlp import TIME, inputs, record, run


def fixture(tmp_path: Path, size: int = 230) -> tuple[Path, Path]:
    rows = [
        record(
            i, source_reference_id=str(i), narrative=f"Engine stalled. Report-specific context {i}."
        )
        for i in range(1, size + 1)
    ]
    # Extra component row in the same complete report; retain every source row.
    rows.append(record(size + 1, source_reference_id="1", narrative=rows[0]["narrative"]))
    corpus = inputs(tmp_path, rows)
    predictions = tmp_path / "predictions.jsonl"
    run(corpus, predictions)
    return corpus, predictions


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def test_exact_counts_empty_gold_complete_groups_and_mapping(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path, 200)
    dest = tmp_path / "prepared"
    manifest = prepare_annotations(corpus, predictions, dest, generation_utc=TIME)
    assert manifest["partition_counts"] == {"development": 100, "held_out": 100}
    mapping = {r["annotation_id"]: r for r in load_rows(dest / "private/mapping.jsonl")}
    assignments = {}
    ids = set()
    for partition in ("development", "held_out"):
        units = load_rows(dest / partition / "worksheet.jsonl")
        assert len(units) == 100
        for raw in units:
            unit = AnnotationUnit.model_validate_json(json.dumps(raw))
            assert unit.annotation_id not in ids
            ids.add(unit.annotation_id)
            assert unit.status == "pending" and unit.annotator_id is None
            assert all(
                not v.component_annotations
                and not v.symptom_annotations
                and not v.association_annotations
                for v in unit.variants
            )
            original = mapping[unit.annotation_id]["source_records"]
            expected = [
                r
                for r in load_rows(corpus)
                if r["source_reference_id"] == original[0]["source_reference_id"]
            ]
            assert original == expected
            assert sum(v.source_row_count for v in unit.variants) == len(expected)
            assignments.update({r["event_id"]: partition for r in original})
            assert "structured_component" not in json.dumps(raw)
            assert "predictions" not in raw and "source_record_id" not in raw
    validate_partition_assignments(dest / "private/global-membership.sqlite", assignments)
    assert len(ids) == len(mapping) == 200
    assert sum(len(r["source_records"]) for r in mapping.values()) == 201
    provenance = json.loads((dest / "provenance.json").read_bytes())
    assert provenance["complete"]
    for name, spec in provenance["outputs"].items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == spec["sha256"]


def test_seeded_bytes_and_source_immutability(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path)
    before = corpus.read_bytes()
    a, b = tmp_path / "a", tmp_path / "b"
    ma = prepare_annotations(corpus, predictions, a, generation_utc=TIME)
    mb = prepare_annotations(corpus, predictions, b, generation_utc=TIME)
    assert ma == mb
    for path in a.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (b / path.relative_to(a)).read_bytes()
    assert corpus.read_bytes() == before


def test_global_duplicate_closure_excludes_nonpool_relatives(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path)
    # Change the corpus and its parent identity deliberately in this synthetic fixture.
    rows = load_rows(corpus)
    rows.append(record(999, source_reference_id="external", narrative=rows[2]["narrative"]))
    inputs(tmp_path, rows)
    meta = predictions.with_suffix(".jsonl.provenance.json")
    provenance = json.loads(meta.read_bytes())
    provenance["source_cleaning_provenance"]["source_clean_sha256"] = hashlib.sha256(
        corpus.read_bytes()
    ).hexdigest()
    meta.write_text(json.dumps(provenance), encoding="utf-8")
    dest = tmp_path / "prepared"
    manifest = prepare_annotations(corpus, predictions, dest, generation_utc=TIME)
    assert manifest["excluded_candidate_reports"]["multi_report_evaluation_group"] == 1
    assert all(
        r["source_reference_id"] != "3"
        for entry in load_rows(dest / "private/mapping.jsonl")
        for r in entry["source_records"]
    )


def test_small_pool_failure_leaves_no_completed_artifacts(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path, 20)
    dest = tmp_path / "prepared"
    with pytest.raises(ValueError, match="insufficient"):
        prepare_annotations(corpus, predictions, dest, generation_utc=TIME)
    assert not dest.exists()
    assert not list(tmp_path.glob("annotation-stage-*"))


def test_refuse_overwrite_and_tampering(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path, 20)
    dest = tmp_path / "prepared"
    dest.mkdir()
    with pytest.raises(FileExistsError):
        prepare_annotations(corpus, predictions, dest, generation_utc=TIME)
    with predictions.open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        prepare_annotations(corpus, predictions, tmp_path / "other", generation_utc=TIME)
    assert not (tmp_path / "other").exists()


def test_seed_changes_membership_and_reports_unmet_quotas(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path)
    a = prepare_annotations(corpus, predictions, tmp_path / "a", seed="one", generation_utc=TIME)
    b = prepare_annotations(corpus, predictions, tmp_path / "b", seed="two", generation_utc=TIME)
    assert a["memberships"] != b["memberships"]
    assert a["unmet_quotas"]["development"]["quality"] == 10
    assert a["allocations"]["development"]["background_fill"] > 0


def test_worksheet_schema_rejects_invalid_labels_without_creating_gold(tmp_path: Path) -> None:
    corpus, predictions = fixture(tmp_path, 200)
    dest = tmp_path / "run"
    prepare_annotations(corpus, predictions, dest, generation_utc=TIME)
    raw = load_rows(dest / "development/worksheet.jsonl")[0]
    raw["status"] = "machine_annotated"
    with pytest.raises(ValidationError):
        AnnotationUnit.model_validate_json(json.dumps(raw))
    assert (dest / "worksheet-schema.json").exists()
    assert all(
        not v["component_annotations"]
        for r in load_rows(dest / "held_out/worksheet.jsonl")
        for v in r["variants"]
    )
