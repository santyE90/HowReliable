"""Explicit bounded P4B experiment; never invoked by the API or application startup."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from howreliable.data.features.nhtsa_complaints import iter_clean_records
from howreliable.demo.index import DEFAULT_INDEX, HistoricalIndex, connect_readonly, report_key
from howreliable.domain.reliability import VehicleAssociation
from howreliable.nlp.owner_reports import _code_hash, _hash, _json, process_owner_reports
from howreliable.nlp.schemas import ExtractionRow
from howreliable.nlp.summaries import summarize_reports

COHORTS = (("bmw", "335i", 2011), ("toyota", "corolla", 2011))
VERSION = "howreliable-vehicle-symptom-review-1.0"


def review_records(rows: list[dict[str, Any]], extraction: Path) -> list[dict[str, Any]]:
    """Keep variants and source lineage, validating every emitted span and reference."""
    packets = [
        ExtractionRow.model_validate_json(line) for line in extraction.read_bytes().splitlines()
    ]
    if len(packets) != len(rows):
        raise ValueError("review record conservation failed")
    reports: dict[str, dict[str, Any]] = {}
    for clean, packet in zip(rows, packets, strict=True):
        if not clean["source_record_id"].strip() or not clean["event_id"].strip():
            raise ValueError("missing source identity")
        if packet.report_group_id != report_key(clean)[0] or packet.event_id != clean["event_id"]:
            raise ValueError("extraction lineage mismatch")
        text = clean["narrative"] or ""
        mentions = {m.mention_id: m for m in packet.mentions}
        if len(mentions) != len(packet.mentions):
            raise ValueError("duplicate mention identity")
        for span in (
            *packet.mentions,
            *packet.associations,
            *(s for m in packet.mentions for s in m.assertion_cue_spans),
        ):
            if text[span.start : span.end] != span.evidence_text:
                raise ValueError("invalid original-text evidence offset")
        for link in packet.associations:
            if link.component_mention_id not in {
                m.mention_id for m in packet.component_mentions
            } or link.symptom_mention_id not in {m.mention_id for m in packet.symptom_mentions}:
                raise ValueError("invalid association reference")
        report = reports.setdefault(
            packet.report_group_id,
            {
                "report_id": packet.report_group_id,
                "fallback": packet.report_group_fallback,
                "source_rows": [],
                "variants": [],
                "structured_components": [],
            },
        )
        report["source_rows"].append(
            {
                "event_id": packet.event_id,
                "source_record_id": packet.source_record_id,
                "source_reference_id": packet.source_reference_id,
                "report_date": clean["report_date"],
                "occurrence_date": clean["occurrence_date"],
                "quality_flags": clean["quality_flags"],
            }
        )
        report["structured_components"].append(clean["component"])
        variant = next(
            (v for v in report["variants"] if v["narrative"] == clean["narrative"]), None
        )
        if variant is None:
            variant = {
                "narrative": clean["narrative"],
                "narrative_sha256": packet.narrative_sha256,
                "source_event_ids": [],
                "processing_status": packet.processing_status,
                "components": [m.model_dump(mode="json") for m in packet.component_mentions],
                "symptoms": [m.model_dump(mode="json") for m in packet.symptom_mentions],
                "associations": [a.model_dump(mode="json") for a in packet.associations],
            }
            report["variants"].append(variant)
        variant["source_event_ids"].append(packet.event_id)
    for report in reports.values():
        report["structured_components"] = sorted(set(report["structured_components"]))
        report["conflicting_narratives"] = len(report["variants"]) > 1
        report["review_status"] = "pending_human_review"
    return [reports[key] for key in sorted(reports)]


def build_review(source: Path, index_path: Path, output: Path, timestamp: datetime) -> None:
    """Scan source once for approved rows; run unchanged NLP only on those rows."""
    offset = timestamp.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("generation timestamp must be UTC")
    output = output.resolve()
    root = Path(__file__).resolve().parents[3]
    if output.is_relative_to(root) and not output.is_relative_to(root / "artifacts/nlp"):
        raise ValueError("repository outputs must be inside ignored artifacts/nlp")
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite review directory")
    index = HistoricalIndex(index_path)
    source_meta = source.with_suffix(source.suffix + ".provenance.json")
    hashes = {
        "source": _hash(source),
        "source_provenance": _hash(source_meta),
        "index": _hash(index_path),
        "code": _code_hash(),
    }
    if hashes["source"] != index.provenance["source_sha256"]:
        raise ValueError("source does not match historical index")
    if hashes["source_provenance"] != index.provenance["cleaning_provenance_sha256"]:
        raise ValueError("cleaning provenance does not match historical index")
    metadata = json.loads(source_meta.read_bytes())
    expected: dict[int, tuple[str, str, str | None, str]] = {}
    identities: dict[str, dict[str, Any]] = {}
    with closing(connect_readonly(index_path)) as db:
        for make, model, year in COHORTS:
            candidates = index.discover(make, model, year)
            if len(candidates) != 1:
                raise ValueError("unmatched or ambiguous approved cohort")
            vehicle = candidates[0]
            identities[vehicle["id"]] = vehicle
            for sequence, report, date, component in db.execute(
                "SELECT sequence,report,report_date,component FROM rows WHERE vehicle=?",
                (vehicle["id"],),
            ):
                if db.execute(
                    "SELECT count(DISTINCT vehicle) FROM rows WHERE report=?", (report,)
                ).fetchone()[0] != 1:
                    raise ValueError("conflicting report vehicle identity requires review")
                expected[sequence] = (vehicle["id"], report, date, component)
                if len(expected) > 10_000:
                    raise ValueError("bounded experiment exceeds 10000 source rows")
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    lineage: list[dict[str, Any]] = []
    count = 0
    for count, row in enumerate(iter_clean_records(source), 1):
        if count not in expected:
            continue
        identity, report, date, component = expected[count]
        canonical = VehicleAssociation(
            make=row["normalized_make"], model=row["normalized_model"], year=row["model_year"]
        )
        if (
            canonical.broad_identity_id != identity
            or row["broad_vehicle_id"] != identity
            or report_key(row)[0] != report
            or row["report_date"] != date
            or row["component"] != component
        ):
            raise ValueError("source/index identity or lineage conflict")
        selected[identity].append(row)
        lineage.append({"source_line": count, "event_id": row["event_id"], "vehicle_id": identity})
    if count != metadata["cleaned_count"] or sum(map(len, selected.values())) != len(expected):
        raise ValueError("source/index count disagreement")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".p4b-", dir=output.parent) as temporary:
        staging = Path(temporary) / "run"
        staging.mkdir()
        (staging / "lineage.json").write_bytes(_json(lineage))
        for identity, vehicle in identities.items():
            directory = staging / f"{vehicle['year']}-{vehicle['make']}-{vehicle['model']}"
            directory.mkdir()
            rows = selected[identity]
            subset = directory / "selected-clean.jsonl"
            # The validated clean contract includes declared field ordering.
            subset.write_bytes(b"".join(
                (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
                for row in rows
            ))
            subset.with_suffix(".jsonl.provenance.json").write_bytes(
                _json(
                    {
                        **metadata,
                        "cleaned_count": len(rows),
                        "derived_subset": True,
                        "parent_clean_sha256": hashes["source"],
                        "selection": vehicle,
                    }
                )
            )
            extraction = directory / "extraction.jsonl"
            process_owner_reports(subset, extraction, clock=lambda: timestamp)
            summarize_reports(extraction, directory / "summary.json", clock=lambda: timestamp)
            reports = review_records(rows, extraction)
            if len(reports) != index.summary(identity)["unique_report_count"]:
                raise ValueError("unique-report conservation failed")
            (directory / "review.json").write_bytes(
                _json(
                    {
                        "schema_version": VERSION,
                        "vehicle": vehicle,
                        "reports": reports,
                        "warning": "Unvalidated rule output; allegations, not verified defects.",
                    }
                )
            )
        if (
            hashes["source"] != _hash(source)
            or hashes["index"] != _hash(index_path)
            or hashes["source_provenance"] != _hash(source_meta)
            or hashes["code"] != _code_hash()
        ):
            raise ValueError("inputs or code changed during experiment")
        files = {
            p.relative_to(staging).as_posix(): _hash(p)
            for p in sorted(staging.rglob("*"))
            if p.is_file()
        }
        (staging / "completion.json").write_bytes(
            _json(
                {
                    "schema_version": VERSION,
                    "complete": True,
                    "generation_utc": timestamp.isoformat(),
                    "inputs": hashes,
                    "scope": list(identities.values()),
                    "files": files,
                    "source_rows_scanned": count,
                    "source_rows_extracted": len(expected),
                    "policy": "All indexed rows for two approved cohorts; no NLP on other rows.",
                }
            )
        )
        os.rename(staging, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    build_review(args.input, args.index, args.output_dir, args.generation_utc)
    print("Bounded vehicle review complete; pending human review. No accuracy claim.")


if __name__ == "__main__":
    main()
