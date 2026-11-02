"""Disk-backed memberships and deterministic duplicate-safe evaluation components."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from howreliable.nlp.schemas import ExtractionRow

GROUPING_VERSION = "howreliable-owner-report-grouping-1.0"
MEMBERSHIP_VERSION = "howreliable-owner-report-membership-1.0"


def create_memberships(db: sqlite3.Connection) -> None:
    """Extend B's existing events index; reuse its reports/texts/variants tables."""
    db.execute("ALTER TABLE events ADD COLUMN sequence INTEGER")
    db.execute("ALTER TABLE events ADD COLUMN report_id TEXT")
    db.execute("ALTER TABLE events ADD COLUMN text_sha256 TEXT")
    db.execute("ALTER TABLE events ADD COLUMN source_type TEXT")
    db.execute("ALTER TABLE events ADD COLUMN source_record_id TEXT")
    db.execute("ALTER TABLE events ADD COLUMN source_reference_id TEXT")
    db.execute("ALTER TABLE events ADD COLUMN report_date TEXT")
    db.execute("ALTER TABLE events ADD COLUMN occurrence_date TEXT")
    db.execute("ALTER TABLE events ADD COLUMN fallback INTEGER")
    db.execute("ALTER TABLE events ADD COLUMN eligible INTEGER")
    db.execute("ALTER TABLE events ADD COLUMN processable INTEGER")
    db.execute("CREATE UNIQUE INDEX event_sequence ON events(sequence)")
    db.execute("CREATE INDEX event_report ON events(report_id)")
    db.execute("CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.executemany(
        "INSERT INTO index_metadata VALUES (?,?)",
        [
            ("schema_version", MEMBERSHIP_VERSION),
            ("grouping_version", GROUPING_VERSION),
        ],
    )


def add_membership(db: sqlite3.Connection, row: ExtractionRow, sequence: int) -> None:
    db.execute(
        "UPDATE events SET sequence=?,report_id=?,text_sha256=?,source_type=?,"
        "source_record_id=?,source_reference_id=?,report_date=?,occurrence_date=?,"
        "fallback=?,eligible=?,processable=? WHERE id=?",
        (
            sequence,
            row.report_group_id,
            row.narrative_sha256,
            row.source_type,
            row.source_record_id,
            row.source_reference_id,
            row.report_date.isoformat() if row.report_date else None,
            row.occurrence_date.isoformat() if row.occurrence_date else None,
            int(row.report_group_fallback),
            int(not row.processing_status.startswith("excluded_")),
            int(row.processing_status == "processed"),
            row.event_id,
        ),
    )


def _root(db: sqlite3.Connection, group: str) -> str:
    # No in-memory graph or path list; halving bounds lookup work on disk.
    while True:
        parent = str(db.execute("SELECT parent FROM parents WHERE id=?", (group,)).fetchone()[0])
        if parent == group:
            return group
        grandparent = str(
            db.execute("SELECT parent FROM parents WHERE id=?", (parent,)).fetchone()[0]
        )
        db.execute("UPDATE parents SET parent=? WHERE id=?", (grandparent, group))
        group = parent


