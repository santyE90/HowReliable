"""Desktop/mobile Edge profile workflows, isolated from P4/P5 and model availability."""

import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.testclient import TestClient

import howreliable.demo.app as demo
from howreliable.data.ingestion.nhtsa_complaints import sha256_file
from howreliable.demo.index import DEFAULT_INDEX, build_index
from test_demo_history import TIME, record, source_file


def test_profile_assets_and_separation(tmp_path: Path) -> None:
    index = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), index, TIME)
    with TestClient(demo.create_app(root=tmp_path, index_path=index)) as client:
        html = client.get("/").text
        assert html.index('id="results"') < html.index('id="profile-panel"') < html.index(
            'id="pricing-panel"',
        )
        assert 'aria-controls="profile-results"' in html
        assert 'id="profile-status" role="status"' in html
        source = client.get("/static/profile.js").text
        assert "textContent" in source
        assert all(token not in source for token in [
            "innerHTML", "localStorage", "sessionStorage", "https://", "purchase-assessments",
            "price-comparisons", "sample-summary", "api/v1/cohorts",
        ])


def browser_check(app: FastAPI, tmp_path: Path, script: str) -> None:
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not edge.exists():
        pytest.skip("Installed Edge unavailable")
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/"]

    @app.get("/")
    def home() -> HTMLResponse:
        page = Path(demo.__file__).with_name("static").joinpath("index.html").read_text("utf-8")
        return HTMLResponse(page.replace(
            "</head>", '<script src="/profile-smoke.js" defer></script></head>',
        ))

    @app.get("/profile-smoke.js")
    def smoke() -> Response:
        return Response(script, media_type="text/javascript")

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, access_log=False, log_level="critical",
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
                f"--user-data-dir={tmp_path / ('profile-browser-' + str(width))}",
                f"--window-size={width},900", "--dump-dom", "--virtual-time-budget=30000",
                f"http://127.0.0.1:{port}",
            ], capture_output=True, timeout=50, creationflags=subprocess.CREATE_NO_WINDOW)
            marker = re.search(rb'data-profile-smoke="([^"]*)"', result.stdout)
            assert marker and marker.group(1) == b"passed", (
                marker.group(1) if marker else b"browser did not finish"
            )
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_profile_browser_synthetic_states(tmp_path: Path) -> None:
    index = tmp_path / "history.sqlite"
    rows = [record(), record(), record(component="electrical"),
            record(component="other", source_reference_id="901"),
            record(component="unknown", source_reference_id="902", report_date=None)]
    build_index(source_file(tmp_path, rows), index, TIME)
    app = demo.create_app(root=tmp_path, index_path=index)
    assert app.state.prediction_service is None
    browser_check(app, tmp_path, r'''
    (async()=>{
      const el=id=>document.getElementById(id), original=window.fetch.bind(window);
      let phase='selection', baseline=null, release=null;
      const wait=async f=>{for(let i=0;i<500;i++){
        if(f())return;await new Promise(r=>setTimeout(r,20));}throw Error('timeout');};
      const assert=(value,message)=>{if(!value)throw Error(message);};
      const set=(id,value)=>{el(id).value=value;el(id).dispatchEvent(new Event('change'));};
      const clone=()=>structuredClone(baseline);
      const reply=(data,status=200)=>new Response(JSON.stringify(data),
        {status,headers:{'Content-Type':'application/json'}});
      const intercept=fn=>{window.fetch=(path,options)=>String(path).includes(
        '/vehicle-problem-profiles')?fn(options):original(path,options);};
      const load=async()=>{el('profile-load').click();
        await wait(()=>el('profile-panel').getAttribute('aria-busy')==='false');};
      const select=async()=>{
        await wait(()=>!el('make').disabled);set('make','mazda');
        await wait(()=>!el('model').disabled);set('model','mazda3');
        await wait(()=>!el('year').disabled);set('year','2020');
      };
      try{
        await select();
        let sent;
        intercept(async options=>{
          sent=JSON.parse(options.body);
          assert(options.credentials==='omit'&&options.cache==='no-store','request policy');
          const response=await original('/api/demo/v1/vehicle-problem-profiles',options);
          baseline=await response.clone().json();return response;
        });
        await load();
        assert(!el('profile-results').hidden,'success hidden '+el('profile-status').textContent);
        assert(Object.keys(sent).sort().join(',')==='make,model,year','inferred configuration');
        assert(document.activeElement.id==='profile-result-title','result focus');
        const text=el('profile-results').textContent;
        for(const fragment of ['3 unique complaint reports','5 original source rows',
          'Categories overlap','not failure rates','Unknown component','Other components',
          'No specific part-level question','General inspection questions',
          'Manufacturer communications / TSBs: Unavailable','Validated NLP symptom evidence',
          'Canadian-market applicability are unverified','source rows have missing report dates'])
          assert(text.includes(fragment),'missing '+fragment);
        const titles=[...el('profile-results').querySelectorAll('h5')].map(e=>e.textContent);
        assert(titles.map(t=>t.split(' —')[0]).join(',')===
          'electrical system,engine,Other components,Unknown component','component order');
        assert(el('profile-results').querySelectorAll('.profile-component').length===4,'categories');
        assert(el('profile-results').textContent.includes('profile-question.v1.structured_component'),
          'rule identifiers');
        const summary=el('profile-results').querySelector('summary');summary.focus();
        assert(document.activeElement===summary,'keyboard summary focus');
        summary.click();assert(summary.parentElement.open,'details expandable');
        assert(el('profile-status').getAttribute('role')==='status','announcement');
        el('profile-result-title').focus();
        assert(getComputedStyle(el('profile-result-title')).outlineStyle==='solid'&&
          parseFloat(getComputedStyle(el('profile-result-title')).outlineWidth)>=2,'focus styling');
        const details=el('profile-results').querySelectorAll('details');
        details.forEach(d=>d.open=true);
        assert(document.documentElement.scrollWidth<=innerWidth+1,'mobile overflow');
        phase='independence';
        el('submit').click();await wait(()=>!el('results').hidden);
        const readiness=el('assessment').textContent;
        await load();assert(el('assessment').textContent===readiness,'P4 modified');
        assert(el('pricing-entries').children.length===0,'pricing modified');
        set('price','12345');assert(!el('profile-results').hidden,'price changed evidence');
        phase='hostile';
        let hostile=clone();hostile.component_evidence[0].label=
          '<img src=x onerror="window.injected=true">';
        hostile.historical_evidence.provenance.source_filename='x'.repeat(500);
        intercept(()=>reply(hostile));await load();
        assert(!el('profile-results').hidden,'hostile response rejected unexpectedly');
        assert(!window.injected&&!el('profile-results').querySelector('img'),'unsafe HTML');
        el('profile-results').querySelectorAll('details').forEach(d=>d.open=true);
        assert(document.documentElement.scrollWidth<=innerWidth+1,'long provenance overflow');
        phase='malformed';
        const mutations=[
          d=>delete d.historical_evidence,d=>delete d.source_coverage,
          d=>d.schema_version='other',d=>d.requested_identity.model='another',
          d=>d.historical_evidence.vehicle.id='different',
          d=>d.historical_evidence.source_row_count=-1,
          d=>d.historical_evidence.unique_report_count=999,
          d=>d.historical_evidence.components[0].unique_report_count=999,
          d=>d.historical_evidence.components.reverse(),
          d=>d.historical_evidence.components.push(d.historical_evidence.components[0]),
          d=>d.historical_evidence.timeline[0].unique_report_count=999,
          d=>d.historical_evidence.first_report_date='2022-02-31',
          d=>d.component_evidence[0].count_reference='unknown',
          d=>d.component_evidence[0].question_ids=['absent'],
          d=>d.inspection_questions[0].supporting_unique_report_count=999,
          d=>d.inspection_questions.push(d.inspection_questions[0]),
          d=>d.source_coverage.recalls.unique_record_count=0,
          d=>d.source_coverage.validated_symptoms.availability='AVAILABLE',
          d=>d.supplied_configuration={trim:'invented'}
        ];
        for(let i=0;i<mutations.length;i++){
          let data=clone();mutations[i](data);intercept(()=>reply(data));await load();
          assert(el('profile-results').hidden&&!el('profile-results').children.length,
            'partial malformed output '+i);
          assert(el('profile-status').classList.contains('error'),'error announcement '+i);
        }
        intercept(()=>new Response('not json'));await load();
        assert(el('profile-results').hidden,'invalid JSON');
        intercept(()=>{throw Error('synthetic network error');});await load();
        assert(el('profile-results').hidden&&el('profile-status').textContent.includes(
          'network error'),'network failure');
        intercept(()=>reply({},422));await load();
        assert(el('profile-status').textContent.includes('HTTP 422'),'422');
        phase='missing states';
        for(const [state,status] of [['NO_MATCHING_REPORTS',200],
          ['AMBIGUOUS_IDENTITY',409],['SOURCE_UNAVAILABLE',503]]){
          const data=clone();data.profile_status=state;
          data.identity_resolution={status:state,candidates:state==='AMBIGUOUS_IDENTITY'?
            [{...data.historical_evidence.vehicle,id:'a'},
             {...data.historical_evidence.vehicle,id:'b'}]:[]};
          data.applicability.cohort_match=state;data.historical_evidence=null;
          data.component_evidence=[];data.inspection_questions=data.inspection_questions.filter(
            q=>q.evidence_basis==='generic_inspection_guidance');
          Object.assign(data.source_coverage.complaints,{availability:state===
            'SOURCE_UNAVAILABLE'?'SOURCE_UNAVAILABLE':'AVAILABLE',unique_record_count:null,
            provenance_reference:null,applicability_status:state});
          intercept(()=>reply(data,status));await load();
          assert(!el('profile-results').hidden,'typed state '+state);
          assert(!el('profile-results').textContent.includes('0 unique complaint reports'),
            'missing is zero '+state);
        }
        const zero=clone();Object.assign(zero.historical_evidence,{
          source_row_count:0,unique_report_count:0,missing_report_date_rows:0,
          first_report_date:null,last_report_date:null,components:[],timeline:[]});
        zero.component_evidence=[];zero.inspection_questions=zero.inspection_questions.filter(
          q=>q.evidence_basis==='generic_inspection_guidance');
        zero.source_coverage.complaints.unique_record_count=0;
        intercept(()=>reply(zero));await load();
        assert(el('profile-results').textContent.includes('Zero recorded reports'),'zero state');
        phase='pending and stale';
        intercept(()=>new Promise(resolve=>{release=resolve;}));
        el('profile-load').click();await wait(()=>release!==null);
        assert(el('profile-load').disabled&&el('profile-panel').getAttribute('aria-busy')===
          'true','busy');
        set('year','');assert(el('profile-results').hidden,'vehicle change invalidation');
        release(reply(clone()));await new Promise(r=>setTimeout(r,40));
        assert(el('profile-results').hidden,'stale response');
        set('year','2020');release=null;el('profile-load').click();
        await wait(()=>release!==null);const oldRelease=release;
        set('year','2020');intercept(()=>reply(clone()));await load();
        oldRelease(reply({}));await new Promise(r=>setTimeout(r,40));
        assert(!el('profile-results').hidden,'older response replaced newer result');
        phase='reset';
        intercept(()=>new Promise(resolve=>{release=resolve;}));release=null;
        el('profile-load').click();await wait(()=>release!==null);
        el('reset').click();release(reply(clone()));
        await wait(()=>!el('make').disabled);await new Promise(r=>setTimeout(r,40));
        assert(el('profile-results').hidden&&el('profile-load').disabled,'reset');
        window.fetch=original;
        document.body.setAttribute('data-profile-smoke','passed');
      }catch(e){document.body.setAttribute('data-profile-smoke','failed:'+phase+':'+e.message);}
    })();''')


