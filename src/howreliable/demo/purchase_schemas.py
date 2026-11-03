"""Purchase-context contracts independent of the frozen prediction schema."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from howreliable.api.schemas import APIModel
from howreliable.demo.schemas import HistoricalSummary, HistoricalVehicle
from howreliable.domain.reliability import Component, VehicleAssociation
from howreliable.domain.vehicle import MAX_MODEL_YEAR, MIN_MODEL_YEAR

MaintenanceHistory = Literal["documented", "partial", "unknown", "undocumented"]
ReportedState = Literal["yes", "no", "unknown"]


class IndividualVehicleDetails(APIModel):
    """Unverified user statements; omission never asserts absence of a problem."""

    outstanding_maintenance: ReportedState = "unknown"
    major_repairs: str | None = Field(default=None, max_length=500)
    maintenance_notes: str | None = Field(default=None, max_length=500)
    mechanical_problems: ReportedState = "unknown"
    warning_lights: ReportedState = "unknown"
    drivability_problems: ReportedState = "unknown"
    problem_description: str | None = Field(default=None, max_length=500)
    accident_history: ReportedState = "unknown"
    accident_documentation: Literal["documented", "seller_reported", "unknown"] = "unknown"
    accident_description: str | None = Field(default=None, max_length=500)
    inspection_status: Literal["not_performed", "performed", "unknown"] = "unknown"
    inspection_result: Literal[
        "no_issues_reported", "issues_found", "inconclusive", "unavailable"
    ] = "unavailable"
    unresolved_inspection_issues: ReportedState = "unknown"
    inspection_summary: str | None = Field(default=None, max_length=500)

    @field_validator(
        "major_repairs", "maintenance_notes", "problem_description", "accident_description",
        "inspection_summary",
    )
    @classmethod
    def blank_text_is_missing(cls, value: str | None) -> str | None:
        return value if value is not None and value.strip() else None

    @model_validator(mode="after")
    def consistent_inspection(self) -> "IndividualVehicleDetails":
        if self.inspection_status != "performed" and (
            self.inspection_result != "unavailable"
            or self.unresolved_inspection_issues != "unknown"
            or self.inspection_summary is not None
        ):
            raise ValueError(
                "Inspection results and findings require inspection_status=performed"
            )
        if (self.inspection_result == "no_issues_reported"
                and self.unresolved_inspection_issues == "yes"):
            raise ValueError("No issues reported conflicts with unresolved inspection issues=yes")
        return self


class PurchaseAssessmentRequest(IndividualVehicleDetails):
    make: str
    model: str
    year: int = Field(ge=MIN_MODEL_YEAR, le=MAX_MODEL_YEAR)
    odometer_km: int | None = Field(default=None, ge=0)
    asking_price_cad: Decimal | None = Field(
        default=None, ge=0, decimal_places=2, allow_inf_nan=False,
    )
    maintenance_history: MaintenanceHistory = "unknown"

    @field_validator("make", "model", mode="before")
    @classmethod
    def normalize_identity(cls, value: object) -> str:
        return VehicleAssociation.normalize_required_text(value)

    @field_validator("asking_price_cad", mode="before")
    @classmethod
    def parse_price(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
            raise ValueError("asking price must be a finite CAD amount")
        try:
            return Decimal(str(value))
        except ArithmeticError as error:
            raise ValueError("asking price must be a finite CAD amount") from error


class ComponentConcern(APIModel):
    category: Component
    label: str
    unique_report_count: int = Field(ge=1)
    source_row_count: int = Field(ge=1)
    total_unique_reports: int = Field(ge=0)
    interpretation: str


class InspectionPriority(APIModel):
    basis: Literal["complaint_supported", "generic"]
    category: Component | None = None
    supporting_unique_reports: int | None = Field(default=None, ge=1)
    rule_id: str
    suggestion: str


class ComponentCoverage(APIModel):
    total_unique_reports: int = Field(ge=0)
    specific_component_unique_reports: int = Field(ge=0)
    unknown_or_other_unique_reports: int = Field(ge=0)
    unknown_or_other_source_rows: int = Field(ge=0)
    interpretation: str = (
        "Counts are report-set unions, not sums of component counts. A report may have both "
        "specific and unknown/other labels, so these coverage groups can overlap."
    )


class PurchaseConsideration(APIModel):
    topic: Literal["odometer", "maintenance", "price"]
    rule_id: str
    explanation: str


class AssessmentPolicy(APIModel):
    mileage_prompt_threshold_km: int
    mileage_policy: str
    ordering: str


class IndividualVehicleContext(APIModel):
    schema_version: Literal["howreliable-individual-vehicle-context-1.0"] = (
        "howreliable-individual-vehicle-context-1.0"
    )
    supplied_information: IndividualVehicleDetails
    missing_information: list[str]
    follow_up_questions: list[str]
    evidence_limitations: list[str]


class RecommendationInput(IndividualVehicleDetails):
    """Purchase-specific statements only; no history, price, mileage, ML or NLP inputs."""

    maintenance_history: MaintenanceHistory = "unknown"


class RecommendationReason(APIModel):
    rule_id: str
    evidence_origin: Literal[
        "user_supplied_condition", "user_entered_inspection", "generic_purchase_guidance"
    ]
    evidence_fields: list[str]
    explanation: str
    next_step: str


class PurchaseRecommendation(APIModel):
    schema_version: Literal["howreliable-purchase-recommendation-1.0"] = (
        "howreliable-purchase-recommendation-1.0"
    )
    policy_version: Literal["howreliable-purchase-readiness-policy-1.0"] = (
        "howreliable-purchase-readiness-policy-1.0"
    )
    outcome: Literal[
        "INSUFFICIENT_INFORMATION", "PROCEED_WITH_CAUTION", "WORTH_CONSIDERING",
        "NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS",
    ]
    explanation: str
    supporting_reasons: list[RecommendationReason]
    missing_information: list[str]
    conditions_that_would_change_recommendation: list[str]
    limitations: list[str]
    reserved_outcomes: tuple[Literal["NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS"], ...] = (
        "NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS",
    )


class PurchaseAssessment(APIModel):
    schema_version: Literal["howreliable-purchase-assessment-1.0"] = (
        "howreliable-purchase-assessment-1.0"
    )
    methodology_version: Literal["howreliable-purchase-rules-1.0"] = (
        "howreliable-purchase-rules-1.0"
    )
    assessment_type: Literal["historical_evidence_and_inspection_prompts"] = (
        "historical_evidence_and_inspection_prompts"
    )
    vehicle: HistoricalVehicle
    purchase_context: PurchaseAssessmentRequest
    individual_vehicle_context: IndividualVehicleContext
    recommendation: PurchaseRecommendation
    historical_evidence: HistoricalSummary
    component_coverage: ComponentCoverage
    reported_component_concerns: list[ComponentConcern]
    inspection_priorities: list[InspectionPriority]
    purchase_considerations: list[PurchaseConsideration]
    evidence_limitations: list[str]
    policy: AssessmentPolicy
