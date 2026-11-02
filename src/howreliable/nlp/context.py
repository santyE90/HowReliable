"""Bounded assertion rules and deliberately narrow local grammatical associations."""

from __future__ import annotations

import re
from typing import Final

from howreliable.nlp.components import _matching_view, extract_components
from howreliable.nlp.schemas import Association, ComponentMention, EvidenceSpan, SymptomMention
from howreliable.nlp.symptoms import extract_symptoms

ASSERTION_VERSION: Final = "howreliable-owner-report-assertion-1.1"
ASSOCIATION_VERSION: Final = "howreliable-owner-report-association-1.0"
_BOUNDARY = re.compile(r"[.!?;,\n]|\b(?:but|however|although|yet|whereas|except)\b")
_UNCERTAIN = re.compile(
    r"\b(?:may|might|could|possibly|possible|perhaps|suspect|suspects|suspected|"
    r"if|unless|would|should|will|believes|thinks|thought|seems|appears)\b"
)
_NEGATED = re.compile(
    r"\b(?:no longer|no|not|never|without|denies|denied)\b|"
    r"\b(?:didn't|doesn't|wasn't|isn't|aren't|weren't|don't)\b"
)
_REPAIR = re.compile(
    r"\b(?:repair|repairs|repaired|replace|replaced|replacement|recall|recalled)\b"
)
_LINK = re.compile(
    r"\s*(?:(?:is|was|were|has|had|been|did|does|not|never|no longer|"
    r"may|might|could|would|will|began|started|to|suddenly|repeatedly|also)\s+)*"
)


def _scope(text: str, start: int, end: int) -> tuple[str, list[int], int, int, int, int]:
    view, mapping = _matching_view(text)
    a = next(i for i, value in enumerate(mapping) if value >= start)
    b = next((i for i, value in enumerate(mapping) if value >= end), len(mapping))
    left, right = 0, len(view)
    for boundary in _BOUNDARY.finditer(view):
        if boundary.end() <= a:
            left = boundary.end()
        elif boundary.start() >= b:
            right = boundary.start()
            break
    return view, mapping, a, b, left, right


