/** Frozen actual-browser first-image/final-result comparison; no held checks. */
const assert = require('node:assert/strict');
const {spawn, execFileSync} = require('node:child_process');
const {createHash, randomUUID} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {createInterface} = require('node:readline');
const {setTimeout: delay} = require('node:timers/promises');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const base = path.join(root, 'benchmarks/staged');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const hash = name => digest(fs.readFileSync(name));
const argv = process.argv.slice(2);
const smoke = argv.includes('--smoke');
const at = argv.indexOf('--out-dir');
assert(at >= 0 && argv[at + 1], '--out-dir is required');
const out = path.resolve(argv[at + 1]);
fs.mkdirSync(out, {recursive:false});
const rules = JSON.parse(fs.readFileSync(path.join(base,'protocol.json')));
assert.equal(hash(path.join(base,'protocol.json')), 'cea35240ac9567bb2df5a93c1f074c645991fe0b78ada431b3cb98e6ca74d53d');
for(const c of rules.cases) {
  assert.equal(hash(path.resolve(base,c.data)),c.data_sha256);
  for(const e of c.edits) assert.equal(hash(path.resolve(base,e.spec)),e.spec_sha256);
}
assert.equal(hash(path.join(root,'benchmarks/incremental/protocol.json')),rules.numerical_cache_protocol_sha256);
const cycles = smoke ? rules.schedule.smoke_cycles : rules.schedule.ordinary.cycles;
const expected = smoke ? rules.schedule.smoke_records : rules.schedule.formal_records;
const python = process.env.PYTHON || 'python';
const env = process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED ? {...process.env}
  : {...process.env,PYTHONPATH:path.join(root,'python')};
if(process.env.GRAPHUNSLOPIFY_PREVIEW_NODE_OPTIONS)
  env.NODE_OPTIONS=process.env.GRAPHUNSLOPIFY_PREVIEW_NODE_OPTIONS;
const git = fs.existsSync('/Library/Developer/CommandLineTools/usr/bin/git')
  ? '/Library/Developer/CommandLineTools/usr/bin/git' : 'git';
