"""Deterministic inspection prompts from read-only historical complaint evidence."""

from contextlib import closing

from howreliable.demo.index import HistoricalIndex, connect_readonly
from howreliable.demo.purchase_schemas import (
    AssessmentPolicy,
    ComponentConcern,
    ComponentCoverage,
    IndividualVehicleContext,
    IndividualVehicleDetails,
    InspectionPriority,
    PurchaseAssessment,
    PurchaseAssessmentRequest,
    PurchaseConsideration,
    RecommendationInput,
)
from howreliable.demo.recommendations import recommend
from howreliable.demo.schemas import HistoricalSummary
from howreliable.domain.reliability import Component

MILEAGE_PROMPT_KM = 200_000
LABELS = {
    Component.ENGINE: "Engine",
    Component.TRANSMISSION: "Transmission",
    Component.ELECTRICAL: "Electrical system",
    Component.COOLING: "Cooling system",
    Component.SUSPENSION: "Suspension",
    Component.BRAKES: "Brakes",
    Component.STEERING: "Steering",
    Component.FUEL_SYSTEM: "Fuel system",
    Component.HVAC: "Heating and air conditioning",
    Component.EXHAUST: "Exhaust",
    Component.BODY: "Body",
    Component.AIRBAGS_RESTRAINTS: "Airbags and restraints",
    Component.TIRES_WHEELS: "Tires and wheels",
}
MAINTENANCE_NOTES = {
    "documented": (
        "Maintenance is reported as documented. Review dates, odometer entries and scope, "
        "and verify that the records apply to this vehicle. Documentation supports a more "
        "informed assessment; it does not establish reliability or current condition."
    ),
    "partial": (
        "Maintenance documentation is reported as partial. Identify gaps and request missing "
        "records before purchasing; incomplete evidence limits assessment confidence."
    ),
    "unknown": (
        "Maintenance documentation availability is unknown. Ask whether records exist and "
        "request them before purchasing; current assessment confidence is limited by missing "
        "service evidence, not a mechanically inferred reliability estimate."
    ),
    "undocumented": (
        "Maintenance is reported as undocumented. Request any available documentation before "
        "purchasing. Undocumented work cannot be verified here and does not prove that "
        "maintenance was never performed."
    ),
}
LIMITATIONS = (
    "NHTSA complaints are owner reports, not verified mechanical failures.",
    "Complaint counts are not normalized by active vehicle population or distance driven; "
    "they are not vehicle failure rates or a basis for mechanical reliability rankings.",
    "Records cover a limited historical period and may reflect later revisions; report-date "
    "coverage is not lifetime coverage or evidence of continuous observation.",
    "Component categories can overlap within one report. Do not sum category frequencies "
    "as a unique-report total. Unknown/other labels do not identify a specific defect.",
    "Zero recorded reports for a component do not establish that the component is safe "
    "or problem-free. Structured mappings can omit detail, including powertrain descriptions.",
    "Make/model/year cohorts combine vehicles with different trims, powertrains and usage. "
    "Historical cohort reports do not establish the condition of this individual vehicle.",
    "Odometer, asking price and maintenance history are user-supplied and unverified. "
    "No market comparison, inspection findings or service-record verification is performed.",
    "This result is not an inspection, appraisal, purchase verdict or validated individual-vehicle "
    "risk score. It provides no mechanical-failure probability or frozen-model forecast.",
)


class PurchaseVehicleNotFoundError(LookupError):
    """No exact historical identity; never fabricate a purchase assessment."""


class PurchaseVehicleAmbiguousError(LookupError):
    """Multiple historical identities; require explicit resolution rather than guessing."""