def classify[M: (ComponentMention, SymptomMention)](text: str, mention: M) -> M:
    view, mapping, a, b, left, right = _scope(text, mention.start, mention.end)
    # Eight preceding tokens within the clause. Longer/difficult scope abstains.
    prefix = view[left:a]
    tokens = list(re.finditer(r"\S+", prefix))
    window_start = left + (tokens[-8].start() if len(tokens) > 8 else 0)
    prefix = view[window_start:a]
    suffix = view[b:right]
    status = "affirmed"
    reason = "explicit_reported_mention"
    cues: tuple[EvidenceSpan, ...] = ()
    uncertain = list(_UNCERTAIN.finditer(prefix))
    negated = [
        m for m in _NEGATED.finditer(prefix) if not re.match(r"\s+only\b", prefix[m.end() :])
    ]
    repair = _REPAIR.search(view[left:right])
    cue = None
    # A future dashboard warning remains speculative unless explicit recurrence
    # in the immediately preceding sentence/current prefix supports a habitual reading.
    internal_modal = re.search(r"\b(?:will|would|may|might|could)\b", view[a:b])
    recent = re.split(r"[.!?\n]", view[max(0, a - 250) : a])
    habitual = bool(
        re.search(
            r"\b(?:sometimes|repeatedly|every time|each time|whenever)\b", " ".join(recent[-2:])
        )
    )
    habitual = habitual and not re.search(
        r"\b(?:if|unless|might|may|could|would|expect|fear)\b", " ".join(recent[-2:])
    )
    explicit_restart = (
        mention.kind == "symptom"
        and mention.code == "no_start"
        and view[a:b] == "not restart automatically"
        and re.search(r"\bwill\s+sometimes\s*$", prefix) is not None
        and not negated
        and not any(m.group() != "will" for m in uncertain)
        and not any(m.group() != "will" for m in _UNCERTAIN.finditer(view[left:a]))
    )
    self_contained_no_start = (
        mention.kind == "symptom"
        and mention.code == "no_start"
        and view[a:b] in {"no other way to turn on the car", "no other way to turn on the vehicle"}
        and not _UNCERTAIN.search(view[left:a])
        and not _NEGATED.search(view[left:a])
    )
    if mention.kind == "component" and (
        mention.code in {"component_ambiguous", "component_unmapped"}
        or mention.ambiguity_reason == "warning_indicator_does_not_establish_component_damage"
    ):
        status, reason = "unresolved", mention.ambiguity_reason
    elif uncertain and negated:
        status, reason = "unresolved", "mixed_negation_uncertainty_scope"
        cue = uncertain[-1]
    elif len(negated) > 1:
        status, reason, cue = "unresolved", "multiple_negation_requires_review", negated[-1]
    elif uncertain:
        status, reason, cue = "uncertain", "bounded_uncertainty", uncertain[-1]
    elif mention.kind == "symptom" and negated:
        status, reason, cue = "negated", "bounded_negation", negated[-1]
    # Postposed suspicion is handled only for a short explicit attribution construction.
    elif post := re.match(r"\s+(?:was|is)\s+(suspected|possible)\b", suffix):
        status, reason = "uncertain", "postposed_uncertainty"
        x, y = b + post.start(1), b + post.end(1)
        start, end = mapping[x], mapping[y - 1] + 1
        cues = (EvidenceSpan(start=start, end=end, evidence_text=text[start:end]),)
    elif mention.kind == "symptom" and (
        post := re.match(r"\s+(?:was|is)\s+(not present|absent|denied)\b", suffix)
    ):
        status, reason = "negated", "postposed_denial"
        x, y = b + post.start(1), b + post.end(1)
        start, end = mapping[x], mapping[y - 1] + 1
        cues = (EvidenceSpan(start=start, end=end, evidence_text=text[start:end]),)
    if (
        mention.kind == "symptom"
        and mention.code == "warning_indicator"
        and internal_modal
        and (internal_modal.group() != "will" or not habitual)
    ):
        status, reason = (
            ("unresolved", "mixed_negation_uncertainty_scope")
            if negated
            else ("uncertain", "internal_warning_modality")
        )
        x, y = a + internal_modal.start(), a + internal_modal.end()
        start, end = mapping[x], mapping[y - 1] + 1
        cues = (EvidenceSpan(start=start, end=end, evidence_text=text[start:end]),)
    if mention.kind == "symptom" and repair:
        status, reason = "unresolved", "repair_context_not_an_observed_symptom"
    elif (
        mention.kind == "symptom"
        and mention.code == "stall_shutdown"
        and re.search(r"\b(?:i|we|driver|owner)\s+(?:deliberately\s+)?$", prefix)
        and "shut" in view[a:b]
    ):
        status, reason = "unresolved", "possible_deliberate_shutdown"
    elif (
        mention.kind == "symptom"
        and mention.code == "operation_loss"
        and not prefix.strip()
        and not re.fullmatch(r"commands?\s+failed", view[a:b])
    ):
        status, reason = "unresolved", "missing_explicit_subject"
    # Do not affirm across ambiguous conjunction or scope beyond the bounded window.
    long_scope = len(tokens) > 8 and (
        (mention.kind == "symptom" and not (explicit_restart or self_contained_no_start))
        or (mention.kind == "component" and _UNCERTAIN.search(view[left:window_start]) is not None)
    )
    if long_scope or (re.search(r"\band\b", prefix) and (negated or uncertain)):
        status, reason = "unresolved", "scope_requires_review"
    if explicit_restart and not repair:
        status, reason, cue, cues = "affirmed", "habitual_restart_failure", None, ()
    # Hold problems can occur after a contrast boundary while the preceding
    # conditional still governs the whole sentence. Do not turn those into observations.
    if (
        mention.kind == "symptom"
        and mention.code == "braking_difficulty"
        and re.fullmatch(
            r"(?:(?:car|vehicle)\s+continues?\s+to\s+roll|abruptly\s+stops?\s+later\s+than\s+intended)",
            view[a:b],
        )
    ):
        sentence_start = max(0, a - 250)
        # Find the last delimiter without changing the offset base during iteration.
        delimiters = list(re.finditer(r"[.!?;\n]", view[sentence_start:a]))
        if delimiters:
            sentence_start += delimiters[-1].end()
        conditional = re.search(r"\b(?:if|unless|might|may|could|would)\b", view[sentence_start:a])
        if conditional:
            x, y = sentence_start + conditional.start(), sentence_start + conditional.end()
            start, end = mapping[x], mapping[y - 1] + 1
            status, reason, cue = "uncertain", "conditional_hold_context", None
            cues = (EvidenceSpan(start=start, end=end, evidence_text=text[start:end]),)
    if cue is not None:
        x, y = window_start + cue.start(), window_start + cue.end()
        start, end = mapping[x], mapping[y - 1] + 1
        cues = (EvidenceSpan(start=start, end=end, evidence_text=text[start:end]),)
    # Pydantic validation is intentional; model_copy(update=...) would skip type validation.
    values = mention.model_dump()
    values.update(assertion=status, ambiguity_reason=reason, assertion_cue_spans=cues)
    return type(mention).model_validate(values)


def extract_report(
    text: str,
) -> tuple[tuple[ComponentMention, ...], tuple[SymptomMention, ...], tuple[Association, ...]]:
    components = tuple(classify(text, m) for m in extract_components(text))
    symptoms = tuple(classify(text, m) for m in extract_symptoms(text))
    associations: list[Association] = []
    for symptom in symptoms:
        if symptom.assertion == "unresolved" or symptom.code == "warning_indicator":
            continue
        view, mapping, a, b, left, right = _scope(text, symptom.start, symptom.end)
        local = [
            c for c in components if c.start >= mapping[left] and c.end <= mapping[right - 1] + 1
        ]
        if len(local) != 1:
            continue
        c = local[0]
        if c.assertion == "unresolved" or _REPAIR.search(view[left:right]):
            continue
        # Subject immediately preceding predicate, or component explicitly inside symptom phrase.
        contained = symptom.start <= c.start and c.end <= symptom.end
        gap = text[c.end : symptom.start] if c.end <= symptom.start else None
        direct = gap is not None and len(gap.split()) <= 6 and _LINK.fullmatch(gap.casefold())
        if not contained and not direct:
            continue
        start, end = min(c.start, symptom.start), max(c.end, symptom.end)
        associations.append(
            Association(
                component_mention_id=c.mention_id,
                symptom_mention_id=symptom.mention_id,
                start=start,
                end=end,
                evidence_text=text[start:end],
                rule_id="association-v1.contained_component"
                if contained
                else "association-v1.subject_predicate",
            )
        )
    return components, symptoms, tuple(associations)