def finalize_memberships(db: sqlite3.Connection) -> None:
    db.execute("CREATE TABLE parents (id TEXT PRIMARY KEY,parent TEXT NOT NULL)")
    db.execute("INSERT INTO parents SELECT id,id FROM reports ORDER BY id")
    db.execute("CREATE INDEX variant_text ON variants(text,report)")
    previous_text: str | None = None
    first_report = ""
    for report, text in db.execute("SELECT report,text FROM variants ORDER BY text,report"):
        if text != previous_text:
            previous_text, first_report = text, report
        else:
            a, b = _root(db, first_report), _root(db, report)
            if a != b:
                low, high = sorted((a, b))
                db.execute("UPDATE parents SET parent=? WHERE id=?", (low, high))
    db.execute(
        "CREATE TABLE report_groups (id TEXT PRIMARY KEY,evaluation_group_id TEXT,"
        "narrative_conflict INTEGER,date_conflict INTEGER)"
    )
    for (group,) in db.execute("SELECT id FROM reports ORDER BY id"):
        variants = db.execute("SELECT count(*) FROM variants WHERE report=?", (group,)).fetchone()[
            0
        ]
        # Missing availability is a distinct variant, never silently imputed from another row.
        dates = db.execute(
            "SELECT count(*) FROM (SELECT DISTINCT report_date FROM events WHERE report_id=?)",
            (group,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO report_groups VALUES (?,?,?,?)",
            (group, "evaluation_" + _root(db, group), int(variants > 1), int(dates > 1)),
        )
    db.commit()


def group_fields(db: sqlite3.Connection, report_id: str) -> dict[str, object]:
    evaluation, narrative, dates = db.execute(
        "SELECT evaluation_group_id,narrative_conflict,date_conflict FROM report_groups WHERE id=?",
        (report_id,),
    ).fetchone()
    return {
        "evaluation_group_id": evaluation,
        "report_group_conflict": bool(narrative),
        "report_date_conflict": bool(dates),
    }


def grouping_counts(db: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "exact_text_duplicate_count": "SELECT count(*)-count(DISTINCT text_sha256) FROM events "
        "WHERE text_sha256 IS NOT NULL",
        "conflicting_report_date_count": "SELECT count(*) FROM report_groups WHERE date_conflict=1",
        "eligible_record_count": "SELECT count(*) FROM events WHERE eligible=1",
        "processable_record_count": "SELECT count(*) FROM events WHERE processable=1",
        "processable_unique_report_count": (
            "SELECT count(DISTINCT report_id) FROM events WHERE processable=1"
        ),
        "eligible_unique_report_count": (
            "SELECT count(DISTINCT report_id) FROM events WHERE eligible=1"
        ),
        "eligible_exact_text_duplicate_count": "SELECT count(*)-count(DISTINCT text_sha256) "
        "FROM events WHERE eligible=1 AND text_sha256 IS NOT NULL",
        "evaluation_group_count": "SELECT count(DISTINCT evaluation_group_id) FROM report_groups",
    }
    return {key: int(db.execute(query).fetchone()[0]) for key, query in queries.items()}


def validate_partition_assignments(index: Path, assignments: Mapping[str, str]) -> None:
    """Reject cross-partition report/text leakage for proposed event-ID assignments.

    Does not sample, assign or score reports. Caller must use the completed run's verified
    membership index and pass the entire proposed assignment, not one split at a time.
    """
    uri = index.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        version = db.execute(
            "SELECT value FROM index_metadata WHERE key='schema_version'"
        ).fetchone()
        if version != (MEMBERSHIP_VERSION,):
            raise ValueError("unsupported membership index")
        # TEMP is connection-local; the persistent index remains read-only. Disk-backed keys
        # avoid an additional unbounded evaluation-group dictionary.
        db.execute("PRAGMA temp_store=FILE")
        db.execute("CREATE TEMP TABLE proposed (group_id TEXT PRIMARY KEY,partition TEXT)")
        for event, partition in assignments.items():
            if not partition.strip():
                raise ValueError("partition names must be nonempty")
            found = db.execute(
                "SELECT g.evaluation_group_id,e.eligible FROM events e JOIN report_groups g "
                "ON e.report_id=g.id WHERE e.id=?",
                (event,),
            ).fetchone()
            if found is None:
                raise ValueError("unknown event in partition assignment")
            if not found[1]:
                raise ValueError("date-excluded event cannot enter an evaluation partition")
            prior = db.execute(
                "SELECT partition FROM proposed WHERE group_id=?", (found[0],)
            ).fetchone()
            if prior is not None and prior[0] != partition:
                raise ValueError("report or exact-text evaluation group crosses partitions")
            db.execute("INSERT OR IGNORE INTO proposed VALUES (?,?)", (found[0], partition))
