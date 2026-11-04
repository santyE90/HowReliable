"""Deterministic profile decoration of existing read-only historical complaint summaries."""

import sqlite3
from typing import Literal

from howreliable.demo.index import HistoricalIndex
from howreliable.demo.official_evidence import OfficialEvidence
from howreliable.demo.profile_schemas import (
    ComponentEvidenceAnnotation,
    EvidenceGap,
    InspectionQuestion,
    ProfileApplicability,
    ProfileIdentity,
    ProfileRequest,
    ProfileResolution,
    ProfileSources,
    ProfileStatus,
    SourceCoverage,
    VehicleProblemProfile,
)
from howreliable.demo.schemas import HistoricalSummary, HistoricalVehicle
from howreliable.domain.reliability import Component

LABELS = {
    "engine": "engine",
    "transmission": "transmission",
    "electrical": "electrical system",
    "cooling": "cooling system",
    "suspension": "suspension",
    "brakes": "brakes",
    "steering": "steering",
    "fuel_system": "fuel system",
    "hvac": "heating and air conditioning",
    "exhaust": "exhaust system",
    "body": "body and doors",
    "airbags_restraints": "airbags and restraints",
    "tires_wheels": "tires and wheels",
}
LIMITATIONS = [
    "NHTSA complaint reports originate in US reporting systems and are allegations, "
    "not verified failures.",
    "Report counts lack vehicle population, distance and time-exposed denominators; "
    "they are not failure rates.",
    "Structured component categories overlap. Do not sum category report counts as a total.",
    "Structured labels are mapped broad categories, not validated narrative mentions or diagnoses.",
    "The historical snapshot is selective, not lifetime/continuous coverage, "
    "and may contain later revisions.",
    "An exact cohort match does not establish trim, powertrain, individual VIN "
    "or Canadian-market applicability.",
    "No Transport Canada recall, open-recall, remedy-completion "
    "or individual-vehicle condition check is performed.",
    "Missing records or zero category counts do not establish absence of problems or safety.",
    "Inspection questions are prompts, not findings, repair instructions, costs "
    "or purchase recommendations.",
]
PROVENANCE_KEYS = {
    "schema_version",
    "source_schema",
    "source_filename",
    "source_sha256",
    "index_sha256",
    "cleaning_provenance_sha256",
    "cleaning_version",
    "mapping_version",
    "builder_sha256",
    "validator_sha256",
    "vehicle_identity_sha256",
    "sqlite_version",
    "generation_utc",
    "report_policy",
    "date_policy",
    "source_row_count",
    "unique_report_count",
    "vehicle_count",
    "missing_report_date_rows",
    "missing_report_date_reports",
    "fallback_source_rows",
    "conflicting_date_reports",
    "conflicting_vehicle_reports",
    "limitation",
}


def _history(
    summary: HistoricalSummary, request: ProfileRequest, candidate: HistoricalVehicle
) -> HistoricalSummary:
    if summary.vehicle != candidate or (candidate.make, candidate.model, candidate.year) != (
        request.make,
        request.model,
        request.year,
    ):
        raise ValueError("profile identity does not match historical evidence")
    n, rows = summary.unique_report_count, summary.source_row_count
    components = sorted(summary.components, key=lambda c: (-c.unique_report_count, c.category))
    if (
        rows < n
        or summary.missing_report_date_rows > rows
        or len({c.category for c in components}) != len(components)
        or any(
            c.source_row_count < c.unique_report_count
            or c.unique_report_count > n
            or c.source_row_count > rows
            for c in components
        )
        or sum(b.unique_report_count for b in summary.timeline) != n
        or sum(b.source_row_count for b in summary.timeline) != rows
        or any(b.source_row_count < b.unique_report_count for b in summary.timeline)
        or len({b.month for b in summary.timeline}) != len(summary.timeline)
    ):
        raise ValueError("profile historical count conservation failed")
    for component in components:
        Component(component.category)
    provenance = {k: v for k, v in summary.provenance.items() if k in PROVENANCE_KEYS}
    if isinstance(provenance.get("source_filename"), str):
        provenance["source_filename"] = (
            provenance["source_filename"].replace("\\", "/").split("/")[-1]
        )
    return HistoricalSummary.model_validate(
        {
            **summary.model_dump(),
            "components": components,
            "provenance": provenance,
            "timeline": sorted(
                summary.timeline, key=lambda b: (b.month is not None, b.month or "")
            ),
        }
    )


