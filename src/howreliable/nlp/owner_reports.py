"""Streaming component-only extraction and accounting; never loads an ML model."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from howreliable.data.features.nhtsa_complaints import iter_clean_records
from howreliable.nlp.components import (
    LEXICON_VERSION,
    MATCHER_VERSION,
    lexicon_sha256,
)
from howreliable.nlp.context import ASSERTION_VERSION, ASSOCIATION_VERSION, extract_report
from howreliable.nlp.grouping import (
    GROUPING_VERSION,
    MEMBERSHIP_VERSION,
    add_membership,
    create_memberships,
    finalize_memberships,
    group_fields,
    grouping_counts,
)
from howreliable.nlp.schemas import ExtractionRow, ProcessingConfig, RunProvenance, Status
from howreliable.nlp.symptoms import SYMPTOM_LEXICON_VERSION, symptom_lexicon_sha256


class ProcessingError(ValueError):
    """Input or accounting validation failed; no completed run is published."""


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: object) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _git_identity() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parents[3]
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout
        return revision, bool(dirty)
    except (OSError, subprocess.SubprocessError):
        return None, None


def _code_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = [
        *Path(__file__).parent.glob("*.py"),
        root / "data/features/nhtsa_complaints.py",
        root / "data/features/schema.py",
        root / "data/cleaning/models.py",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode())
        digest.update(b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _output_paths(
    input_path: Path, output_path: Path, provenance_path: Path, membership_path: Path
) -> None:
    inputs = {
        input_path.resolve(),
        input_path.with_suffix(input_path.suffix + ".provenance.json").resolve(),
    }
    targets = [output_path.resolve(), provenance_path.resolve(), membership_path.resolve()]
    if len(set(targets)) != len(targets) or any(p in inputs for p in targets):
        raise ProcessingError("input/output paths must be distinct")
    # Within this checkout, write only into the separate, ignored NLP artifact areas.
    root = Path(__file__).resolve().parents[3]
    allowed = [root / "data/processed/nlp", root / "artifacts/nlp"]
    for p in targets:
        if p.is_relative_to(root) and not any(p.is_relative_to(a) for a in allowed):
            raise ProcessingError("repository outputs must be inside an NLP artifact directory")
        if p.exists() or p.is_symlink():
            raise FileExistsError("refusing to overwrite an existing NLP output")


def _row(clean: dict[str, Any], config: ProcessingConfig) -> ExtractionRow:
    for key in ("event_id", "source_type", "source_record_id", "broad_vehicle_id"):
        if not clean[key].strip():
            raise ProcessingError("clean input has an empty required identifier")
    ref = clean["source_reference_id"]
    fallback = ref is None or not ref.strip()
    group = [
        clean["source_type"],
        "CMPLID" if fallback else "ODINO",
        clean["source_record_id"] if fallback else ref,
    ]
    group_id = "report_" + hashlib.sha256(_json(group)).hexdigest()
    text = clean["narrative"]
    report_date = date.fromisoformat(clean["report_date"]) if clean["report_date"] else None
    status: Status = "processed"
    if config.mode == "as_of" and report_date is None:
        status = "excluded_missing_report_date"
    elif config.cutoff is not None and report_date is not None and report_date > config.cutoff:
        status = "excluded_after_cutoff"
    elif text is None:
        status = "missing_text"
    elif not text.strip():
        status = "empty_text"
    components, symptoms, associations = (
        extract_report(text) if status == "processed" and text is not None else ((), (), ())
    )
    return ExtractionRow(
        schema_version="howreliable-owner-report-extraction-1.2",
        event_id=clean["event_id"],
        source_type=clean["source_type"],
        source_record_id=clean["source_record_id"],
        source_reference_id=ref,
        broad_vehicle_id=clean["broad_vehicle_id"],
        known_configuration_id=clean["known_configuration_id"],
        normalized_make=clean["normalized_make"],
        normalized_model=clean["normalized_model"],
        model_year=clean["model_year"],
        report_group_id=group_id,
        report_group_fallback=fallback,
        narrative_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
        if text is not None and text.strip()
        else None,
        report_date=report_date,
        occurrence_date=date.fromisoformat(clean["occurrence_date"])
        if clean["occurrence_date"]
        else None,
        mode=config.mode,
        cutoff=config.cutoff,
        processing_status=status,
        quality_flags=tuple(clean["quality_flags"]),
        structured_component=clean["component"],
        source_component=clean["source_component"],
        mentions=tuple(
            sorted((*components, *symptoms), key=lambda m: (m.start, m.end, m.kind, m.code))
        ),
        component_mentions=components,
        symptom_mentions=symptoms,
        associations=associations,
    )


def process_owner_reports(
    input_path: Path,
    output_path: Path,
    *,
    provenance_path: Path | None = None,
    config: ProcessingConfig | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunProvenance:
    """Stage a run; provenance is published last and is its required completion marker.

    Normal exceptions and KeyboardInterrupt remove published files owned by this run.
    Process kill/power loss may leave an uncommitted JSONL; without its matching complete
    provenance it must never be consumed as a finished run. Existing files are never removed.
    """
    config = config or ProcessingConfig()
    provenance_path = provenance_path or output_path.with_suffix(
        output_path.suffix + ".provenance.json"
    )
    membership_path = output_path.with_suffix(output_path.suffix + ".membership.sqlite")
    _output_paths(input_path, output_path, provenance_path, membership_path)
    timestamp = clock()
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ProcessingError("generation timestamp must be timezone-aware")
    timestamp = timestamp.astimezone(UTC)
    source_meta = input_path.with_suffix(input_path.suffix + ".provenance.json")
    metadata = json.loads(source_meta.read_bytes())
    if not isinstance(metadata, dict):
        raise ProcessingError("cleaning provenance must be a JSON object")
    count = metadata.get("cleaned_count")
    if type(count) is not int or count < 0:
        raise ProcessingError("cleaning provenance requires a nonnegative cleaned_count")
    for key in ("cleaning_version", "mapping_version"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise ProcessingError("cleaning provenance lacks version identity")
    input_hash, meta_hash = _hash(input_path), _hash(source_meta)
    code_revision, dirty = _git_identity()
    published: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="howreliable-nlp-") as directory:
            temp = Path(directory)
            with closing(sqlite3.connect(temp / "index.sqlite")) as db:
                db.execute("PRAGMA cache_size=-8192")
                db.execute("CREATE TABLE events (id TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE reports (id TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE texts (id TEXT PRIMARY KEY)")
                db.execute(
                    "CREATE TABLE variants (report TEXT, text TEXT, PRIMARY KEY(report,text))"
                )
                create_memberships(db)
                statuses: Counter[str] = Counter()
                total = fallbacks = 0
                with (temp / "rows").open("wb") as out:
                    for clean in iter_clean_records(input_path):
                        row = _row(clean, config)
                        try:
                            db.execute("INSERT INTO events(id) VALUES (?)", (row.event_id,))
                        except sqlite3.IntegrityError as error:
                            raise ProcessingError("duplicate clean event_id") from error
                        db.execute(
                            "INSERT OR IGNORE INTO reports VALUES (?)", (row.report_group_id,)
                        )
                        if row.narrative_sha256 is not None:
                            db.execute(
                                "INSERT OR IGNORE INTO texts VALUES (?)", (row.narrative_sha256,)
                            )
                            db.execute(
                                "INSERT OR IGNORE INTO variants VALUES (?,?)",
                                (row.report_group_id, row.narrative_sha256),
                            )
                        statuses[row.processing_status] += 1
                        total += 1
                        add_membership(db, row, total)
                        fallbacks += row.report_group_fallback
                        out.write(_json(row.model_dump(mode="json")))
                if total != count or sum(statuses.values()) != total:
                    raise ProcessingError("record conservation/provenance count mismatch")
                if _hash(input_path) != input_hash or _hash(source_meta) != meta_hash:
                    raise ProcessingError("input or provenance changed while processing")
                finalize_memberships(db)
                with (temp / "rows").open("rb") as source, (temp / "final_rows").open("wb") as out:
                    for line in source:
                        value = json.loads(line)
                        value.update(group_fields(db, value["report_group_id"]))
                        value["schema_version"] = "howreliable-owner-report-extraction-1.3"
                        value["eligible"] = not value["processing_status"].startswith("excluded_")
                        finalized = ExtractionRow.model_validate_json(json.dumps(value))
                        out.write(_json(finalized.model_dump(mode="json")))
                os.replace(temp / "final_rows", temp / "rows")

                def scalar(query: str) -> int:
                    return int(db.execute(query).fetchone()[0])

                provenance = RunProvenance(
                    grouping_version=GROUPING_VERSION,
                    membership_schema_version=MEMBERSHIP_VERSION,
                    membership_filename=membership_path.name,
                    membership_sha256=_hash(temp / "index.sqlite"),
                    membership_counts=grouping_counts(db),
                    symptom_extraction_implemented=True,
                    component_lexicon_version=LEXICON_VERSION,
                    component_lexicon_sha256=lexicon_sha256(),
                    component_matcher_version=MATCHER_VERSION,
                    symptom_lexicon_version=SYMPTOM_LEXICON_VERSION,
                    symptom_lexicon_sha256=symptom_lexicon_sha256(),
                    assertion_rules_version=ASSERTION_VERSION,
                    association_rules_version=ASSOCIATION_VERSION,
                    generation_utc=timestamp,
                    input_filename=input_path.name,
                    input_sha256=input_hash,
                    input_provenance_sha256=meta_hash,
                    source_cleaning_provenance=metadata,
                    input_record_count=total,
                    output_filename=output_path.name,
                    output_sha256=_hash(temp / "rows"),
                    output_size_bytes=(temp / "rows").stat().st_size,
                    output_record_count=total,
                    status_counts=dict(sorted(statuses.items())),
                    unique_report_count=scalar("SELECT count(*) FROM reports"),
                    conflicting_report_group_count=scalar(
                        "SELECT count(*) FROM (SELECT report FROM variants "
                        "GROUP BY report HAVING count(*)>1)"
                    ),
                    unique_nonempty_narrative_count=scalar("SELECT count(*) FROM texts"),
                    report_group_fallback_count=fallbacks,
                    configuration=config,
                    configuration_sha256=hashlib.sha256(
                        _json(config.model_dump(mode="json"))
                    ).hexdigest(),
                    code_sha256=_code_hash(),
                    code_revision=code_revision,
                    dirty_worktree=dirty,
                    python_version=platform.python_version(),
                    dependency_versions={
                        "pydantic": version("pydantic"),
                        "sqlite": sqlite3.sqlite_version,
                    },
                    policies={
                        "order": "clean input order",
                        "encoding": "UTF-8; LF; no BOM",
                        "normalization": (
                            "per-code-point NFKC/casefold; dash variants; original offsets"
                        ),
                        "assertion": "eight-token preceding clause scope; conservative abstention",
                        "grouping": "source_type + ODINO; CMPLID fallback",
                        "temporal": "report_date inclusive; missing date excluded in as_of",
                        "completion": "provenance last; verify output hash/count before use",
                        "evaluation_grouping": (
                            "transitive report/exact-text closure; no splits assigned"
                        ),
                        "group_counts": "all input rows, including date-excluded rows",
                        "eligible_counts": "row report_date only; excluded rows never contribute",
                        "conflicting_dates": (
                            "flag all differing values including missing; no imputation"
                        ),
                        "snapshot": "report dates do not prove historical revision availability",
                    },
                )
                (temp / "provenance").write_bytes(_json(provenance.model_dump(mode="json")))
            for staged, target in [
                (temp / "rows", output_path),
                (temp / "index.sqlite", membership_path),
                (temp / "provenance", provenance_path),
            ]:
                target.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation handles races as well as initial overwrite checks.
                with target.open("xb") as out:
                    published.append(target)
                    with staged.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            out.write(chunk)
                    out.flush()
                    os.fsync(out.fileno())
        return provenance
    except BaseException:
        # Do not swallow interrupts, and do not remove another run's pre-existing files.
        for target in reversed(published):
            target.unlink(missing_ok=True)
        raise
