"""Explicit symptom aliases with original-text spans; no component inference."""

import hashlib
import json
import re
from typing import Final

from howreliable.nlp.components import _matching_view, _pattern
from howreliable.nlp.schemas import SymptomCode, SymptomMention

SYMPTOM_LEXICON_VERSION: Final = "howreliable-owner-report-symptom-lexicon-1.1"
SYMPTOMS: tuple[tuple[SymptomCode, tuple[str, ...]], ...] = (
    (
        "stall_shutdown",
        (
            "stalled",
            "stalling",
            "stalls",
            "stall",
            "shut off",
            "shuts off",
            "shut down",
            "shutdown",
        ),
    ),
    (
        "no_start",
        (
            "would not start",
            "will not start",
            "won't start",
            "wouldn't start",
            "failed to start",
            "failure to start",
            "does not start",
            "cannot start",
            "can't start",
            "no start",
            "not restart automatically",
            "failed to restart",
            "failure to restart",
            "would not restart",
            "does not restart",
            "unable to restart",
            "no other way to turn on the car",
            "no other way to turn on the vehicle",
        ),
    ),
    (
        "hesitation_power_loss",
        ("hesitation", "hesitates", "hesitated", "reduced power", "loss of power", "lost power"),
    ),
    (
        "unintended_acceleration",
        ("unintended acceleration", "accelerated without input", "accelerated on its own"),
    ),
    (
        "noise",
        (
            "grinding noise",
            "knocking noise",
            "squealing noise",
            "noise",
            "grinding",
            "knocking",
            "squealing",
        ),
    ),
    ("vibration", ("vibration", "vibrations", "vibrating", "vibrated", "shaking", "shook")),
    (
        "shift_engagement",
        (
            "harsh engagement",
            "harsh shifting",
            "would not shift",
            "failed to shift",
            "rough shifting",
        ),
    ),
    ("leak", ("leaking", "leaked", "leaks", "leak", "leakage", "dripping fluid")),
    ("odor", ("burning odor", "fuel odor", "burning smell", "fuel smell", "odor")),
    ("smoke", ("smoke", "smoking")),
    ("overheating", ("overheated", "overheating", "overheats")),
    (
        "warning_indicator",
        (
            "check engine light",
            "warning light",
            "warning lights",
            "warning lamp",
            "warning message",
            "engine light",
            "abs light",
            "airbag light",
            "battery light",
            "indicator light",
            "dashboard warning",
            "dash warning",
        ),
    ),
    (
        "braking_difficulty",
        (
            "loss of braking",
            "lost braking",
            "brakes failed",
            "brake pedal was hard",
            "hard brake pedal",
            "loss of brake assist",
            "loss of braking assistance",
            "brake pedal became hard",
        ),
    ),
    (
        "steering_difficulty",
        (
            "loss of steering assistance",
            "loss of steering assist",
            "lost steering assist",
            "lost steering assistance",
            "steering locked",
            "heavy steering",
            "loss of power steering",
        ),
    ),
    (
        "electrical_interruption",
        (
            "electrical power cut out",
            "electrical interruption",
            "lights cut out",
            "lights went out",
        ),
    ),
    (
        "intermittent_operation",
        (
            "intermittently stopped working",
            "intermittently stops working",
            "cuts in and out",
            "intermittent operation",
        ),
    ),
    (
        "operation_loss",
        (
            "stopped working",
            "stops working",
            "failed to operate",
            "command failed",
            "commands failed",
        ),
    ),
)
_CONTEXT_RULES: tuple[tuple[SymptomCode, str, str], ...] = (
    (
        "warning_indicator",
        "dashboard_appearance",
        r"(?<!\w)warning\s+(?:(?:will|would|may|might|could)\s+)?appear(?:s|ed)?\s+on\s+(?:the\s+)?(?:dashboard|dash)(?!\w)",
    ),
    ("braking_difficulty", "hold_roll", r"(?<!\w)(?:car|vehicle)\s+continues?\s+to\s+roll(?!\w)"),
    (
        "braking_difficulty",
        "hold_delayed_stop",
        r"(?<!\w)abruptly\s+stops?\s+later\s+than\s+intended(?!\w)",
    ),
)
_RULES = (
    *tuple((code, alias, _pattern(alias)) for code, aliases in SYMPTOMS for alias in aliases),
    *tuple((code, name, re.compile(pattern)) for code, name, pattern in _CONTEXT_RULES),
)


def _context_allowed(view: str, a: int, b: int, code: SymptomCode, rule: str) -> bool:
    prefix = re.split(r"[.!?;\n]", view[max(0, a - 250) : a])[-1]
    if code == "no_start" and (
        re.search(
            r"\b(?:app|application|command|request|software|download|update)\s+(?:(?:has|had)\s+)?$",
            prefix,
        )
        or re.match(r"\s+(?:the\s+)?(?:app|application|software|download|update)\b", view[b:])
    ):
        return False
    if rule in {"hold_roll", "hold_delayed_stop"}:
        return bool(
            re.search(r"\b(?:brake[\s-]+hold|auto[\s-]+hold|parking brake)\b", prefix)
            and not re.search(r"\b(?:off|disabled|disengaged|released)\b", prefix)
            and not re.search(
                r"\b(?:no|without)\s+(?:brake[\s-]+hold|auto[\s-]+hold|parking brake)\b", prefix
            )
            and not re.search(r"\b(?:not|never)\s+(?:engaged|enabled|activated|active)\b", prefix)
        )
    return True


def symptom_lexicon_sha256() -> str:
    return hashlib.sha256(
        json.dumps((SYMPTOMS, _CONTEXT_RULES), separators=(",", ":")).encode()
    ).hexdigest()


def extract_symptoms(text: str) -> tuple[SymptomMention, ...]:
    view, indices = _matching_view(text)
    candidates: list[tuple[int, int, SymptomCode, str]] = []
    for code, alias, pattern in _RULES:
        for match in pattern.finditer(view):
            a, b = match.span()
            if not _context_allowed(view, a, b, code, alias):
                continue
            if (a and indices[a - 1] == indices[a]) or (
                b < len(indices) and indices[b - 1] == indices[b]
            ):
                continue
            candidates.append((indices[a], indices[b - 1] + 1, code, alias))
    selected: list[tuple[int, int, SymptomCode, str]] = []
    for value in sorted(candidates, key=lambda x: (-(x[1] - x[0]), x[0], x[2], x[3])):
        if not any(value[0] < old[1] and old[0] < value[1] for old in selected):
            selected.append(value)
    return tuple(
        SymptomMention(
            mention_id=f"symptom_{a}_{b}_{code}",
            code=code,
            start=a,
            end=b,
            evidence_text=text[a:b],
            rule_id=f"symptom-v1.{code}.{hashlib.sha256(alias.encode()).hexdigest()[:12]}",
            ambiguity_reason="assertion_not_yet_resolved",
        )
        for a, b, code, alias in sorted(selected, key=lambda x: (x[0], x[1], x[2]))
    )