def individual_context(request: PurchaseAssessmentRequest) -> IndividualVehicleContext:
    """Deterministic evidence gaps and questions, with no risk or recommendation inference."""
    fields = IndividualVehicleDetails.model_fields
    supplied = IndividualVehicleDetails.model_validate({
        name: getattr(request, name) for name in fields
    })
    missing = [
        name for name in fields if getattr(supplied, name) in (None, "unknown", "unavailable")
    ]
    questions: list[str] = []
    prompts = (
        ("outstanding_maintenance", "Ask whether maintenance is outstanding and request records."),
        ("mechanical_problems", "Ask about known mechanical problems; verify current condition."),
        ("warning_lights", "Ask whether any dashboard warning lights are present."),
        ("drivability_problems", "Ask about starting, stopping, steering and drivability issues."),
        ("accident_history", "Ask about accident history and request supporting documentation."),
        ("accident_documentation", "Request documents supporting the reported accident history."),
    )
    questions.extend(prompt for name, prompt in prompts if name in missing)
    if supplied.outstanding_maintenance == "yes" and supplied.maintenance_notes is None:
        questions.append("List outstanding maintenance and ask what work remains to be completed.")
    if any(getattr(supplied, name) == "yes" for name in (
        "mechanical_problems", "warning_lights", "drivability_problems"
    )) and supplied.problem_description is None:
        questions.append("Describe the reported problems and request an independent inspection.")
    if supplied.accident_history == "yes" and supplied.accident_description is None:
        questions.append("Request damage/repair details; accident status does not show severity.")
    if supplied.inspection_status != "performed":
        questions.append("Arrange an independent inspection or confirm one was performed.")
    else:
        if supplied.inspection_result in {"unavailable", "inconclusive"}:
            questions.append("Obtain the inspection findings and clarify any inconclusive areas.")
        if supplied.unresolved_inspection_issues == "unknown":
            questions.append("Confirm whether any inspection issues remain unresolved.")
        if supplied.inspection_result == "issues_found" and supplied.inspection_summary is None:
            questions.append("Request a summary of the issues identified during inspection.")
        if supplied.unresolved_inspection_issues == "yes":
            questions.append("Ask an inspector to clarify unresolved findings and next steps.")
    return IndividualVehicleContext(
        supplied_information=supplied, missing_information=missing, follow_up_questions=questions,
        evidence_limitations=[
            "All supplied details are unverified user statements, including inspection summaries.",
            "No problems reported is not independently verified problem-free condition.",
            "Accident status alone does not establish damage severity or repair quality.",
            "Unknown information is not evidence of absence; blank notes mean not supplied.",
            "No documents are uploaded or verified. Do not include personal information in notes.",
            "This context does not change historical complaint counts or produce a purchase "
            "recommendation, valuation or risk estimate.",
        ],
    )


