"""Synthetic purchase inputs, report accounting, deterministic advice and HTTP boundary."""

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import howreliable.demo.app as demo
from howreliable.api.schemas import CohortPage
from howreliable.api.service import PredictionService
from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.demo.index import HistoricalIndex, build_index
from howreliable.demo.purchase import (
    MILEAGE_PROMPT_KM,
    PurchaseAssessmentService,
    PurchaseVehicleAmbiguousError,
    PurchaseVehicleNotFoundError,
    build_assessment,
)
from howreliable.demo.purchase_schemas import (
    ComponentCoverage,
    PurchaseAssessmentRequest,
)
from howreliable.demo.schemas import HistoricalSummary
from test_demo_history import TIME, record, source_file

ENDPOINT = "/api/demo/v1/purchase-assessments"


@pytest.fixture
def history(tmp_path: Path) -> HistoricalIndex:
    # Report 900 spans engine/electrical/other/unknown. Report 901 repeats other rows.
    rows = [record(), record(component="engine"), record(component="electrical"),
            record(component="other"), record(component="unknown"),
            record(component="other", source_reference_id="901"),
            record(component="other", source_reference_id="901")]
    output = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, rows), output, TIME)
    return HistoricalIndex(output)


def request(**overrides: object) -> PurchaseAssessmentRequest:
    return PurchaseAssessmentRequest.model_validate({
        "make": "MAZDA", "model": "MAZDA3", "year": 2020, **overrides,
    })


def test_conservation_component_overlap_and_unknown_union(history: HistoricalIndex) -> None:
    before = sha256_file(history.path)
    result = PurchaseAssessmentService(history).assess(request())
    assert result.historical_evidence.unique_report_count == 2
    assert result.historical_evidence.source_row_count == 7
    assert result.component_coverage.unknown_or_other_unique_reports == 2
    assert result.component_coverage.unknown_or_other_source_rows == 4
    assert result.component_coverage.specific_component_unique_reports == 1
    assert result.component_coverage.total_unique_reports == 2
    assert [(c.category.value, c.unique_report_count, c.source_row_count)
            for c in result.reported_component_concerns] == [
                ("electrical", 1, 1), ("engine", 1, 2)]
    assert [p.category.value for p in result.inspection_priorities
            if p.category is not None] == ["electrical", "engine"]
    assert len([p for p in result.inspection_priorities if p.basis == "generic"]) == 2
    assert result.historical_evidence.provenance == history.provenance
    assert before == sha256_file(history.path)


def test_default_context_and_deterministic_serialization(history: HistoricalIndex) -> None:
    service = PurchaseAssessmentService(history)
    a, b = service.assess(request()), service.assess(request())
    assert a.model_dump_json() == b.model_dump_json()
    assert a.purchase_context.make == "mazda"
    assert a.purchase_context.odometer_km is None
    assert a.purchase_context.asking_price_cad is None
    assert a.purchase_context.maintenance_history == "unknown"
    assert [c.rule_id for c in a.purchase_considerations] == [
        "odometer_missing.v1", "maintenance_unknown.v1", "price_missing.v1",
    ]
    assert request(make="\uff2d\uff21\uff3a\uff24\uff21", model="  MAZDA3  ").make == "mazda"


