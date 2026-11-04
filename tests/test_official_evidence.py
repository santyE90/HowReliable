"""Verified optional snapshots: no network or real source acquisition in tests."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.data.recalls.nhtsa import ingest_archives
from howreliable.demo.app import create_app
from howreliable.demo.index import HistoricalIndex, build_index
from howreliable.demo.official_evidence import (
    OfficialEvidence,
    SourceInput,
    build_official,
    optional_official,
)
from howreliable.demo.problem_profile import ProblemProfileService
from howreliable.demo.profile_schemas import OfficialSourceCoverage, ProfileIdentity, ProfileRequest
from test_demo_history import TIME, record, source_file
from test_manufacturer_communications import run_fixture_ingestion
from test_pricing import listing, payload
from test_recalls import fixture_snapshot, recall_row, run_ingest, write_zip


def recall_input(root: Path) -> SourceInput:
    records, apps, provenance, _ = run_ingest(root)
    return SourceInput("recalls", root / "raw/acquisition-manifest.json", records, apps, provenance)


def communication_input(root: Path) -> SourceInput:
    root.mkdir(parents=True)
    records, apps, provenance, _ = run_fixture_ingestion(root)
    manifest = root / "raw-out/acquisition-manifest.json"
    m, p = json.loads(manifest.read_text()), json.loads(provenance.read_text())
    # Adapt the older synthetic fixture's placeholder receipt to the current contract.
    m["adapter_version"] = p["adapter_version"]
    for artifact in m["artifacts"]:
        artifact["official_source_url"] = (
            "https://static.nhtsa.gov/odi/ffdd/tsbs/" + artifact["filename"]
        )
    p["artifacts"] = m["artifacts"]
    manifest.write_text(json.dumps(m), encoding="utf-8")
    provenance.write_text(json.dumps(p), encoding="utf-8")
    return SourceInput("manufacturer_communications", manifest, records, apps, provenance)


def test_verified_snapshot_deterministic_indexed_lookup_and_atomicity(tmp_path: Path) -> None:
    sources = [recall_input(tmp_path / "r"), communication_input(tmp_path / "c")]
    first, second = tmp_path / "first", tmp_path / "second"
    one = build_official(sources, first, TIME)
    two = build_official(list(reversed(sources)), second, TIME)
    assert one == two
    assert (first / "evidence.sqlite").read_bytes() == (second / "evidence.sqlite").read_bytes()
    reader = OfficialEvidence(first)
    # Discover fixture identities rather than relying on source-specific aliases.
    for source in sources:
        row = json.loads(source.applications.read_text(encoding="utf-8").splitlines()[0])
        identity = ProfileIdentity(
            make=row["normalized_make"], model=row["normalized_model"], year=row["model_year"]
        )
        result = reader.lookup(source.source, identity)
        assert result is not None and result.unique_record_count > 0
        assert result.unique_record_count == len({r.record_id for r in result.records})
        assert result.returned_record_count == len(result.records)
        assert "VIN" in result.records[0].applicability_note
        assert "Canadian-market" in result.records[0].applicability_note
        assert result.provenance["serving_database_sha256"] == one["database_sha256"]
    with pytest.raises(FileExistsError):
        build_official(sources, first, TIME)
    assert not list(tmp_path.glob(".official-stage-*"))


def test_missing_source_and_verified_zero_are_distinct(tmp_path: Path) -> None:
    source = recall_input(tmp_path / "r")
    build_official([source], tmp_path / "official", TIME)
    reader = OfficialEvidence(tmp_path / "official")
    identity = ProfileIdentity(make="absent", model="absent", year=2020)
    result = reader.lookup("recalls", identity)
    assert result is not None
    assert result.unique_record_count == 0 and result.records == []
    assert reader.lookup("manufacturer_communications", identity) is None
    assert optional_official(tmp_path / "missing") is None


@pytest.mark.parametrize("target", ["raw", "records", "applications", "completion", "manifest"])
def test_tampering_and_incomplete_sources_never_publish(tmp_path: Path, target: str) -> None:
    source = recall_input(tmp_path / "r")
    if target == "completion":
        p = json.loads(source.provenance.read_text())
        p["processing_complete"] = False
        source.provenance.write_text(json.dumps(p))
    elif target == "manifest":
        p = json.loads(source.manifest.read_text())
        p["artifacts"] = p["artifacts"][:-1]
        source.manifest.write_text(json.dumps(p))
    else:
        path = {
            "raw": source.manifest.parent / "FLAT_RCL_PRE_2010.zip",
            "records": source.records,
            "applications": source.applications,
        }[target]
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        build_official([source], tmp_path / "official", TIME)
    assert not (tmp_path / "official").exists()
    assert not list(tmp_path.glob(".official-stage-*"))


def test_corruption_falls_back_without_disabling_model_free_demo(tmp_path: Path) -> None:
    source = recall_input(tmp_path / "r")
    output = tmp_path / "official"
    build_official([source], output, TIME)
    db = output / "evidence.sqlite"
    db.write_bytes(db.read_bytes() + b"corruption")
    assert optional_official(output) is None
    index_path = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), index_path, TIME)
    before = sha256_file(index_path)
    with TestClient(
        create_app(root=tmp_path, index_path=index_path, official_path=output)
    ) as client:
        response = client.post(
            "/api/demo/v1/vehicle-problem-profiles",
            json={
                "make": "mazda",
                "model": "mazda3",
                "year": 2020,
            },
        )
        assert response.status_code == 200
        assert response.json()["schema_version"] == "vehicle-problem-profile-1.0"
        assert response.json()["source_coverage"]["recalls"]["records"] is None
    assert sha256_file(index_path) == before


def test_optional_evidence_never_changes_complaints_or_purchase_policy(tmp_path: Path) -> None:
    source = recall_input(tmp_path / "r")
    output = tmp_path / "official"
    build_official([source], output, TIME)
    index_path = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), index_path, TIME)
    index = HistoricalIndex(index_path)
    request = ProfileRequest(make="mazda", model="mazda3", year=2020)
    original = ProblemProfileService(index).profile(request)
    enriched = ProblemProfileService(index, OfficialEvidence(output)).profile(request)
    assert enriched.schema_version == "vehicle-problem-profile-1.1"
    assert enriched.historical_evidence == original.historical_evidence
    assert enriched.inspection_questions == original.inspection_questions
    assert isinstance(enriched.source_coverage.recalls, OfficialSourceCoverage)
    assert enriched.source_coverage.validated_symptoms.records is None
    assert enriched.applicability == original.applicability
    with (
        TestClient(create_app(root=tmp_path, index_path=index_path)) as plain,
        TestClient(
            create_app(root=tmp_path, index_path=index_path, official_path=output)
        ) as enabled,
    ):
        for endpoint, body in [
            ("purchase-assessments", {"make": "mazda", "model": "mazda3", "year": 2020}),
            ("price-comparisons", payload([listing("a"), listing("b"), listing("c")])),
        ]:
            a = plain.post("/api/demo/v1/" + endpoint, json=body)
            b = enabled.post("/api/demo/v1/" + endpoint, json=body)
            assert a.status_code == b.status_code == 200
            assert a.json() == b.json()


def test_bounded_unique_campaign_preview(tmp_path: Path) -> None:
    manifest = fixture_snapshot(tmp_path / "raw")
    archive = manifest.parent / "FLAT_RCL_POST_2010.zip"
    rows = [recall_row(RECORD_ID=str(1000 + i), CAMPNO=f"22V{i:06d}") for i in range(21)]
    rows.append(recall_row(RECORD_ID="2000", CAMPNO="22V000000", COMPNAME="STEERING"))
    write_zip(archive, rows)
    receipt = json.loads(manifest.read_text())
    for item in receipt["artifacts"]:
        item["sha256"] = sha256_file(manifest.parent / item["filename"])
    manifest.write_text(json.dumps(receipt))
    records, applications, provenance = [
        tmp_path / name for name in ["r.jsonl", "a.jsonl", "p.json"]
    ]
    ingest_archives(manifest, records, applications, provenance, clock=lambda: TIME)
    source = SourceInput("recalls", manifest, records, applications, provenance)
    build_official([source], tmp_path / "official", TIME)
    result = OfficialEvidence(tmp_path / "official").lookup(
        "recalls",
        ProfileIdentity(
            make=rows[0][2],
            model=rows[0][3],
            year=2022,
        ),
    )
    assert result is not None
    assert result.unique_record_count == 21
    assert result.returned_record_count == 10 and result.records_truncated
    assert result.records[0].matching_applicability_rows == 2
    assert len({r.record_id for r in result.records}) == 10


def test_interruption_never_publishes_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import howreliable.demo.official_evidence as evidence

    source = recall_input(tmp_path / "r")

    def interrupted(*args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(evidence, "_record", interrupted)
    with pytest.raises(KeyboardInterrupt):
        build_official([source], tmp_path / "official", TIME)
    assert not (tmp_path / "official").exists()
    assert not list(tmp_path.glob(".official-stage-*"))
