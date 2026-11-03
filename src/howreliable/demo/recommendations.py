"""Pure, versioned purchase-readiness policy; no evidence aggregation or text interpretation."""

from typing import Literal

from howreliable.demo.purchase_schemas import (
    PurchaseRecommendation,
    RecommendationInput,
    RecommendationReason,
)

# Order is policy: concerns first, then essential evidence gaps, then conditional readiness.
CONCERNS = (
    (
        "mechanical_problems",
        "yes",
        "mechanical_problem",
        "Mechanical problems are reported; their severity is not established.",
        "Obtain independent findings about the reported mechanical problems.",
    ),
    (
        "warning_lights",
        "yes",
        "warning_indicator",
        "Dashboard warnings are reported; no mechanical diagnosis is inferred.",
        "Have the reported warnings investigated and document the findings.",
    ),
    (
        "drivability_problems",
        "yes",
        "drivability_concern",
        "Drivability problems are reported; their cause and severity are unknown.",
        "Obtain independent assessment of the reported drivability concerns.",
    ),
    (
        "outstanding_maintenance",
        "yes",
        "outstanding_maintenance",
        "Outstanding maintenance is reported, without an estimate of cost or urgency.",
        "Clarify outstanding work and obtain documentation of completion.",
    ),
    (
        "accident_history",
        "yes",
        "reported_accident",
        "An accident history is reported; damage severity and repair quality are not established.",
        "Verify accident and repair records and inspection findings before reconsidering.",
    ),
    (
        "accident_documentation",
        "seller_reported",
        "seller_reported_accident_evidence",
        "Accident-history evidence is described as seller-reported, not independently verified.",
        "Seek documentation supporting the seller's accident-history statements.",
    ),
    (
        "inspection_result",
        "issues_found",
        "inspection_issues",
        "The user reports inspection issues; their resolution has not been verified here.",
        "Clarify inspection findings and obtain evidence that issues were addressed.",
    ),
    (
        "inspection_result",
        "inconclusive",
        "inspection_inconclusive",
        "The entered inspection result is inconclusive.",
        "Obtain a conclusive independent inspection and clarify outstanding findings.",
    ),
    (
        "unresolved_inspection_issues",
        "yes",
        "unresolved_inspection",
        "Unresolved inspection findings are reported, without an inferred danger classification.",
        "Resolve or clarify the inspection findings with an independent inspector.",
    ),
    (
        "maintenance_history",
        "partial",
        "partial_maintenance_records",
        "Maintenance documentation is reported as partial; work is not assumed absent.",
        "Clarify documentation gaps and verify the relevant maintenance history.",
    ),
    (
        "maintenance_history",
        "undocumented",
        "undocumented_maintenance",
        "Maintenance work cannot be checked from the reported documentation status.",
        "Seek service evidence; undocumented work does not mean it was never performed.",
    ),
)

# Optional narrative notes are not required except a nonblank inspection description.
# Its presence supplies context only; its content is never parsed or treated as verification.
ESSENTIAL = (
    ("mechanical_problems", ("unknown",), "Confirm whether mechanical problems are reported."),
    ("warning_lights", ("unknown",), "Confirm whether dashboard warnings are reported."),
    ("drivability_problems", ("unknown",), "Confirm whether drivability problems are reported."),
    ("outstanding_maintenance", ("unknown",), "Clarify outstanding maintenance."),
    ("maintenance_history", ("unknown",), "Obtain maintenance-documentation information."),
    ("accident_history", ("unknown",), "Clarify the reported accident history."),
    ("accident_documentation", ("unknown",), "Obtain supporting accident-history documentation."),
    ("inspection_status", ("unknown", "not_performed"), "Arrange an independent inspection."),
    (
        "inspection_result",
        ("unavailable", "inconclusive"),
        "Obtain conclusive inspection findings.",
    ),
    ("unresolved_inspection_issues", ("unknown",), "Clarify unresolved inspection issues."),
    ("inspection_summary", (None,), "Obtain a nonblank description of the inspection findings."),
)


