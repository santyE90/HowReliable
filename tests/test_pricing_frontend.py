"""Real Edge synthetic, model-free pricing workflow; no external market evidence."""

import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.responses import HTMLResponse, Response
from fastapi.testclient import TestClient

import howreliable.demo.app as demo
from howreliable.demo.index import build_index
from test_demo_history import TIME, record, source_file


def test_pricing_browser_model_free_workflow(tmp_path: Path) -> None:
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if not edge.exists():
        pytest.skip("Installed Edge unavailable")
    index = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record()]), index, TIME)
    app = demo.create_app(root=tmp_path, index_path=index)
    assert app.state.prediction_service is None
    with TestClient(app) as client:
        assert client.get("/static/pricing.js").status_code == 200
        source = client.get("/static/pricing.js").text
        assert all(token not in source for token in [
            "localStorage", "sessionStorage", "document.cookie",
        ])
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/"]

    @app.get("/")
    def home() -> HTMLResponse:
        page = Path(demo.__file__).with_name("static").joinpath("index.html").read_text("utf-8")
        return HTMLResponse(page.replace(
            "</head>", '<script src="/pricing-smoke.js" defer></script></head>',
        ))

    @app.get("/pricing-smoke.js")
    def script() -> Response:
        return Response(r'''
        (async()=>{
          const el=id=>document.getElementById(id), original=window.fetch.bind(window);
          let phase='start',last=null,sent=null,release=null;
          const wait=async f=>{for(let i=0;i<400;i++){
            if(f())return;await new Promise(r=>setTimeout(r,20));}throw Error('timeout '+phase);};
          const set=(id,value)=>{const c=el(id);if(c.type==='checkbox')c.checked=value;
            else c.value=value;c.dispatchEvent(new Event('input',{bubbles:true}));
            c.dispatchEvent(new Event('change',{bubbles:true}));};
          const config={trim:'base',powertrain:'petrol',transmission:'automatic',drivetrain:'fwd',
            body_style:'sedan',province:'ON',city:'Toronto',seller_type:'dealer',
            condition_status:'no_known_issues_reported',accident_history:'no',
            title_status:'normal_reported',tax_fee_basis:'taxes_and_fees_excluded'};
          const recording=async(path,options)=>{
            if(String(path).startsWith('https:'))throw Error('external retrieval');
            const r=await original(path,options);
            if(String(path)==='/api/demo/v1/price-comparisons'){
              sent=JSON.parse(options.body);last=await r.clone().json();
              if(options.cache!=='no-store'||r.headers.get('cache-control')!=='no-store')
                throw Error('storage policy');
            }return r;
          };window.fetch=recording;
          const compare=async()=>{el('pricing-submit').click();
            await wait(()=>!el('pricing-results').hidden);};
          const fill=id=>{
            Object.entries(config).forEach(([key,value])=>set(id+'-'+key,value));
            set(id+'-source_name','Synthetic dealer');set(id+'-source_listing_id',id);
            set(id+'-asking_price',String(10000+Number(id.split('_')[1])*1000)+'.00');
            set(id+'-odometer','200000');set(id+'-odometer_unit','km');
            set(id+'-observed_on','2026-11-03');set(id+'-listing_status','active_reported');
            set(id+'-permission_basis','synthetic');set(id+'-permission_attested',true);
            set(id+'-is_subject_vehicle','no');
          };
          try{
            phase='selection';await wait(()=>!el('make').disabled);set('make','mazda');
            await wait(()=>!el('model').disabled);set('model','mazda3');
            await wait(()=>!el('year').disabled);set('year','2020');set('price','0012000.00');
            set('odometer','200000');set('warning_lights','yes');el('submit').click();
            await wait(()=>el('recommendation')?.textContent.includes('Proceed with caution'));
            const readiness=el('recommendation').textContent;
            el('pricing-panel').querySelector('details').open=true;
            set('pricing-date','2026-11-03');
            Object.entries(config).forEach(([key,value])=>set('price-subject-'+key,value));
            phase='sparse';await compare();
            if(!el('pricing-results').textContent.includes('no primary listings'))
              throw Error('zero primary');
            for(let n=1;n<=3;n++){
              el('pricing-add').click();fill('entry_'+n);await compare();
              if(last.counts.primary!==n)throw Error('primary count');
              if(n<3&&el('pricing-results').textContent.includes('Selected-sample median:'))
                throw Error('sparse median');
            }
            if(!el('pricing-results').textContent.includes('Selected-sample median: CAD 12,000.00'))
              throw Error('median display');
            if(el('recommendation').textContent!==readiness)throw Error('P4 changed');
            if(!el('pricing-results').textContent.includes('input_sha256'))
              throw Error('provenance');
            if(document.activeElement!==el('pricing-result-title'))throw Error('focus');
            if(el('pricing-status').getAttribute('aria-live')!=='polite')throw Error('status');
            phase='classifications';set('entry_2-permission_attested',false);
            set('entry_3-trim','different');await compare();
            if(last.counts.primary!==1||last.counts.contextual!==1||last.counts.excluded!==1)
              throw Error('eligibility accounting');
            for(const label of ['PRIMARY COMPARABLE','CONTEXTUAL COMPARABLE','EXCLUDED']){
              if(!el('pricing-results').textContent.includes(label))throw Error('category label');
            }
            set('entry_1-source_name','<img src=x onerror="window.injected=true">'+'x'.repeat(45));
            set('entry_1-listing_url','https://public.example/synthetic-ad');await compare();
            if(document.querySelector('img')||window.injected)throw Error('unsafe text');
            if(!el('pricing-results').textContent.includes('<img'))throw Error('escaped source');
            phase='malformed';
            for(const mutate of [d=>null,d=>({...d,counts:{primary:99}}),
              d=>({...d,entries:[null]}),d=>({...d,subject:{...d.subject,model:'wrong'}}),
              d=>({...d,subject:{...d.subject,asking_price_cad:'1.00'}}),
              d=>({...d,subject:{...d.subject,odometer_km:1}}),
              d=>({...d,entries:d.entries.map((e,i)=>i?e:{...e,
                observation:{...e.observation,permission_attested:false}})})]){
              window.fetch=async(path,options)=>{
                const r=await recording(path,options);
                return String(path)==='/api/demo/v1/price-comparisons'
                  ?new Response(JSON.stringify(mutate(await r.json())),
                    {headers:{'Content-Type':'application/json'}}):r;
              };
              el('pricing-submit').click();
              await wait(()=>el('pricing-status').textContent.includes('incomplete, unsupported'));
              if(!el('pricing-results').hidden)throw Error('malformed output');
            }
            phase='HTTP errors';
            for(const code of [422,500,503]){
              window.fetch=async(path,options)=>String(path)==='/api/demo/v1/price-comparisons'
                ?new Response('{}',{status:code}):recording(path,options);
              el('pricing-submit').click();
              await wait(()=>el('pricing-status').textContent.includes('HTTP '+code));
            }
            phase='pending edit';window.fetch=(path,options)=>
              String(path)==='/api/demo/v1/price-comparisons'
                ?new Promise(r=>{release=r;}):recording(path,options);
            el('pricing-submit').click();await wait(()=>release);
            set('entry_1-city','Ottawa');release(new Response(JSON.stringify(last)));
            await new Promise(r=>setTimeout(r,60));
            if(!el('pricing-results').hidden)throw Error('stale edit');
            phase='pending remove';release=null;el('pricing-submit').click();
            await wait(()=>release);
            el('pricing-entries').firstElementChild.querySelector('button').click();
            release(new Response(JSON.stringify(last)));await new Promise(r=>setTimeout(r,60));
            if(!el('pricing-results').hidden)throw Error('stale removal');
            phase='pending subject';release=null;el('pricing-submit').click();
            await wait(()=>release);set('price','12500.00');
            release(new Response(JSON.stringify(last)));await new Promise(r=>setTimeout(r,60));
            if(!el('pricing-results').hidden)throw Error('stale subject');
            if(el('recommendation'))throw Error('shared subject edit did not invalidate P4');
            window.fetch=recording;el('submit').click();
            await wait(()=>el('recommendation')?.textContent.includes('Proceed with caution'));
            window.fetch=(path,options)=>String(path)==='/api/demo/v1/price-comparisons'
              ?new Promise(r=>{release=r;}):recording(path,options);
            phase='pending reset';release=null;el('pricing-submit').click();
            await wait(()=>release);el('pricing-clear').click();
            release(new Response(JSON.stringify(last)));await new Promise(r=>setTimeout(r,60));
            if(!el('pricing-results').hidden||el('pricing-entries').children.length)
              throw Error('stale reset');
            phase='network failure';window.fetch=async(path,options)=>
              String(path)==='/api/demo/v1/price-comparisons'
                ?Promise.reject(new TypeError('Synthetic network failure')):recording(path,options);
            el('pricing-submit').click();
            await wait(()=>el('pricing-status').textContent.includes('Synthetic network failure'));
            if(el('pricing-submit').disabled)throw Error('network recovery');
            phase='out of order';const pending=[];
            window.fetch=(path,options)=>String(path)==='/api/demo/v1/price-comparisons'
              ?new Promise(r=>pending.push(r)):recording(path,options);
            el('pricing-submit').click();await wait(()=>pending.length===1);
            set('pricing-date','2026-11-02');el('pricing-submit').click();
            await wait(()=>pending.length===2);
            pending[1](new Response('{}',{status:503}));
            await wait(()=>el('pricing-status').textContent.includes('HTTP 503'));
            pending[0](new Response(JSON.stringify(last)));
            await new Promise(r=>setTimeout(r,60));
            if(!el('pricing-results').hidden||!el('pricing-status').textContent
              .includes('HTTP 503'))
              throw Error('out of order response');
            phase='limit';window.fetch=recording;
            while(el('pricing-entries').children.length<10)el('pricing-add').click();
            if(!el('pricing-add').disabled)throw Error('ten-entry limit');
            el('pricing-entries').lastElementChild.querySelector('button').click();
            if(el('pricing-add').disabled)throw Error('remove reenables add');
            phase='reset';el('pricing-clear').click();
            if(el('pricing-entries').children.length||!el('pricing-results').hidden)
              throw Error('clear');
            if(el('recommendation').textContent!==readiness)throw Error('clear changed P4');
            phase='validation';set('pricing-date','');el('pricing-submit').click();
            if(!el('pricing-status').textContent.includes('highlighted'))
              throw Error('date validation');
            set('pricing-date','2026-11-03');set('year','');el('pricing-submit').click();
            await wait(()=>el('pricing-status').textContent.includes('Choose make'));
            set('year','2020');await compare();set('price','13000.00');
            if(!el('pricing-results').hidden)throw Error('subject edit');
            el('reset').click();await wait(()=>!el('make').disabled);
            if(el('pricing-entries').children.length||!el('pricing-results').hidden)
              throw Error('global reset');
            if(document.documentElement.scrollWidth>innerWidth+1)throw Error('overflow');
            document.body.setAttribute('data-pricing-smoke','passed');
          }catch(e){document.body.setAttribute('data-pricing-smoke','failed:'+phase+':'+e.message);}
        })();''', media_type="text/javascript")

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
                f"--user-data-dir={tmp_path / ('pricing-browser-' + str(width))}",
                f"--window-size={width},900", "--dump-dom", "--virtual-time-budget=30000",
                f"http://127.0.0.1:{port}",
            ], capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            marker = re.search(rb'data-pricing-smoke="([^"]*)"', result.stdout)
            assert marker and marker.group(1) == b"passed", (
                marker.group(1) if marker else b"browser did not finish"
            )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
