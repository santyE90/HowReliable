"""Explicit streaming, narrative-free historical index and read-only queries."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any

from howreliable.data.features.nhtsa_complaints import CLEAN_RECORD_SCHEMA, iter_clean_records
from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.domain.reliability import VehicleAssociation

INDEX_VERSION = "howreliable-history-index-1.0"
DEFAULT_INDEX = Path("data/processed/demo/history-v1-20261102-v2.sqlite")
LIMITATION = (
    "Descriptive historical NHTSA complaint reports, not verified failures, defect rates, "
    "severity rankings or reliability scores. The recovered snapshot may include revisions."
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def report_key(row: dict[str, Any]) -> tuple[str, bool]:
    """Reuse the source-type + ODINO / CMPLID fallback policy, without NLP imports."""
    reference = row["source_reference_id"]
    fallback = reference is None or not reference.strip()
    values = [
        row["source_type"], "CMPLID" if fallback else "ODINO",
        row["source_record_id"] if fallback else reference,
    ]
    # Existing report-group encoding includes a trailing newline (sort_keys is immaterial).
    digest = hashlib.sha256((canonical_json(values) + "\n").encode()).hexdigest()
    return "report_" + digest, fallback


def connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def build_index(source: Path, output: Path, generation_utc: datetime) -> dict[str, Any]:
    """Publish an immutable database, then its checksum completion marker; never replace."""
    offset = generation_utc.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("generation timestamp must be explicitly UTC")
    source, output = source.resolve(), output.resolve()
    marker = output.with_suffix(output.suffix + ".provenance.json")
    source_provenance = source.with_suffix(source.suffix + ".provenance.json")
    if output.exists() or output.is_symlink() or marker.exists() or marker.is_symlink():
        raise FileExistsError("refusing to overwrite index or completion provenance")
    if output in {source, source_provenance} or marker in {source, source_provenance}:
        raise ValueError("output must not alias an input")
    parent = json.loads(source_provenance.read_text(encoding="utf-8"))
    source_hash = sha256_file(source)
    parent_hash = sha256_file(source_provenance)
    output.parent.mkdir(parents=True, exist_ok=True)
    published = False
    marker_published = False
    with tempfile.TemporaryDirectory(prefix=".history-build-", dir=output.parent) as temporary:
        staging = Path(temporary) / "index.sqlite"
        try:
            with closing(sqlite3.connect(staging)) as db:
                db.executescript("""
                    PRAGMA page_size=4096;
                    PRAGMA temp_store=FILE;
                    PRAGMA cache_size=-16384;
                    CREATE TABLE vehicles (
                        id TEXT PRIMARY KEY, make TEXT NOT NULL, model TEXT NOT NULL,
                        year INTEGER NOT NULL);
                    CREATE TABLE rows (
                        sequence INTEGER PRIMARY KEY, report TEXT NOT NULL,
                        vehicle TEXT NOT NULL REFERENCES vehicles(id),
                        report_date TEXT, component TEXT NOT NULL, fallback INTEGER NOT NULL);
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                """)
                count = 0
                for count, row in enumerate(iter_clean_records(source), 1):
                    for key in ("source_type", "source_record_id", "broad_vehicle_id", "event_id"):
                        if not row[key].strip():
                            raise ValueError("empty required source identifier")
                    if row["report_date"] is not None and (
                        date.fromisoformat(row["report_date"]).isoformat() != row["report_date"]
                    ):
                        raise ValueError("report date must use canonical YYYY-MM-DD format")
                    vehicle = VehicleAssociation(
                        make=row["normalized_make"], model=row["normalized_model"],
                        year=row["model_year"],
                    )
                    if vehicle.broad_identity_id != row["broad_vehicle_id"]:
                        raise ValueError("clean vehicle ID disagrees with canonical identity")
                    identity = (
                        vehicle.broad_identity_id, vehicle.make, vehicle.model, vehicle.year,
                    )
                    db.execute("INSERT OR IGNORE INTO vehicles VALUES (?,?,?,?)", identity)
                    report, fallback = report_key(row)
                    db.execute("INSERT INTO rows VALUES (?,?,?,?,?,?)", (
                        count, report, vehicle.broad_identity_id, row["report_date"],
                        row["component"], int(fallback),
                    ))
                if count != parent["cleaned_count"]:
                    raise ValueError("source record count disagrees with cleaning provenance")
                db.executescript("""
                    CREATE INDEX vehicle_identity ON vehicles(make,model,year,id);
                    CREATE INDEX row_vehicle_date ON rows(vehicle,report_date,report);
                    CREATE INDEX row_vehicle_component ON rows(vehicle,component,report);
                    CREATE INDEX row_report ON rows(report);
                    CREATE TABLE reports AS
                        SELECT report, count(*) AS source_rows,
                        count(DISTINCT vehicle) AS vehicle_count,
                        count(DISTINCT coalesce(report_date,'')) AS date_variants
                        FROM rows GROUP BY report ORDER BY report;
                    CREATE UNIQUE INDEX report_identity ON reports(report);
                """)
                def scalar(sql: str) -> int:
                    return int(db.execute(sql).fetchone()[0])
                metadata: dict[str, Any] = {
                    "schema_version": INDEX_VERSION,
                    "source_schema": list(CLEAN_RECORD_SCHEMA),
                    "source_filename": source.name,
                    "source_sha256": source_hash,
                    "cleaning_provenance_sha256": parent_hash,
                    "cleaning_version": parent["cleaning_version"],
                    "mapping_version": parent["mapping_version"],
                    "builder_sha256": sha256_file(Path(__file__)),
                    "validator_sha256": sha256_file(
                        Path(__file__).parents[1] / "data/features/nhtsa_complaints.py"),
                    "vehicle_identity_sha256": sha256_file(
                        Path(__file__).parents[1] / "domain/reliability.py"),
                    "sqlite_version": sqlite3.sqlite_version,
                    "generation_utc": generation_utc.isoformat().replace("+00:00", "Z"),
                    "report_policy": "source_type + ODINO; CMPLID fallback; no text merging",
                    "date_policy": "report dates only; missing retained; invalid input rejected",
                    "source_row_count": count,
                    "unique_report_count": scalar("SELECT count(*) FROM reports"),
                    "vehicle_count": scalar("SELECT count(*) FROM vehicles"),
                    "missing_report_date_rows": scalar(
                        "SELECT count(*) FROM rows WHERE report_date IS NULL"),
                    "missing_report_date_reports": scalar(
                        "SELECT count(DISTINCT report) FROM rows WHERE report_date IS NULL"),
                    "fallback_source_rows": scalar("SELECT count(*) FROM rows WHERE fallback=1"),
                    "conflicting_date_reports": scalar(
                        "SELECT count(*) FROM reports WHERE date_variants>1"),
                    "conflicting_vehicle_reports": scalar(
                        "SELECT count(*) FROM reports WHERE vehicle_count>1"),
                    "limitation": LIMITATION,
                }
                db.executemany("INSERT INTO metadata VALUES (?,?)", [
                    (key, canonical_json(value)) for key, value in sorted(metadata.items())
                ])
                db.commit()
                if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("index integrity check failed")
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("index foreign key check failed")
                if scalar("SELECT coalesce(sum(source_rows),0) FROM reports") != count:
                    raise ValueError("report accounting failed")
            if sha256_file(source) != source_hash or sha256_file(source_provenance) != parent_hash:
                raise ValueError("input changed during build")
            provenance = {**metadata, "index_sha256": sha256_file(staging)}
            staging_marker = Path(temporary) / "provenance.json"
            staging_marker.write_text(canonical_json(provenance) + "\n", encoding="utf-8")
            for path in (staging, staging_marker):
                with path.open("r+b") as stream:
                    os.fsync(stream.fileno())
            # Atomic create-if-absent hard links on the same filesystem, including Windows NTFS.
            # The loader requires the marker; an interrupted publication is never ready.
            os.link(staging, output)
            published = True
            os.link(staging_marker, marker)
            marker_published = True
            return provenance
        except BaseException:
            if marker_published:
                marker.unlink()
            if published:
                output.unlink()
            raise


class HistoricalIndex:
    """Validate once at startup, then query with short-lived read-only connections."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        marker = path.with_suffix(path.suffix + ".provenance.json")
        self.provenance: dict[str, Any] = json.loads(marker.read_text(encoding="utf-8"))
        if self.provenance["schema_version"] != INDEX_VERSION:
            raise ValueError("unsupported historical index schema")
        if self.provenance["index_sha256"] != sha256_file(path):
            raise ValueError("historical index checksum mismatch")
        with closing(connect_readonly(path)) as db:
            metadata = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM metadata")}
            if metadata != {k: v for k, v in self.provenance.items() if k != "index_sha256"}:
                raise ValueError("index and completion provenance disagree")

    def discover(
        self, make: str | None, model: str | None, year: int | None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[str | int] = []
        # Canonical normalization, not fuzzy matching; supplied model requires make.
        if model is not None and make is None:
            raise ValueError("model filtering requires make")
        if make is not None:
            normalized = VehicleAssociation(make=make, model=model or "_", year=year or 2000)
            clauses.append("make=?")
            values.append(normalized.make)
            if model is not None:
                clauses.append("model=?")
                values.append(normalized.model)
        if year is not None:
            clauses.append("year=?")
            values.append(year)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with closing(connect_readonly(self.path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT id,make,model,year FROM vehicles" + where + " ORDER BY make,model,year,id",
                values,
            )]

    def summary(self, vehicle_id: str) -> dict[str, Any]:
        with closing(connect_readonly(self.path)) as db:
            identity = db.execute("SELECT id,make,model,year FROM vehicles WHERE id=?",
                                  (vehicle_id,)).fetchone()
            if identity is None:
                raise KeyError("unknown vehicle")
            rows, reports, missing = db.execute(
                "SELECT count(*),count(DISTINCT report),"
                "coalesce(sum(report_date IS NULL),0) FROM rows WHERE vehicle=?", (vehicle_id,),
            ).fetchone()
            first, last = db.execute(
                "SELECT min(report_date),max(report_date) FROM rows WHERE vehicle=?", (vehicle_id,),
            ).fetchone()
            # One monthly bin per report only if all its rows agree on a nonmissing date.
            # Otherwise retain it in an explicit unknown/conflicting bucket.
            timeline = [dict(month=month, unique_report_count=n, source_row_count=r)
                        for month, n, r in db.execute(
                "SELECT month,count(*),sum(source_rows) FROM (SELECT count(*) AS source_rows, "
                "CASE WHEN "
                "count(DISTINCT coalesce(report_date,''))=1 AND min(report_date) IS NOT NULL "
                "THEN substr(min(report_date),1,7) ELSE NULL END AS month "
                "FROM rows WHERE vehicle=? GROUP BY report) GROUP BY month ORDER BY month",
                (vehicle_id,),
            )]
            components = [dict(category=c, source_row_count=r, unique_report_count=n)
                          for c, r, n in db.execute(
                "SELECT component,count(*),count(DISTINCT report) FROM rows WHERE vehicle=? "
                "GROUP BY component ORDER BY count(DISTINCT report) DESC,component", (vehicle_id,),
            )]
            return {
                "vehicle": dict(zip(("id", "make", "model", "year"), identity, strict=True)),
                "source_row_count": rows, "unique_report_count": reports,
                "missing_report_date_rows": missing, "timeline": timeline,
                "first_report_date": first, "last_report_date": last,
                "timeline_policy": (
                    "Each report occurs once; missing or conflicting report dates use the null "
                    "month bucket, including all their source rows. Component counts overlap."
                ),
                "components": components, "provenance": self.provenance,
                "limitation": LIMITATION,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local narrative-free complaint index")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    result = build_index(args.input, args.output, args.generation_utc)
    print(canonical_json(result))


if __name__ == "__main__":
    main()
