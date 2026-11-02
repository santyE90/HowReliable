"""Verified, offline descriptive summaries of completed Milestone E extraction runs."""

from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from howreliable.nlp.grouping import MEMBERSHIP_VERSION
from howreliable.nlp.owner_reports import _code_hash, _git_identity, _hash, _json
from howreliable.nlp.schemas import ExtractionRow, RunProvenance

SUMMARY_VERSION = "howreliable-owner-report-summary-1.0"
PROVENANCE_VERSION = "howreliable-owner-report-summary-provenance-1.0"
LABEL = (
    "Descriptive complaint-report patterns; not verified failures, defect rates, "
    "severity or reliability estimates."
)


def _targets(sources: list[Path], targets: list[Path]) -> None:
    resolved = [p.resolve() for p in targets]
    if len(set(resolved)) != len(resolved) or set(resolved) & {p.resolve() for p in sources}:
        raise ValueError("summary sources and destinations must be distinct")
    root = Path(__file__).resolve().parents[3]
    allowed = [root / "data/processed/nlp", root / "artifacts/nlp"]
    for p, original in zip(resolved, targets, strict=True):
        if p.is_relative_to(root) and not any(p.is_relative_to(a) for a in allowed):
            raise ValueError("repository summaries must remain in NLP artifact directories")
        if original.exists() or original.is_symlink():
            raise FileExistsError("refusing to overwrite summary artifact")


def _fact(
    db: sqlite3.Connection, section: str, category: str, status: str, row: ExtractionRow
) -> None:
    db.execute(
        "INSERT INTO facts VALUES (?,?,?,?,?,1) ON CONFLICT DO UPDATE "
        "SET occurrences=occurrences+1",
        (section, category, status, row.event_id, row.report_group_id),
    )


