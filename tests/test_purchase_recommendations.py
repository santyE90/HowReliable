"""Synthetic readiness scenarios; no corpus, model predictions or NLP materials."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from howreliable.demo.app import create_app
from howreliable.demo.index import HistoricalIndex, build_index
from howreliable.demo.purchase import PurchaseAssessmentService
from howreliable.demo.purchase_schemas import PurchaseAssessmentRequest, RecommendationInput
from howreliable.demo.recommendations import recommend
from test_demo_history import TIME, record, source_file


def favorable(**changes: object) -> RecommendationInput:
    return RecommendationInput.model_validate(
        {
            "outstanding_maintenance": "no",
            "mechanical_problems": "no",
            "warning_lights": "no",
            "drivability_problems": "no",
            "maintenance_history": "documented",
            "accident_history": "no",
            "accident_documentation": "documented",
            "inspection_status": "performed",
            "inspection_result": "no_issues_reported",
            "unresolved_inspection_issues": "no",
            "inspection_summary": "User reports an inspection and no outstanding findings.",
            **changes,
        }
    )


def test_unknown_and_no_inspection_do_not_establish_readiness() -> None:
    for context in [RecommendationInput(), RecommendationInput(inspection_status="not_performed")]:
        result = recommend(context)
        assert result.outcome == "INSUFFICIENT_INFORMATION"
        assert "inspection_status" in result.missing_information
        assert "inspection_summary" in result.missing_information
        assert all(
            r.evidence_origin == "generic_purchase_guidance" for r in result.supporting_reasons
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("mechanical_problems", "yes"),
        ("warning_lights", "yes"),
        ("drivability_problems", "yes"),
        ("outstanding_maintenance", "yes"),
        ("accident_history", "yes"),
        ("accident_documentation", "seller_reported"),
        ("inspection_result", "issues_found"),
        ("inspection_result", "inconclusive"),
        ("maintenance_history", "partial"),
        ("maintenance_history", "undocumented"),
    ],
)
def test_explicit_concerns_and_documentation_limits(field: str, value: str) -> None:
    result = recommend(favorable(**{field: value}))
    assert result.outcome == "PROCEED_WITH_CAUTION"
    assert field in result.supporting_reasons[0].evidence_fields
    assert result.conditions_that_would_change_recommendation


def test_unresolved_inspection_and_concern_precedence_over_gaps() -> None:
    result = recommend(
        RecommendationInput(
            mechanical_problems="yes",
            inspection_status="performed",
            inspection_result="issues_found",
            unresolved_inspection_issues="yes",
        )
    )
    assert result.outcome == "PROCEED_WITH_CAUTION"
    assert result.missing_information
    assert any(r.rule_id == "readiness.v1.unresolved_inspection" for r in result.supporting_reasons)
    assert any(r.evidence_origin == "user_entered_inspection" for r in result.supporting_reasons)


@pytest.mark.parametrize(
    "changes",
    [
        {"mechanical_problems": "unknown"},
        {"warning_lights": "unknown"},
        {"drivability_problems": "unknown"},
        {"outstanding_maintenance": "unknown"},
        {"maintenance_history": "unknown"},
        {"accident_history": "unknown"},
        {"accident_documentation": "unknown"},
        {"inspection_result": "unavailable"},
        {"unresolved_inspection_issues": "unknown"},
        {"inspection_summary": None},
        {"inspection_summary": "  "},
        {
            "inspection_status": "not_performed",
            "inspection_result": "unavailable",
            "unresolved_inspection_issues": "unknown",
            "inspection_summary": None,
        },
    ],
)
def test_each_essential_gap_blocks_favorable_outcome(changes: dict[str, object]) -> None:
    assert recommend(favorable(**changes)).outcome == "INSUFFICIENT_INFORMATION"


def test_favorable_is_conditional_and_notes_never_diagnose() -> None:
    result = recommend(favorable())
    assert result.outcome == "WORTH_CONSIDERING"
    assert not result.missing_information
    assert "independently verifying" in result.explanation
    assert [r.evidence_origin for r in result.supporting_reasons] == [
        "user_supplied_condition", "user_entered_inspection", "generic_purchase_guidance",
    ]
    for note in [
        "vehicle unsafe",
        "perfectly reliable",
        "repairs cost 99999",
        "Inspection described.",
    ]:
        changed = recommend(
            favorable(
                inspection_summary=note,
                problem_description=note,
                accident_description=note,
                maintenance_notes=note,
            )
        )
        assert changed == result
    assert result.reserved_outcomes == ("NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS",)


def test_conflicting_statements_rejected_before_policy() -> None:
    with pytest.raises(ValidationError):
        favorable(unresolved_inspection_issues="yes")
    with pytest.raises(ValidationError):
        favorable(inspection_status="not_performed")


def test_generic_issue_flags_cannot_activate_reserved_negative_outcome() -> None:
    context = favorable(
        mechanical_problems="yes", warning_lights="yes", drivability_problems="yes",
        outstanding_maintenance="yes", accident_history="yes", inspection_result="issues_found",
        unresolved_inspection_issues="yes", maintenance_history="undocumented",
        problem_description="Unverified severe problem description.",
    )
    result = recommend(context)
    assert result.outcome == "PROCEED_WITH_CAUTION"
    assert "NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS" in result.reserved_outcomes


def test_reason_order_and_serialization_are_deterministic() -> None:
    context = favorable(
        mechanical_problems="yes",
        warning_lights="yes",
        accident_history="yes",
        maintenance_history="partial",
    )
    result = recommend(context)
    assert [r.rule_id for r in result.supporting_reasons] == [
        "readiness.v1.mechanical_problem",
        "readiness.v1.warning_indicator",
        "readiness.v1.reported_accident",
        "readiness.v1.partial_maintenance_records",
    ]
    assert result.model_dump_json() == recommend(context).model_dump_json()


@pytest.mark.parametrize(
    "field",
    [
        "historical_complaints",
        "odometer_km",
        "asking_price_cad",
        "prediction",
        "nlp_summary",
    ],
)
def test_non_policy_inputs_are_not_accepted(field: str) -> None:
    with pytest.raises(ValidationError):
        RecommendationInput.model_validate({field: 1})


def test_counts_mileage_price_and_model_availability_do_not_control_outcomes(
    tmp_path: Path,
) -> None:
    rows = [
        record(event_id=f"event_{i}", source_record_id=str(i), source_reference_id=str(i))
        for i in range(100)
    ]
    rows.append(
        record(
            event_id="sparse",
            source_record_id="sparse",
            source_reference_id="sparse",
            normalized_model="sparse",
        )
    )
    index_path = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, rows), index_path, TIME)
    index = HistoricalIndex(index_path)
    service = PurchaseAssessmentService(index)
    outcomes = []
    for model in ["mazda3", "sparse"]:
        result = service.assess(
            PurchaseAssessmentRequest.model_validate(
                {
                    **favorable().model_dump(),
                    "make": "mazda",
                    "model": model,
                    "year": 2020,
                    "odometer_km": 1_000_000,
                    "asking_price_cad": "1.00",
                }
            )
        )
        outcomes.append(result.recommendation)
        concern = service.assess(
            PurchaseAssessmentRequest.model_validate(
                {
                    **favorable(mechanical_problems="yes").model_dump(),
                    "make": "mazda",
                    "model": model,
                    "year": 2020,
                }
            )
        )
        assert concern.recommendation.outcome == "PROCEED_WITH_CAUTION"
        assert concern.historical_evidence == result.historical_evidence
    assert outcomes[0] == outcomes[1]
    assert outcomes[0].outcome == "WORTH_CONSIDERING"
    client = TestClient(create_app(root=tmp_path, index_path=index_path))
    legacy = client.post(
        "/api/demo/v1/purchase-assessments",
        json={
            "make": "mazda",
            "model": "mazda3",
            "year": 2020,
        },
    )
    assert legacy.status_code == 200
    assert legacy.json()["recommendation"]["outcome"] == "INSUFFICIENT_INFORMATION"
    assert legacy.json()["historical_evidence"]["unique_report_count"] == 100
    assert client.get("/api/v1/model").status_code == 503