def test_real_cohorts_browser_model_free(tmp_path: Path) -> None:
    index = Path(DEFAULT_INDEX).resolve()
    if not index.is_file():
        pytest.skip("Restored historical index unavailable")
    before = sha256_file(index)
    app = demo.create_app(root=tmp_path, index_path=index)
    assert app.state.prediction_service is None
    browser_check(app, tmp_path, r'''
    (async()=>{
      const el=id=>document.getElementById(id);
      const wait=async f=>{for(let i=0;i<500;i++){
        if(f())return;await new Promise(r=>setTimeout(r,20));}throw Error('timeout');};
      const set=(id,value)=>{el(id).value=value;el(id).dispatchEvent(new Event('change'));};
      try{
        await wait(()=>!el('make').disabled);
        for(const [make,model,reports,rows] of [['bmw','335i',22,35],
          ['toyota','corolla',23,32]]){
          set('make',make);await wait(()=>!el('model').disabled);set('model',model);
          await wait(()=>!el('year').disabled);set('year','2011');el('profile-load').click();
          await wait(()=>!el('profile-results').hidden);
          const text=el('profile-results').textContent;
          if(!text.includes(reports+' unique complaint reports')||!text.includes(
            rows+' original source rows')||!el('profile-result-title').textContent.includes(model))
            throw Error('real cohort counts or identity');
          el('profile-results').querySelectorAll('details').forEach(d=>d.open=true);
          if(document.documentElement.scrollWidth>innerWidth+1)throw Error('overflow');
        }
        document.body.setAttribute('data-profile-smoke','passed');
      }catch(e){document.body.setAttribute('data-profile-smoke','failed:'+e.message);}
    })();''')
    assert sha256_file(index) == before