def build_problem_profile(
    request: ProfileRequest,
    candidates: list[HistoricalVehicle],
    history: HistoricalSummary | None,
    *,
    source_available: bool = True,
) -> VehicleProblemProfile:
    """Pure composition; no narrative, model, pricing, NLP or source-artifact reads."""
    candidates = sorted(candidates, key=lambda c: (c.make, c.model, c.year, c.id))
    status: ProfileStatus
    match: Literal[
        "EXACT_COHORT_MATCH", "NO_MATCHING_REPORTS", "AMBIGUOUS_IDENTITY", "SOURCE_UNAVAILABLE"
    ]
    if not source_available:
        status, match = "SOURCE_UNAVAILABLE", "SOURCE_UNAVAILABLE"
        candidates, history = [], None
    elif not candidates:
        status, match = "NO_MATCHING_REPORTS", "NO_MATCHING_REPORTS"
    elif len(candidates) > 1:
        status, match = "AMBIGUOUS_IDENTITY", "AMBIGUOUS_IDENTITY"
    else:
        status, match = "AVAILABLE", "EXACT_COHORT_MATCH"
    if status == "AVAILABLE":
        if history is None:
            raise ValueError("matched profile requires a historical summary")
        history = _history(history, request, candidates[0])
    elif history is not None:
        raise ValueError("unresolved profile cannot carry guessed historical evidence")
    annotations: list[ComponentEvidenceAnnotation] = []
    questions: list[InspectionQuestion] = []
    gaps = [EvidenceGap(code="configuration_applicability_unresolved", explanation=LIMITATIONS[5])]
    if history is not None:
        for component in history.components:
            category = Component(component.category)
            label = LABELS.get(
                category, "Other components" if category == "other" else "Unknown component"
            )
            question_id = f"profile.v1.component.{category}"
            supported = category in LABELS and component.unique_report_count > 0
            limits = [LIMITATIONS[0], LIMITATIONS[3], LIMITATIONS[5]]
            if component.unique_report_count == 1:
                limits.append("One report cannot establish a recurring complaint pattern.")
            annotations.append(
                ComponentEvidenceAnnotation(
                    category=category,
                    label=label,
                    count_reference=category,
                    question_ids=[question_id] if supported else [],
                    interpretation="Reports associated with this structured component category; "
                    "frequency is not severity or failure probability.",
                    limitations=limits,
                )
            )
            if supported:
                questions.append(
                    InspectionQuestion(
                        question_id=question_id,
                        question_text="What did the independent pre-purchase inspection find about "
                        f"the current condition of the {label}, and what relevant "
                        "service records can be verified for this vehicle?",
                        supporting_component=category,
                        supporting_unique_report_count=component.unique_report_count,
                        evidence_basis="structured_component_reports",
                        rule_id="profile-question.v1.structured_component",
                        limitations=limits,
                    )
                )
        if any(c.category in {"other", "unknown"} for c in history.components):
            gaps.append(
                EvidenceGap(
                    code="broad_component_labels",
                    explanation=(
                        "Unknown/other labels cannot identify a specific part. "
                        "Powertrain descriptions "
                        "may map to other; do not infer no transmission concerns."
                    ),
                )
            )
        if any(b.month is None for b in history.timeline) or history.missing_report_date_rows:
            gaps.append(
                EvidenceGap(
                    code="incomplete_report_dates",
                    explanation=(
                        "Missing/conflicting report dates remain "
                        "in the unknown-month accounting bucket."
                    ),
                )
            )
        if history.unique_report_count == 0:
            gaps.append(EvidenceGap(code="zero_recorded_reports", explanation=LIMITATIONS[7]))
    else:
        gaps.append(
            EvidenceGap(
                code=status.lower(),
                explanation=(
                    "No resolved historical evidence is available; "
                    "null counts are not a healthy zero."
                ),
            )
        )
    for name, question in (
        (
            "independent_inspection",
            "Has an independent inspector assessed the whole vehicle, "
            "including areas with no recorded complaints?",
        ),
        (
            "service_records",
            "Which service records can be verified against this vehicle's "
            "dates and odometer history?",
        ),
    ):
        questions.append(
            InspectionQuestion(
                question_id=f"profile.v1.generic.{name}",
                question_text=question,
                supporting_component=None,
                supporting_unique_report_count=None,
                evidence_basis="generic_inspection_guidance",
                rule_id=f"profile-question.v1.{name}",
                limitations=[LIMITATIONS[8]],
            )
        )
    gaps.extend(
        [
            EvidenceGap(
                code="official_sources_unavailable",
                explanation="Processed recall/TSB serving evidence is unavailable, not zero.",
            ),
            EvidenceGap(
                code="validated_symptoms_unavailable",
                explanation="Human NLP validation remains deferred; "
                "no symptom claims are published.",
            ),
        ]
    )
    unavailable = SourceCoverage(
        availability="SOURCE_UNAVAILABLE",
        reason_code="processed_serving_artifact_unavailable",
        explanation="Processed local serving evidence is unavailable; "
        "no source records were checked.",
        applicability_status="NOT_EVALUATED",
    )
    return VehicleProblemProfile(
        profile_status=status,
        requested_identity=ProfileIdentity(
            make=request.make, model=request.model, year=request.year
        ),
        supplied_configuration=request.configuration,
        identity_resolution=ProfileResolution(status=match, candidates=candidates),
        applicability=ProfileApplicability(
            cohort_match=match, limitations=[LIMITATIONS[5], LIMITATIONS[6]]
        ),
        historical_evidence=history,
        component_evidence=annotations,
        inspection_questions=questions,
        source_coverage=ProfileSources(
            complaints=SourceCoverage(
                availability="AVAILABLE" if source_available else "SOURCE_UNAVAILABLE",
                reason_code="resolved_historical_index" if history is not None else status.lower(),
                explanation="NHTSA ODI US complaint reporting; allegations, not verified failures.",
                applicability_status=match,
                unique_record_count=history.unique_report_count if history is not None else None,
                provenance_reference="historical_evidence.provenance"
                if history is not None
                else None,
                snapshot_date=str(history.provenance.get("generation_utc"))
                if history is not None and history.provenance.get("generation_utc")
                else None,
            ),
            recalls=unavailable,
            manufacturer_communications=unavailable,
            validated_symptoms=SourceCoverage(
                availability="VALIDATED_EVIDENCE_UNAVAILABLE",
                reason_code="nlp_human_validation_deferred",
                explanation="Validated symptom evidence unavailable; "
                "experimental outputs are not public evidence.",
                applicability_status="NOT_VALIDATED",
            ),
        ),
        missing_information=gaps,
        limitations=list(LIMITATIONS),
    )