@pytest.mark.parametrize("values", [
    {"make": " "}, {"make": 1}, {"model": ""}, {"year": "2020"},
    {"year": True}, {"year": 1885}, {"year": 2101},
    {"odometer_km": -1}, {"odometer_km": True}, {"odometer_km": 200000.5},
    {"odometer_km": "200000"}, {"asking_price_cad": -1},
    {"asking_price_cad": "NaN"}, {"asking_price_cad": float("inf")},
    {"asking_price_cad": "not money"}, {"asking_price_cad": True},
    {"asking_price_cad": "1.001"}, {"maintenance_history": "good"},
    {"maintenance_history": None}, {"currency": "USD"}, {"risk_score": 0.8},
])
def test_invalid_inputs(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        request(**values)


@pytest.mark.parametrize("price", [0, 14500, 14500.5, "14500.50", Decimal("14500.50")])
def test_price_is_finite_cad_context_only(history: HistoricalIndex, price: object) -> None:
    service = PurchaseAssessmentService(history)
    base = service.assess(request())
    result = service.assess(request(asking_price_cad=price))
    assert result.historical_evidence == base.historical_evidence
    assert result.reported_component_concerns == base.reported_component_concerns
    assert result.inspection_priorities == base.inspection_priorities
    consideration = result.purchase_considerations[2]
    assert consideration.rule_id == "price_context_only.v1"
    assert "context only" in consideration.explanation
    assert "No market comparisons" in consideration.explanation
    assert result.purchase_context.asking_price_cad == Decimal(str(price))


@pytest.mark.parametrize("maintenance,phrase", [
    ("documented", "verify that the records apply"),
    ("partial", "Identify gaps"),
    ("unknown", "Ask whether records exist"),
    ("undocumented", "does not prove that maintenance was never performed"),
])
def test_maintenance_changes_documentation_context_only(
    history: HistoricalIndex, maintenance: str, phrase: str,
) -> None:
    service = PurchaseAssessmentService(history)
    base = service.assess(request())
    result = service.assess(request(maintenance_history=maintenance))
    assert result.historical_evidence == base.historical_evidence
    assert result.reported_component_concerns == base.reported_component_concerns
    assert phrase in result.purchase_considerations[1].explanation


def test_mileage_threshold_does_not_change_historical_evidence(history: HistoricalIndex) -> None:
    service = PurchaseAssessmentService(history)
    before = service.assess(request(odometer_km=MILEAGE_PROMPT_KM - 1))
    at = service.assess(request(odometer_km=MILEAGE_PROMPT_KM))
    assert before.purchase_considerations[0].rule_id == "odometer_supplied.v1"
    assert at.purchase_considerations[0].rule_id == "odometer_context_prompt.v1"
    assert "particularly important" in at.purchase_considerations[0].explanation
    assert "not a validated failure threshold" in at.purchase_considerations[0].explanation
    assert before.historical_evidence == at.historical_evidence
    assert before.reported_component_concerns == at.reported_component_concerns
    assert service.assess(request(odometer_km=0)).purchase_context.odometer_km == 0


def test_empty_sparse_and_unknown_only_evidence(history: HistoricalIndex) -> None:
    item = history.discover("mazda", "mazda3", 2020)[0]
    base = HistoricalSummary(**history.summary(item["id"]))
    empty = base.model_copy(update={
        "source_row_count": 0, "unique_report_count": 0, "components": [],
        "timeline": [], "first_report_date": None, "last_report_date": None,
    })
    coverage = ComponentCoverage(total_unique_reports=0, specific_component_unique_reports=0,
                                 unknown_or_other_unique_reports=0, unknown_or_other_source_rows=0)
    result = build_assessment(request(), empty, coverage)
    assert result.reported_component_concerns == []
    assert all(p.basis == "generic" for p in result.inspection_priorities)
    assert any("No historical reports" in line for line in result.evidence_limitations)
    sparse = base.model_copy(update={
        "unique_report_count": 1,
        "components": [c for c in base.components if c.category == "unknown"],
    })
    coverage = ComponentCoverage(total_unique_reports=1, specific_component_unique_reports=0,
                                 unknown_or_other_unique_reports=1, unknown_or_other_source_rows=1)
    result = build_assessment(request(), sparse, coverage)
    assert not result.reported_component_concerns
    assert any("Only one unique historical report" in line for line in result.evidence_limitations)
    assert any("Zero recorded reports" in line for line in result.evidence_limitations)


def test_unknown_and_ambiguous_identity(history: HistoricalIndex) -> None:
    with pytest.raises(PurchaseVehicleNotFoundError):
        PurchaseAssessmentService(history).assess(request(model="missing"))
    mock = Mock(spec=HistoricalIndex)
    mock.discover.return_value = [{"id": "one"}, {"id": "two"}]
    with pytest.raises(PurchaseVehicleAmbiguousError):
        PurchaseAssessmentService(mock).assess(request())
    mock.summary.assert_not_called()


def test_order_count_descending_then_code(history: HistoricalIndex) -> None:
    item = history.discover("mazda", "mazda3", 2020)[0]
    base = HistoricalSummary(**history.summary(item["id"]))
    components = list(reversed(base.components))
    components = [c.model_copy(update={"unique_report_count": 2})
                  if c.category == "engine" else c for c in components]
    base = base.model_copy(update={"components": components})
    coverage = ComponentCoverage(total_unique_reports=2, specific_component_unique_reports=2,
                                 unknown_or_other_unique_reports=2, unknown_or_other_source_rows=4)
    result = build_assessment(request(), base, coverage)
    assert [c.category.value for c in result.reported_component_concerns] == [
        "engine", "electrical",
    ]


def test_no_scores_valuations_or_frozen_prediction_fields(history: HistoricalIndex) -> None:
    result = PurchaseAssessmentService(history).assess(request(
        odometer_km=250000, asking_price_cad="12000.00", maintenance_history="undocumented",
    ))
    payload = result.model_dump(mode="json")
    prohibited = {"risk_score", "reliability_score", "failure_probability", "confidence_score",
                  "market_value", "repair_cost", "prediction", "predicted_classification"}

    def check_keys(value: object) -> None:
        if isinstance(value, dict):
            assert not prohibited.intersection(value)
            for child in value.values():
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)

    check_keys(payload)
    assert "%" not in json.dumps(payload)
    assert "definitely avoid" not in json.dumps(payload).lower()
    assert "No specific defect or repair is inferred" in result.inspection_priorities[0].suggestion


