"""Development-only working copies and narrative-safe semantic validation."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from howreliable.nlp.annotations import AnnotationUnit
from howreliable.nlp.owner_reports import _hash, _json
from howreliable.nlp.schemas import ComponentMention, EvidenceSpan, StrictModel, SymptomMention

STATES = Literal["pending", "in_progress", "annotated", "needs_adjudication", "reviewed"]
STATE_MAP = {
    "pending": "pending",
    "in_progress": "pending",
    "annotated": "annotated",
    "needs_adjudication": "disputed",
    "reviewed": "reviewed",
}


class ReviewError(ValueError):
    """Message contains only fixed error codes, never source text."""


class WorkingReport(StrictModel):
    annotation: AnnotationUnit
    state: STATES = "pending"
    completed_variants: tuple[str, ...] = ()
    confirmed_empty_variants: tuple[str, ...] = ()


class WorkingFile(StrictModel):
    schema_version: Literal["howreliable-development-review-1.0"] = (
        "howreliable-development-review-1.0"
    )
    source_sha256: str
    revision: int = Field(ge=0)
    reports: tuple[WorkingReport, ...]


def source_path(path: Path) -> Path:
    """Allow only an explicitly selected development/worksheet.jsonl."""
    resolved = path.resolve()
    for candidate in (path, resolved):
        if any(
            part.lower() in {"private", "held_out", "held-out"}
            or "prediction" in part.lower()
            or "mapping" in part.lower()
            or "partition-manifest" in part.lower()
            for part in candidate.parts
        ):
            raise ReviewError("forbidden_source_path")
    if resolved.name != "worksheet.jsonl" or resolved.parent.name != "development":
        raise ReviewError("development_worksheet_required")
    return resolved


def read_source(path: Path) -> tuple[AnnotationUnit, ...]:
    path = source_path(path)
    try:
        units = tuple(
            AnnotationUnit.model_validate_json(line) for line in path.read_bytes().splitlines()
        )
    except (ValidationError, ValueError):
        raise ReviewError("invalid_source_schema") from None
    if not units or len({u.annotation_id for u in units}) != len(units):
        raise ReviewError("invalid_source_identities")
    for unit in units:
        if (
            unit.partition != "development"
            or unit.status != "pending"
            or any(
                v.component_annotations or v.symptom_annotations or v.association_annotations
                for v in unit.variants
            )
        ):
            raise ReviewError("frozen_empty_development_source_required")
        if not unit.variants or len({v.variant_id for v in unit.variants}) != len(unit.variants):
            raise ReviewError("invalid_variant_identities")
        for variant in unit.variants:
            text = variant.narrative
            digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else None
            if digest != variant.narrative_sha256:
                raise ReviewError("source_narrative_hash_mismatch")
    return units


def working_path(path: Path, source: Path) -> Path:
    resolved = path.resolve()
    root = Path(__file__).resolve().parents[3]
    if "annotation-work" not in resolved.parts or resolved.is_relative_to(source.parent.parent):
        raise ReviewError("separate_annotation_work_directory_required")
    if resolved.is_relative_to(root) and not any(
        resolved.is_relative_to(root / p) for p in ("artifacts/nlp", "data/processed/nlp")
    ):
        raise ReviewError("ignored_nlp_work_directory_required")
    if any(p.lower() in {"private", "held_out", "held-out"} for p in resolved.parts):
        raise ReviewError("forbidden_work_path")
    if path.is_symlink() or resolved.suffix != ".json":
        raise ReviewError("regular_json_working_file_required")
    return resolved


def validate_working(
    source: Path, document: WorkingFile, *, require_complete: bool = False
) -> None:
    originals = read_source(source)
    if document.source_sha256 != _hash(source) or len(originals) != len(document.reports):
        raise ReviewError("source_identity_mismatch")
    for index, (original, work) in enumerate(zip(originals, document.reports, strict=True)):

        def fail(code: str, position: int = index) -> None:
            raise ReviewError(f"report_{position + 1}:{code}")

        unit = work.annotation
        if (unit.annotation_id, unit.partition, unit.schema_version) != (
            original.annotation_id,
            original.partition,
            original.schema_version,
        ) or len(unit.variants) != len(original.variants):
            fail("immutable_identity_changed")
        ids = {v.variant_id for v in original.variants}
        completed, empty = set(work.completed_variants), set(work.confirmed_empty_variants)
        if (
            len(completed) != len(work.completed_variants)
            or len(empty) != len(work.confirmed_empty_variants)
            or not empty <= completed <= ids
        ):
            fail("invalid_variant_completion")
        all_mention_ids: set[str] = set()
        has_labels = False
        for old, variant in zip(original.variants, unit.variants, strict=True):
            exclude = {"component_annotations", "symptom_annotations", "association_annotations"}
            if old.model_dump(exclude=exclude) != variant.model_dump(exclude=exclude):
                fail("immutable_variant_changed")
            text = variant.narrative or ""
            mentions: tuple[ComponentMention | SymptomMention, ...] = (
                *variant.component_annotations,
                *variant.symptom_annotations,
            )
            has_labels |= bool(mentions or variant.association_annotations)
            for mention in mentions:
                if "assertion" not in mention.model_fields_set:
                    fail("explicit_assertion_required")
                if mention.mention_id in all_mention_ids:
                    fail("duplicate_mention_id")
                all_mention_ids.add(mention.mention_id)
                if (
                    not mention.mention_id.strip()
                    or not mention.rule_id.strip()
                    or not mention.ambiguity_reason.strip()
                ):
                    fail("blank_annotation_metadata")
                spans: tuple[ComponentMention | EvidenceSpan, ...] = (
                    mention,
                    *mention.assertion_cue_spans,
                )
                for span in spans:
                    if (
                        span.start < 0
                        or span.end > len(text)
                        or text[span.start : span.end] != span.evidence_text
                    ):
                        fail("invalid_evidence_offset")
                if len(set((c.start, c.end) for c in mention.assertion_cue_spans)) != len(
                    mention.assertion_cue_spans
                ):
                    fail("duplicate_cue_span")
            components = {m.mention_id: m for m in variant.component_annotations}
            symptoms = {m.mention_id: m for m in variant.symptom_annotations}
            links: set[tuple[str, str]] = set()
            for association in variant.association_annotations:
                pair = (association.component_mention_id, association.symptom_mention_id)
                c, s = components.get(pair[0]), symptoms.get(pair[1])
                if c is None or s is None or pair in links:
                    fail("invalid_association_reference")
                assert c is not None and s is not None
                links.add(pair)
                if c.assertion == "unresolved" or s.assertion == "unresolved":
                    fail("unresolved_association_endpoint")
                if (
                    association.end > len(text)
                    or text[association.start : association.end] != association.evidence_text
                    or association.start > min(c.start, s.start)
                    or association.end < max(c.end, s.end)
                    or not association.rule_id.strip()
                ):
                    fail("invalid_association_evidence")
            if variant.variant_id in completed:
                if not mentions and variant.variant_id not in empty:
                    fail("empty_review_not_confirmed")
                if mentions and variant.variant_id in empty:
                    fail("empty_review_contains_labels")
        if unit.status != STATE_MAP[work.state]:
            fail("state_status_mismatch")
        if work.state == "pending" and (has_labels or completed or empty):
            fail("pending_contains_work")
        if work.state in {"annotated", "reviewed"} and (
            completed != ids or not (unit.annotator_id or "").strip()
        ):
            fail("incomplete_annotation")
        if work.state == "reviewed" and (
            not (unit.reviewer_id or "").strip() or unit.reviewer_id == unit.annotator_id
        ):
            fail("independent_reviewer_required")
        if work.state == "needs_adjudication" and not (unit.review_notes or "").strip():
            fail("adjudication_notes_required")
        if require_complete and work.state not in {"annotated", "reviewed"}:
            fail("report_not_complete")


def parse_working(payload: bytes) -> WorkingFile:
    try:
        return WorkingFile.model_validate_json(payload)
    except (ValueError, ValidationError):
        raise ReviewError("invalid_working_schema") from None


class ReviewStore:
    def __init__(self, source: Path, working: Path) -> None:
        self.source = source_path(source)
        self.originals = read_source(self.source)
        self.source_hash = _hash(self.source)
        self.working = working_path(working, self.source)
        self.lock = threading.RLock()
        self.read()

    def read(self) -> WorkingFile:
        if working_path(self.working, self.source) != self.working:
            raise ReviewError("working_path_redirected")
        if _hash(self.source) != self.source_hash:
            raise ReviewError("frozen_source_changed")
        if self.working.exists():
            document = parse_working(self.working.read_bytes())
        else:
            document = WorkingFile(
                source_sha256=self.source_hash,
                revision=0,
                reports=tuple(WorkingReport(annotation=u) for u in self.originals),
            )
        validate_working(self.source, document)
        return document

    def save(self, index: int, report: WorkingReport, revision: int) -> WorkingFile:
        with self.lock:
            self.working.parent.mkdir(parents=True, exist_ok=True)
            lock = self.working.with_suffix(".lock")
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise ReviewError("save_lock_busy") from None
            os.close(fd)
            temporary: Path | None = None
            try:
                current = self.read()
                if current.revision != revision:
                    raise ReviewError("stale_revision_reload_required")
                if not 0 <= index < len(current.reports):
                    raise ReviewError("unknown_report")
                rows = list(current.reports)
                rows[index] = report
                updated = WorkingFile(
                    source_sha256=self.source_hash, revision=revision + 1, reports=tuple(rows)
                )
                validate_working(self.source, updated)
                if self.working.exists():
                    backup = self.working.parent / "backups"
                    backup.mkdir(exist_ok=True)
                    if not backup.resolve().is_relative_to(self.working.parent):
                        raise ReviewError("backup_path_redirected")
                    with tempfile.TemporaryDirectory(prefix=".backup-stage-", dir=backup) as folder:
                        staged_backup = Path(folder) / "saved.json"
                        with staged_backup.open("xb") as handle:
                            handle.write(self.working.read_bytes())
                            handle.flush()
                            os.fsync(handle.fileno())
                        os.rename(
                            staged_backup,
                            backup / f"revision-{current.revision}-{time.time_ns()}.json",
                        )
                descriptor, name = tempfile.mkstemp(dir=self.working.parent, prefix=".review-")
                temporary = Path(name)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(_json(updated.model_dump(mode="json")))
                    handle.flush()
                    os.fsync(handle.fileno())
                if working_path(self.working, self.source) != self.working:
                    raise ReviewError("working_path_redirected")
                if _hash(self.source) != self.source_hash:
                    raise ReviewError("frozen_source_changed")
                os.replace(temporary, self.working)
                return updated
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a development annotation working copy")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--working", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = source_path(args.source)
        path = working_path(args.working, source)
        document = parse_working(path.read_bytes())
        validate_working(source, document, require_complete=args.require_complete)
    except (ReviewError, OSError) as error:
        print(str(error) if isinstance(error, ReviewError) else "working_file_unavailable")
        return 1
    print(
        f"Validated {len(document.reports)} development reports; states="
        f"{dict(Counter(r.state for r in document.reports))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