def _counts(db: sqlite3.Connection, section: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for category, status, occurrences, rows, reports in db.execute(
        "SELECT category,status,sum(occurrences),count(DISTINCT event),count(DISTINCT report) "
        "FROM facts WHERE section=? GROUP BY category,status "
        "ORDER BY count(DISTINCT report) DESC,count(DISTINCT event) DESC,category,status",
        (section,),
    ):
        item: dict[str, object] = {
            "occurrence_count": occurrences,
            "source_row_count": rows,
            "unique_report_count": reports,
        }
        if section == "association":
            component, symptom = category.split("|")
            ca, sa = status.split("|")
            item.update(
                component=component,
                symptom=symptom,
                component_assertion=ca,
                symptom_assertion=sa,
                primary_pattern=ca == sa == "affirmed",
            )
        else:
            item.update(
                category=category,
                assertion=status,
                primary_pattern=status == "affirmed"
                and not category.endswith(("_ambiguous", "_unmapped")),
            )
        result.append(item)
    return result


def summarize_reports(
    extraction: Path,
    output: Path,
    *,
    extraction_provenance: Path | None = None,
    membership: Path | None = None,
    provenance: Path | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Require a completed E run; aggregate eligible rows using its read-only index.

    Output schemas are independent of extraction schemas. Legacy extraction readers remain
    unchanged; pre-E runs without a verified membership index cannot be summarized safely.
    """
    source_meta = extraction_provenance or extraction.with_suffix(
        extraction.suffix + ".provenance.json"
    )
    membership = membership or extraction.with_suffix(extraction.suffix + ".membership.sqlite")
    provenance = provenance or output.with_suffix(output.suffix + ".provenance.json")
    _targets([extraction, source_meta, membership], [output, provenance])
    generated = clock()
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("summary generation timestamp must be timezone-aware")
    generated = generated.astimezone(UTC)
    meta = RunProvenance.model_validate_json(source_meta.read_bytes())
    if meta.milestone != "E" or meta.membership_schema_version != MEMBERSHIP_VERSION:
        raise ValueError("summary requires a completed E run with verified membership")
    hashes = [_hash(p) for p in (extraction, source_meta, membership)]
    if hashes[0] != meta.output_sha256 or hashes[2] != meta.membership_sha256:
        raise ValueError("extraction/membership checksum mismatch")
    if extraction.stat().st_size != meta.output_size_bytes:
        raise ValueError("extraction size mismatch")
    owned: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="howreliable-summary-") as directory:
            temp = Path(directory)
            with closing(sqlite3.connect(temp / "counts.sqlite", uri=True)) as db:
                db.execute("PRAGMA cache_size=-8192")
                db.execute("PRAGMA temp_store=FILE")
                db.execute(
                    "ATTACH DATABASE ? AS membership", (membership.resolve().as_uri() + "?mode=ro",)
                )
                v = db.execute(
                    "SELECT value FROM membership.index_metadata WHERE key='schema_version'"
                ).fetchone()
                if v != (MEMBERSHIP_VERSION,):
                    raise ValueError("unsupported membership schema")
                db.execute(
                    "CREATE TABLE seen (event TEXT PRIMARY KEY,report TEXT,eligible INTEGER,"
                    "processable INTEGER,status TEXT,mentions INTEGER,associations INTEGER)"
                )
                db.execute(
                    "CREATE TABLE facts (section TEXT,category TEXT,status TEXT,event TEXT,"
                    "report TEXT,occurrences INTEGER,PRIMARY KEY(section,category,status,event))"
                )
                with extraction.open("rb") as source:
                    for sequence, line in enumerate(source, 1):
                        row = ExtractionRow.model_validate_json(line)
                        if row.schema_version != meta.schema_version or (
                            row.mode != meta.configuration.mode
                            or row.cutoff != meta.configuration.cutoff
                        ):
                            raise ValueError("row schema/temporal policy differs from provenance")
                        observed = db.execute(
                            "SELECT e.sequence,e.report_id,e.text_sha256,e.eligible,e.processable,"
                            "e.report_date,e.occurrence_date,g.evaluation_group_id,"
                            "g.narrative_conflict,g.date_conflict FROM membership.events e "
                            "JOIN membership.report_groups g ON e.report_id=g.id WHERE e.id=?",
                            (row.event_id,),
                        ).fetchone()
                        expected = (
                            sequence,
                            row.report_group_id,
                            row.narrative_sha256,
                            int(bool(row.eligible)),
                            int(row.processing_status == "processed"),
                            row.report_date.isoformat() if row.report_date else None,
                            row.occurrence_date.isoformat() if row.occurrence_date else None,
                            row.evaluation_group_id,
                            int(bool(row.report_group_conflict)),
                            int(bool(row.report_date_conflict)),
                        )
                        if observed != expected:
                            raise ValueError("extraction row disagrees with membership")
                        db.execute(
                            "INSERT INTO seen VALUES (?,?,?,?,?,?,?)",
                            (
                                row.event_id,
                                row.report_group_id,
                                int(bool(row.eligible)),
                                int(row.processing_status == "processed"),
                                row.processing_status,
                                len(row.mentions),
                                len(row.associations),
                            ),
                        )
                        if not row.eligible or row.processing_status != "processed":
                            continue
                        for mention in row.mentions:
                            _fact(db, mention.kind, mention.code, mention.assertion, row)
                        components = {m.mention_id: m for m in row.component_mentions}
                        symptoms = {m.mention_id: m for m in row.symptom_mentions}
                        for relation in row.associations:
                            c, s = (
                                components[relation.component_mention_id],
                                symptoms[relation.symptom_mention_id],
                            )
                            # Count emitted links, never narrative co-occurrence.
                            _fact(
                                db,
                                "association",
                                c.code + "|" + s.code,
                                c.assertion + "|" + s.assertion,
                                row,
                            )

                def count(query: str) -> int:
                    return int(db.execute(query).fetchone()[0])

                total = count("SELECT count(*) FROM seen")
                if total != meta.output_record_count or total != count(
                    "SELECT count(*) FROM membership.events"
                ):
                    raise ValueError("summary input record conservation mismatch")
                denominators = {
                    "total_source_rows": total,
                    "total_unique_reports": count("SELECT count(DISTINCT report) FROM seen"),
                    "eligible_source_rows": count("SELECT count(*) FROM seen WHERE eligible=1"),
                    "eligible_unique_reports": count(
                        "SELECT count(DISTINCT report) FROM seen WHERE eligible=1"
                    ),
                    "processable_source_rows": count(
                        "SELECT count(*) FROM seen WHERE processable=1"
                    ),
                    "processable_unique_reports": count(
                        "SELECT count(DISTINCT report) FROM seen WHERE processable=1"
                    ),
                }
                if denominators["total_unique_reports"] != meta.unique_report_count:
                    raise ValueError("summary report conservation mismatch")
                statuses = [
                    {"status": status, "source_row_count": n, "unique_report_count": reports}
                    for status, n, reports in db.execute(
                        "SELECT status,count(*),count(DISTINCT report) FROM seen "
                        "GROUP BY status ORDER BY status"
                    )
                ]
                if {
                    str(x["status"]): x["source_row_count"] for x in statuses
                } != meta.status_counts:
                    raise ValueError("summary status accounting mismatch")
                assertions = [
                    {
                        "assertion": status,
                        "occurrence_count": n,
                        "source_row_count": rows,
                        "unique_report_count": reports,
                    }
                    for status, n, rows, reports in db.execute(
                        "SELECT status,sum(occurrences),count(DISTINCT event),"
                        "count(DISTINCT report) FROM facts WHERE section!='association' "
                        "GROUP BY status ORDER BY status"
                    )
                ]
                unresolved = [_counts(db, kind) for kind in ("component", "symptom")]
                category_totals = {
                    kind: [
                        {
                            "category": category,
                            "occurrence_count": occurrences,
                            "source_row_count": rows,
                            "unique_report_count": reports,
                        }
                        for category, occurrences, rows, reports in db.execute(
                            "SELECT category,sum(occurrences),count(DISTINCT event),"
                            "count(DISTINCT report) FROM facts WHERE section=? "
                            "GROUP BY category ORDER BY count(DISTINCT report) DESC,"
                            "count(DISTINCT event) DESC,category",
                            (kind,),
                        )
                    ]
                    for kind in ("component", "symptom")
                }
                summary: dict[str, object] = {
                    "schema_version": SUMMARY_VERSION,
                    "interpretation": LABEL,
                    "primary_measure": "unique_report_count; affirmed named labels only",
                    "mode": meta.configuration.mode,
                    "cutoff": meta.configuration.cutoff.isoformat()
                    if meta.configuration.cutoff
                    else None,
                    "denominators": denominators,
                    "category_totals_all_assertions": category_totals,
                    "processing_statuses": statuses,
                    "components": _counts(db, "component"),
                    "symptoms": _counts(db, "symptom"),
                    "associations": _counts(db, "association"),
                    "assertions": assertions,
                    "unresolved_mentions": {
                        "components": [x for x in unresolved[0] if x["assertion"] == "unresolved"],
                        "symptoms": [x for x in unresolved[1] if x["assertion"] == "unresolved"],
                    },
                    "eligible_processed_without_mentions": {
                        "source_row_count": count(
                            "SELECT count(*) FROM seen WHERE processable=1 AND mentions=0"
                        ),
                        "unique_report_count": count(
                            "SELECT count(DISTINCT report) FROM seen "
                            "WHERE processable=1 AND mentions=0"
                        ),
                    },
                    "eligible_processed_without_associations": {
                        "source_row_count": count(
                            "SELECT count(*) FROM seen WHERE processable=1 AND associations=0"
                        ),
                        "unique_report_count": count(
                            "SELECT count(DISTINCT report) FROM seen "
                            "WHERE processable=1 AND associations=0"
                        ),
                    },
                    "limitations": [
                        "Reports and statuses overlap; counts are not additive incident totals.",
                        "Identical text across distinct reports is not merged.",
                        "No supported association is not proof of an extraction abstention.",
                        "Snapshot revisions can postdate the historical cutoff.",
                        "Rule quality is not validated by frequency counts.",
                    ],
                }
            if [_hash(p) for p in (extraction, source_meta, membership)] != hashes:
                raise ValueError("summary source changed during processing")
            payload = _json(summary)
            (temp / "summary").write_bytes(payload)
            revision, dirty = _git_identity()
            completion: dict[str, object] = {
                "schema_version": PROVENANCE_VERSION,
                "summary_schema_version": SUMMARY_VERSION,
                "complete": True,
                "generation_utc": generated.isoformat().replace("+00:00", "Z"),
                "source_extraction_sha256": hashes[0],
                "source_provenance_sha256": hashes[1],
                "membership_sha256": hashes[2],
                "source_schema_version": meta.schema_version,
                "source_rule_identities": {
                    key: value
                    for key, value in meta.model_dump().items()
                    if key.endswith(("_version", "_sha256"))
                    and key not in {"input_sha256", "input_provenance_sha256", "output_sha256"}
                },
                "temporal_policy": meta.configuration.model_dump(mode="json"),
                "counting_policy": "eligible processable rows; unique reports by report_group_id; "
                "once per category/assertion/report; associations by endpoint assertions",
                "output_sha256": _hash(temp / "summary"),
                "output_size_bytes": len(payload),
                "code_sha256": _code_hash(),
                "code_revision": revision,
                "dirty_worktree": dirty,
            }
            (temp / "provenance").write_bytes(_json(completion))
            for staged, target in [(temp / "summary", output), (temp / "provenance", provenance)]:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    owned.append(target)
                    with staged.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
        return completion
    except BaseException:
        for target in reversed(owned):
            target.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize a verified NLP run descriptively")
    parser.add_argument("--extraction", type=Path, required=True)
    parser.add_argument("--extraction-provenance", type=Path)
    parser.add_argument("--membership", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args(argv)
    result = summarize_reports(
        args.extraction,
        args.output,
        extraction_provenance=args.extraction_provenance,
        membership=args.membership,
        provenance=args.provenance,
        clock=lambda: args.generation_utc,
    )
    print(f"Descriptive summary complete; SHA-256={result['output_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
