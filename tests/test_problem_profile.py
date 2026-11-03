"""Read-only profiles: counting, applicability, missingness and legacy API separation."""

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from howreliable.data.features.nhtsa_complaints import FeatureGenerationError
from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.demo.app import create_app
from howreliable.demo.index import HistoricalIndex, build_index
from howreliable.demo.problem_profile import LABELS, ProblemProfileService, build_problem_profile
from howreliable.demo.profile_schemas import ProfileRequest
from howreliable.demo.schemas import HistoricalSummary, HistoricalVehicle
from test_demo_history import TIME, record, source_file

ROUTE = "/api/demo/v1/vehicle-problem-profiles"
REQUEST: dict[str, Any] = {"make": "MAZDA", "model": "Mazda3", "year": 2020}


def index_for(tmp_path: Path, rows: list[dict[str, Any]]) -> HistoricalIndex:
    path = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, rows), path, TIME)
    return HistoricalIndex(path)


def test_overlap_duplicates_dates_and_determinism(tmp_path: Path) -> None:
    index = index_for(
        tmp_path,
        [
            record(),
            record(),
            record(component="electrical"),
            record(source_reference_id="901", component="other", report_date=None),
            record(source_reference_id="902", component="unknown", report_date=None),
            record(source_reference_id="903", report_date="2022-02-01"),
            record(source_reference_id="903", report_date="2022-03-01"),
        ],
    )
    before = sha256_file(index.path)
    service = ProblemProfileService(index)
    result = service.profile(ProfileRequest(**REQUEST))
    assert result.profile_status == "AVAILABLE"
    history = result.historical_evidence
    assert history is not None
    assert (history.source_row_count, history.unique_report_count) == (7, 4)
    assert sum(c.unique_report_count for c in history.components) == 5
    assert history.timeline[0].month is None
    assert history.timeline[0].unique_report_count == 3
    assert sum(b.source_row_count for b in history.timeline) == 7
    assert sum(b.unique_report_count for b in history.timeline) == 4
    assert [c.category for c in history.components] == ["engine", "electrical", "other", "unknown"]
    assert [q.supporting_component for q in result.inspection_questions] == [
        "engine",
        "electrical",
        None,
        None,
    ]
    assert [q.supporting_unique_report_count for q in result.inspection_questions] == [
        2,
        1,
        None,
        None,
    ]
    assert result.model_dump_json() == service.profile(ProfileRequest(**REQUEST)).model_dump_json()
    assert sha256_file(index.path) == before
    assert "SYNTHETIC PRIVATE TEXT" not in result.model_dump_json()


@pytest.mark.parametrize("category", sorted(LABELS))
def test_thirteen_category_question_mapping(tmp_path: Path, category: str) -> None:
    result = ProblemProfileService(index_for(tmp_path, [record(component=category)])).profile(
        ProfileRequest(**REQUEST),
    )
    question = result.inspection_questions[0]
    assert question.supporting_component == category
    assert question.supporting_unique_report_count == 1
    assert LABELS[category] in question.question_text
    assert question.question_id == f"profile.v1.component.{category}"
    assert question.rule_id == "profile-question.v1.structured_component"
    assert any("One report" in limit for limit in question.limitations)
    assert result.component_evidence[0].question_ids == [question.question_id]


def test_fallback_reports_and_unknown_only(tmp_path: Path) -> None:
    result = ProblemProfileService(
        index_for(
            tmp_path,
            [
                record(source_reference_id=None, component="unknown"),
                record(source_reference_id=None, component="unknown"),
                record(source_reference_id=None, source_record_id="2", component="other"),
            ],
        )
    ).profile(ProfileRequest(**REQUEST))
    assert result.historical_evidence is not None
    assert result.historical_evidence.unique_report_count == 2
    assert result.historical_evidence.source_row_count == 3
    assert all(q.supporting_component is None for q in result.inspection_questions)
    assert len(result.component_evidence) == 2


def test_configuration_normalization_and_missing_sources(tmp_path: Path) -> None:
    service = ProblemProfileService(index_for(tmp_path, [record()]))
    plain = service.profile(ProfileRequest(**REQUEST))
    configured = service.profile(
        ProfileRequest.model_validate(
            {
                "make": "  \uff2d\uff21\uff3a\uff24\uff21  ",
                "model": " MAZDA3 ",
                "year": 2020,
                "configuration": {"trim": " Sport ", "powertrain": " ", "market_country": "CA"},
            }
        )
    )
    assert configured.historical_evidence == plain.historical_evidence
    assert configured.supplied_configuration is not None
    assert configured.supplied_configuration.trim == "sport"
    assert configured.supplied_configuration.powertrain is None
    assert configured.applicability.configuration == "CONFIGURATION_APPLICABILITY_UNRESOLVED"
    assert configured.applicability.individual_vehicle == "INDIVIDUAL_VEHICLE_NOT_VERIFIED"
    assert configured.applicability.market == "US_SOURCE_MARKET_APPLICABILITY_UNRESOLVED"
    sources = configured.source_coverage
    assert sources.complaints.availability == "AVAILABLE"
    for source in [
        sources.recalls,
        sources.manufacturer_communications,
        sources.validated_symptoms,
    ]:
        assert source.unique_record_count is None and source.records is None
    assert sources.validated_symptoms.reason_code == "nlp_human_validation_deferred"
    assert "ewr" not in configured.model_dump_json().lower()


