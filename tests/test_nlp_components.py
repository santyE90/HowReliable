"""Component-only synthetic matching, boundaries, offsets and assertion limitations."""

import json

import pytest
from pydantic import ValidationError

from howreliable.nlp.components import LEXICON, extract_components, lexicon_sha256
from howreliable.nlp.schemas import ComponentMention


@pytest.mark.parametrize(
    "text,code",
    [
        ("engine cylinder", "engine"),
        ("gearbox", "transmission"),
        ("alternator", "electrical"),
        ("water pump", "cooling"),
        ("shock absorbers", "suspension"),
        ("brake booster", "brakes"),
        ("power steering", "steering"),
        ("fuel pump", "fuel_system"),
        ("cabin heater", "hvac"),
        ("catalytic converter", "exhaust"),
        ("door latch", "body"),
        ("seatbelt", "airbags_restraints"),
        ("tyres", "tires_wheels"),
        ("ABS", "brakes"),
        ("SRS", "airbags_restraints"),
        ("HVAC", "hvac"),
    ],
)
def test_explicit_categories_and_variants(text: str, code: str) -> None:
    mentions = extract_components(f"The {text} was inspected.")
    assert mentions and all(m.code == code for m in mentions)
    assert all(
        m.assertion == "unresolved" and m.rule_id.startswith("component-v1.") for m in mentions
    )


@pytest.mark.parametrize(
    "text",
    [
        "engineering, tired, exhausted, doorway, windowpane, brakefluid, gearboxed",
        "Vibration, grinding, stalling, smoke, heat, loss of power.",
        "my abs hurt; srs; hvac",
        "engine_software",
        "enginé",
        "",
        "  ",
    ],
)
def test_boundaries_and_no_symptom_based_component_inference(text: str) -> None:
    assert extract_components(text) == ()


def test_longest_overlaps_multiple_and_repeated_components() -> None:
    text = "Steering wheel, wheel rim, brake pedal, ENGINE, engine cylinders, road wheels."
    mentions = extract_components(text)
    assert [(m.evidence_text, m.code) for m in mentions] == [
        ("Steering wheel", "steering"),
        ("wheel rim", "tires_wheels"),
        ("brake pedal", "brakes"),
        ("ENGINE", "engine"),
        ("engine cylinders", "engine"),
        ("road wheels", "tires_wheels"),
    ]
    assert len({m.mention_id for m in mentions}) == len(mentions)


@pytest.mark.parametrize(
    "text",
    [
        "🚗 Café: \uff25\uff2e\uff27\uff29\uff2e\uff25 and fuel\u00a0pump.",
        "e\u0301: power\t\nsteering and water\u2011pump.",
        "Straße: BRAKES; seat\u2003belt!",
        "\uff21\uff22\uff33 and engine cylinder",
    ],
)
def test_original_unicode_codepoint_and_whitespace_offsets(text: str) -> None:
    before = text
    mentions = extract_components(text)
    assert mentions
    for m in mentions:
        assert text[m.start : m.end] == m.evidence_text
        assert m.end - m.start == len(m.evidence_text)
        assert json.loads(m.model_dump_json())["evidence_text"] == m.evidence_text
    assert text == before


def test_expansion_alignment_does_not_match_partial_compatibility_character() -> None:
    assert extract_components("aß") == ()
    text = "ﬂower ENGINE"
    m = extract_components(text)[0]
    assert m.evidence_text == "ENGINE" and m.start == text.index("ENGINE")


def test_warning_lights_are_unresolved_referents_never_damage_claims() -> None:
    mentions = extract_components("Check engine light, ABS warning lamp and airbag indicator.")
    assert [m.code for m in mentions] == ["engine", "brakes", "airbags_restraints"]
    assert all(m.assertion == "unresolved" for m in mentions)
    assert all(
        m.ambiguity_reason == "warning_indicator_does_not_establish_component_damage"
        for m in mentions
    )


@pytest.mark.parametrize(
    "text",
    [
        "The engine stalled",
        "The engine did not stall",
        "Perhaps the engine",
        "The engine was replaced",
        "If the engine stops",
        "No engine problem",
    ],
)
def test_assertion_scope_is_explicitly_deferred(text: str) -> None:
    m = extract_components(text)[0]
    assert m.assertion == "unresolved" and m.assertion_cue_spans == ()
    assert m.ambiguity_reason == "assertion_scope_deferred_to_milestone_d"


def test_bare_wheel_ambiguity_does_not_choose_a_component() -> None:
    m = extract_components("Wheel problem")[0]
    assert m.code == "component_ambiguous"
    assert m.candidate_codes == ("steering", "tires_wheels")
    assert m.assertion == "unresolved"


def test_lexicon_and_serialization_are_stable() -> None:
    aliases = [(rule.code, alias) for rule in LEXICON for alias in rule.aliases]
    assert len(aliases) == len(set(aliases))
    assert len(lexicon_sha256()) == 64
    text = "Brakes, battery, fuel pump, and brakes."
    a, b = extract_components(text), extract_components(text)
    assert [x.model_dump_json() for x in a] == [x.model_dump_json() for x in b]
    assert [(x.start, x.end, x.kind, x.code) for x in a] == sorted(
        (x.start, x.end, x.kind, x.code) for x in a
    )
    value = a[0].model_dump(mode="json")
    value["assertion"] = "invalid_assertion"
    with pytest.raises(ValidationError):
        ComponentMention.model_validate_json(json.dumps(value))
    value["assertion"] = "unresolved"
    value["end"] = 100
    with pytest.raises(ValidationError):
        ComponentMention.model_validate_json(json.dumps(value))
