"""Explicit offline publication and optional, read-only official-evidence lookups."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.data.manufacturer_communications.nhtsa import (
    ADAPTER_VERSION as MC_ADAPTER,
)
from howreliable.data.manufacturer_communications.nhtsa import (
    APPLICABILITY_SCHEMA as MC_APPLICATION,
)
from howreliable.data.manufacturer_communications.nhtsa import COMMUNICATION_SCHEMA
from howreliable.data.recalls.nhtsa import ADAPTER_VERSION as RECALL_ADAPTER
from howreliable.data.recalls.nhtsa import APPLICABILITY_SCHEMA as RECALL_APPLICATION
from howreliable.data.recalls.nhtsa import CAMPAIGN_SCHEMA
from howreliable.demo.index import canonical_json, connect_readonly
from howreliable.demo.profile_schemas import OfficialRecord, OfficialSourceCoverage, ProfileIdentity
from howreliable.domain.reliability import VehicleAssociation

SCHEMA = "howreliable-official-evidence-1.0"
MATCHING = "official-exact-nfkc-whitespace-casefold-1.0"
DEFAULT_OFFICIAL = Path("data/processed/official/p7-20261104-v1")
SOURCES = {"recalls", "manufacturer_communications"}
APPLICABILITY = (
    "Exact normalized make/model/model-year relationship only. Individual VIN, trim, "
    "engine, drivetrain, Canadian-market applicability and remedy completion are unverified. "
    "Descriptions and components are campaign/document-wide, not diagnoses of this vehicle."
)


@dataclass(frozen=True)
class SourceInput:
    source: str
    manifest: Path
    records: Path
    applications: Path
    provenance: Path


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected metadata object")
    return value


def _rows(path: Path, schema: tuple[str, ...]) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if len(line) > 2_000_000:
                raise ValueError("oversized canonical row")
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != set(schema):
                raise ValueError("unexpected canonical schema")
            yield row


def _verified(source: SourceInput) -> dict[str, Any]:
    if source.source not in SOURCES:
        raise ValueError("unsupported official source")
    p, manifest = _json(source.provenance), _json(source.manifest)
    recall = source.source == "recalls"
    adapter = RECALL_ADAPTER if recall else MC_ADAPTER
    required = (
        {"FLAT_RCL_PRE_2010.zip", "FLAT_RCL_POST_2010.zip", "RCL.txt"}
        if recall
        else {
            "TSBS_RECEIVED_2020-2024.zip",
            "MFR_COMMS_RECEIVED_2020-2024.zip",
            "TSBS.txt",
        }
    )
    items = manifest.get("artifacts")
    if (
        not isinstance(items, list)
        or len(items) != 3
        or {a.get("filename") for a in items if isinstance(a, dict)} != required
    ):
        raise ValueError("incomplete acquisition manifest")
    for item in items:
        if (
            not item["official_source_url"].startswith("https://static.nhtsa.gov/odi/ffdd/")
            or not item.get("retrieval_timestamp_utc")
            or sha256_file(source.manifest.parent / item["filename"]) != item["sha256"]
        ):
            raise ValueError("invalid official source receipt/checksum")
    records_hash = "campaigns_sha256" if recall else "communications_sha256"
    if (
        p.get("processing_complete") is not True
        or p.get("adapter_version") != adapter
        or manifest.get("adapter_version") != adapter
        or p.get("artifacts") != items
        or p.get(records_hash) != sha256_file(source.records)
        or p.get("applicability_sha256") != sha256_file(source.applications)
    ):
        raise ValueError("incomplete or mismatched ingestion provenance")
    p["verified_inputs"] = {
        "acquisition_manifest_sha256": sha256_file(source.manifest),
        "ingestion_provenance_sha256": sha256_file(source.provenance),
        "records_sha256": p[records_hash],
        "applicability_sha256": p["applicability_sha256"],
        "adapter_version": adapter,
        "source_schema_version": p["source_schema_version"],
        "dictionary_sha256": next(a["sha256"] for a in items if a["filename"].endswith(".txt")),
    }
    p["snapshot_date"] = max(a["retrieval_timestamp_utc"] for a in items)
    p["snapshot_scope"] = (
        "Complete NHTSA PRE/POST-2010 recall flat-file snapshot; vehicle applications only."
        if recall
        else "NHTSA communications received in 2020-2024; rich TSV canonical, "
        "compact CSV overlap audit only. Not all historical or current communications."
    )
    return p


def _record(row: dict[str, Any], recall: bool) -> OfficialRecord:
    identifier = row["nhtsa_campaign_number"] if recall else row["source_nhtsa_id"]
    return OfficialRecord.model_validate_json(
        canonical_json(
            {
                "kind": "recall" if recall else "communication",
                "record_id": row["campaign_id" if recall else "communication_id"],
                "source_identifier": identifier,
                "manufacturer_identifiers": row["manufacturer_campaign_numbers"]
                if recall
                else [row["manufacturer_document_id"]],
                "title": f"NHTSA recall {identifier}"
                if recall
                else f"{row['communication_type'].replace('_', ' ').title()}: "
                f"{row['manufacturer_document_id']}",
                "descriptions": row["defect_descriptions"] if recall else [row["summary"]],
                "consequences": row["consequence_descriptions"] if recall else [],
                "remedies": row["corrective_actions"] if recall else [],
                "communication_type": None if recall else row["communication_type"],
                "original_communication_type": None
                if recall
                else row["original_communication_type"],
                "components": row["canonical_components"],
                "dates": {
                    k: row[k]
                    for k in [
                        "report_received_dates",
                        "owner_notification_dates",
                        "record_creation_dates",
                    ]
                }
                if recall
                else {
                    "date_added": [row["date_added"]] if row["date_added"] else [],
                    "communication_date": [row["communication_date"]]
                    if row["communication_date"]
                    else [],
                },
                "quality_flags": row["quality_flags"] if recall else row["date_quality_flags"],
                "source_artifacts": row["source_artifact_filenames"]
                if recall
                else [row["source_artifact_filename"]],
                "matching_applicability_rows": 1,
                "applicability_note": APPLICABILITY,
            }
        )
    )


def build_official(
    inputs: list[SourceInput],
    output: Path,
    generation_utc: datetime,
) -> dict[str, Any]:
    """Publish a new directory only after every included source and database validates."""
    if output.exists():
        raise FileExistsError("refusing to overwrite official serving artifact")
    if (
        not inputs
        or len({s.source for s in inputs}) != len(inputs)
        or generation_utc.tzinfo is None
    ):
        raise ValueError("unique sources and an injected UTC timestamp are required")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".official-stage-", dir=output.parent))
    try:
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA,
            "matching_policy_version": MATCHING,
            "generation_utc": generation_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "builder_sha256": sha256_file(Path(__file__)),
            "sources": {},
            "complete": True,
        }
        with closing(sqlite3.connect(staging / "evidence.sqlite")) as db:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                PRAGMA cache_size=-8192;
                CREATE TABLE records(source TEXT,id TEXT,data TEXT,PRIMARY KEY(source,id));
                CREATE TABLE applications(source TEXT,id TEXT,record TEXT,make TEXT,model TEXT,
                    year INTEGER,data TEXT,PRIMARY KEY(source,id),
                    FOREIGN KEY(source,record) REFERENCES records(source,id));
                CREATE INDEX vehicle_lookup ON applications(source,make,model,year,record);
                CREATE TABLE metadata(value TEXT NOT NULL);
            """)
            for source in sorted(inputs, key=lambda s: s.source):
                p = _verified(source)
                recall = source.source == "recalls"
                count = 0
                for row in _rows(
                    source.records, CAMPAIGN_SCHEMA if recall else COMMUNICATION_SCHEMA
                ):
                    record = _record(row, recall)
                    raw = record.model_dump_json()
                    if len(raw.encode("utf-8")) > 131072:
                        raise ValueError("official record exceeds bounded serving size")
                    db.execute(
                        "INSERT INTO records VALUES (?,?,?)",
                        (
                            source.source,
                            record.record_id,
                            raw,
                        ),
                    )
                    count += 1
                declared = p["unique_campaign_count" if recall else "unique_communication_count"]
                if count != declared:
                    raise ValueError("record count conservation failed")
                applications = eligible = 0
                for row in _rows(
                    source.applications, RECALL_APPLICATION if recall else MC_APPLICATION
                ):
                    applications += 1
                    year = row["model_year"]
                    if year is None:
                        continue
                    identity = VehicleAssociation(
                        make=row["normalized_make"],
                        model=row["normalized_model"],
                        year=year,
                    )
                    if (
                        identity.make != row["normalized_make"]
                        or identity.model != row["normalized_model"]
                        or (recall and row["product_type"] != "VEHICLE")
                    ):
                        raise ValueError("invalid canonical vehicle applicability")
                    db.execute(
                        "INSERT INTO applications VALUES (?,?,?,?,?,?,?)",
                        (
                            source.source,
                            row["applicability_id"],
                            row["campaign_id" if recall else "communication_id"],
                            identity.make,
                            identity.model,
                            year,
                            canonical_json(row),
                        ),
                    )
                    eligible += 1
                declared_apps = p[
                    "vehicle_applicability_count" if recall else "applicability_count"
                ]
                if applications != declared_apps:
                    raise ValueError("application count conservation failed")
                metadata["sources"][source.source] = {
                    "snapshot_date": p["snapshot_date"],
                    "snapshot_scope": p["snapshot_scope"],
                    "provenance": p["verified_inputs"],
                    "record_count": count,
                    "application_count": applications,
                    "eligible_application_count": eligible,
                    "unknown_year_applications": applications - eligible,
                }
            db.execute("INSERT INTO metadata VALUES (?)", (canonical_json(metadata),))
            db.commit()
            if (
                db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                or db.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise ValueError("official artifact integrity failed")
        receipt = {**metadata, "database_sha256": sha256_file(staging / "evidence.sqlite")}
        (staging / "manifest.json").write_text(canonical_json(receipt) + "\n", encoding="utf-8")
        os.rename(staging, output)
        return receipt
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class OfficialEvidence:
    """Verify once at optional startup; bounded indexed reads, no acquisition or model calls."""

    def __init__(self, directory: Path):
        self.path = directory / "evidence.sqlite"
        self.metadata = _json(directory / "manifest.json")
        expected = self.metadata.copy()
        checksum = expected.pop("database_sha256", None)
        if (
            expected.get("complete") is not True
            or expected.get("schema_version") != SCHEMA
            or expected.get("matching_policy_version") != MATCHING
            or not expected.get("sources")
            or not set(expected["sources"]) <= SOURCES
            or checksum != sha256_file(self.path)
        ):
            raise ValueError("unverified official serving artifact")
        with closing(connect_readonly(self.path)) as db:
            values = db.execute("SELECT value FROM metadata").fetchall()
            if values != [(canonical_json(expected),)]:
                raise ValueError("official artifact completion metadata mismatch")

    def lookup(self, source: str, identity: ProfileIdentity) -> OfficialSourceCoverage | None:
        if source not in self.metadata["sources"]:
            return None
        parameters = (source, identity.make, identity.model, identity.year)
        with closing(connect_readonly(self.path)) as db:
            total = db.execute(
                "SELECT count(DISTINCT record) FROM applications "
                "WHERE source=? AND make=? AND model=? AND year=?",
                parameters,
            ).fetchone()[0]
            rows = db.execute(
                "SELECT r.data,count(*) FROM applications a JOIN records r "
                "ON r.source=a.source AND r.id=a.record WHERE a.source=? "
                "AND a.make=? AND a.model=? AND a.year=? GROUP BY r.id "
                "ORDER BY r.id LIMIT 10",
                parameters,
            ).fetchall()
        records = [
            OfficialRecord.model_validate_json(data).model_copy(
                update={
                    "matching_applicability_rows": count,
                }
            )
            for data, count in rows
        ]
        scope = self.metadata["sources"][source]
        return OfficialSourceCoverage(
            explanation="NHTSA U.S. regulatory/documentary evidence, not failure frequency. "
            "A zero result means no exact match within this verified snapshot only.",
            snapshot_date=scope["snapshot_date"],
            snapshot_scope=scope["snapshot_scope"],
            provenance={
                **scope["provenance"],
                "serving_database_sha256": self.metadata["database_sha256"],
                "serving_schema_version": SCHEMA,
                "matching_policy_version": MATCHING,
            },
            unique_record_count=total,
            returned_record_count=len(records),
            records_truncated=total > len(records),
            records=records,
        )


def optional_official(directory: Path) -> OfficialEvidence | None:
    """Optional corruption/missingness must never disable complaint-only startup."""
    try:
        return OfficialEvidence(directory)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build verified offline official evidence")
    parser.add_argument("--recalls", type=Path)
    parser.add_argument("--communications", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    inputs = []
    for kind, directory in [
        ("recalls", args.recalls),
        ("manufacturer_communications", args.communications),
    ]:
        if directory is not None:
            raw = Path("data/raw/nhtsa") / kind / directory.name / "acquisition-manifest.json"
            records = directory / (
                "campaigns.jsonl" if kind == "recalls" else "communications.jsonl"
            )
            inputs.append(
                SourceInput(
                    kind,
                    raw,
                    records,
                    directory / "applicability.jsonl",
                    directory / "ingestion.provenance.json",
                )
            )
    print(canonical_json(build_official(inputs, args.output_dir, args.generation_utc)))


if __name__ == "__main__":
    main()
