"""Local frontend serving and real-browser synthetic integration checks."""

import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.testclient import TestClient

import howreliable.demo.app as demo
from howreliable.api.schemas import CohortPage, CohortSummary
from howreliable.api.service import PredictionService
from howreliable.demo.index import build_index
from test_demo_history import TIME, record, source_file

EVIL = '<img src=x onerror="window.injected=true">'


@pytest.fixture
def application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    rows = [record(), record(component="airbags_restraints"), record(normalized_model="other")]
    index = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, rows), index, TIME)
    service = Mock(spec=PredictionService)
    cohort = CohortSummary(cohort_id=rows[0]["broad_vehicle_id"], make="mazda", model="mazda3",
                           model_year=2020)
    service.list_cohorts.return_value = CohortPage(items=(cohort,), total=1, limit=100, offset=0)

    def factory(**kwargs: Any) -> FastAPI:
        app = FastAPI()
        app.state.prediction_service = service

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/api/v1/cohorts/{identifier}")
        def prediction(identifier: str) -> dict[str, Any]:
            return {
                "prediction": {"predicted_future_complaint_percentage": 75.0},
                "classification": {"presentation_label": "Future complaint activity predicted",
                                   "predicted_classification": "positive", "threshold": 0.5},
                "explanation": {"top_positive_contributors": [
                    {"human_readable_label": EVIL, "contribution_probability": 0.1}],
                    "top_negative_contributors": [], "method": "synthetic method"},
                "evidence": {"historical_complaint_support": 4, "cohort_age_years": 2},
                "general_limitation": "Synthetic limitation", "limitation_flags": [],
                "provenance": {"model_identifier": "synthetic-only"},
            }

        return app

    monkeypatch.setattr(demo, "create_prediction_app", factory)
    summary = tmp_path / demo.G1_SUMMARY
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({"components": [], "symptoms": [], "denominators": {}}))
    from howreliable.data.ingestion.nhtsa_complaints import sha256_file
    summary.with_suffix(".json.provenance.json").write_text(json.dumps({
        "complete": True, "output_sha256": sha256_file(summary),
        "source_rule_identities": {"component_lexicon_version": "older-synthetic"},
    }))
    return demo.create_app(root=tmp_path, index_path=index)


def test_home_assets_and_existing_routes(application: FastAPI) -> None:
    client = TestClient(application)
    home = client.get("/")
    assert home.status_code == 200
    assert "Vehicle complaint intelligence from NHTSA data" in home.text
    assert "default-src 'self'" in home.headers["content-security-policy"]
    assert home.headers["referrer-policy"] == "no-referrer"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/api/demo/v1/vehicles").json()["total"] == 2
    for path in ("demo.js", "demo.css"):
        assert client.get("/static/" + path).status_code == 200
    assert client.get("/static/missing.js").status_code == 404
    assert client.get("/static/../index.py").status_code == 404
    script = client.get("/static/demo.js").text
    assert "innerHTML" not in script
    assert "textContent" in script
    assert "limit: \"1\"" in script
    assert "https://" not in script
    assert 'aria-live="polite"' in home.text and '<label for="make">' in home.text
    css = client.get("/static/demo.css").text
    assert "@media(max-width:480px)" in css
    assert ":focus-visible" in css and "prefers-reduced-motion" in css


def test_browser_vehicle_workflow_safe_text_errors_and_mobile(
    application: FastAPI, tmp_path: Path,
) -> None:
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not edge.exists():
        pytest.skip("Installed Edge unavailable; browser integration not verified")
    application.router.routes[:] = [
        r for r in application.router.routes if getattr(r, "path", None) != "/"
    ]

    @application.get("/")
    def home() -> HTMLResponse:
        html = Path(demo.__file__).with_name("static").joinpath("index.html").read_text("utf-8")
        return HTMLResponse(html.replace(
            "</head>", '<script src="/smoke.js" defer></script></head>',
        ))

    @application.get("/smoke.js")
    def script() -> Response:
        return Response(r'''
        (async () => {
          const el=id=>document.getElementById(id);
          const originalFetch=window.fetch.bind(window);
          async function wait(fn){for(let i=0;i<400;i++){
            if(fn())return;await new Promise(r=>setTimeout(r,25));}throw Error('timeout');}
          function choose(id,value){el(id).value=value;el(id).dispatchEvent(new Event('change'));}
          try {
            await wait(()=>!el('make').disabled); choose('make','mazda');
            await wait(()=>!el('model').disabled); choose('model','mazda3');
            await wait(()=>!el('year').disabled); choose('year','2020'); el('submit').click();
            await wait(()=>el('prediction').textContent.includes('75.0%'));
            if(!el('history').textContent.includes('Unique reports'))throw Error('history');
            if(!el('history').textContent.includes('Airbags & restraints'))throw Error('labels');
            if(!el('history').textContent.includes('not vehicle failure rates'))
              throw Error('rates');
            if(!el('prediction').textContent.includes('at least one NHTSA complaint'))
              throw Error('target definition');
            if(!el('prediction').textContent.includes('Not a mechanical failure or repair'))
              throw Error('model limitations');
            if(parseFloat(getComputedStyle(el('prediction').querySelector('.probability')).fontSize)
               >=parseFloat(getComputedStyle(el('history').querySelector('.primary-metric strong'))
                 .fontSize))throw Error('hierarchy');
            for(const id of ['make','model','year','submit']){
              el(id).focus();if(document.activeElement!==el(id))throw Error('focus');}
            if(document.querySelector('img')||window.injected)throw Error('unsafe rendering');
            if(!el('prediction').textContent.includes('<img'))throw Error('escaped text missing');
            choose('model','other'); await wait(()=>!el('year').disabled);
            choose('year','2020'); el('submit').click();
            await wait(()=>el('prediction').textContent.includes('No frozen prediction'));
            el('load-nlp').click();
            await wait(()=>el('nlp-content').textContent.includes('Global G1 sample only'));
            el('reset').click(); await wait(()=>!el('make').disabled);
            if(!el('results').hidden||!el('model').disabled)throw Error('reset');
            window.fetch=async path=>String(path).startsWith('/api/demo/v1/vehicles?')
              ? new Response(JSON.stringify({makes:[],models:[],years:[],items:[],total:0}),
                {headers:{'Content-Type':'application/json'}}):originalFetch(path);
            el('reset').click();
            await wait(()=>el('search-status').textContent.includes('No matching vehicles'));
            window.fetch=async ()=>new Response('{}',{status:503}); el('reset').click();
            await wait(()=>el('search-status').textContent.includes('HTTP 503'));
            if(el('retry').hidden)throw Error('retry');
            window.fetch=originalFetch; el('retry').click(); await wait(()=>!el('make').disabled);
            if(document.documentElement.scrollWidth>window.innerWidth+1)throw Error('overflow');
            document.body.setAttribute('data-demo-smoke','passed');
          }catch(error){document.body.setAttribute('data-demo-smoke','failed:'+error.message);}
        })();''', media_type="text/javascript")

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        application, host="127.0.0.1", port=port, access_log=False, log_level="critical",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.02)
        for width in (1200, 390):
            result = subprocess.run([
                str(edge), "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--disable-extensions", "--disable-sync",
                "--disable-background-networking", "--disable-component-update",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                f"--user-data-dir={tmp_path / ('browser-' + str(width))}",
                f"--window-size={width},900", "--dump-dom", "--virtual-time-budget=20000",
                f"http://127.0.0.1:{port}",
            ], capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
            assert b'data-demo-smoke="passed"' in result.stdout, result.stdout[-2000:]
    finally:
        server.should_exit = True
        thread.join(timeout=5)
