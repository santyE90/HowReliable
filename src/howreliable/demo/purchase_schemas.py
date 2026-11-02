"""Purchase-context contracts independent of the frozen prediction schema."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from howreliable.api.schemas import APIModel
from howreliable.demo.schemas import HistoricalSummary, HistoricalVehicle
from howreliable.domain.reliability import Component, VehicleAssociation
from howreliable.domain.vehicle import MAX_MODEL_YEAR, MIN_MODEL_YEAR

MaintenanceHistory = Literal["documented", "partial", "unknown", "undocumented"]


class PurchaseAssessmentRequest(APIModel):
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
    historical_evidence: HistoricalSummary
    component_coverage: ComponentCoverage
    reported_component_concerns: list[ComponentConcern]
    inspection_priorities: list[InspectionPriority]
    purchase_considerations: list[PurchaseConsideration]
    evidence_limitations: list[str]
    policy: AssessmentPolicy
