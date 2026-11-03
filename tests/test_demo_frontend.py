"""Local frontend serving and real-browser synthetic integration checks."""

import json
import re
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
          let sent=null, lastAssessment=null;
          const recordingFetch=async(path,options)=>{
            const response=await originalFetch(path,options);
            if(String(path)==='/api/demo/v1/purchase-assessments'){
              sent=JSON.parse(options.body);lastAssessment=await response.clone().json();
            }return response;
          };
          window.fetch=recordingFetch;
          async function wait(fn){for(let i=0;i<400;i++){
            if(fn())return;await new Promise(r=>setTimeout(r,25));}throw Error('timeout');}
          function choose(id,value){el(id).value=value;el(id).dispatchEvent(new Event('change'));}
          function input(id,value){el(id).value=value;el(id).dispatchEvent(new Event('input'));}
          try {
            await wait(()=>!el('make').disabled); choose('make','mazda');
            await wait(()=>!el('model').disabled); choose('model','mazda3');
            await wait(()=>!el('year').disabled); choose('year','2020');
            input('odometer','300000');input('price','12000.50');choose('maintenance','partial');
            el('submit').click();
            await wait(()=>el('prediction').textContent.includes('75.0%'));
            if(sent.odometer_km!==300000||sent.asking_price_cad!=='12000.50'
              ||sent.maintenance_history!=='partial')throw Error('request context');
            if(!el('assessment').textContent.includes('particularly important'))
              throw Error('mileage');
            for(const text of ['Complaint-supported inspection prompts','Generic inspection advice',
              'Unknown/other labels','Evidence limitations','No specific defect or repair']){
              if(!el('assessment').textContent.includes(text))throw Error('assessment rendering');
            }
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
            for(const id of ['make','model','year','odometer','price','maintenance','submit']){
              el(id).focus();if(document.activeElement!==el(id))throw Error('focus');}
            if(document.querySelector('img')||window.injected)throw Error('unsafe rendering');
            if(!el('prediction').textContent.includes('<img'))throw Error('escaped text missing');
            const savedContext=[...document.querySelectorAll('[data-context]')]
              .map(control=>[control.id,control.value]);
            const favorable={maintenance:'documented',mechanical_problems:'no',warning_lights:'no',
              drivability_problems:'no',outstanding_maintenance:'no',accident_history:'no',
              accident_documentation:'documented',inspection_status:'performed',
              inspection_result:'no_issues_reported',unresolved_inspection_issues:'no'};
            const cases=[['Insufficient information',{maintenance:'unknown'}],
              ['Worth considering',favorable],['Proceed with caution',{warning_lights:'yes'}]];
            for(const [label,values] of cases){
              for(const [id,value] of Object.entries(values))choose(id,value);
              if(values.inspection_status==='performed')
                input('inspection_summary','Synthetic reported inspection; verify records.');
              el('submit').click();
              await wait(()=>el('recommendation')?.textContent.includes(label));
              if(el('recommendation').querySelector('.recommendation-outcome').textContent!==label)
                throw Error('outcome label');
              if(!el('search-status').textContent.includes(label))
                throw Error('outcome announcement');
              if(!el('recommendation').textContent.includes('Evidence origin:'))
                throw Error('evidence origin missing');
              if(!el('recommendation').textContent.includes('Conditions that could change'))
                throw Error('reconsideration missing');
              if(!el('recommendation').textContent.includes('Essential missing information'))
                throw Error('missing information missing');
              for(const reason of lastAssessment.recommendation.supporting_reasons){
                if(!el('recommendation').textContent.includes(reason.explanation))
                  throw Error('reason explanation missing');
              }
              for(const text of lastAssessment.recommendation
                .conditions_that_would_change_recommendation){
                if(!el('recommendation').textContent.includes(text))
                  throw Error('reconsideration condition missing');
              }
              for(const key of lastAssessment.recommendation.missing_information){
                if(!el('recommendation').textContent.includes(el(key)?.labels?.[0]?.textContent
                  ||key.replaceAll('_',' ')))throw Error('missing field label');
              }
              if(document.activeElement!==el('assessment-title'))throw Error('result focus');
              const summary=el('recommendation').querySelector('details summary');
              summary.focus();if(document.activeElement!==summary)throw Error('details focus');
              summary.click();if(!summary.parentElement.open)throw Error('details expand');
              if(!el('recommendation').textContent.includes('independently verified'))
                throw Error('qualification missing');
              if(!el('recommendation').textContent.includes('2020 mazda mazda3'))
                throw Error('recommendation identity');
              if(lastAssessment.historical_evidence.unique_report_count!==1
                ||lastAssessment.historical_evidence.source_row_count!==2)
                throw Error('historical count changed');
            }
            for(const [id,value] of savedContext){
              if(el(id).tagName==='SELECT')choose(id,value);else input(id,value);
            }
            choose('maintenance','partial');
            const malformed=[null,{}, {outcome:'UNKNOWN'}, {outcome:{toString:null}},
              {...lastAssessment.recommendation,supporting_reasons:[null]},
              {...lastAssessment.recommendation,missing_information:'bad'},
              {...lastAssessment.recommendation,conditions_that_would_change_recommendation:null},
              {...lastAssessment.recommendation,schema_version:'unsupported'},
              {...lastAssessment.recommendation,supporting_reasons:[{
                ...lastAssessment.recommendation.supporting_reasons[0],
                evidence_origin:'unknown-origin'}]}];
            for(const broken of [undefined,...malformed]){
              window.fetch=async(path,options)=>{
                const response=await recordingFetch(path,options);
                if(String(path)!=='/api/demo/v1/purchase-assessments')return response;
                const data=await response.json();data.recommendation=broken;
                return new Response(JSON.stringify(data),
                  {headers:{'Content-Type':'application/json'}});
              };
              el('submit').click();
              await wait(()=>el('recommendation')?.textContent
                .includes('Recommendation unavailable'));
              if(el('recommendation').querySelector('.recommendation-outcome'))
                throw Error('malformed outcome displayed');
              if(el('results').hidden||!el('history').textContent.includes('Unique reports'))
                throw Error('malformed recommendation blocks history');
            }
            window.fetch=async(path,options)=>{
              const response=await recordingFetch(path,options);
              if(String(path)!=='/api/demo/v1/purchase-assessments')return response;
              const data=await response.json();
              data.recommendation.outcome='NOT_RECOMMENDED_UNDER_CURRENT_CONDITIONS';
              data.recommendation.supporting_reasons[0].explanation=
                '<img src=x onerror="window.injected=true">';
              return new Response(JSON.stringify(data),
                {headers:{'Content-Type':'application/json'}});
            };
            el('submit').click();
            await wait(()=>el('recommendation')?.textContent.includes('reserved and inactive'));
            if(!el('recommendation').textContent
              .includes('Not recommended under current conditions'))
              throw Error('reserved outcome label');
            if(document.querySelector('img')||window.injected)throw Error('unsafe reason');
            window.fetch=async(path,options)=>{
              const response=await recordingFetch(path,options);
              if(String(path)!=='/api/demo/v1/purchase-assessments')return response;
              const data=await response.json();data.vehicle.model='wrong-vehicle';
              return new Response(JSON.stringify(data),
                {headers:{'Content-Type':'application/json'}});
            };
            el('submit').click();
            await wait(()=>el('search-status').textContent
              .includes('does not match your selection'));
            if(!el('results').hidden||el('recommendation'))throw Error('wrong vehicle displayed');
            window.fetch=recordingFetch;
            el('major_repairs').closest('details').open=true;
            input('major_repairs','<img src=x onerror="window.injected=true">');
            choose('outstanding_maintenance','yes');
            el('inspection_status').closest('details').open=true;
            choose('inspection_status','not_performed');
            choose('inspection_result','no_issues_reported');
            el('submit').click();
            await wait(()=>el('search-status').textContent.includes('Check the inspection fields'));
            if(document.activeElement!==el('inspection_status'))throw Error('inspection focus');
            choose('inspection_status','performed');choose('inspection_result','issues_found');
            input('inspection_summary','Reported brake wear; not verified.');
            choose('unresolved_inspection_issues','yes');
            el('submit').click();
            await wait(()=>!el('results').hidden);
            if(sent.outstanding_maintenance!=='yes'||sent.inspection_status!=='performed'
              ||!sent.inspection_summary)throw Error('expanded context payload');
            if(!el('assessment').textContent.includes('<img src=x onerror='))
              throw Error('expanded context echo');
            if(document.querySelector('img')||window.injected)throw Error('unsafe user notes');
            input('maintenance_notes','new note');
            if(!el('results').hidden||el('recommendation'))throw Error('new context invalidation');
            el('submit').click();await wait(()=>!el('results').hidden);
            let predictionRelease=null;
            window.fetch=(path,options)=>String(path).endsWith('/prediction')
              ? new Promise(resolve=>{predictionRelease=resolve;}):recordingFetch(path,options);
            el('submit').click();
            await wait(()=>predictionRelease!==null);
            if(el('submit').disabled)throw Error('optional ML blocks assessment action');
            predictionRelease(new Response(JSON.stringify({status:'unsupported'}),
              {headers:{'Content-Type':'application/json'}}));
            await wait(()=>el('prediction').textContent.includes('No frozen prediction'));
            const hostile='<img src=x onerror="window.injected=true">';
            window.fetch=async(path,options)=>{
              const response=await recordingFetch(path,options);
              if(String(path)!=='/api/demo/v1/purchase-assessments')return response;
              const data=await response.json();
              data.reported_component_concerns[0].label=hostile;
              data.inspection_priorities[0].suggestion=hostile;
              data.purchase_considerations[0].explanation=hostile;
              data.evidence_limitations[0]=hostile;
              data.historical_evidence.provenance.synthetic_note=hostile;
              return new Response(JSON.stringify(data),
                {headers:{'Content-Type':'application/json'}});
            };
            el('submit').click();
            await wait(()=>el('assessment').textContent.includes(hostile));
            if(document.querySelector('img')||window.injected)throw Error('unsafe assessment text');
            window.fetch=recordingFetch;
            input('price','14000.00');if(!el('results').hidden)throw Error('stale context');
            el('submit').click();await wait(()=>el('prediction').textContent.includes('75.0%'));
            let release=null;
            window.fetch=(path,options)=>String(path)==='/api/demo/v1/purchase-assessments'
              ? new Promise(resolve=>{release=resolve;}):recordingFetch(path,options);
            el('submit').click();await wait(()=>release!==null);
            input('problem_description','Changed');
            release(new Response(JSON.stringify(lastAssessment),
              {headers:{'Content-Type':'application/json'}}));
            await new Promise(r=>setTimeout(r,60));
            if(!el('results').hidden||el('assessment').textContent)throw Error('stale response');
            for(const code of [404,409,422,500]){
              window.fetch=async(path,options)=>String(path)==='/api/demo/v1/purchase-assessments'
                ? new Response('{}',{status:code}):recordingFetch(path,options);
              el('submit').click();
              await wait(()=>el('search-status').textContent.includes('HTTP '+code));
              if(!el('results').hidden)throw Error('error retains old results');
            }
            window.fetch=recordingFetch;
            input('price','1.001');el('submit').click();
            if(!el('search-status').textContent.includes('highlighted inputs'))
              throw Error('price validation');
            input('price','');input('odometer','9007199254740992');el('submit').click();
            if(!el('odometer').validity.rangeOverflow||document.activeElement!==el('odometer'))
              throw Error('odometer native validation and focus');
            input('price','');input('odometer','');choose('maintenance','unknown');
            choose('model','other'); await wait(()=>!el('year').disabled);
            choose('year','2020'); el('submit').click();
            await wait(()=>el('prediction').textContent.includes('No frozen prediction'));
            if(sent.odometer_km!==null||sent.asking_price_cad!==null)
              throw Error('optional fields');
            let catalogRelease=null;
            window.fetch=(path,options)=>String(path).startsWith('/api/demo/v1/vehicles?')
              ? new Promise(resolve=>{catalogRelease=resolve;}):recordingFetch(path,options);
            choose('make','mazda');
            if(!el('submit').disabled)throw Error('assessment enabled during discovery');
            choose('make','');
            catalogRelease(new Response(JSON.stringify({models:['stale'],years:[],makes:[]}),
              {headers:{'Content-Type':'application/json'}}));
            await new Promise(r=>setTimeout(r,60));
            if(!el('model').disabled||el('model').options.length!==1)
              throw Error('stale vehicle discovery');
            window.fetch=recordingFetch;
            el('load-nlp').click();
            await wait(()=>el('nlp-content').textContent.includes('Global G1 sample only'));
            el('reset').click(); await wait(()=>!el('make').disabled);
            if(!el('results').hidden||!el('model').disabled||el('recommendation'))
              throw Error('reset');
            if(el('inspection_status').value!=='unknown'||el('inspection_result').value!=='unavailable'
              ||el('major_repairs').value!==''||el('maintenance_notes').value!=='')
              throw Error('expanded context reset');
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
            marker = re.search(rb'data-demo-smoke="([^"]*)"', result.stdout)
            assert marker and marker.group(1) == b"passed", (
                marker.group(1) if marker else b"browser did not finish"
            )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
