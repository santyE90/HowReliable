"""Synthetic historical accounting, safe publication and demo API contracts."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import howreliable.demo.app as demo_app
from howreliable.api.schemas import CohortPage, CohortSummary
from howreliable.api.service import PredictionService
from howreliable.data.features.nhtsa_complaints import (
    CLEAN_RECORD_SCHEMA,
    FeatureGenerationError,
    iter_clean_records,
)
from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.demo.index import HistoricalIndex, build_index, connect_readonly, report_key
from howreliable.domain.reliability import VehicleAssociation

TIME = datetime(2026, 11, 2, 18, tzinfo=UTC)


def record(**changes: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "event_id": "event_1", "source_type": "nhtsa_complaint", "source_record_id": "1",
        "source_reference_id": "900", "known_configuration_id": None,
        "source_make": "MAZDA", "normalized_make": "mazda", "source_model": "MAZDA3",
        "normalized_model": "mazda3", "source_model_year": "2020", "model_year": 2020,
        "component": "engine", "source_component": "ENGINE", "severity": "low",
        "death_count": 0, "injury_count": 0, "crash": False, "fire": False,
        "mileage": 100, "mileage_unit": "miles", "occurrence_date": "2021-01-02",
        "report_date": "2022-01-02", "narrative": "SYNTHETIC PRIVATE TEXT NOT FOR INDEX",
        "quality_flags": [],
    }
    row.update(changes)
    row.setdefault("broad_vehicle_id", VehicleAssociation(
        make=row["normalized_make"], model=row["normalized_model"], year=row["model_year"],
    ).broad_identity_id)
    return {key: row[key] for key in CLEAN_RECORD_SCHEMA}


def source_file(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    source = tmp_path / "clean.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    source.with_suffix(".jsonl.provenance.json").write_text(json.dumps({
        "cleaned_count": len(rows), "cleaning_version": "synthetic-1.0",
        "mapping_version": "synthetic-1.0",
    }), encoding="utf-8")
    return source


def test_duplicate_components_dates_and_no_narratives(tmp_path: Path) -> None:
    rows = [record(), record(), record(component="brakes"),
            record(source_reference_id="901", report_date=None),
            record(source_reference_id="902", report_date="2022-02-02"),
            record(source_reference_id="902", report_date="2022-03-02")]
    source = source_file(tmp_path, rows)
    original = source.read_bytes()
    path = tmp_path / "history.sqlite"
    provenance = build_index(source, path, TIME)
    assert source.read_bytes() == original
    assert provenance["source_row_count"] == 6
    assert provenance["unique_report_count"] == 3
    assert provenance["conflicting_date_reports"] == 1
    summary = HistoricalIndex(path).summary(rows[0]["broad_vehicle_id"])
    assert summary["timeline"] == [
        {"month": None, "unique_report_count": 2, "source_row_count": 3},
        {"month": "2022-01", "unique_report_count": 1, "source_row_count": 3},
    ]
    assert summary["components"] == [
        {"category": "engine", "source_row_count": 5, "unique_report_count": 3},
        {"category": "brakes", "source_row_count": 1, "unique_report_count": 1},
    ]
    assert rows[0]["narrative"].encode() not in path.read_bytes()
    assert summary["missing_report_date_rows"] == 1
    assert sum(v["unique_report_count"] for v in summary["timeline"]) == 3
    assert sum(v["source_row_count"] for v in summary["timeline"]) == 6


def test_fallback_does_not_merge_identical_text_reports(tmp_path: Path) -> None:
    rows = [record(source_reference_id=None), record(source_reference_id=" "),
            record(source_reference_id=None, source_record_id="2"), record()]
    path = tmp_path / "index.sqlite"
    p = build_index(source_file(tmp_path, rows), path, TIME)
    assert p["unique_report_count"] == 3
    assert p["fallback_source_rows"] == 3
    assert report_key(rows[0]) == report_key(rows[1])


def test_determinism_integrity_and_overwrite(tmp_path: Path) -> None:
    source = source_file(tmp_path, [record()])
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    assert build_index(source, a, TIME) == build_index(source, b, TIME)
    assert a.read_bytes() == b.read_bytes()
    assert a.with_suffix(".sqlite.provenance.json").read_bytes() == (
        b.with_suffix(".sqlite.provenance.json").read_bytes())
    with closing(connect_readonly(a)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM rows")
    with pytest.raises(FileExistsError):
        build_index(source, a, TIME)
    a.with_suffix(".sqlite.provenance.json").unlink()
    with pytest.raises(FileNotFoundError):
        HistoricalIndex(a)
    with pytest.raises(FileExistsError):
        build_index(source, a, TIME)


@pytest.mark.parametrize("change", [
    {"report_date": "not-a-date"}, {"report_date": "2022-02-30"},
    {"broad_vehicle_id": "wrong"}, {"source_record_id": ""}, {"report_date": "20220102"},
])
def test_bad_input_never_publishes(tmp_path: Path, change: dict[str, Any]) -> None:
    source = source_file(tmp_path, [record(), record(**change)])
    out = tmp_path / "index.sqlite"
    with pytest.raises((ValueError, FeatureGenerationError)):
        build_index(source, out, TIME)
    assert not out.exists()
    assert not list(tmp_path.glob(".history-build-*"))


def test_count_mismatch_and_non_utc_rejected(tmp_path: Path) -> None:
    source = source_file(tmp_path, [record()])
    marker = source.with_suffix(".jsonl.provenance.json")
    value = json.loads(marker.read_text())
    value["cleaned_count"] = 2
    marker.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="count"):
        build_index(source, tmp_path / "index.sqlite", TIME)
    with pytest.raises(ValueError, match="UTC"):
        build_index(source, tmp_path / "index.sqlite", TIME.replace(tzinfo=None))


def test_interrupted_publication_cleans_owned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = source_file(tmp_path, [record()])
    out = tmp_path / "index.sqlite"
    original = os.link
    calls = 0

    def interrupt(a: Path, b: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        original(a, b)

    monkeypatch.setattr(os, "link", interrupt)
    with pytest.raises(KeyboardInterrupt):
        build_index(source, out, TIME)
    assert not out.exists()
    assert not out.with_suffix(".sqlite.provenance.json").exists()


def test_checksum_tamper_rejected(tmp_path: Path) -> None:
    source = source_file(tmp_path, [record()])
    out = tmp_path / "index.sqlite"
    build_index(source, out, TIME)
    with out.open("ab") as target:
        target.write(b"modified")
    with pytest.raises(ValueError, match="checksum"):
        HistoricalIndex(out)


def test_api_discovery_summaries_and_prediction_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [record(), record(normalized_model="other"), record(normalized_make="other")]
    path = tmp_path / "index.sqlite"
    build_index(source_file(tmp_path, rows), path, TIME)
    cohort = CohortSummary(cohort_id=rows[0]["broad_vehicle_id"], make="mazda", model="mazda3",
                           model_year=2020)
    service = Mock(spec=PredictionService)
    service.list_cohorts.return_value = CohortPage(items=(cohort,), total=1, limit=100, offset=0)

    def factory(**kwargs: Any) -> FastAPI:
        assert kwargs["settings"].artifact_backend == "local"
        app = FastAPI()
        app.state.prediction_service = service
        return app

    monkeypatch.setattr(demo_app, "create_prediction_app", factory)
    client = TestClient(demo_app.create_app(root=tmp_path, index_path=path))
    prefix = "/api/demo/v1"
    page = client.get(prefix + "/vehicles").json()
    assert page["makes"] == ["mazda", "other"]
    assert page["total"] == 3
    assert client.get(prefix + "/vehicles?make=MAZDA&model=MAZDA3").json()["years"] == [2020]
    assert client.get(prefix + "/vehicles?model=mazda3").status_code == 422
    assert client.get(prefix + "/vehicles/resolve?make=mazda&model=missing&year=2020").json()[
        "status"] == "unmatched"
    assert client.get(prefix + "/vehicles/resolve?make=MAZDA&model=MAZDA3&year=2020").json()[
        "status"] == "matched"
    base = prefix + "/vehicles/" + rows[0]["broad_vehicle_id"]
    assert client.get(base + "/history").json()["unique_report_count"] == 1
    assert client.get(base + "/prediction").json()["status"] == "supported"
    unsupported = prefix + "/vehicles/" + rows[1]["broad_vehicle_id"] + "/prediction"
    assert client.get(unsupported).json()["status"] == "unsupported"
    service.list_cohorts.return_value = CohortPage(
        items=(cohort.model_copy(update={"cohort_id": "different"}),),
        total=1, limit=100, offset=0,
    )
    ambiguous_client = TestClient(demo_app.create_app(root=tmp_path, index_path=path))
    assert ambiguous_client.get(base + "/prediction").json()["status"] == "ambiguous"
    assert client.get(prefix + "/vehicles/missing/history").status_code == 404
    assert client.get(prefix + "/nlp/sample-summary").status_code == 503
    assert client.get(prefix + "/vehicles?limit=1&offset=1").json()["items"] == page["items"][1:2]


def test_ambiguous_resolution_abstains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Defensive resolver: if a future index permits multiple broad identities, never guess.
    fake_index = SimpleNamespace(discover=lambda *args: [
        {"id": "one", "make": "a", "model": "b", "year": 2000},
        {"id": "two", "make": "a", "model": "b", "year": 2000},
    ])
    monkeypatch.setattr(demo_app, "HistoricalIndex", lambda _: fake_index)
    service = Mock(spec=PredictionService)
    service.list_cohorts.return_value = CohortPage(items=(), total=0, limit=100, offset=0)

    def factory(**kwargs: Any) -> FastAPI:
        app = FastAPI()
        app.state.prediction_service = service
        return app

    monkeypatch.setattr(demo_app, "create_prediction_app", factory)
    client = TestClient(demo_app.create_app(root=tmp_path))
    assert client.get("/api/demo/v1/vehicles/resolve?make=a&model=b&year=2000").json()[
        "status"] == "ambiguous"


def test_changed_input_is_not_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import howreliable.demo.index as module

    source = source_file(tmp_path, [record()])
    out = tmp_path / "index.sqlite"
    original = iter_clean_records

    def changing_input(path: Path) -> Any:
        yield from original(path)
        with path.open("a") as target:
            target.write("\n")

    monkeypatch.setattr(module, "iter_clean_records", changing_input)
    with pytest.raises(ValueError, match="input changed"):
        build_index(source, out, TIME)
    assert not out.exists()


def test_existing_completion_marker_is_never_overwritten(tmp_path: Path) -> None:
    source = source_file(tmp_path, [record()])
    out = tmp_path / "index.sqlite"
    marker = out.with_suffix(".sqlite.provenance.json")
    marker.write_text("existing")
    with pytest.raises(FileExistsError):
        build_index(source, out, TIME)
    assert marker.read_text() == "existing"
    assert not out.exists()


def test_source_report_policy_matches_existing_grouping() -> None:
    # A policy regression check, not an extraction run or annotation/prediction access.
    from howreliable.nlp.owner_reports import _row
    from howreliable.nlp.schemas import ProcessingConfig

    for row in (record(), record(source_reference_id=None),
                record(source_reference_id=" ", source_record_id="unicode-é")):
        extracted = _row(row, ProcessingConfig())
        assert report_key(row) == (extracted.report_group_id, extracted.report_group_fallback)


def test_global_nlp_endpoint_is_unfiltered_verified_and_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "index.sqlite"
    build_index(source_file(tmp_path, [record()]), path, TIME)
    service = Mock(spec=PredictionService)
    service.list_cohorts.return_value = CohortPage(items=(), total=0, limit=100, offset=0)

    def factory(**kwargs: Any) -> FastAPI:
        app = FastAPI()
        app.state.prediction_service = service
        return app

    monkeypatch.setattr(demo_app, "create_prediction_app", factory)
    summary = tmp_path / demo_app.G1_SUMMARY
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({"denominators": {"source_rows": 1000}}))
    marker = summary.with_suffix(".json.provenance.json")
    marker.write_text(json.dumps({"complete": True, "output_sha256": sha256_file(summary),
                                  "source_rule_identities": {"schema_version": "1.3"}}))
    client = TestClient(demo_app.create_app(root=tmp_path, index_path=path))
    endpoint = "/api/demo/v1/nlp/sample-summary"
    response = client.get(endpoint)
    assert response.status_code == 200
    result = response.json()
    assert result["vehicle_specific"] is False
    assert result["predates_current_rules"] is True
    assert result["scope"] == "global_bounded_G1_sample_only"
    summary.write_text("{}")
    assert client.get(endpoint).status_code == 503