def recommend(context: RecommendationInput) -> PurchaseRecommendation:
    """Assess readiness to continue considering; all evidence remains unverified."""
    reasons: list[RecommendationReason] = []
    for field, value, rule, explanation, action in CONCERNS:
        if getattr(context, field) == value:
            reasons.append(
                RecommendationReason(
                    rule_id=f"readiness.v1.{rule}",
                    evidence_origin=(
                        "user_entered_inspection"
                        if field.startswith("inspection_")
                        or field == "unresolved_inspection_issues"
                        else "user_supplied_condition"
                    ),
                    evidence_fields=[field],
                    explanation=explanation,
                    next_step=action,
                )
            )
    has_concerns = bool(reasons)
    missing: list[str] = []
    for field, absent, action in ESSENTIAL:
        if getattr(context, field) in absent:
            missing.append(field)
            reasons.append(
                RecommendationReason(
                    rule_id=f"readiness.v1.missing_{field}",
                    evidence_origin="generic_purchase_guidance",
                    evidence_fields=[field],
                    explanation=f"Essential purchase evidence is incomplete: {field}.",
                    next_step=action,
                )
            )
    outcome: Literal["PROCEED_WITH_CAUTION", "INSUFFICIENT_INFORMATION", "WORTH_CONSIDERING"]
    if has_concerns:
        outcome = "PROCEED_WITH_CAUTION"
        explanation = (
            "Reported concerns or evidence limitations require investigation before proceeding. "
            "This is purchase-process guidance, not a finding of mechanical danger."
        )
    elif missing:
        outcome = "INSUFFICIENT_INFORMATION"
        explanation = (
            "Essential condition or inspection evidence is incomplete. There is not enough "
            "information to assess readiness to continue considering this vehicle."
        )
    else:
        outcome = "WORTH_CONSIDERING"
        explanation = (
            "The supplied statements are sufficiently complete with no reported unresolved "
            "concerns. Continuing consideration is conditional on independently verifying the "
            "inspection findings and supporting records; this does not mean buy or good value."
        )
        reasons.extend([
            RecommendationReason(
                rule_id="readiness.v1.favorable_condition_statements",
                evidence_origin="user_supplied_condition",
                evidence_fields=[field for field, _, _ in ESSENTIAL[:7]],
                explanation="No condition concerns are reported and supporting histories are "
                            "described as documented; neither statement is verified here.",
                next_step="Verify the condition statements and supporting history documents.",
            ),
            RecommendationReason(
                rule_id="readiness.v1.favorable_inspection_statement",
                evidence_origin="user_entered_inspection",
                evidence_fields=[field for field, _, _ in ESSENTIAL[7:]],
                explanation="A performed inspection with no issues and no unresolved findings "
                            "is reported with a summary; this is not independent verification.",
                next_step="Verify the inspection's authenticity, scope and current applicability.",
            ),
        ])
        reasons.append(
            RecommendationReason(
                rule_id="readiness.v1.conditional_readiness",
                evidence_origin="generic_purchase_guidance",
                evidence_fields=[field for field, _, _ in ESSENTIAL],
                explanation="Structured answers satisfy the documented readiness requirements, "
                "including reported inspection findings, not verified condition.",
                next_step="Reassess if an answer, inspection finding or supporting record changes.",
            )
        )
    conditions = list(dict.fromkeys(r.next_step for r in reasons))
    conditions.append(
        "Verify the inspection description and relevant records independently; "
        "update the structured answers if verification contradicts them."
    )
    return PurchaseRecommendation(
        outcome=outcome,
        explanation=explanation,
        supporting_reasons=reasons,
        missing_information=missing,
        conditions_that_would_change_recommendation=conditions,
        limitations=[
            "All condition and inspection information is entered by the user and unverified.",
            "A nonblank inspection summary is required context, not proof of inspection quality.",
            "Free-text notes are not interpreted as severity, diagnoses, danger or repair costs.",
            "Historical NHTSA allegations are separate cohort evidence, not individual condition.",
            "Complaint volume, mileage, price, ML and NLP outputs do not control this outcome.",
            "No market comparison is performed; worth considering does not establish good value.",
            "The negative outcome is reserved: current inputs cannot establish a verified blocker.",
        ],
    )
