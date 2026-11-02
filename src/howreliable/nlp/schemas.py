"""Versioned offline NLP schemas; no changes to frozen model or API schemas."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION: Final = "howreliable-owner-report-extraction-1.3"
TAXONOMY_VERSION: Final = "howreliable-owner-report-taxonomy-1.0"
GUIDE_VERSION: Final = "howreliable-owner-report-annotation-1.0"
Status = Literal[
    "processed",
    "missing_text",
    "empty_text",
    "unsupported_text",
    "unalignable_text",
    "excluded_missing_report_date",
    "excluded_after_cutoff",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


ComponentCode = Literal[
    "engine",
    "transmission",
    "electrical",
    "cooling",
    "suspension",
    "brakes",
    "steering",
    "fuel_system",
    "hvac",
    "exhaust",
    "body",
    "airbags_restraints",
    "tires_wheels",
    "component_ambiguous",
    "component_unmapped",
]


class ComponentMention(StrictModel):
    mention_id: str = Field(min_length=1)
    kind: Literal["component"] = "component"
    code: ComponentCode
    assertion: Literal["affirmed", "negated", "uncertain", "unresolved"] = "unresolved"
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    evidence_text: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    assertion_cue_spans: tuple[EvidenceSpan, ...] = ()
    candidate_codes: tuple[ComponentCode, ...] = ()
    ambiguity_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span(self) -> ComponentMention:
        if self.end <= self.start or self.end - self.start != len(self.evidence_text):
            raise ValueError("component span length mismatch")
        return self


class EvidenceSpan(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    evidence_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span(self) -> EvidenceSpan:
        if self.end - self.start != len(self.evidence_text):
            raise ValueError("evidence span length mismatch")
        return self


SymptomCode = Literal[
    "stall_shutdown",
    "no_start",
    "hesitation_power_loss",
    "unintended_acceleration",
    "noise",
    "vibration",
    "leak",
    "odor",
    "smoke",
    "overheating",
    "warning_indicator",
    "braking_difficulty",
    "steering_difficulty",
    "electrical_interruption",
    "shift_engagement",
    "intermittent_operation",
    "operation_loss",
    "symptom_unmapped",
    "symptom_ambiguous",
]


class SymptomMention(EvidenceSpan):
    mention_id: str = Field(min_length=1)
    kind: Literal["symptom"] = "symptom"
    code: SymptomCode
    assertion: Literal["affirmed", "negated", "uncertain", "unresolved"] = "unresolved"
    rule_id: str = Field(min_length=1)
    assertion_cue_spans: tuple[EvidenceSpan, ...] = ()
    candidate_codes: tuple[SymptomCode, ...] = ()
    ambiguity_reason: str = Field(min_length=1)


class Association(EvidenceSpan):
    component_mention_id: str
    symptom_mention_id: str
    relation: Literal["reported_with"] = "reported_with"
    rule_id: str = Field(min_length=1)


class ProcessingConfig(StrictModel):
    mode: Literal["full_corpus", "as_of"] = "full_corpus"
    cutoff: date | None = None

    @model_validator(mode="after")
    def validate_cutoff(self) -> ProcessingConfig:
        if (self.mode == "as_of") != (self.cutoff is not None):
            raise ValueError("as_of requires a cutoff; full_corpus forbids a cutoff")
        return self


class ExtractionRow(StrictModel):
    schema_version: Literal[
        "howreliable-owner-report-extraction-1.0",
        "howreliable-owner-report-extraction-1.1",
        "howreliable-owner-report-extraction-1.2",
        "howreliable-owner-report-extraction-1.3",
    ] = SCHEMA_VERSION
    taxonomy_version: Literal["howreliable-owner-report-taxonomy-1.0"] = TAXONOMY_VERSION
    event_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_reference_id: str | None
    broad_vehicle_id: str = Field(min_length=1)
    known_configuration_id: str | None
    normalized_make: str
    normalized_model: str
    model_year: int
    report_group_id: str
    report_group_fallback: bool
    evaluation_group_id: str | None = None
    report_group_conflict: bool | None = None
    report_date_conflict: bool | None = None
    eligible: bool | None = None
    narrative_sha256: str | None
    report_date: date | None
    occurrence_date: date | None
    mode: Literal["full_corpus", "as_of"]
    cutoff: date | None
    processing_status: Status
    quality_flags: tuple[str, ...]
    structured_component: str
    source_component: str | None
    mentions: tuple[ComponentMention | SymptomMention, ...] = ()
    component_mentions: tuple[ComponentMention, ...] = ()
    symptom_mentions: tuple[SymptomMention, ...] = ()
    associations: tuple[Association, ...] = ()

    @model_validator(mode="after")
    def validate_temporal_configuration(self) -> ExtractionRow:
        ProcessingConfig(mode=self.mode, cutoff=self.cutoff)
        if self.schema_version.endswith("1.3"):
            if (
                not self.evaluation_group_id
                or self.report_group_conflict is None
                or (self.report_date_conflict is None or self.eligible is None)
            ):
                raise ValueError("schema 1.3 requires finalized membership fields")
            expected_eligible = self.mode == "full_corpus" or (
                self.report_date is not None
                and self.cutoff is not None
                and self.report_date <= self.cutoff
            )
            if self.eligible != expected_eligible:
                raise ValueError("eligibility must agree with report availability")
        all_mentions: list[ComponentMention | SymptomMention] = [
            *self.component_mentions,
            *self.symptom_mentions,
        ]
        combined = tuple(
            sorted(
                all_mentions,
                key=lambda m: (m.start, m.end, m.kind, m.code),
            )
        )
        if self.mentions != combined:
            raise ValueError("combined mentions must match the sorted component/symptom arrays")
        if self.schema_version.endswith("1.1") and (self.symptom_mentions or self.associations):
            raise ValueError("schema 1.1 is component-only")
        if self.schema_version.endswith("1.0") and (self.mentions or self.associations):
            raise ValueError("schema 1.0 has empty extraction arrays")
        keys = [(m.start, m.end, m.kind, m.code) for m in self.mentions]
        if keys != sorted(set(keys)) or len({m.mention_id for m in self.mentions}) != len(keys):
            raise ValueError("mentions must have unique identities and deterministic ordering")
        if self.processing_status != "processed" and self.mentions:
            raise ValueError("excluded or unprocessable rows cannot contain mentions")
        components = {m.mention_id: m for m in self.component_mentions}
        symptoms = {m.mention_id: m for m in self.symptom_mentions}
        for association in self.associations:
            c = components.get(association.component_mention_id)
            s = symptoms.get(association.symptom_mention_id)
            if c is None or s is None or c.assertion == "unresolved" or s.assertion == "unresolved":
                raise ValueError("association must reference resolved component/symptom mentions")
            if association.start > min(c.start, s.start) or association.end < max(c.end, s.end):
                raise ValueError("association evidence must cover both endpoints")
        return self


class RunProvenance(StrictModel):
    schema_version: Literal[
        "howreliable-owner-report-extraction-1.0",
        "howreliable-owner-report-extraction-1.1",
        "howreliable-owner-report-extraction-1.2",
        "howreliable-owner-report-extraction-1.3",
    ] = SCHEMA_VERSION
    taxonomy_version: str = TAXONOMY_VERSION
    annotation_guide_version: str = GUIDE_VERSION
    milestone: Literal["B", "C", "D", "E"] = "E"
    extraction_implemented: bool = True
    symptom_extraction_implemented: bool = False
    component_lexicon_version: str | None = None
    component_lexicon_sha256: str | None = None
    component_matcher_version: str | None = None
    symptom_lexicon_version: str | None = None
    symptom_lexicon_sha256: str | None = None
    assertion_rules_version: str | None = None
    association_rules_version: str | None = None
    grouping_version: str | None = None
    membership_schema_version: str | None = None
    membership_filename: str | None = None
    membership_sha256: str | None = None
    membership_counts: dict[str, int] | None = None
    complete: Literal[True] = True
    generation_utc: datetime
    input_filename: str
    input_sha256: str
    input_provenance_sha256: str
    source_cleaning_provenance: dict[str, object]
    input_record_count: int = Field(ge=0)
    output_filename: str
    output_sha256: str
    output_size_bytes: int = Field(ge=0)
    output_record_count: int = Field(ge=0)
    status_counts: dict[str, int]
    unique_report_count: int
    conflicting_report_group_count: int
    unique_nonempty_narrative_count: int
    report_group_fallback_count: int
    configuration: ProcessingConfig
    configuration_sha256: str
    code_sha256: str
    code_revision: str | None
    dirty_worktree: bool | None
    python_version: str
    dependency_versions: dict[str, str]
    policies: dict[str, str]

    @field_validator("generation_utc")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("generation_utc must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def validate_accounting(self) -> RunProvenance:
        expected = {"B": "1.0", "C": "1.1", "D": "1.2", "E": "1.3"}[self.milestone]
        if not self.schema_version.endswith(expected):
            raise ValueError("milestone/schema version mismatch")
        if self.extraction_implemented != (self.milestone != "B") or (
            self.symptom_extraction_implemented != (self.milestone in {"D", "E"})
        ):
            raise ValueError("milestone capability flags mismatch")
        if self.milestone != "B" and not all(
            (
                self.component_lexicon_version,
                self.component_lexicon_sha256,
                self.component_matcher_version,
            )
        ):
            raise ValueError("component rule identities required")
        if self.milestone in {"D", "E"} and not all(
            (
                self.symptom_lexicon_version,
                self.symptom_lexicon_sha256,
                self.assertion_rules_version,
                self.association_rules_version,
            )
        ):
            raise ValueError("symptom/context rule identities required")
        if self.milestone == "E" and (
            not all(
                (
                    self.grouping_version,
                    self.membership_schema_version,
                    self.membership_filename,
                    self.membership_sha256,
                )
            )
            or self.membership_counts is None
        ):
            raise ValueError("E requires a completed membership index identity and counts")
        if (
            self.input_record_count != self.output_record_count
            or sum(self.status_counts.values()) != self.output_record_count
            or any(n < 0 for n in self.status_counts.values())
        ):
            raise ValueError("provenance record accounting mismatch")
        return self
