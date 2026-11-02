"""Versioned literal component lexicon and original-text matching; no diagnosis."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from howreliable.nlp.schemas import ComponentCode, ComponentMention

LEXICON_VERSION: Final = "howreliable-owner-report-component-lexicon-1.1"
MATCHER_VERSION: Final = "howreliable-owner-report-component-matcher-1.1"


@dataclass(frozen=True)
class ComponentRule:
    code: ComponentCode
    aliases: tuple[str, ...]


# Explicit plurals/variants only. No stemming, fuzzy matching or domain-enum mutation.
LEXICON: Final = (
    ComponentRule("engine", ("engine cylinder", "engine cylinders", "engine", "engines")),
    ComponentRule(
        "transmission",
        ("transmission", "transmissions", "gearbox", "gearboxes", "clutch", "clutches"),
    ),
    ComponentRule(
        "electrical",
        ("electrical system", "battery", "batteries", "alternator", "alternators", "wiring"),
    ),
    ComponentRule(
        "cooling",
        ("coolant system", "cooling system", "radiator", "radiators", "water pump", "water pumps"),
    ),
    ComponentRule(
        "suspension", ("suspension", "strut", "struts", "shock absorber", "shock absorbers")
    ),
    ComponentRule(
        "brakes",
        (
            "brake hold system",
            "brake pedal",
            "brake pedals",
            "brake booster",
            "brake boosters",
            "anti lock braking system",
            "abs",
            "brake",
            "brakes",
        ),
    ),
    ComponentRule(
        "steering",
        (
            "steering wheel column",
            "steering column",
            "steering wheel",
            "power steering",
            "steering",
        ),
    ),
    ComponentRule(
        "fuel_system",
        (
            "fuel system",
            "fuel pump",
            "fuel pumps",
            "fuel line",
            "fuel lines",
            "fuel tank",
            "fuel tanks",
        ),
    ),
    ComponentRule(
        "hvac",
        ("air conditioning", "air conditioner", "cabin heater", "defroster", "defrosters", "hvac"),
    ),
    ComponentRule(
        "exhaust",
        (
            "exhaust pipe",
            "exhaust pipes",
            "muffler",
            "mufflers",
            "catalytic converter",
            "catalytic converters",
            "exhaust",
        ),
    ),
    ComponentRule(
        "body",
        ("door", "doors", "window", "windows", "latch", "latches", "body panel", "body panels"),
    ),
    ComponentRule(
        "airbags_restraints",
        (
            "airbag",
            "airbags",
            "air bag",
            "air bags",
            "seat belt",
            "seat belts",
            "seatbelt",
            "seatbelts",
            "restraint",
            "restraints",
            "srs",
        ),
    ),
    ComponentRule(
        "tires_wheels",
        ("tire", "tires", "tyre", "tyres", "road wheel", "road wheels", "wheel rim", "wheel rims"),
    ),
    ComponentRule("component_ambiguous", ("wheel", "wheels")),
)


def lexicon_sha256() -> str:
    value = [(rule.code, rule.aliases) for rule in LEXICON]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def _pattern(alias: str) -> re.Pattern[str]:
    # Hyphen or whitespace between declared words only; never consume punctuation clauses.
    return re.compile(r"(?<!\w)" + r"(?:\s+|-)".join(map(re.escape, alias.split())) + r"(?!\w)")


_PATTERNS = tuple((r.code, alias, _pattern(alias)) for r in LEXICON for alias in r.aliases)
_ACRONYMS: Final = frozenset({"abs", "srs", "hvac"})
_DASHES: Final = frozenset("\u2010\u2011\u2012\u2013\u2014\u2015")
_INDICATOR = re.compile(r"^\s*(?:warning\s+)?(?:light|lamp|indicator|message)\b")
_BUILDING = r"(?:garage|house|building|apartment|shed|warehouse|hangar)"


def _nonvehicle_body(view: str, a: int, b: int) -> bool:
    # Explicit building modifiers or narrowly anchored local coreference only.
    # A garage elsewhere in the narrative does not suppress a vehicle door.
    prefix = re.split(r"[.!?;,\n]", view[max(0, a - 110) : a])[-1]
    return bool(
        re.search(r"\b" + _BUILDING + r"(?:['\u2019]s)?\s+(?:(?:door|window)\s+)?$", prefix)
        or re.search(r"\b" + _BUILDING + r"\s+with\s+(?:the|its)\s+$", prefix)
        or re.match(r"\s+(?:of|to)\s+(?:(?:the|a|my|our)\s+)?" + _BUILDING + r"\b", view[b:])
    )


def _matching_view(text: str) -> tuple[str, list[int]]:
    """Per-code-point NFKC/casefold with an explicit original-index map.

    Deliberately does not compose across input code points or repair uncertain encoding.
    Expanded compatibility characters may match only when their whole expansion is used.
    """
    chars: list[str] = []
    indices: list[int] = []
    for index, char in enumerate(text):
        normalized = "-" if char in _DASHES else unicodedata.normalize("NFKC", char).casefold()
        chars.append(normalized)
        indices.extend([index] * len(normalized))
    return "".join(chars), indices


def extract_components(narrative: str) -> tuple[ComponentMention, ...]:
    """Return component referents only; assertion scope is always unresolved in C."""
    view, indices = _matching_view(narrative)
    candidates: list[tuple[int, int, ComponentCode, str, str]] = []
    for code, alias, pattern in _PATTERNS:
        for match in pattern.finditer(view):
            a, b = match.span()
            if (a and indices[a - 1] == indices[a]) or (
                b < len(indices) and indices[b - 1] == indices[b]
            ):
                continue
            start, end = indices[a], indices[b - 1] + 1
            evidence = narrative[start:end]
            # Short acronyms must be uppercase as written, preventing e.g. "my abs".
            if alias in _ACRONYMS and not evidence.isupper():
                continue
            if code == "body" and _nonvehicle_body(view, a, b):
                continue
            reason = "assertion_scope_deferred_to_milestone_d"
            if code == "component_ambiguous":
                reason = "wheel_referent_ambiguous"
            elif _INDICATOR.match(view[b:]):
                reason = "warning_indicator_does_not_establish_component_damage"
            candidates.append((start, end, code, alias, reason))
    # Longest explicit phrase wins overlap; lexical ties are independent of lexicon order.
    selected: list[tuple[int, int, ComponentCode, str, str]] = []
    for candidate in sorted(candidates, key=lambda x: (-(x[1] - x[0]), x[0], x[2], x[3])):
        if not any(candidate[0] < old[1] and old[0] < candidate[1] for old in selected):
            selected.append(candidate)
    results = []
    for start, end, code, alias, reason in sorted(selected, key=lambda x: (x[0], x[1], x[2])):
        results.append(
            ComponentMention(
                mention_id=f"component_{start}_{end}_{code}",
                code=code,
                start=start,
                end=end,
                evidence_text=narrative[start:end],
                rule_id=f"component-v1.{code}.{hashlib.sha256(alias.encode()).hexdigest()[:12]}",
                ambiguity_reason=reason,
                candidate_codes=("steering", "tires_wheels")
                if code == "component_ambiguous"
                else (),
            )
        )
    return tuple(results)