def test_zero_reports_is_not_unavailable_or_unmatched(tmp_path: Path) -> None:
    index = index_for(tmp_path, [record()])
    vehicle = HistoricalVehicle(**index.discover("mazda", "mazda3", 2020)[0])
    history = HistoricalSummary(**index.summary(vehicle.id)).model_copy(
        update={
            "source_row_count": 0,
            "unique_report_count": 0,
            "missing_report_date_rows": 0,
            "first_report_date": None,
            "last_report_date": None,
            "timeline": [],
            "components": [],
        }
    )
    request = ProfileRequest(**REQUEST)
    zero = build_problem_profile(request, [vehicle], history)
    assert zero.profile_status == "AVAILABLE"
    assert zero.source_coverage.complaints.unique_record_count == 0
    assert any(g.code == "zero_recorded_reports" for g in zero.missing_information)
    unmatched = build_problem_profile(request, [], None)
    assert unmatched.profile_status == "NO_MATCHING_REPORTS"
    assert unmatched.historical_evidence is None
    assert unmatched.source_coverage.complaints.unique_record_count is None
    unavailable = build_problem_profile(request, [], None, source_available=False)
    assert unavailable.profile_status == "SOURCE_UNAVAILABLE"
    assert unavailable.source_coverage.complaints.availability == "SOURCE_UNAVAILABLE"


def test_safe_provenance_and_corrupt_counts(tmp_path: Path) -> None:
    index = index_for(tmp_path, [record()])
    candidate = HistoricalVehicle(**index.discover("mazda", "mazda3", 2020)[0])
    history = HistoricalSummary(**index.summary(candidate.id))
    modified = history.model_copy(
        update={
            "provenance": {
                **history.provenance,
                "private_mapping": "DO NOT PUBLISH",
                "source_filename": "C:\\private\\clean.jsonl",
            }
        }
    )
    result = build_problem_profile(ProfileRequest(**REQUEST), [candidate], modified)
    assert result.historical_evidence is not None
    assert result.historical_evidence.provenance["source_filename"] == "clean.jsonl"
    assert "DO NOT PUBLISH" not in result.model_dump_json()
    with pytest.raises(ValueError, match="conservation"):
        build_problem_profile(
            ProfileRequest(**REQUEST),
            [candidate],
            history.model_copy(
                update={"unique_report_count": 2},
            ),
        )


def test_model_free_route_and_failure_envelopes(tmp_path: Path) -> None:
    index = index_for(tmp_path, [record()])
    with TestClient(create_app(root=tmp_path, index_path=index.path)) as client:
        response = client.post(ROUTE, json=REQUEST)
        assert response.status_code == 200
        assert response.json()["schema_version"] == "vehicle-problem-profile-1.0"
        assert client.get("/api/demo/v1/vehicles").status_code == 200
        assert (
            client.post(ROUTE, json={**REQUEST, "model": "not present"}).json()["profile_status"]
            == "NO_MATCHING_REPORTS"
        )
        candidate = index.discover("mazda", "mazda3", 2020)[0]
        with patch.object(
            HistoricalIndex,
            "discover",
            return_value=[
                {**candidate, "id": "z"},
                {**candidate, "id": "a"},
            ],
        ):
            ambiguous = client.post(ROUTE, json=REQUEST)
            assert ambiguous.status_code == 409
            assert [v["id"] for v in ambiguous.json()["identity_resolution"]["candidates"]] == [
                "a",
                "z",
            ]
            assert ambiguous.json()["historical_evidence"] is None
        with patch.object(HistoricalIndex, "summary", side_effect=sqlite3.DatabaseError("private")):
            unavailable = client.post(ROUTE, json=REQUEST)
            assert unavailable.status_code == 503
            assert unavailable.json()["profile_status"] == "SOURCE_UNAVAILABLE"
            assert "private" not in unavailable.text


@pytest.mark.parametrize(
    "changes",
    [
        {"make": " "},
        {"make": "x\x00"},
        {"model": "x" * 101},
        {"year": "2020"},
        {"year": 1800},
        {"year": True},
        {"vin": "not accepted"},
        {"configuration": {"transmission": "guess"}},
        {"configuration": {"trim": "x" * 101}},
        {"configuration": {"powertrain": "a\x00"}},
        {"configuration": {"market_country": "GB"}},
        {"schema_version": "other"},
    ],
)
def test_invalid_requests(tmp_path: Path, changes: dict[str, Any]) -> None:
    index = index_for(tmp_path, [record()])
    with TestClient(create_app(root=tmp_path, index_path=index.path)) as client:
        assert client.post(ROUTE, json={**REQUEST, **changes}).status_code == 422


def test_missing_index_remains_fail_closed(tmp_path: Path) -> None:
    with pytest.raises((OSError, ValueError)):
        create_app(root=tmp_path, index_path=tmp_path / "absent.sqlite")


def test_invalid_source_dates_never_become_profile_evidence(tmp_path: Path) -> None:
    with pytest.raises(FeatureGenerationError, match="invalid report_date"):
        index_for(tmp_path, [record(report_date="not-a-date")])
    assert not (tmp_path / "history.sqlite").exists()


def test_missing_identity_fields(tmp_path: Path) -> None:
    index = index_for(tmp_path, [record()])
    with TestClient(create_app(root=tmp_path, index_path=index.path)) as client:
        for field in ("make", "model", "year"):
            assert client.post(ROUTE, json={
                k: v for k, v in REQUEST.items() if k != field
            }).status_code == 422


def test_mismatched_evidence_identity_fails_closed(tmp_path: Path) -> None:
    index = index_for(tmp_path, [record()])
    summary = index.summary(index.discover("mazda", "mazda3", 2020)[0]["id"])
    summary["vehicle"] = {**summary["vehicle"], "model": "different"}
    with patch.object(index, "summary", return_value=summary):
        result = ProblemProfileService(index).profile(ProfileRequest(**REQUEST))
    assert result.profile_status == "SOURCE_UNAVAILABLE"
    assert result.historical_evidence is None