def test_http_contract_unsupported_predictions_do_not_block_assessment(
    history: HistoricalIndex, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_service = Mock(spec=PredictionService)
    model_service.list_cohorts.return_value = CohortPage(items=(), total=0, limit=100, offset=0)

    def factory(**kwargs: object) -> FastAPI:
        app = FastAPI()
        app.state.prediction_service = model_service
        return app

    monkeypatch.setattr(demo, "create_prediction_app", factory)
    client = TestClient(demo.create_app(root=tmp_path, index_path=history.path))
    data = {"make": "MAZDA", "model": "mazda3", "year": 2020, "asking_price_cad": 12000.50}
    response = client.post(ENDPOINT, json=data)
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "howreliable-purchase-assessment-1.0"
    assert payload["purchase_context"]["asking_price_cad"] == "12000.5"
    assert payload["historical_evidence"]["unique_report_count"] == 2
    assert client.post(ENDPOINT, json={**data, "model": "missing"}).status_code == 404
    assert client.post(ENDPOINT, json={**data, "odometer_km": "100000"}).status_code == 422
    assert client.get("/api/demo/v1/vehicles").status_code == 200
    identifier = payload["vehicle"]["id"]
    assert client.get(f"/api/demo/v1/vehicles/{identifier}/prediction").json()[
        "status"] == "unsupported"
    model_service.predict.assert_not_called()
    assert ENDPOINT in client.get("/openapi.json").json()["paths"]


def test_mismatched_evidence_is_rejected(history: HistoricalIndex) -> None:
    result = PurchaseAssessmentService(history).assess(request())
    with pytest.raises(ValueError, match="identity"):
        build_assessment(request(model="other"), result.historical_evidence,
                         result.component_coverage)
    bad_coverage = result.component_coverage.model_copy(update={"total_unique_reports": 3})
    with pytest.raises(ValueError, match="denominator"):
        build_assessment(request(), result.historical_evidence, bad_coverage)


@pytest.mark.parametrize("odometer", [1_000_000, 9_007_199_254_740_991])
def test_very_high_valid_odometer_is_context_only(
    history: HistoricalIndex, odometer: int,
) -> None:
    service = PurchaseAssessmentService(history)
    base = service.assess(request())
    result = service.assess(request(odometer_km=odometer))
    assert result.purchase_context.odometer_km == odometer
    assert result.historical_evidence == base.historical_evidence
    assert result.reported_component_concerns == base.reported_component_concerns
    assert result.inspection_priorities == base.inspection_priorities
    assert "not a validated failure threshold" in result.purchase_considerations[0].explanation


def test_substantial_evidence_and_overlapping_unknown_coverage(tmp_path: Path) -> None:
    rows = []
    for report in range(100):
        # Same report can have both specific and uninformative labels, with repeated rows.
        rows.extend([
            record(source_reference_id=str(report), component="engine"),
            record(source_reference_id=str(report), component="engine"),
            record(source_reference_id=str(report), component="other"),
            record(source_reference_id=str(report), component="unknown"),
        ])
    path = tmp_path / "large-history.sqlite"
    build_index(source_file(tmp_path, rows), path, TIME)
    result = PurchaseAssessmentService(HistoricalIndex(path)).assess(request())
    assert result.historical_evidence.source_row_count == 400
    assert result.historical_evidence.unique_report_count == 100
    assert result.component_coverage.unknown_or_other_unique_reports == 100
    assert result.component_coverage.specific_component_unique_reports == 100
    assert result.component_coverage.unknown_or_other_source_rows == 200
    assert result.reported_component_concerns[0].unique_report_count == 100
    assert result.reported_component_concerns[0].source_row_count == 200
    assert len(result.reported_component_concerns) == 1


@pytest.mark.parametrize("values", [
    {"odometer_km": float("nan")}, {"odometer_km": float("inf")},
    {"asking_price_cad": {}}, {"asking_price_cad": []}, {"year": 2020.0},
])
def test_additional_invalid_numeric_context(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        request(**values)