const packageFiles = {};
function inventory(folder, prefix='') {
  for(const entry of fs.readdirSync(folder,{withFileTypes:true})) {
    const name=prefix+entry.name, file=path.join(folder,entry.name);
    if(entry.isDirectory() && entry.name!=='__pycache__') inventory(file,name+'/');
    else if(entry.isFile() && /\.(py|mjs|js|json|txt|css|html|ipynb)$/.test(name)) packageFiles[name]=hash(file);
  }
}
inventory(path.join(root,'python/graphunslopify'));
const result = {
  schema_version:1,protocol_sha256:hash(path.join(base,'protocol.json')),
  mode:smoke?'smoke':'formal',scope:rules.scope,
  source_commit:execFileSync(git,['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  source_git_dirty:!!execFileSync(git,['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),
  driver_sources:Object.fromEntries(['scripts/benchmark-staged-preview.cjs','scripts/serve-staged-benchmark.py',
    'scripts/profile-preview-phases.py','scripts/rendering-benchmark.py'].map(n=>[n,hash(path.join(root,n))])),
  expected_records:expected,cycles,cases:[],complete:false,passed:false,
  clocks:rules.clocks,started_at:new Date().toISOString(),
};
const median = values => {const s=[...values].sort((a,b)=>a-b);return (s[Math.floor((s.length-1)/2)]+s[Math.ceil((s.length-1)/2)])/2;};
const p90 = values => {const s=[...values].sort((a,b)=>a-b),p=(s.length-1)*.9,l=Math.floor(p);return s[l]+(s[Math.min(l+1,s.length-1)]-s[l])*(p-l);};
const references = new Map();
let browser;

function epochs(events, max, kind, source) {
  const groups=new Map();
  for(const {execution:e} of events) {
    assert.equal(e.mode,'worker');assert.equal(e.kind,kind);
    assert.equal(e.runtime_source_sha256,source);
    assert(Number.isInteger(e.pid) && e.pid>0);assert.match(e.request_id,/^[0-9a-f]{32}$/);
    const key=e.process_starts;
    if(!groups.has(key))groups.set(key,{pid:e.pid,requests:[]});
    const group=groups.get(key);assert.equal(group.pid,e.pid);group.requests.push(e);
  }
  const ordered=[...groups.entries()].sort((a,b)=>a[0]-b[0]);
  for(const [i,[start,group]] of ordered.entries()) {
    assert.equal(start,i+1);
    const rows=group.requests.sort((a,b)=>a.request_number-b.request_number);
    assert(rows.length<=max);
    if(i<ordered.length-1)assert.equal(rows.length,max,'Healthy worker recycled before its unchanged budget');
    for(const [index,e] of rows.entries()) {
      assert.equal(e.request_number,index+1);assert.equal(e.process_started,index===0);
    }
  }
  return {actual_operations:events.length,actual_epochs:ordered.length,max_requests:max,
    epochs:ordered.map(([start,g])=>({process_starts:start,pid:g.pid,requests:g.requests.length}))};
}

// This executes in the real document. Decode/identity checks run in both arms.
function installClock() {
  window.__guStagedBenchmark = {label:null,active:null};
  addEventListener('DOMContentLoaded',()=>{
    const image=document.querySelector('#preview'), status=document.querySelector('#status');
    function sample() {
      const active=window.__guStagedBenchmark.active;
      if(!active || active.final || image.hidden || !image.getClientRects().length) return;
      const phase=image.dataset.phase, src=image.currentSrc || image.src;
      if(!['unverified','final'].includes(phase) || !src) return;
      const generation=image.dataset.generation, runId=image.dataset.runId;
      const key=[phase,src,generation,runId].join('|');
      if(active.decoding.has(key)) return;
      active.decoding.add(key);
      image.decode().then(()=>{
        if(window.__guStagedBenchmark.active!==active || active.final || image.hidden ||
          image.dataset.phase!==phase || image.dataset.generation!==generation ||
          (image.currentSrc || image.src)!==src || !image.naturalWidth) return;
        const seconds=(performance.now()-active.start)/1000;
        const snapshot={seconds,phase,generation,width:image.naturalWidth,height:image.naturalHeight,
          status:status.dataset.state,files:document.querySelectorAll('#files a').length,
          bundle_disabled:document.querySelector('#bundle').disabled,
          text_hidden:document.querySelector('#text-targets').hidden,
          diagnostics_hidden:document.querySelector('#diagnostic-targets').hidden,
          claims:document.querySelector('#claims').textContent,
          image_sha256:image.dataset.imageSha256 || null,run_id:runId || null};
        if(phase==='unverified') {
          if(snapshot.status!=='unverified' || !snapshot.bundle_disabled || snapshot.files ||
            !snapshot.text_hidden || !snapshot.diagnostics_hidden || snapshot.claims)
            active.errors.push('Unverified DOM carries final acceptance/exports/targets');
          active.provisional=snapshot;
        }
        if(!active.first)active.first=snapshot;
        if(phase==='final' && ['passed','failed','incomplete'].includes(snapshot.status)) {
          if(!runId || snapshot.bundle_disabled || !snapshot.files)
            active.errors.push('Final DOM does not contain its current exports');
          active.final=snapshot;
        }
      }).catch(()=>{}); // A replaced image is not an observed current image.
    }
    new MutationObserver(sample).observe(document.documentElement,
      {subtree:true,childList:true,attributes:true,characterData:true});
    image.addEventListener('load',sample);
    document.addEventListener('click',event=>{
      if(!event.target.closest?.('#render'))return;
      window.__guStagedBenchmark.active={label:window.__guStagedBenchmark.label,
        start:performance.now(),first:null,final:null,provisional:null,errors:[],decoding:new Set()};
    },true);
  });
}

async function armCase(c,arm) {
  const folder=path.join(out,c.id,arm);
  fs.mkdirSync(folder,{recursive:true});
  const started=performance.now();
  const server=spawn(python,[path.join(root,'scripts/serve-staged-benchmark.py'),'--arm',arm,
    '--out-dir',path.join(folder,'server')],{env,cwd:root,stdio:['pipe','pipe','pipe']});
  let stderr=''; server.stderr.on('data',b=>stderr=(stderr+b).slice(-30000));
  const safeError=error=>String(error).replace(/([?&]token=)[^&\s]+/g,'$1[redacted]');
  const lines=createInterface({input:server.stdout}),pending=new Map();
  let acceptReady,rejectReady;
  const ready=new Promise((accept,reject)=>{acceptReady=accept;rejectReady=reject;});
  lines.on('line',line=>{
    try {const body=JSON.parse(line);if(body.url)acceptReady(body);
      else if(body.id && pending.has(body.id)){const p=pending.get(body.id);pending.delete(body.id);
        body.error?p.reject(Error(body.error)):p.accept(body.result);}}
    catch(error){rejectReady(error);}
  });
  server.once('exit',code=>{rejectReady(Error('Benchmark server exited '+code+': '+safeError(stderr)));
    for(const p of pending.values())p.reject(Error('Benchmark server exited '+code));});
  function rpc(body) {return new Promise((accept,reject)=>{const id=randomUUID();pending.set(id,{accept,reject});
    server.stdin.write(JSON.stringify({...body,id})+'\n');});}
  let context;
  const record={id:c.id,arm,records:[],passed:false};result.cases.push(record);
  try {
    const info=await Promise.race([ready,delay(30000,undefined,{ref:false}).then(()=>{throw Error('Server startup deadline');})]);
    record.server_startup_seconds=(performance.now()-started)/1000;
    record.server=info;
    assert.deepEqual(info.package_files,packageFiles,'Actually imported package must match all source files');
    for(const name of ['numpy','pandas','matplotlib','scipy','pyarrow']) {
      const module=info.environment[name]?.module;
      assert(module,'Scientific dependency missing: '+name);
      const relative=path.relative(info.environment.prefix,module);
      assert(!relative.startsWith('..') && !path.isAbsolute(relative),'Dependency outside actual environment: '+name);
    }
    const sourceRoot=path.join(root,'python/graphunslopify');
    assert.equal(path.resolve(info.environment.package_root)===sourceRoot,!process.env.GRAPHUNSLOPIFY_PREVIEW_INSTALLED);
    const created=performance.now();
    context=await browser.newContext({viewport:{width:1500,height:1000}});
    record.context_startup_seconds=(performance.now()-created)/1000;
    const page=await context.newPage();page.setDefaultTimeout(130000);
    await page.addInitScript(installClock);
    const errors=[],external=[],requestOwners=new WeakMap();
    let current=null;
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',request=>{
      if(current)requestOwners.set(request,current);
      if(!request.url().startsWith(info.url) && !request.url().startsWith('data:'))external.push('external request');
      if(current && new URL(request.url()).pathname==='/api/render') current.render_request=request;
    });
    page.on('response',response=>{
      const owner=requestOwners.get(response.request());
      if(!owner)return;
      const pathname=new URL(response.url()).pathname;
      if(pathname==='/api/render' || pathname.startsWith('/stage/'))
        owner.responses.push({response,pathname});
    });
    async function inspectResponses(owner) {
      // No body retrieval, JSON validation or independent PNG digest in live clocks.
      owner.request=owner.render_request?.postDataJSON();
      for(const {response,pathname} of owner.responses) {
        if(pathname==='/api/render') {
          try {owner.answer=await response.json();}
          catch(error){owner.response_error=safeError(error);}
        } else {
          try {
            if(pathname.endsWith('/png'))owner.progress_png_sha256.push(digest(await response.body()));
            else {
              const body=await response.json();
              owner.progress.push({phase:body.phase,verified:body.verified,
                image_sha256:body.image?.sha256 || null,producer_pid:body.producer_pid || null});
            }
          } catch {owner.progress_transport_unavailable++;}
        }
      }
    }
    const setup=performance.now();
    const infoResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/info');
    await page.goto(info.url);
    assert.equal((await (await infoResponse).json()).staged_preview,arm==='staged');
    await page.waitForFunction(()=>document.querySelectorAll('#kind option').length===21);
    await page.locator('#live').uncheck();
    await page.locator('#advanced').evaluate(node=>node.setAttribute('open',''));
    await page.locator('#data-file').setInputFiles(path.resolve(base,c.data));
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready to render');
    record.page_and_upload_setup_seconds=(performance.now()-setup)/1000;
    const schedule=[{phase:'first-fresh-font',cycle:null,edit:c.edits[0]}];
    for(let cycle=0;cycle<cycles;cycle++)for(const edit of c.edits)schedule.push({phase:'ordinary-warm-font',cycle,edit});
    schedule.push({phase:'instrumented-warm-font',cycle:null,edit:c.edits[0]});
    const preserved=new Set();
    for(const [index,item] of schedule.entries()) {
      const label=`${index}-${item.phase}-${item.edit.id}`;
      const entry={index,phase:item.phase,cycle:item.cycle,edit:item.edit.id,passed:false};
      record.records.push(entry);
      current={responses:[],progress:[],progress_png_sha256:[],progress_transport_unavailable:0};
      try {
        await rpc({op:'prepare',label,instrumented:item.phase==='instrumented-warm-font'});
        const setupStart=performance.now();
        await page.locator('#spec').fill(fs.readFileSync(path.resolve(base,item.edit.spec),'utf8'));
        await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ready to render');
        assert(await page.locator('#preview').isHidden());
        assert.equal(await page.locator('#files a').count(),0);
        entry.intent_setup_seconds=(performance.now()-setupStart)/1000;
        await page.evaluate(label=>{window.__guStagedBenchmark.label=label;},label);
        await page.locator('#render').click();
        await page.waitForFunction(()=>!!window.__guStagedBenchmark.active?.final);
        const clock=await page.evaluate(()=>{
          const a=window.__guStagedBenchmark.active;
          return {label:a.label,first:a.first,final:a.final,provisional:a.provisional,errors:a.errors};
        });
        Object.assign(entry,{clock,first_image_seconds:clock.first?.seconds ?? null,
          final_result_seconds:clock.final?.seconds ?? null,
          no_provisional_observed:!clock.provisional});
        await inspectResponses(current);
        assert(!current.response_error,current.response_error);
        const answer=current.answer;
        entry.exit_code=answer?.exit_code;entry.status=answer?.report?.status;
        entry.verified_result_seconds=entry.status==='passed'?entry.final_result_seconds:null;
        entry.final_failure_seconds=entry.status==='failed'?entry.final_result_seconds:null;
        assert(answer?.report && !answer.stale && !answer.export_errors.length);
        assert.deepEqual(current.request.spec,JSON.parse(fs.readFileSync(path.resolve(base,item.edit.spec))),'Actual UI request differs from frozen intent');
        assert.equal(answer.report.data.sha256_prefix,c.data_sha256.slice(0,16));
        assert.equal(answer.exit_code,c.expected_exit_code);assert.equal(answer.report.status,c.expected_status);
        assert.equal(answer.report.policy.strict,true);
        assert.equal(answer.execution.mode,'worker');assert.equal(answer.execution.provisional,arm==='staged');
        assert.equal(answer.execution.instrumented,item.phase==='instrumented-warm-font');
        assert.equal(answer.translation_execution.mode,'worker');
        assert.equal(answer.translation_execution.runtime_source_sha256,packageFiles['_translator.mjs']);
        assert.equal(answer.execution.runtime_source_sha256,info.runtime_source_sha256);
        assert(answer.execution.statistics_cache.enabled);
        assert.equal(answer.execution.statistics_cache.pid,answer.execution.pid);
        const cache=answer.execution.statistics_cache;
        assert.equal(cache.version,1);assert.equal(cache.max_entries,64);
        assert.equal(cache.max_bytes,33554432);assert.equal(cache.max_entry_bytes,8388608);
        assert(cache.entries<=cache.max_entries && cache.serialized_bytes<=cache.max_bytes);
        assert.equal(clock.label,label);assert.deepEqual(clock.errors,[]);
        assert.equal(clock.final.run_id,answer.run_id);assert.equal(Number(clock.final.generation),answer.generation);
        assert.equal(clock.first.generation,clock.final.generation);assert.equal(clock.final.status,c.expected_status);
        assert(clock.first.seconds>0 && clock.final.seconds>=clock.first.seconds);
        for(const p of current.progress)if(p.phase==='unverified')assert.equal(p.verified,false);
        if(arm==='final-only')assert.equal(current.progress.length,0);
        const proof=await rpc({op:'proof',label,run_id:answer.run_id,preserve_reference:!preserved.has(item.edit.id)});
        preserved.add(item.edit.id);
        assert.equal(proof.input_sha256,c.data_sha256);
        assert.equal(proof.native_events.length,1);
        assert.deepEqual(proof.formats,[...JSON.parse(fs.readFileSync(path.resolve(base,item.edit.spec))).output.formats].sort());
        for(const sha of current.progress_png_sha256)assert.equal(sha,proof.png_sha256);
        if(clock.provisional) {
          assert.equal(clock.provisional.image_sha256,proof.png_sha256);
          assert(current.progress_png_sha256.includes(proof.png_sha256));
        }
        const key=c.id+'/'+item.edit.id;
        if(references.has(key))assert.equal(proof.signature_sha256,references.get(key),'Original science/script/data/PNG/table/maps changed across arms/cycles');
        else references.set(key,proof.signature_sha256);
        Object.assign(entry,{passed:true,clock,
          first_image_seconds:clock.first.seconds,final_result_seconds:clock.final.seconds,
          verified_result_seconds:c.expected_status==='passed'?clock.final.seconds:null,
          final_failure_seconds:c.expected_status==='failed'?clock.final.seconds:null,
          no_provisional_observed:!clock.provisional,exit_code:answer.exit_code,status:answer.report.status,
          generation:answer.generation,execution:answer.execution,translation_execution:answer.translation_execution,
          proof,progress:current.progress,progress_png_sha256:current.progress_png_sha256,
          progress_transport_unavailable:current.progress_transport_unavailable});
        assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
        console.log(`${c.id}/${arm}/${index+1}/${schedule.length} passed`);
      } catch(error) {
        entry.error=safeError(error);
        if(!entry.clock) {
          try {
            entry.partial_clock=await page.evaluate(()=>{
              const a=window.__guStagedBenchmark.active;
              return a?{label:a.label,first:a.first,final:a.final,provisional:a.provisional,errors:a.errors}:null;
            });
            if(entry.partial_clock?.label===label) {
              entry.first_image_seconds=entry.partial_clock.first?.seconds ?? null;
              entry.final_result_seconds=entry.partial_clock.final?.seconds ?? null;
              entry.no_provisional_observed=!entry.partial_clock.provisional;
            }
          } catch { /* The closed page is an explicitly untimed failed attempt. */ }
        }
        throw error;
      }
      finally {
        fs.appendFileSync(path.join(out,'records.jsonl'),JSON.stringify({case:c.id,arm,...entry})+'\n');
      }
    }
    record.passed=true;
    record.javascript_errors=errors;record.external_requests=external;
  } catch(error) {record.error=safeError(error);record.stderr=safeError(stderr);}
  finally {
    if(context)await context.close();
    if(server.exitCode===null) {
      const exited=new Promise(resolve=>server.once('exit',resolve));
      server.stdin.end(JSON.stringify({op:'close',id:randomUUID()})+'\n');
      await Promise.race([exited,delay(145000,undefined,{ref:false}).then(()=>{server.kill('SIGINT');throw Error('Owned benchmark server close deadline');})]);
    }
    lines.close();
    const closed=JSON.parse(fs.readFileSync(path.join(folder,'server/closed.json')));
    record.closed=closed;
    assert(closed.native_closed && closed.compiler_closed && closed.temporary_root_removed);
    record.native_lifecycle=epochs(closed.native_events,rules.both_arms.native_max_requests,
      'renderer',record.server.runtime_source_sha256);
    record.compiler_lifecycle=epochs(closed.compiler_events,rules.both_arms.compiler_max_requests,
      'translator',packageFiles['_translator.mjs']);
    fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');
  }
}

