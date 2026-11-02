"""Synthetic-only development editor and semantic validation tests."""

import hashlib
import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.responses import HTMLResponse, Response
from fastapi.testclient import TestClient

from howreliable.nlp.annotation_review import (
    ReviewError,
    ReviewStore,
    WorkingFile,
    main,
    parse_working,
    read_source,
    validate_working,
)
from howreliable.nlp.owner_reports import _json
from howreliable.nlp.review_app import create_app
from howreliable.nlp.review_app import main as launch

TEXT = "🚗 Café: engine did not stall; battery leaked."


def setup(tmp: Path) -> tuple[Path, Path, ReviewStore]:
    source = tmp / "frozen/development/worksheet.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(
        _json(
            {
                "annotation_id": "ann_synthetic",
                "partition": "development",
                "variants": [
                    {
                        "variant_id": "v1",
                        "narrative": TEXT,
                        "narrative_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
                        "source_row_count": 2,
                        "report_dates": ["2022-01-01"],
                        "occurrence_dates": [None],
                    }
                ],
            }
        )
    )
    working = tmp / "annotation-work/development.json"
    return source, working, ReviewStore(source, working)


def draft(store: ReviewStore) -> dict[str, Any]:
    value: dict[str, Any] = store.read().model_dump(mode="json")
    value["reports"][0]["state"] = "in_progress"
    return value


def mention(kind: str, code: str, phrase: str, identity: str) -> dict[str, Any]:
    start = TEXT.index(phrase)
    return {
        "mention_id": identity,
        "kind": kind,
        "code": code,
        "start": start,
        "end": start + len(phrase),
        "evidence_text": phrase,
        "assertion": "affirmed",
        "rule_id": "human-guide-1.0",
        "ambiguity_reason": "Explicit referent in this synthetic text",
    }


def labeled(store: ReviewStore) -> dict[str, Any]:
    value = draft(store)
    variant = value["reports"][0]["annotation"]["variants"][0]
    variant["component_annotations"] = [mention("component", "engine", "engine", "c1")]
    symptom = mention("symptom", "stall_shutdown", "stall", "s1")
    symptom["assertion"] = "negated"
    symptom["assertion_cue_spans"] = [
        {"start": TEXT.index("not"), "end": TEXT.index("not") + 3, "evidence_text": "not"}
    ]
    variant["symptom_annotations"] = [symptom]
    start, end = TEXT.index("engine"), TEXT.index("stall") + 5
    variant["association_annotations"] = [
        {
            "component_mention_id": "c1",
            "symptom_mention_id": "s1",
            "start": start,
            "end": end,
            "evidence_text": TEXT[start:end],
            "rule_id": "human-guide-1.0",
        }
    ]
    return value


def parse(value: dict[str, Any]) -> WorkingFile:
    return parse_working(_json(value))


def test_unicode_semantics_save_resume_backups_and_stale_edits(tmp_path: Path) -> None:
    source, working, store = setup(tmp_path)
    before = source.read_bytes()
    document = parse(labeled(store))
    validate_working(source, document)
    saved = store.save(0, document.reports[0], revision=0)
    assert saved.revision == 1 and source.read_bytes() == before
    resumed = ReviewStore(source, working).read()
    assert resumed == saved
    before_work = working.read_bytes()
    with pytest.raises(ReviewError, match="stale_revision"):
        store.save(0, saved.reports[0], revision=0)
    assert working.read_bytes() == before_work
    store.save(0, saved.reports[0], revision=1)
    backups = list((working.parent / "backups").glob("*.json"))
    assert len(backups) == 1 and backups[0].read_bytes() == before_work


@pytest.mark.parametrize(
    "case",
    [
        "offset",
        "cue",
        "duplicate",
        "endpoint",
        "narrative",
        "identity",
        "assertion_missing",
        "state",
        "unresolved_link",
    ],
)
def test_reject_semantic_errors(tmp_path: Path, case: str) -> None:
    source, _, store = setup(tmp_path)
    value = labeled(store)
    report = value["reports"][0]
    unit = report["annotation"]
    variant = unit["variants"][0]
    c = variant["component_annotations"][0]
    s = variant["symptom_annotations"][0]
    if case == "offset":
        c["start"] += 1
        c["end"] += 1
    elif case == "cue":
        s["assertion_cue_spans"][0]["start"] += 1
        s["assertion_cue_spans"][0]["end"] += 1
    elif case == "duplicate":
        s["mention_id"] = c["mention_id"]
    elif case == "endpoint":
        variant["association_annotations"][0]["symptom_mention_id"] = "missing"
    elif case == "narrative":
        variant["narrative"] += " changed"
    elif case == "identity":
        unit["partition"] = "held_out"
    elif case == "assertion_missing":
        del c["assertion"]
    elif case == "state":
        report["state"] = "pending"
    elif case == "unresolved_link":
        s["assertion"] = "unresolved"
    with pytest.raises(ReviewError):
        validate_working(source, parse(value))


