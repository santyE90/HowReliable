"""Prepare blinded, empty annotation worksheets; never extract or score predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import Field

from howreliable.data.features.nhtsa_complaints import iter_clean_records
from howreliable.nlp.grouping import (
    add_membership,
    create_memberships,
    finalize_memberships,
    validate_partition_assignments,
)
from howreliable.nlp.owner_reports import _code_hash, _git_identity, _hash, _json
from howreliable.nlp.schemas import (
    Association,
    ComponentMention,
    ExtractionRow,
    RunProvenance,
    StrictModel,
    SymptomMention,
)

VERSION: Final = "howreliable-owner-report-annotation-preparation-1.0"
SEED = "howreliable-phase8a-g2a-20261027-v1"
QUOTAS = {
    "rare": 15,
    "negated": 10,
    "uncertain": 5,
    "multiple_components": 10,
    "no_mentions": 10,
    "context": 10,
    "quality": 10,
    "common": 10,
    "background": 20,
}


class Variant(StrictModel):
    variant_id: str
    narrative: str | None
    narrative_sha256: str | None
    source_row_count: int = Field(gt=0)
    report_dates: tuple[str | None, ...]
    occurrence_dates: tuple[str | None, ...]
    component_annotations: tuple[ComponentMention, ...] = ()
    symptom_annotations: tuple[SymptomMention, ...] = ()
    association_annotations: tuple[Association, ...] = ()


class AnnotationUnit(StrictModel):
    schema_version: Literal["howreliable-owner-report-annotation-preparation-1.0"] = VERSION
    annotation_id: str
    partition: Literal["development", "held_out"]
    variants: tuple[Variant, ...]
    status: Literal["pending", "annotated", "reviewed", "disputed", "adjudicated"] = "pending"
    annotator_id: str | None = None
    reviewer_id: str | None = None
    adjudicator_id: str | None = None
    review_notes: str | None = None


def identity_row(clean: dict[str, Any]) -> ExtractionRow:
    """Membership-only adapter: no lexicon or extraction function is called."""
    ref = clean["source_reference_id"]
    fallback = ref is None or not ref.strip()
    key = [
        clean["source_type"],
        "CMPLID" if fallback else "ODINO",
        clean["source_record_id"] if fallback else ref,
    ]
    text = clean["narrative"]
    return ExtractionRow(
        schema_version="howreliable-owner-report-extraction-1.2",
        **{
            k: clean[k]
            for k in (
                "event_id",
                "source_type",
                "source_record_id",
                "source_reference_id",
                "broad_vehicle_id",
                "known_configuration_id",
                "normalized_make",
                "normalized_model",
                "model_year",
                "source_component",
            )
        },
        report_group_id="report_" + hashlib.sha256(_json(key)).hexdigest(),
        report_group_fallback=fallback,
        narrative_sha256=hashlib.sha256(text.encode()).hexdigest()
        if text and text.strip()
        else None,
        report_date=date.fromisoformat(clean["report_date"]) if clean["report_date"] else None,
        occurrence_date=date.fromisoformat(clean["occurrence_date"])
        if clean["occurrence_date"]
        else None,
        mode="full_corpus",
        cutoff=None,
        processing_status="missing_text"
        if text is None
        else "empty_text"
        if not text.strip()
        else "processed",
        quality_flags=tuple(clean["quality_flags"]),
        structured_component=clean["component"],
    )


def rank(seed: str, *parts: str) -> str:
    return hashlib.sha256(_json([seed, *parts])).hexdigest()


def prepare_annotations(
    corpus: Path,
    predictions: Path,
    destination: Path,
    *,
    seed: str = SEED,
    generation_utc: datetime,
) -> dict[str, Any]:
    """Use a verified bounded candidate pool; globally index identities without NLP."""
    if not seed.strip() or generation_utc.utcoffset() != UTC.utcoffset(generation_utc):
        raise ValueError("nonempty seed and UTC timestamp required")
    root = Path(__file__).resolve().parents[3]
    target = destination.resolve()
    if target.is_relative_to(root) and not any(
        target.is_relative_to(root / p) for p in ("artifacts/nlp", "data/processed/nlp")
    ):
        raise ValueError("annotation artifacts must stay in ignored NLP directories")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("refusing to overwrite annotation run")
    source_meta = corpus.with_suffix(corpus.suffix + ".provenance.json")
    pred_meta = predictions.with_suffix(predictions.suffix + ".provenance.json")
    pred_index = predictions.with_suffix(predictions.suffix + ".membership.sqlite")
    meta = RunProvenance.model_validate_json(pred_meta.read_bytes())
    hashes = {str(p): _hash(p) for p in (corpus, source_meta, predictions, pred_meta, pred_index)}
    if meta.milestone != "E" or meta.configuration.mode != "full_corpus":
        raise ValueError("candidate pool must be a completed full-corpus-mode E extraction")
    if (
        hashes[str(predictions)] != meta.output_sha256
        or hashes[str(pred_index)] != meta.membership_sha256
    ):
        raise ValueError("candidate extraction/index checksum mismatch")
    if hashes[str(corpus)] not in (
        meta.input_sha256,
        meta.source_cleaning_provenance.get("source_clean_sha256"),
    ):
        raise ValueError("candidate pool does not identify this source corpus")
    pool: dict[str, list[ExtractionRow]] = defaultdict(list)
    for line in predictions.read_bytes().splitlines():
        row = ExtractionRow.model_validate_json(line)
        pool[row.report_group_id].append(row)
    if sum(map(len, pool.values())) != meta.output_record_count:
        raise ValueError("candidate pool count mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="annotation-stage-", dir=destination.parent) as tmp:
        stage = Path(tmp) / "run"
        stage.mkdir()
        index = stage / "private" / "global-membership.sqlite"
        index.parent.mkdir()
        originals: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with closing(sqlite3.connect(index)) as db:
            db.execute("PRAGMA cache_size=-8192")
            db.execute("CREATE TABLE events(id TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE reports(id TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE texts(id TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE variants(report TEXT,text TEXT,PRIMARY KEY(report,text))")
            create_memberships(db)
            count = 0
            for count, clean in enumerate(iter_clean_records(corpus), 1):
                identity = identity_row(clean)
                group = identity.report_group_id
                db.execute("INSERT INTO events(id) VALUES (?)", (identity.event_id,))
                db.execute("INSERT OR IGNORE INTO reports VALUES (?)", (group,))
                if identity.narrative_sha256:
                    db.execute(
                        "INSERT OR IGNORE INTO texts VALUES (?)", (identity.narrative_sha256,)
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO variants VALUES (?,?)",
                        (group, identity.narrative_sha256),
                    )
                add_membership(db, identity, count)
                if group in pool:
                    originals[group].append(clean)
            if count != json.loads(source_meta.read_bytes())["cleaned_count"]:
                raise ValueError("source provenance count mismatch")
            finalize_memberships(db)
            db.execute("CREATE INDEX evaluation_groups ON report_groups(evaluation_group_id)")
            db.commit()
            excluded: Counter[str] = Counter()
            eligible: dict[str, str] = {}
            for group, values in sorted(pool.items()):
                clean_values = originals[group]
                if {x.event_id for x in values} != {x["event_id"] for x in clean_values}:
                    excluded["incomplete_report_in_candidate_pool"] += 1
                    continue
                clean_by_event = {x["event_id"]: x for x in clean_values}
                for value in values:
                    original = identity_row(clean_by_event[value.event_id])
                    if (value.narrative_sha256, value.report_date, value.occurrence_date) != (
                        original.narrative_sha256,
                        original.report_date,
                        original.occurrence_date,
                    ):
                        raise ValueError("candidate lineage differs from corpus")
                if any(x.report_group_fallback for x in values):
                    excluded["missing_odi"] += 1
                    continue
                if not any(x.narrative_sha256 for x in values):
                    excluded["no_inspectable_narrative"] += 1
                    continue
                evaluation = str(
                    db.execute(
                        "SELECT evaluation_group_id FROM report_groups WHERE id=?", (group,)
                    ).fetchone()[0]
                )
                size = db.execute(
                    "SELECT count(*) FROM report_groups WHERE evaluation_group_id=?", (evaluation,)
                ).fetchone()[0]
                if size != 1:
                    excluded["multi_report_evaluation_group"] += 1
                    continue
                eligible[group] = evaluation
        support: Counter[str] = Counter()
        codes: dict[str, set[str]] = {}
        for group in eligible:
            codes[group] = {m.code for row in pool[group] for m in row.mentions}
            support.update(codes[group])
        tags: dict[str, set[str]] = {}
        for group in eligible:
            rows = pool[group]
            mentions = [m for row in rows for m in row.mentions]
            flags = {flag for row in rows for flag in row.quality_flags}
            labels = {"background"}
            if any(support[c] <= 15 for c in codes[group]):
                labels.add("rare")
            if any(support[c] >= 50 for c in codes[group]):
                labels.add("common")
            labels.update(
                s for s in ("negated", "uncertain") if any(m.assertion == s for m in mentions)
            )
            if len({m.code for row in rows for m in row.component_mentions}) >= 2:
                labels.add("multiple_components")
            if not mentions:
                labels.add("no_mentions")
            if any(m.assertion == "unresolved" or m.code.endswith("_ambiguous") for m in mentions):
                labels.add("context")
            if flags & {"encoding_control_character", "short_narrative", "oversized_narrative"}:
                labels.add("quality")
            tags[group] = labels
        selected: dict[str, str] = {}
        allocations: dict[str, Counter[str]] = {}
        unmet: dict[str, dict[str, int]] = {}
        primary: dict[str, str] = {}
        # Interleave partitions per stratum to avoid giving one partition first access
        # to every rare bucket. Quotas are selection buckets, not gold label quotas.
        partitions = ("development", "held_out")
        allocations = {p: Counter() for p in partitions}
        for stratum, quota in QUOTAS.items():
            for partition in partitions:
                available = sorted(
                    (g for g in eligible if g not in selected and stratum in tags[g]),
                    key=lambda g: (rank(seed, partition, stratum, g), g),
                )
                for group in available[:quota]:
                    selected[group] = partition
                    primary[group] = stratum
                    allocations[partition][stratum] += 1
        for partition in partitions:
            unmet[partition] = {
                s: q - allocations[partition][s]
                for s, q in QUOTAS.items()
                if allocations[partition][s] < q
            }
            deficit = 100 - sum(p == partition for p in selected.values())
            rest = sorted(
                (g for g in eligible if g not in selected),
                key=lambda g: (rank(seed, partition, "fill", g), g),
            )
            if len(rest) < deficit:
                raise ValueError("insufficient eligible complete ODI reports for 100/100")
            for group in rest[:deficit]:
                selected[group] = partition
                primary[group] = "background_fill"
                allocations[partition]["background_fill"] += 1
        assignments = {
            row["event_id"]: partition
            for group, partition in selected.items()
            for row in originals[group]
        }
        validate_partition_assignments(index, assignments)
        manifest_rows = []
        private_rows = []
        prediction_rows = []
        for group in sorted(selected, key=lambda g: (selected[g], rank(seed, "id", g))):
            partition = selected[group]
            annotation = "ann_" + rank(seed, "annotation", group)
            variants: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
            for clean in originals[group]:
                variants[clean["narrative"]].append(clean)
            worksheets = []
            for number, (text, clean_rows) in enumerate(variants.items(), 1):
                worksheets.append(
                    Variant(
                        variant_id=f"v{number}",
                        narrative=text,
                        narrative_sha256=hashlib.sha256(text.encode()).hexdigest()
                        if text is not None
                        else None,
                        source_row_count=len(clean_rows),
                        report_dates=tuple(
                            sorted({r["report_date"] for r in clean_rows}, key=lambda x: x or "")
                        ),
                        occurrence_dates=tuple(
                            sorted(
                                {r["occurrence_date"] for r in clean_rows}, key=lambda x: x or ""
                            )
                        ),
                    )
                )
            unit = AnnotationUnit(
                annotation_id=annotation,
                partition=cast(Literal["development", "held_out"], partition),
                variants=tuple(worksheets),
            )
            folder = stage / partition
            folder.mkdir(exist_ok=True)
            with (folder / "worksheet.jsonl").open("ab") as handle:
                handle.write(_json(unit.model_dump(mode="json")))
            manifest_rows.append(
                {
                    "annotation_id": annotation,
                    "partition": partition,
                    "evaluation_group_id": eligible[group],
                    "source_row_count": len(originals[group]),
                }
            )
            private_rows.append(
                {
                    "annotation_id": annotation,
                    "report_group_id": group,
                    "source_records": originals[group],
                }
            )
            prediction_rows.append(
                {
                    "annotation_id": annotation,
                    "partition": partition,
                    "selection_stratum": primary[group],
                    "sampling_tags": sorted(tags[group]),
                    "predictions": [r.model_dump(mode="json") for r in pool[group]],
                }
            )
        for name, rows_to_write in (
            ("mapping.jsonl", private_rows),
            ("predictions.jsonl", prediction_rows),
        ):
            (stage / "private" / name).write_bytes(b"".join(_json(r) for r in rows_to_write))
        manifest = {
            "schema_version": VERSION,
            "seed": seed,
            "generation_utc": generation_utc.isoformat().replace("+00:00", "Z"),
            "partition_counts": dict(Counter(selected.values())),
            "memberships": manifest_rows,
            "quotas_per_partition": QUOTAS,
            "allocations": allocations,
            "unmet_quotas": unmet,
            "candidate_reports": len(pool),
            "eligible_candidate_reports": len(eligible),
            "excluded_candidate_reports": dict(excluded),
            "pool_category_support": dict(sorted(support.items())),
            "coverage": {
                p: dict(Counter(t for g in selected if selected[g] == p for t in tags[g]))
                for p in partitions
            },
            "policy": "Two-stage candidate pool; seeded SHA256 ranking in overlapping "
            "strata; complete ODI reports; exclude globally multi-report evaluation groups. "
            "Fixed quotas precede labels; unmet slots filled from remaining background. "
            "Inclusion probabilities not analytically derived; no population estimates.",
            "held_out_frozen": True,
            "custodian_assigned": False,
            "prior_exposure": "G1 predictions and aggregate diagnostics; no human gold labels. "
            "Custodian must confirm no prior narrative-based rule tuning.",
        }
        (stage / "worksheet-schema.json").write_bytes(_json(AnnotationUnit.model_json_schema()))
        (stage / "partition-manifest.json").write_bytes(_json(manifest))
        if any(_hash(Path(p)) != digest for p, digest in hashes.items()):
            raise ValueError("sampling source changed during run")
        revision, dirty = _git_identity()
        completion = {
            "schema_version": VERSION,
            "complete": True,
            "generation_utc": manifest["generation_utc"],
            "seed": seed,
            "inputs_sha256": hashes,
            "code_sha256": _code_hash(),
            "code_revision": revision,
            "dirty_worktree": dirty,
            "source_prediction_provenance": meta.model_dump(mode="json"),
            "outputs": {
                str(p.relative_to(stage)): {"sha256": _hash(p), "bytes": p.stat().st_size}
                for p in sorted(stage.rglob("*"))
                if p.is_file()
            },
        }
        (stage / "provenance.json").write_bytes(_json(completion))
        if destination.exists():
            raise FileExistsError("annotation destination appeared during generation")
        os.rename(stage, destination)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare blinded annotation materials, without scoring"
    )
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", default=SEED)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        result = prepare_annotations(
            args.corpus,
            args.predictions,
            args.output_dir,
            seed=args.seed,
            generation_utc=args.generation_utc,
        )
    except (ValueError, OSError, sqlite3.Error) as error:
        # Validation exceptions can embed narrative text; never print their payloads.
        parser.exit(
            2, f"Annotation preparation failed ({type(error).__name__}); no run published.\n"
        )
    print("Annotation preparation complete; partition counts=" + str(result["partition_counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