(async()=>{
  try {
    const mac='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
    const executable=process.env.GRAPHUNSLOPIFY_BROWSER || (fs.existsSync(mac)?mac:undefined);
    const began=performance.now();
    browser=await chromium.launch({headless:true,...(executable?{executablePath:executable}:{})});
    result.browser={version:browser.version(),startup_seconds:(performance.now()-began)/1000};
    for(const [index,c] of rules.cases.entries())
      for(const arm of (index%2?[...rules.arms].reverse():rules.arms))await armCase(c,arm);
    const records=result.cases.flatMap(c=>c.records);
    result.observed_records=records.length;
    result.complete=records.length===expected && result.cases.every(c=>c.records.length===cycles*7+2);
    result.passed=result.complete && result.cases.every(c=>c.passed) && records.every(r=>r.passed);
    result.outcomes={clean:records.filter(r=>r.exit_code===0).length,original_negative:records.filter(r=>r.exit_code===2).length};
    result.summaries=result.cases.map(c=>({id:c.id,arm:c.arm,edits:rules.cases.find(r=>r.id===c.id).edits.map(e=>{
      const attempted=c.records.filter(r=>r.phase==='ordinary-warm-font' && r.edit===e.id);
      const rows=attempted.filter(r=>Number.isFinite(r.first_image_seconds) && Number.isFinite(r.final_result_seconds));
      const firstRows=attempted.filter(r=>Number.isFinite(r.first_image_seconds));
      const finalRows=attempted.filter(r=>Number.isFinite(r.final_result_seconds));
      return {edit:e.id,ordinary_attempted:attempted.length,ordinary_passed:attempted.filter(r=>r.passed).length,
        ordinary_timed:rows.length,ordinary_untimed:attempted.length-rows.length,
        ordinary_first_image_timed:firstRows.length,ordinary_final_result_timed:finalRows.length,
        ordinary_not_run:cycles-attempted.length,ordinary_expected:cycles,
        timing_population:'All finite measured attempts, including nonconforming failures; all raw/untimed/unrun counts retained',
        no_provisional_observed:rows.filter(r=>r.no_provisional_observed).length,
        first_image_seconds:firstRows.length?{median:median(firstRows.map(r=>r.first_image_seconds)),p90:p90(firstRows.map(r=>r.first_image_seconds))}:null,
        final_result_seconds:finalRows.length?{median:median(finalRows.map(r=>r.final_result_seconds)),p90:p90(finalRows.map(r=>r.final_result_seconds))}:null};
    })}));
    if(!result.passed)process.exitCode=1;
  } catch(error){result.error=String(error);process.exitCode=1;}
  finally {
    if(browser)await browser.close();
    result.completed_at=new Date().toISOString();
    fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify({passed:result.passed,complete:result.complete,
      observed_records:result.observed_records,expected_records:expected,out}));
  }
})();