def build_assessment(
    request: PurchaseAssessmentRequest,
    history: HistoricalSummary,
    coverage: ComponentCoverage,
) -> PurchaseAssessment:
    """Pure assessment transformation; no inference, narrative access or persistence."""
    vehicle = history.vehicle
    if (request.make, request.model, request.year) != (vehicle.make, vehicle.model, vehicle.year):
        raise ValueError("assessment identity does not match historical evidence")
    if coverage.total_unique_reports != history.unique_report_count:
        raise ValueError("coverage denominator does not match historical evidence")
    if any(n > history.unique_report_count for n in (
        coverage.specific_component_unique_reports, coverage.unknown_or_other_unique_reports,
        *(c.unique_report_count for c in history.components),
    )):
        raise ValueError("component report count exceeds the report denominator")

    concerns: list[ComponentConcern] = []
    priorities: list[InspectionPriority] = []
    for item in sorted(history.components, key=lambda c: (-c.unique_report_count, c.category)):
        category = Component(item.category)
        if category not in LABELS or item.unique_report_count == 0:
            continue
        label = LABELS[category]
        concerns.append(ComponentConcern(
            category=category, label=label, unique_report_count=item.unique_report_count,
            source_row_count=item.source_row_count,
            total_unique_reports=history.unique_report_count,
            interpretation=(
                f"{label}-related complaints appear in {item.unique_report_count} of the "
                f"{history.unique_report_count} available unique historical reports. This is "
                "reported component evidence, not a failure probability or verified defect."
            ),
        ))
        priorities.append(InspectionPriority(
            basis="complaint_supported", category=category,
            supporting_unique_reports=item.unique_report_count,
            rule_id=f"reported_component.{category.value}.v1",
            suggestion=(f"Include {label.lower()} in an independent pre-purchase inspection; "
                        "ask the inspector to assess current condition and review relevant "
                        "service records. No specific defect or repair is inferred."),
        ))
    priorities.extend([
        InspectionPriority(
            basis="generic", rule_id="independent_inspection.v1",
            suggestion="Arrange an independent pre-purchase inspection of the whole vehicle, "
            "including areas without recorded complaints. Historical reports do not inspect "
            "this car.",
        ),
        InspectionPriority(
            basis="generic", rule_id="verify_service_records.v1",
            suggestion="Request service records and check that dates and odometer entries "
            "are consistent with the vehicle being offered.",
        ),
    ])

    if request.odometer_km is None:
        odometer_rule, odometer_note = "odometer_missing.v1", (
            "Current odometer reading was not supplied. Request and verify the reading in "
            "kilometres; no mileage-based condition inference is available."
        )
    elif request.odometer_km >= MILEAGE_PROMPT_KM:
        odometer_rule, odometer_note = "odometer_context_prompt.v1", (
            f"The supplied odometer reading is {request.odometer_km:,} km. At this mileage, "
            "an independent pre-purchase inspection is particularly important, along with "
            f"condition and service evidence. The {MILEAGE_PROMPT_KM:,} km prompt is an advice "
            "heuristic, not a validated failure threshold or probability."
        )
    else:
        odometer_rule, odometer_note = "odometer_supplied.v1", (
            f"The supplied odometer reading is {request.odometer_km:,} km. Verify it and "
            "review condition and service evidence; being below the context-prompt threshold "
            "does not establish good condition or lower mechanical risk."
        )
    if request.asking_price_cad is None:
        price_rule, price_note = "price_missing.v1", (
            "No asking price was supplied. No market value or price assessment is available."
        )
    else:
        price_rule, price_note = "price_context_only.v1", (
            f"The supplied asking price is CAD {request.asking_price_cad:,.2f}, recorded as "
            "context only. No market comparisons were performed; this is not a fair-price, "
            "overpriced or bargain determination, appraisal, or repair-cost estimate."
        )
    limitations = list(LIMITATIONS)
    if history.unique_report_count == 0:
        limitations.append("No historical reports are available in this evidence summary; "
                           "this does not establish absence of problems.")
    elif history.unique_report_count == 1:
        limitations.append("Only one unique historical report is available; it cannot "
                           "establish a recurring complaint pattern.")
    return PurchaseAssessment(
        vehicle=vehicle, purchase_context=request, historical_evidence=history,
        individual_vehicle_context=individual_context(request),
        recommendation=recommend(RecommendationInput.model_validate({
            name: getattr(request, name) for name in RecommendationInput.model_fields
        })),
        component_coverage=coverage, reported_component_concerns=concerns,
        inspection_priorities=priorities,
        purchase_considerations=[
            PurchaseConsideration(topic="odometer", rule_id=odometer_rule,
                                  explanation=odometer_note),
            PurchaseConsideration(topic="maintenance",
                                  rule_id=f"maintenance_{request.maintenance_history}.v1",
                                  explanation=MAINTENANCE_NOTES[request.maintenance_history]),
            PurchaseConsideration(topic="price", rule_id=price_rule, explanation=price_note),
        ],
        evidence_limitations=limitations,
        policy=AssessmentPolicy(
            mileage_prompt_threshold_km=MILEAGE_PROMPT_KM,
            mileage_policy="Context prompt only, not an empirical failure threshold; "
            "no probabilistic or numeric risk score is computed.",
            ordering="Specific components by unique-report count descending, then category "
            "code ascending; generic inspection advice follows. Frequency is not severity.",
        ),
    )


class PurchaseAssessmentService:
    """Reuse exact historical discovery/summary, plus a read-only report-set union query."""

    def __init__(self, history: HistoricalIndex):
        self.history = history

    def assess(self, request: PurchaseAssessmentRequest) -> PurchaseAssessment:
        candidates = self.history.discover(request.make, request.model, request.year)
        if not candidates:
            raise PurchaseVehicleNotFoundError("no historical vehicle match")
        if len(candidates) != 1:
            raise PurchaseVehicleAmbiguousError("ambiguous historical vehicle match")
        history = HistoricalSummary(**self.history.summary(candidates[0]["id"]))
        # Aggregate set unions because other/unknown can overlap with each other and with
        # specific component reports. No narratives, new tables or index writes are involved.
        with closing(connect_readonly(self.history.path)) as db:
            specific, unknown, unknown_rows = db.execute(
                "SELECT count(DISTINCT CASE WHEN component NOT IN ('other','unknown') "
                "THEN report END),count(DISTINCT CASE WHEN component IN ('other','unknown') "
                "THEN report END),coalesce(sum(component IN ('other','unknown')),0) "
                "FROM rows WHERE vehicle=?", (history.vehicle.id,),
            ).fetchone()
        return build_assessment(request, history, ComponentCoverage(
            total_unique_reports=history.unique_report_count,
            specific_component_unique_reports=specific,
            unknown_or_other_unique_reports=unknown,
            unknown_or_other_source_rows=unknown_rows,
        ))