class ProblemProfileService:
    def __init__(self, index: HistoricalIndex, official: OfficialEvidence | None = None):
        self.index = index
        self.official = official

    def profile(self, request: ProfileRequest) -> VehicleProblemProfile:
        try:
            candidates = [
                HistoricalVehicle(**row)
                for row in self.index.discover(request.make, request.model, request.year)
            ]
            history = (
                HistoricalSummary(**self.index.summary(candidates[0].id))
                if len(candidates) == 1
                else None
            )
            result = build_problem_profile(request, candidates, history)
        except (OSError, sqlite3.Error, ValueError, KeyError):
            return build_problem_profile(request, [], None, source_available=False)
        if result.profile_status != "AVAILABLE" or self.official is None:
            return result
        updates = {}
        for source in ("recalls", "manufacturer_communications"):
            try:
                coverage = self.official.lookup(source, result.requested_identity)
            except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
                coverage = None
            if coverage is not None:
                updates[source] = coverage
        if not updates:
            return result
        gaps = [g for g in result.missing_information if g.code != "official_sources_unavailable"]
        if len(updates) < 2:
            gaps.append(EvidenceGap(code="official_sources_unavailable", explanation=(
                "Some official evidence remains unavailable; see source coverage."
            )))
        return result.model_copy(update={
            "schema_version": "vehicle-problem-profile-1.1",
            "source_coverage": result.source_coverage.model_copy(update=updates),
            "missing_information": gaps,
        })
