"""Prepare a bounded, blinded development challenge; never evaluate or tune rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from howreliable.nlp.annotation_review import ReviewError, ReviewStore, read_source
from howreliable.nlp.annotations import AnnotationUnit, Variant, identity_row, rank
from howreliable.nlp.context import extract_report
from howreliable.nlp.development_predictions import DevelopmentPacket, DevelopmentVariant
from howreliable.nlp.grouping import MEMBERSHIP_VERSION, validate_partition_assignments
from howreliable.nlp.owner_reports import _hash, _json

VERSION = "howreliable-development-challenge-1.1"
SEED = "howreliable-phase8a-g2c2-challenge-20261102-v2"
RULE_FILES = ("components.py", "context.py", "schemas.py", "symptoms.py")
# Frozen selection proxies, not semantic labels. No extraction result guides selection.
SCREENS = {
    "negation": r"\b(?:no|not|without|never|denied|denies)\b|"
    r"\b(?:did|does|was|is|were|are|do)n['\u2019]?t\b",
    "uncertainty": r"\b(?:suspect\w*|possibly|possible|might|may)\b",
    "hypothetical": r"\bif\b|\bcould (?:have|cause|result)\b|\bwould\b",
    "nonvehicle_objects": r"\b(?:garage|house|building|apartment)\s+(?:door|window)\b|"
    r"\bgarage\b[^.!?\n]{0,45}\bdoor\b",
    "app_remote": r"\b(?:app|application|smartphone|remote\s+(?:start|command|control))\b",
    "warning_status": r"\b(?:warning|indicator|dashboard|dash|hold)\b",
    "auto_stop_restart": r"\b(?:auto(?:matic)?[\s/-]*(?:stop|start)|"
    r"start/stop|stop/start|restart)\b",
    "braking_steering": r"\b(?:brak\w*|steer\w*|column lock)\b",
    "ordinary": r"\b(?:engine|brakes?|steering|transmission|battery)\b[\s\S]*"
    r"\b(?:stall\w*|leak\w*|smoke|noise|vibrat\w*|fail\w*)\b",
}
QUOTAS = {name: 4 if name == "ordinary" else 2 for name in SCREENS}
ORDER = (
    "nonvehicle_objects",
    "app_remote",
    "auto_stop_restart",
    "negation",
    "uncertainty",
    "hypothetical",
    "warning_status",
    "braking_steering",
    "ordinary",
)


def rule_hashes() -> dict[str, str]:
    return {name: _hash(Path(__file__).with_name(name)) for name in RULE_FILES}


def tags(rows: list[dict[str, Any]]) -> set[str]:
    # Keep row/variant boundaries: words in separate narratives cannot form one screen.
    return {
        name
        for name, pattern in SCREENS.items()
        if any(re.search(pattern, r["narrative"] or "", re.I) for r in rows)
    }


def prepare(
    sample: Path,
    reserved_manifest: Path,
    index: Path,
    output: Path,
    *,
    generation_utc: datetime,
    seed: str = SEED,
    max_rows: int = 1000,
) -> dict[str, Any]:
    if (
        not seed.strip()
        or generation_utc.tzinfo is None
        or generation_utc.utcoffset() != UTC.utcoffset(generation_utc)
    ):
        raise ReviewError("seed_and_UTC_timestamp_required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("challenge_destination_exists")
    resolved = output.resolve()
    root = Path(__file__).resolve().parents[3]
    if resolved.is_relative_to(reserved_manifest.parent.resolve()) or any(
        p.lower() in {"held_out", "held-out", "private"} for p in resolved.parts
    ):
        raise ReviewError("separate_development_challenge_required")
    if resolved.is_relative_to(root) and not any(
        resolved.is_relative_to(root / p) for p in ("artifacts/nlp", "data/processed/nlp")
    ):
        raise ReviewError("ignored_nlp_directory_required")
    sample_meta = sample.with_suffix(sample.suffix + ".provenance.json")
    membership_meta = reserved_manifest.parent / "provenance.json"
    inputs = (sample, sample_meta, reserved_manifest, index, membership_meta)
    if any(p.resolve().is_relative_to(resolved) for p in inputs):
        raise ReviewError("challenge_destination_contains_input")
    metadata = json.loads(sample_meta.read_bytes())
    if not 0 < metadata["cleaned_count"] <= max_rows:
        raise ReviewError("bounded_sample_required_not_full_corpus")
    hashes = {str(p): _hash(p) for p in inputs}
    if hashes[str(sample)] != metadata["sample_sha256"]:
        raise ReviewError("sample_checksum_mismatch")
    completed = json.loads(membership_meta.read_bytes())
    if not completed.get("complete"):
        raise ReviewError("completed_membership_provenance_required")
    for path in (reserved_manifest, index):
        key = path.resolve().relative_to(membership_meta.parent.resolve()).as_posix()
        expected = {k.replace("\\", "/"): v for k, v in completed["outputs"].items()}
        if hashes[str(path)] != expected[key]["sha256"]:
            raise ReviewError("membership_checksum_mismatch")
    corpus_hashes = [
        v for k, v in completed["inputs_sha256"].items() if Path(k).name == "complaints-clean.jsonl"
    ]
    if metadata["source_clean_sha256"] not in corpus_hashes:
        raise ReviewError("sample_membership_snapshot_mismatch")
    reserved = json.loads(reserved_manifest.read_bytes())
    barred: dict[str, str] = {}
    for item in reserved["memberships"]:
        group = item["evaluation_group_id"]
        if group in barred and barred[group] != item["partition"]:
            raise ReviewError("existing_partition_leakage")
        barred[group] = item["partition"]
    frozen = rule_hashes()  # Freeze before inspecting any candidate narrative.
    freeze_id = hashlib.sha256(_json(frozen)).hexdigest()
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups: dict[str, str] = {}
    excluded: Counter[str] = Counter()
    scanned = 0
    with closing(sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("SELECT value FROM index_metadata WHERE key='schema_version'").fetchone() != (
            MEMBERSHIP_VERSION,
        ):
            raise ReviewError("unsupported_membership_schema")
        with sample.open("rb") as handle:
            for scanned, line in enumerate(handle, 1):
                if scanned > max_rows:
                    raise ReviewError("sample_limit_exceeded")
                # Route by source ID before decoding narratives; barred records are opaque.
                event = re.search(rb'"event_id"\s*:\s*"([^"\\]+)"', line)
                if event is None:
                    raise ReviewError("simple_source_event_id_required")
                found = db.execute(
                    "SELECT e.report_id,g.evaluation_group_id,e.fallback FROM events e "
                    "JOIN report_groups g ON e.report_id=g.id WHERE e.id=?",
                    (event[1].decode(),),
                ).fetchone()
                if found is None:
                    raise ReviewError("sample_event_missing_from_index")
                group, evaluation, fallback = found
                if evaluation in barred:
                    excluded["reserved_source_rows"] += 1
                    continue
                if fallback:
                    excluded["missing_odi_source_rows"] += 1
                    continue
                clean = json.loads(line)
                row = identity_row(clean)
                indexed = db.execute(
                    "SELECT text_sha256,report_date,occurrence_date FROM events WHERE id=?",
                    (row.event_id,),
                ).fetchone()
                if row.report_group_id != group or indexed != (
                    row.narrative_sha256,
                    row.report_date.isoformat() if row.report_date else None,
                    row.occurrence_date.isoformat() if row.occurrence_date else None,
                ):
                    raise ReviewError("sample_lineage_mismatch")
                groups[group] = evaluation
                candidates[group].append(clean)
        if scanned != metadata["cleaned_count"]:
            raise ReviewError("bounded_sample_count_mismatch")
        for group in list(candidates):
            rows = candidates[group]
            if len({r["event_id"] for r in rows}) != len(rows):
                raise ReviewError("duplicate_source_row")
            all_ids = {
                r[0] for r in db.execute("SELECT id FROM events WHERE report_id=?", (group,))
            }
            reason = None
            if all_ids != {r["event_id"] for r in rows}:
                reason = "incomplete_report_groups"
            elif (
                db.execute(
                    "SELECT count(*) FROM report_groups WHERE evaluation_group_id=?",
                    (groups[group],),
                ).fetchone()[0]
                != 1
            ):
                reason = "multi_report_evaluation_groups"
            elif not any((r["narrative"] or "").strip() for r in rows):
                reason = "uninspectable_reports"
            if reason:
                excluded[reason] += 1
                del candidates[group]
    screening = {g: tags(rows) for g, rows in candidates.items()}
    selected: list[str] = []
    allocation: dict[str, str] = {}
    unmet = {}
    for stratum in ORDER:
        quota = QUOTAS[stratum]
        available = sorted(
            (g for g in candidates if g not in allocation and stratum in screening[g]),
            key=lambda g: (rank(seed, stratum, g), g),
        )
        for group in available[:quota]:
            selected.append(group)
            allocation[group] = stratum
        if len(available) < quota:
            unmet[stratum] = quota - len(available)
    remaining = sorted(
        (g for g in candidates if g not in allocation),
        key=lambda g: (rank(seed, "background_fill", g), g),
    )
    if len(selected) + len(remaining) < 20:
        raise ReviewError("insufficient_fresh_reports")
    for group in remaining[: 20 - len(selected)]:
        selected.append(group)
        allocation[group] = "background_fill"
    selected.sort(key=lambda g: (rank(seed, "display_order", g), g))
    coverage = Counter(t for g in selected for t in screening[g])
    if set(SCREENS) - set(coverage):
        raise ReviewError("challenge_mixture_incomplete")
    assignments = {
        row["event_id"]: "challenge_development" for g in selected for row in candidates[g]
    }
    validate_partition_assignments(index, assignments)
    if any(groups[g] in barred for g in selected) or len({groups[g] for g in selected}) != 20:
        raise ReviewError("challenge_duplicate_isolation_failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="challenge-stage-", dir=output.parent) as temp:
        stage = Path(temp) / "run"
        (stage / "frozen/development").mkdir(parents=True)
        (stage / "private/rules").mkdir(parents=True)
        for name in RULE_FILES:
            (stage / "private/rules" / name).write_bytes(
                Path(__file__).with_name(name).read_bytes()
            )
        units, predictions, mappings = [], [], []
        for group in selected:
            annotation_id = "challenge_" + rank(seed, "annotation", group)
            variant_rows: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
            for clean_row in candidates[group]:
                variant_rows[clean_row["narrative"]].append(clean_row)
            variants, pv = [], []
            for number, (text, rows) in enumerate(variant_rows.items(), 1):
                variant_id = f"v{number}"
                digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else None
                variants.append(
                    Variant(
                        variant_id=variant_id,
                        narrative=text,
                        narrative_sha256=digest,
                        source_row_count=len(rows),
                        report_dates=tuple(
                            sorted({r["report_date"] for r in rows}, key=lambda d: d or "")
                        ),
                        occurrence_dates=tuple(
                            sorted({r["occurrence_date"] for r in rows}, key=lambda d: d or "")
                        ),
                    )
                )
                c, s, a = extract_report(text) if text and text.strip() else ((), (), ())
                pv.append(
                    DevelopmentVariant(
                        variant_id=variant_id,
                        narrative_sha256=digest,
                        source_row_count=len(rows),
                        component_mentions=c,
                        symptom_mentions=s,
                        associations=a,
                    )
                )
            units.append(
                AnnotationUnit(
                    annotation_id=annotation_id, partition="development", variants=tuple(variants)
                )
            )
            predictions.append(
                DevelopmentPacket(annotation_id=annotation_id, predictions=tuple(pv))
            )
            mappings.append(
                {
                    "annotation_id": annotation_id,
                    "report_group_id": group,
                    "evaluation_group_id": groups[group],
                    "sampling_stratum": allocation[group],
                    "sampling_tags": sorted(screening[group]),
                    "source_records": candidates[group],
                }
            )
        worksheet = stage / "frozen/development/worksheet.jsonl"
        worksheet.write_bytes(b"".join(_json(u.model_dump(mode="json")) for u in units))
        (stage / "frozen/worksheet-schema.json").write_bytes(
            _json(AnnotationUnit.model_json_schema())
        )
        (stage / "private/development-predictions.jsonl").write_bytes(
            b"".join(_json(p.model_dump(mode="json")) for p in predictions)
        )
        (stage / "private/mapping.jsonl").write_bytes(b"".join(_json(m) for m in mappings))
        report = {
            "schema_version": VERSION,
            "seed": seed,
            "generation_utc": generation_utc.isoformat().replace("+00:00", "Z"),
            "report_count": 20,
            "source_row_count": len(assignments),
            "bounded_sample_rows": scanned,
            "fresh_candidate_reports": len(candidates),
            "excluded": dict(sorted(excluded.items())),
            "quotas": QUOTAS,
            "allocated": dict(Counter(allocation.values())),
            "unmet_quotas": unmet,
            "overlapping_coverage": dict(Counter(t for g in selected for t in screening[g])),
            "screening_patterns": SCREENS,
            "reserved_partition_counts": reserved["partition_counts"],
            "selection_order": ORDER,
            "duplicate_isolation": "Outside reserved evaluation groups; complete singletons.",
            "rule_bundle_sha256": freeze_id,
            "rule_file_sha256": frozen,
            "python_version": platform.python_version(),
            "memberships": [
                {"annotation_id": u.annotation_id, "evaluation_group_id": groups[g]}
                for u, g in zip(units, selected, strict=True)
            ],
            "limitations": [
                "Two-stage G1 pool; not population sampling; prior machine benchmark exposure.",
                "Text screens are proxies, not gold labels or guaranteed semantic coverage.",
                "Multi-report global duplicate groups are excluded rather than split.",
                "No annotation/evaluation. Future evaluation must accept source-bound challenge "
                "provenance; do not regenerate after gold is filled.",
            ],
        }
        (stage / "private/sampling-manifest.json").write_bytes(_json(report))
        read_source(worksheet)
        store = ReviewStore(worksheet, stage / "annotation-work/development-review.json")
        blank = store.read()
        assert len(blank.reports) == 20 and all(r.state == "pending" for r in blank.reports)
        if rule_hashes() != frozen or any(_hash(Path(p)) != h for p, h in hashes.items()):
            raise ReviewError("challenge_inputs_or_rules_changed")
        provenance = {
            "schema_version": VERSION,
            "complete": True,
            "generation_utc": report["generation_utc"],
            "input_sha256": hashes,
            "rule_bundle_sha256": freeze_id,
            "rule_file_sha256": frozen,
            "outputs": {
                str(p.relative_to(stage)).replace("\\", "/"): {
                    "sha256": _hash(p),
                    "bytes": p.stat().st_size,
                }
                for p in sorted(stage.rglob("*"))
                if p.is_file()
            },
        }
        (stage / "provenance.json").write_bytes(_json(provenance))
        if output.exists():
            raise FileExistsError("challenge_destination_exists")
        os.rename(stage, output)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare 20 fresh blinded development challenge reports"
    )
    for name in ("sample", "reserved-manifest", "membership", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--seed", default=SEED)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare(
            args.sample,
            args.reserved_manifest,
            args.membership,
            args.output_dir,
            generation_utc=args.generation_utc,
            seed=args.seed,
        )
    except (ValueError, OSError, KeyError, sqlite3.Error):
        print(
            "Challenge preparation stopped: validation, quota or destination error; "
            "no run published."
        )
        return 1
    print(f"Prepared {result['report_count']} blank challenge reports; no evaluation performed.")
    print("Selection bucket counts:", result["allocated"], "Unmet quotas:", result["unmet_quotas"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
