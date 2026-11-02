"""Read-only preliminary development evaluation; never opens held-out annotations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, get_args

from howreliable.nlp.annotation_review import (
    STATE_MAP,
    ReviewError,
    parse_working,
    read_source,
    source_path,
    validate_working,
    working_path,
)
from howreliable.nlp.development_predictions import (
    VERSION as DEVELOPMENT_VERSION,
)
from howreliable.nlp.development_predictions import (
    DevelopmentPacket,
)
from howreliable.nlp.owner_reports import _code_hash, _git_identity, _hash, _json
from howreliable.nlp.schemas import (
    ComponentCode,
    ComponentMention,
    ExtractionRow,
    SymptomCode,
    SymptomMention,
)

VERSION = "howreliable-development-evaluation-1.0"
LABEL = (
    "Preliminary, tiny non-representative development sample; not held-out validation. "
    "No claim that the 90% precision target is met."
)
ASSERTIONS = ("affirmed", "negated", "uncertain", "unresolved")


@dataclass(frozen=True, order=True)
class Mention:
    start: int
    end: int
    kind: str
    code: str
    assertion: str


@dataclass
class Evidence:
    mentions: list[Mention]
    associations: set[tuple[int, int]]


def evidence(components: Any, symptoms: Any, associations: Any) -> Evidence:
    """Canonicalize by semantic identity, not source-row-local mention IDs."""
    originals = [*components, *symptoms]
    by_id = {m.mention_id: Mention(m.start, m.end, m.kind, m.code, m.assertion) for m in originals}
    mentions = sorted(set(by_id.values()))
    positions = {m: i for i, m in enumerate(mentions)}
    return Evidence(
        mentions,
        {
            (positions[by_id[a.component_mention_id]], positions[by_id[a.symptom_mention_id]])
            for a in associations
        },
    )


@dataclass
class Edge:
    target: int
    reverse: int
    capacity: int
    cost: tuple[Fraction, int]


def match(
    gold: list[Mention], predicted: list[Mention], *, overlap: bool = False, assertion: bool = True
) -> list[tuple[int, int]]:
    """Max cardinality, then exact total IoU, then lexical pair preference.

    Successive shortest augmenting paths with rational costs avoid greedy matching
    and floating-point tie changes. Lexical ties prefer earlier sorted span pairs.
    """
    candidates = []
    for i, g in enumerate(gold):
        for j, p in enumerate(predicted):
            intersection = min(g.end, p.end) - max(g.start, p.start)
            if (g.kind, g.code) != (p.kind, p.code) or (assertion and g.assertion != p.assertion):
                continue
            if intersection <= 0 or (not overlap and (g.start, g.end) != (p.start, p.end)):
                continue
            candidates.append(
                (i, j, Fraction(intersection, max(g.end, p.end) - min(g.start, p.start)))
            )
    size = 2 + len(gold) + len(predicted)
    sink = size - 1
    graph: list[list[Edge]] = [[] for _ in range(size)]
    zero = (Fraction(0), 0)

    def add(a: int, b: int, cost: tuple[Fraction, int]) -> Edge:
        forward = Edge(b, len(graph[b]), 1, cost)
        graph[a].append(forward)
        graph[b].append(Edge(a, len(graph[a]) - 1, 0, (-cost[0], -cost[1])))
        return forward

    for i in range(len(gold)):
        add(0, 1 + i, zero)
    for j in range(len(predicted)):
        add(1 + len(gold) + j, sink, zero)
    references = []
    for order, (i, j, iou) in enumerate(candidates):
        edge = add(1 + i, 1 + len(gold) + j, (-iou, -(1 << (len(candidates) - order - 1))))
        references.append((i, j, edge))
    while True:
        distances: list[tuple[Fraction, int] | None] = [None] * size
        previous: list[tuple[int, int] | None] = [None] * size
        distances[0] = zero
        for _ in range(size - 1):
            changed = False
            for node in range(size):
                distance = distances[node]
                if distance is None:
                    continue
                for n, edge in enumerate(graph[node]):
                    cost = (distance[0] + edge.cost[0], distance[1] + edge.cost[1])
                    old = distances[edge.target]
                    if edge.capacity and (old is None or cost < old):
                        distances[edge.target] = cost
                        previous[edge.target] = (node, n)
                        changed = True
            if not changed:
                break
        if previous[sink] is None:
            break
        node = sink
        while node:
            step = previous[node]
            assert step is not None
            parent, number = step
            edge = graph[parent][number]
            edge.capacity -= 1
            graph[node][edge.reverse].capacity += 1
            node = parent
    return [(i, j) for i, j, edge in references if edge.capacity == 0]


def metrics(tp: int, fp: int, fn: int) -> dict[str, Any]:
    predicted, support = tp + fp, tp + fn
    precision = tp / predicted if predicted else None
    recall = tp / support if support else None
    denominator = 2 * tp + fp + fn
    interval = None
    if predicted:
        z = 1.959963984540054
        center = (tp / predicted + z * z / (2 * predicted)) / (1 + z * z / predicted)
        radius = (
            z
            * math.sqrt(
                (tp / predicted) * (1 - tp / predicted) / predicted + z * z / (4 * predicted**2)
            )
            / (1 + z * z / predicted)
        )
        interval = [max(0.0, center - radius), min(1.0, center + radius)]
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "gold_support": support,
        "predicted_support": predicted,
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / denominator if denominator else None,
        "precision_wilson_95": interval,
        "insufficient_support": predicted < 20,
    }


def load_development_predictions(path: Path, allowed: set[str]) -> dict[str, list[ExtractionRow]]:
    """Read canonical G2A headers before decoding any prediction payload.

    Frozen G2A stores both partitions in one JSONL. Held-out payloads are skipped
    as opaque bytes, never decoded, exposed or scored. No source mappings needed.
    """
    if any(p.lower() in {"held_out", "held-out"} for p in (*path.parts, *path.resolve().parts)):
        raise ReviewError("held_out_prediction_path_forbidden")
    result: dict[str, list[ExtractionRow]] = {}
    with path.open("rb") as stream:
        for line in stream:
            prefix, separator, _ = line.partition(b',"predictions":')
            if not separator:
                raise ReviewError("canonical_prediction_header_required")
            header = json.loads(prefix + b"}")
            if set(header) != {"annotation_id", "partition"}:
                raise ReviewError("invalid_prediction_header")
            if header["partition"] == "held_out":
                continue
            if header["partition"] != "development" or header["annotation_id"] not in allowed:
                raise ReviewError("unexpected_development_prediction_identity")
            identity = header["annotation_id"]
            if identity in result:
                raise ReviewError("duplicate_prediction_packet")
            packet = json.loads(line)
            result[identity] = [
                ExtractionRow.model_validate_json(_json(row)) for row in packet["predictions"]
            ]
    return result


def prediction_variants(
    rows: list[ExtractionRow], variants: Any
) -> tuple[dict[str, Evidence], list[str]]:
    grouped: dict[str, list[ExtractionRow]] = {v.variant_id: [] for v in variants}
    for row in rows:
        matches = []
        for variant in variants:
            text = variant.narrative
            fingerprint = (
                hashlib.sha256(text.encode()).hexdigest() if text and text.strip() else None
            )
            status = (
                "missing_text"
                if text is None
                else "empty_text"
                if not text.strip()
                else "processed"
            )
            if row.narrative_sha256 == fingerprint and row.processing_status == status:
                matches.append(variant)
        if len(matches) != 1:
            raise ReviewError("ambiguous_prediction_variant_identity")
        variant = matches[0]
        text = variant.narrative or ""
        for mention in row.mentions:
            for span in (mention, *mention.assertion_cue_spans):
                if text[span.start : span.end] != span.evidence_text or span.end > len(text):
                    raise ReviewError("prediction_evidence_mismatch")
        for association in row.associations:
            if text[association.start : association.end] != association.evidence_text:
                raise ReviewError("prediction_association_evidence_mismatch")
        grouped[variant.variant_id].append(row)
    result = {}
    missing = []
    for variant in variants:
        values = grouped[variant.variant_id]
        if len(values) != variant.source_row_count:
            missing.append(variant.variant_id)
            continue
        if (
            len({r.event_id for r in values}) != len(values)
            or len({r.report_group_id for r in values}) != 1
        ):
            raise ReviewError("duplicate_or_conflicting_prediction_lineage")
        all_values = [
            evidence(r.component_mentions, r.symptom_mentions, r.associations) for r in values
        ]
        if any(v != all_values[0] for v in all_values[1:]):
            raise ReviewError("conflicting_duplicate_row_predictions")
        result[variant.variant_id] = all_values[0]
    return result, missing


def development_variant_evidence(
    packet: DevelopmentPacket | None, variants: Any
) -> tuple[dict[str, Evidence], list[str]]:
    values = {v.variant_id: v for v in packet.predictions} if packet else {}
    if packet and len(values) != len(packet.predictions):
        raise ReviewError("duplicate_development_variant")
    if set(values) - {v.variant_id for v in variants}:
        raise ReviewError("unexpected_development_variant")
    result, missing = {}, []
    for original in variants:
        v = values.get(original.variant_id)
        if v is None:
            missing.append(original.variant_id)
            continue
        if (
            v.narrative_sha256 != original.narrative_sha256
            or v.source_row_count != original.source_row_count
        ):
            raise ReviewError("development_variant_identity_mismatch")
        text = original.narrative or ""
        mentions: tuple[ComponentMention | SymptomMention, ...] = (
            *v.component_mentions,
            *v.symptom_mentions,
        )
        for mention in mentions:
            for span in (mention, *mention.assertion_cue_spans):
                if span.end > len(text) or text[span.start : span.end] != span.evidence_text:
                    raise ReviewError("development_prediction_offset_mismatch")
        for a in v.associations:
            if a.end > len(text) or text[a.start : a.end] != a.evidence_text:
                raise ReviewError("development_association_offset_mismatch")
        result[v.variant_id] = evidence(v.component_mentions, v.symptom_mentions, v.associations)
    return result, missing


def evaluate(
    source: Path,
    working: Path,
    predictions: Path,
    output: Path,
    *,
    generation_utc: datetime,
    prediction_provenance: Path | None = None,
) -> dict[str, Any]:
    source = source_path(source)
    working = working_path(working, source)
    originals = read_source(source)
    working_payload = working.read_bytes()
    document = parse_working(working_payload)
    # Validate every row, but demote incomplete completion claims only for eligibility.
    # No mutation of the in-memory submitted objects or saved human files occurs.
    validation_problems = []
    skipped: Counter[str] = Counter()
    incomplete: set[int] = set()
    eligible = []
    for i, report in enumerate(document.reports):
        if report.state not in {"annotated", "reviewed"}:
            skipped[report.state] += 1
            continue
        unit = report.annotation
        ids, completed, empty = (
            {v.variant_id for v in unit.variants},
            set(report.completed_variants),
            set(report.confirmed_empty_variants),
        )
        if (
            len(completed) != len(report.completed_variants)
            or len(empty) != len(report.confirmed_empty_variants)
            or not empty <= completed <= ids
            or unit.status != STATE_MAP[report.state]
            or any(
                v.variant_id in empty and (v.component_annotations or v.symptom_annotations)
                for v in unit.variants
            )
        ):
            raise ReviewError("invalid_review_completion_flags")
        if (
            completed != ids
            or not (unit.annotator_id or "").strip()
            or any(
                not v.component_annotations
                and not v.symptom_annotations
                and v.variant_id not in empty
                for v in unit.variants
            )
            or (
                report.state == "reviewed"
                and (not (unit.reviewer_id or "").strip() or unit.reviewer_id == unit.annotator_id)
            )
        ):
            skipped["incomplete_completion_claim"] += 1
            validation_problems.append({"position": i + 1, "error": "incomplete_completion_claim"})
            incomplete.add(i)
            continue
        eligible.append(report)
    # Incomplete claims are excluded rather than silently completed. Every other semantic
    # problem is fatal (offsets/source identities/references must never be repaired).
    sanitized = document.model_copy(
        update={
            "reports": tuple(
                r.model_copy(
                    update={
                        "state": "in_progress",
                        "annotation": r.annotation.model_copy(update={"status": "pending"}),
                        "completed_variants": (),
                        "confirmed_empty_variants": (),
                    }
                )
                if i in incomplete
                else r
                for i, r in enumerate(document.reports)
            )
        }
    )
    validate_working(source, sanitized)
    if generation_utc.tzinfo is None or generation_utc.utcoffset() != UTC.utcoffset(generation_utc):
        raise ReviewError("UTC_generation_timestamp_required")
    provenance = prediction_provenance or (
        predictions.parent / "provenance.json"
        if predictions.name == "development-predictions.jsonl"
        else predictions.parent.parent / "provenance.json"
    )
    for path in (predictions, provenance):
        if any(p.lower() in {"held_out", "held-out"} for p in (*path.parts, *path.resolve().parts)):
            raise ReviewError("held_out_input_forbidden")
    if (
        predictions.name not in {"predictions.jsonl", "development-predictions.jsonl"}
        or provenance.name != "provenance.json"
    ):
        raise ReviewError("frozen_prediction_file_required")
    frozen_payload = provenance.read_bytes()
    frozen = json.loads(frozen_payload)
    if not frozen.get("complete"):
        raise ReviewError("completed_prediction_provenance_required")
    variant_format = frozen.get("schema_version") == DEVELOPMENT_VERSION
    if variant_format:
        prediction_hash = frozen["prediction_sha256"]
        if (
            frozen.get("partition") != "development"
            or frozen.get("source_sha256") != _hash(source)
            or frozen.get("working_sha256") != hashlib.sha256(working_payload).hexdigest()
            or prediction_hash != _hash(predictions)
        ):
            raise ReviewError("development_prediction_provenance_mismatch")
    else:
        expected = {k.replace("\\", "/"): v for k, v in frozen["outputs"].items()}
        for path in (source, predictions):
            relative = path.resolve().relative_to(provenance.parent.resolve()).as_posix()
            if relative not in expected or _hash(path) != expected[relative]["sha256"]:
                raise ReviewError("frozen_input_checksum_mismatch")
        prediction_hash = expected[
            predictions.resolve().relative_to(provenance.parent.resolve()).as_posix()
        ]["sha256"]
    paths = (source, working, predictions, provenance)
    hashes = {
        str(source): document.source_sha256,
        str(working): hashlib.sha256(working_payload).hexdigest(),
        str(predictions): prediction_hash,
        str(provenance): hashlib.sha256(frozen_payload).hexdigest(),
    }
    resolved = output.resolve()
    root = Path(__file__).resolve().parents[3]
    if (
        resolved.is_relative_to(source.parent.parent)
        or any(p.lower() in {"held_out", "held-out", "private"} for p in resolved.parts)
        or any(resolved == p.resolve() or p.resolve().is_relative_to(resolved) for p in paths)
    ):
        raise ReviewError("separate_development_evaluation_directory_required")
    if resolved.is_relative_to(root) and not any(
        resolved.is_relative_to(root / p) for p in ("artifacts/nlp", "data/processed/nlp")
    ):
        raise ReviewError("ignored_nlp_output_required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("evaluation_output_exists")
    variant_packets: dict[str, DevelopmentPacket] = {}
    if variant_format:
        for line in predictions.read_bytes().splitlines():
            packet = DevelopmentPacket.model_validate_json(line)
            if packet.annotation_id in variant_packets or packet.annotation_id not in {
                u.annotation_id for u in originals
            }:
                raise ReviewError("invalid_development_packet_identity")
            variant_packets[packet.annotation_id] = packet
        if len(variant_packets) != frozen.get("report_count"):
            raise ReviewError("development_prediction_count_mismatch")
        packets = {}
    else:
        packets = load_development_predictions(predictions, {u.annotation_id for u in originals})
    per_kind: dict[str, Counter[str]] = {k: Counter() for k in ("component", "symptom")}
    per_category: dict[str, dict[str, Counter[str]]] = {
        "component": {
            c: Counter()
            for c in get_args(ComponentCode)
            if not c.endswith(("_unmapped", "_ambiguous"))
        },
        "symptom": {
            c: Counter()
            for c in get_args(SymptomCode)
            if not c.endswith(("_unmapped", "_ambiguous"))
        },
    }
    span_counts: dict[str, dict[str, Counter[str]]] = {
        mode: {kind: Counter() for kind in per_kind} for mode in ("exact", "overlap")
    }
    association_counts: dict[str, Counter[str]] = {mode: Counter() for mode in ("exact", "overlap")}
    confusion = {g: {p: 0 for p in ASSERTIONS} for g in ASSERTIONS}
    assertion_unmatched: Counter[str] = Counter()
    disagreements = []
    paired = []
    missing_reports = []
    negative_reports = 0

    def disagree(identity: str, variant: str | None, kind: str, **details: Any) -> None:
        disagreements.append(
            {"annotation_id": identity, "variant_id": variant, "type": kind, **details}
        )

    for report in eligible:
        unit = report.annotation
        identity = unit.annotation_id
        predicted, missing = (
            development_variant_evidence(variant_packets.get(identity), unit.variants)
            if variant_format
            else prediction_variants(packets.get(identity, []), unit.variants)
        )
        if missing:
            missing_reports.append(identity)
            for variant_id in missing:
                disagree(identity, variant_id, "missing_prediction")
            continue
        paired.append(identity)
        gold_variants = {
            v.variant_id: evidence(
                v.component_annotations, v.symptom_annotations, v.association_annotations
            )
            for v in unit.variants
        }
        if not any(v.mentions for v in gold_variants.values()):
            negative_reports += 1
        for kind in per_kind:
            gold_codes = {
                m.code
                for v in gold_variants.values()
                for m in v.mentions
                if m.kind == kind and m.assertion == "affirmed" and m.code in per_category[kind]
            }
            pred_codes = {
                m.code
                for v in predicted.values()
                for m in v.mentions
                if m.kind == kind and m.assertion == "affirmed" and m.code in per_category[kind]
            }
            for name, codes in (
                ("tp", gold_codes & pred_codes),
                ("fp", pred_codes - gold_codes),
                ("fn", gold_codes - pred_codes),
            ):
                per_kind[kind][name] += len(codes)
                for code in sorted(codes):
                    per_category[kind][code][name] += 1
                    if name != "tp":
                        disagree(identity, None, f"{kind}_{name}", code=code)
        for variant_id, gold in gold_variants.items():
            pred = predicted[variant_id]
            assertion_pairs = match(gold.mentions, pred.mentions, assertion=False)
            for g, p in assertion_pairs:
                gm, pm = gold.mentions[g], pred.mentions[p]
                confusion[gm.assertion][pm.assertion] += 1
                if gm.assertion != pm.assertion:
                    disagree(
                        identity,
                        variant_id,
                        "assertion_mismatch",
                        gold=asdict(gm),
                        prediction=asdict(pm),
                    )
            assertion_unmatched["gold"] += len(gold.mentions) - len(assertion_pairs)
            assertion_unmatched["prediction"] += len(pred.mentions) - len(assertion_pairs)
            for mode in span_counts:
                pairs = match(gold.mentions, pred.mentions, overlap=mode == "overlap")
                mapped = {p: g for g, p in pairs}
                for kind in per_kind:
                    tp = sum(gold.mentions[g].kind == kind for g, _ in pairs)
                    span_counts[mode][kind].update(
                        tp=tp,
                        fp=sum(m.kind == kind for m in pred.mentions) - tp,
                        fn=sum(m.kind == kind for m in gold.mentions) - tp,
                    )
                if mode == "exact":
                    for g in sorted(set(range(len(gold.mentions))) - {g for g, _ in pairs}):
                        disagree(
                            identity, variant_id, "exact_span_fn", gold=asdict(gold.mentions[g])
                        )
                    for p in sorted(set(range(len(pred.mentions))) - set(mapped)):
                        disagree(
                            identity,
                            variant_id,
                            "exact_span_fp",
                            prediction=asdict(pred.mentions[p]),
                        )
                correct = 0
                for c, s in sorted(pred.associations):
                    if c in mapped and s in mapped and (mapped[c], mapped[s]) in gold.associations:
                        correct += 1
                    elif mode == "exact":
                        disagree(identity, variant_id, "association_fp")
                association_counts[mode].update(
                    tp=correct,
                    fp=len(pred.associations) - correct,
                    fn=len(gold.associations) - correct,
                )
                if mode == "exact":
                    for _ in range(len(gold.associations) - correct):
                        disagree(identity, variant_id, "association_fn")

    def result(counts: Counter[str]) -> dict[str, Any]:
        return metrics(counts["tp"], counts["fp"], counts["fn"])

    aligned = sum(sum(row.values()) for row in confusion.values())
    correct_assertions = sum(confusion[s][s] for s in ASSERTIONS)
    aggregate = {
        "schema_version": VERSION,
        "interpretation": LABEL,
        "completed_eligible_reports": len(eligible),
        "evaluated_reports": len(paired),
        "missing_prediction_reports": len(missing_reports),
        "excluded_reports": dict(sorted(skipped.items())),
        "annotation_validation_problems": validation_problems,
        "empty_gold_reports_evaluated": negative_reports,
        "completed_state_counts": dict(Counter(r.state for r in eligible)),
        "primary_report_metrics": {k: result(v) for k, v in per_kind.items()},
        "per_category": {
            k: {code: result(c) for code, c in sorted(values.items())}
            for k, values in per_category.items()
        },
        "span_metrics": {
            mode: {k: result(c) for k, c in values.items()} for mode, values in span_counts.items()
        },
        "association_metrics": {mode: result(c) for mode, c in association_counts.items()},
        "assertions": {
            "aligned_exact_spans": aligned,
            "correct": correct_assertions,
            "accuracy": correct_assertions / aligned if aligned else None,
            "confusion_gold_rows_prediction_columns": confusion,
            "unmatched_gold": assertion_unmatched["gold"],
            "unmatched_predictions": assertion_unmatched["prediction"],
        },
        "disagreement_types": dict(sorted(Counter(d["type"] for d in disagreements).items())),
        "limitations": [
            "Named affirmed report labels are primary; spans include all codes and assertions.",
            "Missing prediction coverage excludes the report from paired metrics, not ordinary FN.",
            "Assertion accuracy uses exact kind/code/spans; unmatched labels are separate.",
            "Wilson intervals do not account for label/report dependence or selection bias.",
            "Under 20 category predictions is insufficient support; no target attainment claim.",
            "Source rows collapse within variants; report labels collapse across variants.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="evaluation-stage-", dir=output.parent) as temp:
        stage = Path(temp) / "run"
        stage.mkdir()
        (stage / "aggregate.json").write_bytes(_json(aggregate))
        (stage / "development-disagreements.jsonl").write_bytes(
            b"".join(_json(d) for d in sorted(disagreements, key=lambda d: _json(d)))
        )
        if any(_hash(Path(p)) != digest for p, digest in hashes.items()):
            raise ReviewError("evaluation_input_changed")
        revision, dirty = _git_identity()
        marker = {
            "schema_version": VERSION,
            "complete": True,
            "generation_utc": generation_utc.isoformat().replace("+00:00", "Z"),
            "input_sha256": hashes,
            "working_revision": document.revision,
            "source_prediction_identity": {
                k: v
                for k, v in frozen.get("source_prediction_provenance", {}).items()
                if k.endswith(("_version", "_sha256")) or k in {"milestone", "configuration"}
            },
            "code_sha256": _code_hash(),
            "code_revision": revision,
            "dirty_worktree": dirty,
            "outputs": {
                p.name: {"sha256": _hash(p), "bytes": p.stat().st_size}
                for p in sorted(stage.iterdir())
            },
            "matching_policy": "max cardinality, max rational total IoU, lexical pair ties",
        }
        (stage / "provenance.json").write_bytes(_json(marker))
        if output.exists():
            raise FileExistsError("evaluation_output_exists")
        os.rename(stage, output)
    return aggregate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preliminary development-only annotation evaluation"
    )
    for name in ("source", "working", "predictions", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prediction-provenance", type=Path)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        report = evaluate(
            args.source,
            args.working,
            args.predictions,
            args.output_dir,
            generation_utc=args.generation_utc,
            prediction_provenance=args.prediction_provenance,
        )
    except ReviewError as error:
        print(f"Evaluation stopped: {error}; no run published.")
        return 1
    except (ValueError, OSError, KeyError, TypeError):
        print(
            "Evaluation stopped: input validation, provenance or destination check failed; "
            "no run published."
        )
        return 1
    print(LABEL)
    print(
        f"Eligible completed reports: {report['completed_eligible_reports']}; "
        f"evaluated: {report['evaluated_reports']}"
    )
    print(_json(report["primary_report_metrics"]).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