def test_explicit_empty_completion_and_independent_review(tmp_path: Path) -> None:
    source, _, store = setup(tmp_path)
    value = draft(store)
    r = value["reports"][0]
    r["state"] = "annotated"
    r["annotation"]["status"] = "annotated"
    r["annotation"]["annotator_id"] = "human_a"
    r["completed_variants"] = ["v1"]
    with pytest.raises(ReviewError, match="empty_review_not_confirmed"):
        validate_working(source, parse(value))
    r["confirmed_empty_variants"] = ["v1"]
    validate_working(source, parse(value), require_complete=True)
    r["state"] = "reviewed"
    r["annotation"]["status"] = "reviewed"
    r["annotation"]["reviewer_id"] = "human_a"
    with pytest.raises(ReviewError, match="independent_reviewer"):
        validate_working(source, parse(value))
    r["annotation"]["reviewer_id"] = "human_b"
    validate_working(source, parse(value), require_complete=True)


def test_draft_incomplete_and_adjudication_states(tmp_path: Path) -> None:
    source, _, store = setup(tmp_path)
    value = draft(store)
    validate_working(source, parse(value))
    with pytest.raises(ReviewError, match="report_not_complete"):
        validate_working(source, parse(value), require_complete=True)
    r = value["reports"][0]
    r["state"] = "needs_adjudication"
    r["annotation"]["status"] = "disputed"
    with pytest.raises(ReviewError, match="adjudication_notes"):
        validate_working(source, parse(value))
    r["annotation"]["review_notes"] = "Synthetic scope requires another reviewer."
    validate_working(source, parse(value))


def test_atomic_write_failure_preserves_previous_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, working, store = setup(tmp_path)
    document = parse(draft(store))
    store.save(0, document.reports[0], revision=0)
    original = working.read_bytes()

    def fail(*args: Any) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr("howreliable.nlp.annotation_review.os.replace", fail)
    with pytest.raises(OSError):
        store.save(0, document.reports[0], revision=1)
    assert working.read_bytes() == original and source.exists()
    assert not list(working.parent.glob(".review-*"))
    assert not working.with_suffix(".lock").exists()


@pytest.mark.parametrize(
    "path",
    [
        "held_out/worksheet.jsonl",
        "private/predictions.jsonl",
        "private/mapping.jsonl",
        "partition-manifest.json",
    ],
)
def test_forbidden_files_refused_before_read(tmp_path: Path, path: str) -> None:
    target = tmp_path / path
    with pytest.raises(ReviewError):
        read_source(target)


def test_frozen_source_changed_and_work_path_protection(tmp_path: Path) -> None:
    source, _, store = setup(tmp_path)
    with pytest.raises(ReviewError):
        ReviewStore(source, source)
    with pytest.raises(ReviewError):
        ReviewStore(source, source.parent / "annotation-work/draft.json")
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ReviewError, match="frozen_source_changed"):
        store.read()


def test_schema_errors_are_narrative_safe(tmp_path: Path) -> None:
    _, _, store = setup(tmp_path)
    value = labeled(store)
    value["reports"][0]["annotation"]["variants"][0]["component_annotations"][0]["code"] = "invalid"
    with pytest.raises(ReviewError, match="invalid_working_schema") as error:
        parse(value)
    assert TEXT not in str(error.value)


def test_validate_cli_is_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source, working, store = setup(tmp_path)
    store.save(0, parse(draft(store)).reports[0], revision=0)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    args = ["--source", str(source), "--working", str(working)]
    assert main(args) == 0
    assert main([*args, "--require-complete"]) == 1
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert TEXT not in capsys.readouterr().out


