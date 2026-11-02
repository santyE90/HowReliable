"""Synthetic-only preliminary development scoring; no real gold or holdout access."""

import json
from pathlib import Path
from typing import Any

import pytest

from howreliable.nlp.annotation_review import ReviewError, parse_working
from howreliable.nlp.development_evaluation import Mention, evaluate, match, metrics
from howreliable.nlp.owner_reports import _hash, _json
from test_annotation_review import TEXT, draft, labeled, setup
from test_owner_report_nlp import TIME, inputs, record, run


def fixture(tmp: Path, *, empty: bool = False, completed: bool = True) -> tuple[Path, Path, Path]:
    source, working, store = setup(tmp)
    value = draft(store) if empty else labeled(store)
    report = value["reports"][0]
    if completed:
        report["state"] = "annotated"
        report["annotation"]["status"] = "annotated"
        report["annotation"]["annotator_id"] = "human_synthetic"
        report["completed_variants"] = ["v1"]
        report["confirmed_empty_variants"] = ["v1"] if empty else []
    store.save(0, parse_working(_json(value)).reports[0], revision=0)
    clean = tmp / "synthetic-input"
    clean.mkdir()
    extraction = clean / "extraction.jsonl"
    run(inputs(clean, [record(1, narrative=TEXT), record(2, narrative=TEXT)]), extraction)
    rows = [json.loads(line) for line in extraction.read_bytes().splitlines()]
    gold = labeled(store)["reports"][0]["annotation"]["variants"][0]
    for row in rows:
        row["component_mentions"] = gold["component_annotations"]
        row["symptom_mentions"] = gold["symptom_annotations"]
        row["mentions"] = sorted(
            [*row["component_mentions"], *row["symptom_mentions"]],
            key=lambda m: (m["start"], m["end"], m["kind"], m["code"]),
        )
        row["associations"] = gold["association_annotations"]
    predictions = source.parent.parent / "private/predictions.jsonl"
    predictions.parent.mkdir()
    predictions.write_bytes(
        _json({"annotation_id": "ann_synthetic", "partition": "development", "predictions": rows})
    )
    freeze(source, predictions)
    return source, working, predictions


def freeze(source: Path, predictions: Path) -> None:
    root = source.parent.parent
    (root / "provenance.json").write_bytes(
        _json(
            {
                "complete": True,
                "outputs": {
                    p.relative_to(root).as_posix(): {"sha256": _hash(p)}
                    for p in (source, predictions)
                },
            }
        )
    )


def change_predictions(source: Path, predictions: Path, change: Any) -> None:
    packet = json.loads(predictions.read_bytes())
    change(packet)
    predictions.write_bytes(_json(packet))
    freeze(source, predictions)


def score(paths: tuple[Path, Path, Path], output: Path) -> dict[str, Any]:
    return evaluate(*paths, output, generation_utc=TIME)


