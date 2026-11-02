"""New development-only variant predictions; no source mapping or held-out file access."""

from __future__ import annotations

import argparse
import os
import platform
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, model_validator

from howreliable.nlp.annotation_review import (
    ReviewError,
    parse_working,
    read_source,
    source_path,
    validate_working,
    working_path,
)
from howreliable.nlp.components import LEXICON_VERSION, MATCHER_VERSION, lexicon_sha256
from howreliable.nlp.context import ASSERTION_VERSION, ASSOCIATION_VERSION, extract_report
from howreliable.nlp.owner_reports import _code_hash, _git_identity, _hash, _json
from howreliable.nlp.schemas import (
    TAXONOMY_VERSION,
    Association,
    ComponentMention,
    StrictModel,
    SymptomMention,
)
from howreliable.nlp.symptoms import SYMPTOM_LEXICON_VERSION, symptom_lexicon_sha256

VERSION: Final = "howreliable-development-predictions-1.0"


class DevelopmentVariant(StrictModel):
    variant_id: str = Field(min_length=1)
    narrative_sha256: str | None
    source_row_count: int = Field(gt=0)
    component_mentions: tuple[ComponentMention, ...] = ()
    symptom_mentions: tuple[SymptomMention, ...] = ()
    associations: tuple[Association, ...] = ()

    @model_validator(mode="after")
    def references(self) -> DevelopmentVariant:
        mentions: tuple[ComponentMention | SymptomMention, ...] = (
            *self.component_mentions,
            *self.symptom_mentions,
        )
        if len({m.mention_id for m in mentions}) != len(mentions):
            raise ValueError("duplicate development mention identity")
        components = {m.mention_id: m for m in self.component_mentions}
        symptoms = {m.mention_id: m for m in self.symptom_mentions}
        for a in self.associations:
            c, s = components.get(a.component_mention_id), symptoms.get(a.symptom_mention_id)
            if c is None or s is None or c.assertion == "unresolved" or s.assertion == "unresolved":
                raise ValueError("invalid development association references")
            if a.start > min(c.start, s.start) or a.end < max(c.end, s.end):
                raise ValueError("development association must cover endpoints")
        return self


class DevelopmentPacket(StrictModel):
    annotation_id: str = Field(min_length=1)
    partition: Literal["development"] = "development"
    predictions: tuple[DevelopmentVariant, ...]


def generate(
    source: Path,
    working: Path,
    output: Path,
    *,
    generation_utc: datetime,
    expected_reports: int | None = None,
) -> dict[str, object]:
    source = source_path(source)
    working = working_path(working, source)
    source_hash, working_hash = _hash(source), _hash(working)
    originals = read_source(source)
    document = parse_working(working.read_bytes())
    validate_working(source, document)
    selected = {
        r.annotation.annotation_id for r in document.reports if r.state in {"annotated", "reviewed"}
    }
    if not selected or (expected_reports is not None and len(selected) != expected_reports):
        raise ReviewError("unexpected_completed_development_count")
    if generation_utc.tzinfo is None or generation_utc.utcoffset() != UTC.utcoffset(generation_utc):
        raise ReviewError("UTC_timestamp_required")
    resolved = output.resolve()
    root = Path(__file__).resolve().parents[3]
    if resolved.is_relative_to(source.parent.parent) or any(
        p.lower() in {"held_out", "held-out", "private"} for p in resolved.parts
    ):
        raise ReviewError("separate_development_prediction_directory_required")
    if any(p.resolve().is_relative_to(resolved) for p in (source, working)):
        raise ReviewError("output_contains_input")
    if resolved.is_relative_to(root) and not any(
        resolved.is_relative_to(root / p) for p in ("artifacts/nlp", "data/processed/nlp")
    ):
        raise ReviewError("ignored_nlp_output_required")
    if output.exists() or output.is_symlink():
        raise FileExistsError("prediction_output_exists")
    packets = []
    for unit in originals:
        if unit.annotation_id not in selected:
            continue
        values = []
        for v in unit.variants:
            components, symptoms, associations = (
                extract_report(v.narrative) if v.narrative and v.narrative.strip() else ((), (), ())
            )
            values.append(
                DevelopmentVariant(
                    variant_id=v.variant_id,
                    narrative_sha256=v.narrative_sha256,
                    source_row_count=v.source_row_count,
                    component_mentions=components,
                    symptom_mentions=symptoms,
                    associations=associations,
                )
            )
        packets.append(
            DevelopmentPacket(annotation_id=unit.annotation_id, predictions=tuple(values))
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dev-predictions-stage-", dir=output.parent) as temp:
        stage = Path(temp) / "run"
        stage.mkdir()
        predictions = stage / "development-predictions.jsonl"
        predictions.write_bytes(b"".join(_json(p.model_dump(mode="json")) for p in packets))
        revision, dirty = _git_identity()
        provenance: dict[str, object] = {
            "schema_version": VERSION,
            "complete": True,
            "partition": "development",
            "generation_utc": generation_utc.isoformat().replace("+00:00", "Z"),
            "source_sha256": source_hash,
            "working_sha256": working_hash,
            "prediction_sha256": _hash(predictions),
            "output_size_bytes": predictions.stat().st_size,
            "report_count": len(packets),
            "variant_count": sum(len(p.predictions) for p in packets),
            "source_row_count": sum(v.source_row_count for p in packets for v in p.predictions),
            "code_sha256": _code_hash(),
            "code_revision": revision,
            "dirty_worktree": dirty,
            "python_version": platform.python_version(),
            "source_prediction_provenance": {
                "taxonomy_version": TAXONOMY_VERSION,
                "component_lexicon_version": LEXICON_VERSION,
                "component_lexicon_sha256": lexicon_sha256(),
                "component_matcher_version": MATCHER_VERSION,
                "symptom_lexicon_version": SYMPTOM_LEXICON_VERSION,
                "symptom_lexicon_sha256": symptom_lexicon_sha256(),
                "assertion_rules_version": ASSERTION_VERSION,
                "association_rules_version": ASSOCIATION_VERSION,
            },
            "policy": "One prediction per development variant; retain row multiplicity. "
            "No fabricated IDs. Gold labels select reports only; extraction uses source text.",
        }
        (stage / "provenance.json").write_bytes(_json(provenance))
        if _hash(source) != source_hash or _hash(working) != working_hash:
            raise ReviewError("development_input_changed")
        if output.exists():
            raise FileExistsError("prediction_output_exists")
        os.rename(stage, output)
    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate only completed development variant predictions"
    )
    for name in ("source", "working", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-reports", type=int, default=5)
    parser.add_argument("--generation-utc", type=datetime.fromisoformat, required=True)
    args = parser.parse_args(argv)
    try:
        result = generate(
            args.source,
            args.working,
            args.output_dir,
            generation_utc=args.generation_utc,
            expected_reports=args.expected_reports,
        )
    except (ValueError, OSError):
        print("Development prediction generation stopped; check validation, paths and count.")
        return 1
    print(f"Generated {result['report_count']} development packets; no held-out files accessed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