def test_http_isolated_routes_save_and_origin_guards(tmp_path: Path) -> None:
    source, working, store = setup(tmp_path)
    app = create_app(source, working)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/").status_code == 200
        assert client.get("/app.js").status_code == 200
        assert client.get("/style.css").status_code == 200
        session = client.get("/api/session")
        assert TEXT not in session.text
        assert "engine" in session.json()["components"]
        assert session.headers["cache-control"] == "no-store"
        assert (
            client.get("/api/report/0").json()["report"]["annotation"]["partition"] == "development"
        )
        payload = {"revision": 0, "report": draft(store)["reports"][0]}
        assert client.post("/api/report/0", json=payload).status_code == 403
        headers = {"X-Review-Request": "1", "Origin": "http://127.0.0.1:8765"}
        assert client.post("/api/report/0", json=payload, headers=headers).status_code == 200
        assert client.post("/api/report/0", json=payload, headers=headers).status_code == 409
        assert client.get("/api/session", headers={"host": "evil.example:8765"}).status_code == 403
        assert (
            client.get("/api/session", headers={"origin": "https://evil.example"}).status_code
            == 403
        )
        assert (
            client.get("/api/session", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        )
        assert client.get("/held_out/worksheet.jsonl").status_code == 404
        assert client.get("/private/predictions.jsonl").status_code == 404
        assert client.get("/partition-manifest.json").status_code == 404
        assert client.get("/api/report/99").status_code == 409
        payload["report"]["annotation"]["variants"][0]["extra"] = TEXT
        response = client.post("/api/report/0", json=payload, headers=headers)
        assert response.status_code == 409 and TEXT not in response.text


def test_launch_forces_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, working, _ = setup(tmp_path)
    calls = []
    monkeypatch.setattr("howreliable.nlp.review_app.uvicorn.run", lambda *a, **kw: calls.append(kw))
    assert launch(["--source", str(source), "--working", str(working)]) == 0
    assert calls[0]["host"] == "127.0.0.1" and not calls[0]["access_log"]


def test_browser_unicode_selection_conversion() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable; Unicode server checks still covered")
    script = Path(__file__).resolve().parents[1] / "src/howreliable/nlp/review.js"
    code = (
        "const {selectedSpan}=require(process.argv[1]); "
        "console.log(JSON.stringify(selectedSpan(...JSON.parse(process.argv[2]))));"
    )
    phrase = "engine"
    start = TEXT.index(phrase)
    result = subprocess.run(
        [node, "-e", code, str(script), json.dumps([TEXT, TEXT[:start], phrase])],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "start": start,
        "end": start + len(phrase),
        "evidence_text": phrase,
    }


def test_headless_browser_selection_save_and_reload(tmp_path: Path) -> None:
    """Optional installed browser; all text and labels in this test are synthetic."""
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not edge.exists():
        pytest.skip("Installed headless Edge unavailable")
    source, working, store = setup(tmp_path)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    app = create_app(source, working, port=port)
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/"]

    @app.get("/")
    def page() -> HTMLResponse:
        path = Path(__file__).resolve().parents[1] / "src/howreliable/nlp/review.html"
        return HTMLResponse(
            path.read_text().replace("</head>", '<script src="/smoke.js" defer></script></head>')
        )

    @app.get("/smoke.js")
    def smoke() -> Response:
        return Response(
            r"""
        (async () => {
          const el = id => document.getElementById(id);
          async function wait(predicate) {
            for (let i=0;i<300;i++) {
              if (predicate()) return;
              await new Promise(resolve => setTimeout(resolve, 30));
            }
            throw Error('timeout');
          }
          function input(id, value) {
            el(id).value=value; el(id).dispatchEvent(new Event('input'));
          }
          try {
            await wait(() => el('identity').textContent.includes('ann_synthetic'));
            if (!sessionStorage.getItem('saved')) {
              const text=el('narrative').firstChild;
              const range=document.createRange(), start=text.textContent.indexOf('engine');
              range.setStart(text,start); range.setEnd(text,start+6);
              window.getSelection().removeAllRanges(); window.getSelection().addRange(range);
              el('narrative').dispatchEvent(new MouseEvent('mouseup'));
              input('code','engine'); input('assertion','affirmed');
              input('reason','Explicit synthetic engine referent');
              el('add').click(); input('annotator','synthetic_reviewer');
              el('complete').click(); el('state').value='annotated';
              el('state').dispatchEvent(new Event('change')); el('save').click();
              await wait(() => el('message').textContent.startsWith('Saved revision 1'));
              sessionStorage.setItem('saved','yes'); window.location.reload(); return;
            }
            if (el('state').value !== 'annotated' || !el('mentions').textContent.includes('engine'))
              throw Error('resume_failed');
            const payload=await (await fetch('/api/report/0')).json();
            payload.report.annotation.variants[0].narrative += ' tamper';
            const response=await fetch('/api/report/0',{method:'POST',
              headers:{'Content-Type':'application/json','X-Review-Request':'1'},
              body:JSON.stringify(payload)});
            if (response.status !== 409) throw Error('immutable_guard_failed');
            document.body.setAttribute('data-review-smoke','passed');
          } catch(error) { document.body.setAttribute('data-review-smoke','failed'); }
        })();
        """,
            media_type="text/javascript",
        )

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="critical")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.02)
        result = subprocess.run(
            [
                str(edge),
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-component-update",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                f"--user-data-dir={tmp_path / 'browser-profile'}",
                "--dump-dom",
                "--virtual-time-budget=15000",
                f"http://127.0.0.1:{port}",
            ],
            capture_output=True,
            timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert b'data-review-smoke="passed"' in result.stdout
        assert ReviewStore(source, working).read().reports[0].state == "annotated"
        assert read_source(source) == store.originals
    finally:
        server.should_exit = True
        thread.join(timeout=5)
