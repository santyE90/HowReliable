"""Verified official records in model-free desktop/mobile profile presentation."""

import json
from pathlib import Path

import pytest

from howreliable.demo.app import create_app
from howreliable.demo.index import DEFAULT_INDEX, build_index
from howreliable.demo.official_evidence import DEFAULT_OFFICIAL, build_official
from test_demo_history import TIME, record, source_file
from test_official_evidence import communication_input, recall_input
from test_profile_frontend import browser_check


def test_official_profile_browser(tmp_path: Path) -> None:
    sources = [recall_input(tmp_path / "r"), communication_input(tmp_path / "c")]
    output = tmp_path / "official"
    build_official(sources, output, TIME)
    application = next(json.loads(line) for line in sources[0].applications.read_text(
        encoding="utf-8",
    ).splitlines() if json.loads(line)["model_year"] == 2021)
    index = tmp_path / "history.sqlite"
    build_index(source_file(tmp_path, [record(
        normalized_make=application["normalized_make"],
        normalized_model=application["normalized_model"], model_year=2021,
    )]), index, TIME)
    app = create_app(root=tmp_path, index_path=index, official_path=output)
    assert app.state.prediction_service is None
    browser_check(app, tmp_path, r'''
    (async()=>{
      const el=id=>document.getElementById(id), original=window.fetch.bind(window);
      const wait=async fn=>{for(let i=0;i<400;i++){
        if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('timeout');};
      const assert=(value,message)=>{if(!value)throw Error(message);};
      const choose=(id,value)=>{el(id).value=value;el(id).dispatchEvent(new Event('change'));};
      const load=async()=>{el('profile-load').click();await wait(()=>
        el('profile-panel').getAttribute('aria-busy')==='false');};
      let baseline=null,phase='selection';
      const mock=data=>{window.fetch=(path,options)=>String(path).includes(
        'vehicle-problem-profiles')?Promise.resolve(new Response(JSON.stringify(data),
        {headers:{'Content-Type':'application/json'}})):original(path,options);};
      try{
        await wait(()=>!el('make').disabled);choose('make',el('make').options[1].value);
        await wait(()=>!el('model').disabled);choose('model',el('model').options[1].value);
        await wait(()=>!el('year').disabled);choose('year','2021');
        window.fetch=async(path,options)=>{const r=await original(path,options);
          if(String(path).includes('vehicle-problem-profiles'))baseline=await r.clone().json();
          return r;};
        await load();
        assert(baseline.schema_version==='vehicle-problem-profile-1.1','version');
        assert(!el('profile-results').hidden,'render '+el('profile-status').textContent);
        let text=el('profile-results').textContent;
        for(const phrase of ['NHTSA recalls','unique campaigns',
          'Manufacturer communications / TSBs',
          'unique documents','Consequence text','Remedy text','Structured fixture summary',
          'U.S. regulatory/documentary','Canadian-market applicability',
          'Validated NLP symptom evidence: Unavailable'])
          assert(text.includes(phrase),'missing '+phrase);
        assert(el('profile-results').querySelectorAll('.official-evidence').length===2,
          'source separation');
        assert(baseline.source_coverage.recalls.unique_record_count===1,'campaign deduplication');
        phase='hostile';const hostile=structuredClone(baseline);
        hostile.source_coverage.recalls.records[0].descriptions=[
          '<img src=x onerror="window.bad=true">'];
        mock(hostile);await load();assert(!el('profile-results').hidden,'hostile text');
        assert(!window.bad&&!el('profile-results').querySelector('img'),'HTML execution');
        el('profile-results').querySelectorAll('details').forEach(d=>d.open=true);
        assert(document.documentElement.scrollWidth<=innerWidth+1,'overflow');
        phase='malformed';
        const mutations=[
          d=>d.schema_version='vehicle-problem-profile-1.0',
          d=>d.source_coverage.recalls.unique_record_count=-1,
          d=>d.source_coverage.recalls.returned_record_count=99,
          d=>d.source_coverage.recalls.records_truncated=true,
          d=>d.source_coverage.recalls.records[0].kind='communication',
          d=>d.source_coverage.recalls.records[0].remedies={},
          d=>delete d.source_coverage.recalls.records[0].applicability_note,
          d=>d.source_coverage.recalls.provenance.serving_database_sha256='bad',
          d=>d.source_coverage.recalls.records.push(d.source_coverage.recalls.records[0])
        ];
        for(const mutate of mutations){const data=structuredClone(baseline);mutate(data);
          mock(data);await load();
          assert(el('profile-results').hidden,'malformed evidence visible');}
        phase='verified zero';const zero=structuredClone(baseline);
        Object.assign(zero.source_coverage.recalls,{unique_record_count:0,returned_record_count:0,
          records_truncated:false,records:[]});mock(zero);await load();
        assert(el('profile-results').textContent.includes('No exact matching records'),
          'zero scoped');
        phase='bounded preview';const preview=structuredClone(baseline);
        Object.assign(preview.source_coverage.recalls,{unique_record_count:12,records_truncated:true});
        mock(preview);await load();assert(el('profile-results').textContent.includes(
          'Showing the first 1 of 12'),'truncation notice');
        phase='reset';el('reset').click();await wait(()=>!el('make').disabled);
        assert(el('profile-results').hidden,'reset retains official evidence');
        document.body.setAttribute('data-profile-smoke','passed');
      }catch(e){document.body.setAttribute('data-profile-smoke','failed:'+phase+':'+e.message);}
    })();''')


