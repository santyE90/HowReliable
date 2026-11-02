"""Synthetic G2C.1 context, explicit symptom and referent assertion regressions."""

import pytest

from howreliable.nlp.context import extract_report


@pytest.mark.parametrize(
    "text",
    [
        "The garage door was shut.",
        "An attached garage with the door shut.",
        "The door of the garage closed.",
        "A house window broke.",
        "The garage door latch failed.",
    ],
)
def test_building_referents_not_vehicle_body(text: str) -> None:
    assert not extract_report(text)[0]


@pytest.mark.parametrize(
    "text",
    [
        "The vehicle door was shut in the garage.",
        "Parked in a garage. My car door broke.",
        "Inside the garage with the vehicle door open.",
        "The driver door failed.",
        "The door to my car broke near the garage.",
        "Garage door shut; vehicle window broke.",
    ],
)
def test_vehicle_body_survives_nearby_garage_context(text: str) -> None:
    assert any(m.code == "body" for m in extract_report(text)[0])


@pytest.mark.parametrize(
    "text,code,status",
    [
        ("The vehicle did not restart automatically.", "no_start", "affirmed"),
        (
            "When stopped in traffic the vehicle will sometimes not restart automatically.",
            "no_start",
            "affirmed",
        ),
        ("If the vehicle does not restart automatically.", "no_start", "uncertain"),
        (
            "If the vehicle after a very long and detailed journey "
            "will sometimes not restart automatically.",
            "no_start",
            "unresolved",
        ),
        ("The vehicle failed to restart.", "no_start", "affirmed"),
        ("There was no other way to turn on the vehicle.", "no_start", "affirmed"),
        ("Command failed.", "operation_loss", "affirmed"),
        ("The remote command failed.", "operation_loss", "affirmed"),
        ("If the command failed.", "operation_loss", "uncertain"),
        ("No command failed.", "operation_loss", "negated"),
        ("A warning appeared on the dashboard.", "warning_indicator", "affirmed"),
        ("A warning will appear on the dashboard.", "warning_indicator", "uncertain"),
        ("A warning might appear on the dashboard.", "warning_indicator", "uncertain"),
        (
            "Sometimes the vehicle fails to restart. A warning will appear on the dash.",
            "warning_indicator",
            "affirmed",
        ),
        (
            "If the vehicle sometimes fails to restart. A warning will appear on the dash.",
            "warning_indicator",
            "uncertain",
        ),
        ("No warning appeared on the dashboard.", "warning_indicator", "negated"),
        (
            "Brake hold was engaged but the vehicle continues to roll.",
            "braking_difficulty",
            "affirmed",
        ),
        (
            "The brake hold system signals HOLD but the car continues to roll, "
            "and abruptly stops later than intended.",
            "braking_difficulty",
            "affirmed",
        ),
        (
            "If brake hold is engaged but the vehicle continues to roll.",
            "braking_difficulty",
            "uncertain",
        ),
    ],
)
def test_explicit_contextual_symptoms(text: str, code: str, status: str) -> None:
    symptoms = [m for m in extract_report(text)[1] if m.code == code]
    assert symptoms and symptoms[0].assertion == status
    for m in symptoms:
        assert text[m.start : m.end] == m.evidence_text
        for cue in m.assertion_cue_spans:
            assert text[cue.start : cue.end] == cue.evidence_text


@pytest.mark.parametrize(
    "text",
    [
        "The command failed to start the app.",
        "The app failed to start.",
        "The software failed to restart.",
        "The vehicle failed to start the application.",
    ],
)
def test_app_start_is_not_physical_no_start(text: str) -> None:
    assert not any(m.code == "no_start" for m in extract_report(text)[1])


@pytest.mark.parametrize(
    "text",
    [
        "The vehicle continues to roll.",
        "The car abruptly stops later than intended.",
        "Brake hold was released and the car continues to roll.",
        "Brake hold is off but the vehicle continues to roll.",
        "Brake hold is not engaged but the vehicle continues to roll.",
        "Without brake hold the car continues to roll.",
        "The brake hold indicator displays HOLD.",
        "The engine performs a normal automatic stop.",
        "A message on the phone said hello.",
    ],
)
def test_normal_or_unanchored_behavior_not_inferred(text: str) -> None:
    assert not extract_report(text)[1]


@pytest.mark.parametrize(
    "text",
    [
        "The vehicle had been taken to the workshop for inspection of the engine.",
        "A specialist examined the vehicle and diagnosed a problem with the engine.",
        "The driver had no physical key available to start the engine.",
        "The owner described an incident involving the steering wheel column.",
    ],
)
def test_long_named_referent_is_affirmed_without_defect_inference(text: str) -> None:
    assert all(m.assertion == "affirmed" for m in extract_report(text)[0])


def test_ambiguity_uncertainty_and_warning_reference_stay_conservative() -> None:
    assert extract_report("Dealer suspects fuel pump.")[0][0].assertion == "uncertain"
    assert (
        extract_report("Perhaps after a long conversation about the repair history the engine.")[0][
            0
        ].assertion
        == "unresolved"
    )
    assert extract_report("Check engine light.")[0][0].assertion == "unresolved"
    assert extract_report("Wheel problem.")[0][0].assertion == "unresolved"
    assert extract_report("The engine did not stall.")[1][0].assertion == "negated"


def test_unicode_offsets_order_and_repeatability() -> None:
    text = (
        "🚗 Café e\u0301: \uff23ommand failed; "
        "brake hold system signals HOLD but the car continues to roll."
    )
    a = extract_report(text)
    assert a == extract_report(text)
    assert {m.code for m in a[1]} == {"operation_loss", "braking_difficulty"}
    for group in a:
        for span in group:
            assert text[span.start : span.end] == span.evidence_text


def test_long_self_contained_failure_preserves_hypothetical_scope() -> None:
    text = ("The technician explained the situation in detail "
            "and there was no other way to turn on the car.")
    symptom = extract_report(text)[1][0]
    assert symptom.code == "no_start" and symptom.assertion == "affirmed"
    conditional = ("If the technician explained the situation in detail "
                   "and there was no other way to turn on the car.")
    assert extract_report(conditional)[1][0].assertion != "affirmed"