def test_duplicate_rows_collapse_and_perfect_alignment(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    result = score(paths, tmp_path / "evaluation")
    assert result["evaluated_reports"] == 1
    c = result["primary_report_metrics"]["component"]
    assert (c["tp"], c["fp"], c["fn"], c["precision"], c["recall"], c["f1"]) == (
        1,
        0,
        0,
        1.0,
        1.0,
        1.0,
    )
    assert result["primary_report_metrics"]["symptom"]["precision"] is None
    assert result["span_metrics"]["exact"]["symptom"]["tp"] == 1
    assert result["association_metrics"]["exact"]["tp"] == 1
    assert result["assertions"]["accuracy"] == 1
    assert result["assertions"]["aligned_exact_spans"] == 2
    assert result["disagreement_types"] == {}
    assert result["per_category"]["component"]["engine"]["gold_support"] == 1


def test_assertion_mismatch_is_separate_from_span_and_report_errors(tmp_path: Path) -> None:
    paths = fixture(tmp_path)

    def mutate(packet: Any) -> None:
        for row in packet["predictions"]:
            row["symptom_mentions"][0]["assertion"] = "affirmed"
            next(m for m in row["mentions"] if m["kind"] == "symptom")["assertion"] = "affirmed"

    change_predictions(paths[0], paths[2], mutate)
    result = score(paths, tmp_path / "evaluation")
    assert result["assertions"]["accuracy"] == 0.5
    assert result["primary_report_metrics"]["symptom"]["fp"] == 1
    assert result["disagreement_types"]["assertion_mismatch"] == 1
    assert result["association_metrics"]["exact"]["fp"] == 1
    assert result["association_metrics"]["exact"]["fn"] == 1


def test_exact_vs_overlap_and_endpoint_associations(tmp_path: Path) -> None:
    paths = fixture(tmp_path)

    def mutate(packet: Any) -> None:
        for row in packet["predictions"]:
            for component in [
                row["component_mentions"][0],
                next(m for m in row["mentions"] if m["kind"] == "component"),
            ]:
                component["end"] -= 1
                component["evidence_text"] = component["evidence_text"][:-1]

    change_predictions(paths[0], paths[2], mutate)
    result = score(paths, tmp_path / "evaluation")
    assert result["span_metrics"]["exact"]["component"]["tp"] == 0
    assert result["span_metrics"]["overlap"]["component"]["tp"] == 1
    assert result["association_metrics"]["exact"]["tp"] == 0
    assert result["association_metrics"]["overlap"]["tp"] == 1


def test_empty_human_labels_are_valid_negative_examples(tmp_path: Path) -> None:
    paths = fixture(tmp_path, empty=True)
    result = score(paths, tmp_path / "evaluation")
    assert result["evaluated_reports"] == result["empty_gold_reports_evaluated"] == 1
    c = result["primary_report_metrics"]["component"]
    assert c["fp"] == 1 and c["precision"] == 0 and c["recall"] is None and c["f1"] == 0
    assert result["assertions"]["accuracy"] is None


@pytest.mark.parametrize("incomplete", [False, True])
def test_drafts_and_incomplete_claims_not_scored(tmp_path: Path, incomplete: bool) -> None:
    paths = fixture(tmp_path, completed=False)
    if incomplete:
        value = json.loads(paths[1].read_bytes())
        value["reports"][0]["state"] = "annotated"
        value["reports"][0]["annotation"]["status"] = "annotated"
        paths[1].write_bytes(_json(value))
    original = paths[1].read_bytes()
    result = score(paths, tmp_path / "evaluation")
    assert result["evaluated_reports"] == 0
    assert result["primary_report_metrics"]["component"]["precision"] is None
    assert paths[1].read_bytes() == original
    assert bool(result["annotation_validation_problems"]) == incomplete


def test_missing_coverage_is_not_false_negatives(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    change_predictions(paths[0], paths[2], lambda packet: packet.update(predictions=[]))
    result = score(paths, tmp_path / "evaluation")
    assert result["completed_eligible_reports"] == 1 and result["evaluated_reports"] == 0
    assert result["missing_prediction_reports"] == 1
    assert result["primary_report_metrics"]["component"]["fn"] == 0
    assert result["disagreement_types"] == {"missing_prediction": 1}


def test_held_out_payload_is_never_decoded(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    with paths[2].open("ab") as handle:
        handle.write(b'{"annotation_id":"opaque","partition":"held_out","predictions":NOT_JSON}\n')
    freeze(paths[0], paths[2])
    result = score(paths, tmp_path / "evaluation")
    assert result["evaluated_reports"] == 1


def test_matching_maximum_cardinality_not_greedy_and_deterministic_ties() -> None:
    def m(start: int, end: int) -> Mention:
        return Mention(start, end, "component", "engine", "affirmed")

    gold, pred = [m(0, 10), m(10, 20)], [m(0, 9), m(0, 20)]
    assert match(gold, pred, overlap=True) == [(0, 0), (1, 1)]
    assert match([m(0, 2), m(1, 3)], [m(0, 3)], overlap=True) == [(0, 0)]
    assert (
        metrics(0, 0, 0)["precision"]
        is metrics(0, 0, 0)["recall"]
        is metrics(0, 0, 0)["f1"]
        is None
    )


def test_checksums_determinism_overwrite_and_no_raw_text(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    before = {p: p.read_bytes() for p in paths}
    a, b = tmp_path / "eval-a", tmp_path / "eval-b"
    assert score(paths, a) == score(paths, b)
    for p in a.iterdir():
        assert p.read_bytes() == (b / p.name).read_bytes()
        assert TEXT.encode() not in p.read_bytes()
        assert b"evidence_text" not in p.read_bytes()
    provenance = json.loads((a / "provenance.json").read_bytes())
    for name, spec in provenance["outputs"].items():
        assert _hash(a / name) == spec["sha256"]
    with pytest.raises(FileExistsError):
        score(paths, a)
    assert all(p.read_bytes() == value for p, value in before.items())


def test_tampered_offsets_fail_without_publication(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    value = json.loads(paths[1].read_bytes())
    mention = value["reports"][0]["annotation"]["variants"][0]["component_annotations"][0]
    mention["start"] += 1
    mention["end"] += 1
    paths[1].write_bytes(_json(value))
    with pytest.raises(ReviewError, match="invalid_evidence_offset"):
        score(paths, tmp_path / "evaluation")
    assert not (tmp_path / "evaluation").exists()


def test_empty_emitted_output_is_fn_not_missing_coverage(tmp_path: Path) -> None:
    paths = fixture(tmp_path)

    def mutate(packet: Any) -> None:
        for row in packet["predictions"]:
            for key in ("component_mentions", "symptom_mentions", "mentions", "associations"):
                row[key] = []

    change_predictions(paths[0], paths[2], mutate)
    result = score(paths, tmp_path / "evaluation")
    assert result["evaluated_reports"] == 1 and result["missing_prediction_reports"] == 0
    c = result["primary_report_metrics"]["component"]
    assert c["fn"] == 1 and c["precision"] is None and c["recall"] == c["f1"] == 0


def test_interrupted_publication_cleans_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = fixture(tmp_path)

    def interrupt(*args: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("howreliable.nlp.development_evaluation.os.rename", interrupt)
    with pytest.raises(KeyboardInterrupt):
        score(paths, tmp_path / "evaluation")
    assert not (tmp_path / "evaluation").exists()
    assert not list(tmp_path.glob("evaluation-stage-*"))


def test_concurrent_input_changes_are_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import howreliable.nlp.development_evaluation as implementation

    paths = fixture(tmp_path)
    original = implementation.load_development_predictions

    def change(path: Path, allowed: set[str]) -> Any:
        result = original(path, allowed)
        with paths[1].open("ab") as handle:
            handle.write(b"\n")
        return result

    monkeypatch.setattr(implementation, "load_development_predictions", change)
    with pytest.raises(ReviewError, match="evaluation_input_changed"):
        score(paths, tmp_path / "evaluation")
    assert not (tmp_path / "evaluation").exists()


def test_explicit_held_out_paths_rejected_without_opening(tmp_path: Path) -> None:
    paths = fixture(tmp_path)
    with pytest.raises(ReviewError, match="held_out_input_forbidden"):
        evaluate(
            paths[0],
            paths[1],
            tmp_path / "held_out/predictions.jsonl",
            tmp_path / "eval",
            generation_utc=TIME,
        )