def test_real_official_profile_browser(tmp_path: Path) -> None:
    index, official = Path(DEFAULT_INDEX).resolve(), Path(DEFAULT_OFFICIAL).resolve()
    if not index.exists() or not (official / "manifest.json").exists():
        pytest.skip("Verified local official and complaint snapshots unavailable")
    app = create_app(root=tmp_path, index_path=index, official_path=official)
    browser_check(app, tmp_path, r'''
    (async()=>{
      const el=id=>document.getElementById(id), original=window.fetch.bind(window);
      const wait=async fn=>{for(let i=0;i<500;i++){
        if(fn())return;await new Promise(r=>setTimeout(r,20));}throw Error('timeout');};
      const set=(id,v)=>{el(id).value=v;el(id).dispatchEvent(new Event('change'));};
      let profile;
      window.fetch=async(path,options)=>{const r=await original(path,options);
        if(String(path).includes('vehicle-problem-profiles'))profile=await r.clone().json();
        return r;};
      try{
        await wait(()=>!el('make').disabled);
        for(const [make,model,recalls,documents] of [['bmw','335i',7,8],
          ['toyota','corolla',9,101]]){
          set('make',make);await wait(()=>!el('model').disabled);set('model',model);
          await wait(()=>!el('year').disabled);set('year','2011');el('profile-load').click();
          await wait(()=>!el('profile-results').hidden);
          if(profile.schema_version!=='vehicle-problem-profile-1.1'||
            profile.source_coverage.recalls.unique_record_count!==recalls||
            profile.source_coverage.manufacturer_communications.unique_record_count!==documents)
            throw Error('snapshot identity/counts');
          const sections=el('profile-results').querySelectorAll('.official-evidence');
          if(sections.length!==2||!sections[0].textContent.includes(recalls+' unique campaigns')||
            !sections[1].textContent.includes(documents+' unique documents'))
            throw Error('source rendering');
          if(documents>10&&!sections[1].textContent.includes('Showing the first 10 of 101'))
            throw Error('preview missing');
          if(!el('profile-results').textContent.includes('Canadian-market applicability'))
            throw Error('market applicability');
          el('profile-results').querySelectorAll('details').forEach(d=>d.open=true);
          if(document.documentElement.scrollWidth>innerWidth+1)throw Error('overflow');
        }
        document.body.setAttribute('data-profile-smoke','passed');
      }catch(e){document.body.setAttribute('data-profile-smoke','failed:'+e.message);}
    })();''')
