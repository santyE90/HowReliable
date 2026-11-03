"""Structured complaint profile contracts, separate from models and purchase decisions."""

import unicodedata
from typing import Literal

from pydantic import Field, field_validator

from howreliable.api.schemas import APIModel
from howreliable.demo.schemas import HistoricalSummary, HistoricalVehicle
from howreliable.domain.reliability import Component, VehicleAssociation

ProfileStatus = Literal[
    "AVAILABLE", "NO_MATCHING_REPORTS", "AMBIGUOUS_IDENTITY", "SOURCE_UNAVAILABLE"
]


def normalized_text(value: str) -> str:
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("control characters are not allowed")
    return VehicleAssociation.normalize_required_text(value)


class ProfileConfiguration(APIModel):
    trim: str | None = Field(default=None, max_length=100)
    powertrain: str | None = Field(default=None, max_length=100)
    body_style: str | None = Field(default=None, max_length=100)
    generation: str | None = Field(default=None, max_length=100)
    transmission: Literal["automatic", "manual", "cvt", "dct", "other", "unknown"] = "unknown"
    drivetrain: Literal["fwd", "rwd", "awd", "four_wd", "other", "unknown"] = "unknown"
    market_country: Literal["CA", "US", "other", "unknown"] = "unknown"

    @field_validator("trim", "powertrain", "body_style", "generation")
    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        if value is not None and any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("control characters are not allowed")
        return normalized_text(value) if value is not None and value.strip() else None


class ProfileIdentity(APIModel):
    make: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1886, le=2100)

    @field_validator("make", "model")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalized_text(value)


class ProfileRequest(ProfileIdentity):
    schema_version: Literal["vehicle-problem-profile-1.0"] = "vehicle-problem-profile-1.0"
    configuration: ProfileConfiguration | None = None


class ProfileResolution(APIModel):
    status: Literal[
        "EXACT_COHORT_MATCH", "NO_MATCHING_REPORTS", "AMBIGUOUS_IDENTITY", "SOURCE_UNAVAILABLE"
    ]
    candidates: list[HistoricalVehicle]


class ProfileApplicability(APIModel):
    cohort_match: str
    configuration: Literal["CONFIGURATION_APPLICABILITY_UNRESOLVED"] = (
        "CONFIGURATION_APPLICABILITY_UNRESOLVED"
    )
    individual_vehicle: Literal["INDIVIDUAL_VEHICLE_NOT_VERIFIED"] = (
        "INDIVIDUAL_VEHICLE_NOT_VERIFIED"
    )
    market: Literal["US_SOURCE_MARKET_APPLICABILITY_UNRESOLVED"] = (
        "US_SOURCE_MARKET_APPLICABILITY_UNRESOLVED"
    )
    limitations: list[str]


class ComponentEvidenceAnnotation(APIModel):
    category: Component
    label: str
    count_reference: Component
    denominator_reference: Literal["historical_evidence.unique_report_count"] = (
        "historical_evidence.unique_report_count"
    )
    evidence_basis: Literal["documented_structured_component_mapping"] = (
        "documented_structured_component_mapping"
    )
    rule_id: Literal["profile-evidence.v1.structured_component"] = (
        "profile-evidence.v1.structured_component"
    )
    question_ids: list[str]
    interpretation: str
    limitations: list[str]


class InspectionQuestion(APIModel):
    question_id: str
    question_text: str
    supporting_component: Component | None
    supporting_unique_report_count: int | None = Field(ge=1)
    evidence_basis: Literal["structured_component_reports", "generic_inspection_guidance"]
    rule_id: str
    limitations: list[str]


class SourceCoverage(APIModel):
    availability: Literal["AVAILABLE", "SOURCE_UNAVAILABLE", "VALIDATED_EVIDENCE_UNAVAILABLE"]
    reason_code: str
    explanation: str
    applicability_status: str
    snapshot_date: str | None = None
    provenance_reference: str | None = None
    unique_record_count: int | None = Field(default=None, ge=0)
    records: None = None


class ProfileSources(APIModel):
    complaints: SourceCoverage
    recalls: SourceCoverage
    manufacturer_communications: SourceCoverage
    validated_symptoms: SourceCoverage


class EvidenceGap(APIModel):
    code: str
    explanation: str


class VehicleProblemProfile(APIModel):
    schema_version: Literal["vehicle-problem-profile-1.0"] = "vehicle-problem-profile-1.0"
    policy_version: Literal["howreliable-problem-evidence-policy-1.0"] = (
        "howreliable-problem-evidence-policy-1.0"
    )
    profile_status: ProfileStatus
    requested_identity: ProfileIdentity
    supplied_configuration: ProfileConfiguration | None
    identity_resolution: ProfileResolution
    applicability: ProfileApplicability
    historical_evidence: HistoricalSummary | None
    component_evidence: list[ComponentEvidenceAnnotation]
    inspection_questions: list[InspectionQuestion]
    source_coverage: ProfileSources
    missing_information: list[EvidenceGap]
    limitations: list[str]
