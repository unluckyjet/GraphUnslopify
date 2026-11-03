// Local portable intent is a proposal. The owning editor applies and verifies it.
export function createIntentReuse({mount,context,api,flush=()=>{},apply,onState=()=>{}}) {
  mount.innerHTML = `<details id="reuse-panel"><summary>Templates &amp; export presets</summary>
    <p class="muted">Save a design as a local file, or reuse one with this dataset. Review field mappings, calculations and authored text before applying. Checks run again.</p>
    <label>Template name<input id="reuse-name" type="text" maxlength="100" value="My figure design"></label>
    <button id="reuse-save" class="secondary">Save template file</button>
    <label>Open template file<input id="reuse-file" type="file" accept=".json,application/json"></label>
    <p id="reuse-loaded" class="muted"></p><div id="reuse-mapping"></div>
    <label class="reuse-check"><input id="reuse-claims" type="checkbox">Replace current claims with template claims</label>
    <button id="reuse-template-review" class="secondary">Review template</button>
    <label>Export preset<select id="reuse-preset"></select></label>
    <p id="reuse-preset-description" class="muted"></p>
    <button id="reuse-preset-review" class="secondary">Review export preset</button>
    <p id="reuse-status" class="muted" role="status" aria-live="polite"></p>
    <div id="reuse-review" hidden><h3 id="reuse-title"></h3><p id="reuse-policy"></p>
      <div id="reuse-changes" class="reuse-changes"></div><ul id="reuse-findings"></ul><ul id="reuse-notes"></ul>
      <label class="reuse-check"><input id="reuse-reviewed" type="checkbox">I reviewed these changes for the current data</label>
      <button id="reuse-apply" disabled>Apply reviewed intent</button>
    </div><button id="reuse-cancel" class="quiet">Close or cancel review</button></details>`;
  const $=id=>mount.querySelector("#reuse-"+id),pretty=value=>value===undefined?"(absent)":JSON.stringify(value);
  let template=null,plan=null,busy=false,epoch=0,key="",fields=[],mapping=Object.create(null),presetKey="",allowedPaths=null,proposalGuard=null;
  const current=()=>{try{return context();}catch{return {key:"invalid",busy:true,reason:"Correct the current JSON before reusing intent.",columns:[],presets:[]};}};
  const say=text=>{$("status").textContent=text;};
  function reset(message="",notify=true){epoch++;plan=null;busy=false;proposalGuard=null;$("review").hidden=true;$("reviewed").checked=false;if(message)say(message);buttons();if(notify)onState();}
  function buttons(){
    const ctx=current(),blocked=busy||ctx.busy;
    $("preset-description").textContent=(ctx.presets||[]).find(p=>p.id===$("preset").value)?.description||"";
    $("save").disabled=blocked||!ctx.canRead||!$("name").value.trim();
    $("file").disabled=blocked||!ctx.editable;$("preset").disabled=blocked||!ctx.editable;
    $("claims").disabled=blocked||!ctx.editable||!template;
    $("template-review").disabled=blocked||!ctx.editable||!template;
    $("preset-review").disabled=blocked||!ctx.editable||!$("preset").value;
    $("apply").disabled=blocked||!ctx.editable||!plan?.can_apply||!$("reviewed").checked;
    for(const select of $("mapping").querySelectorAll("select"))select.disabled=blocked||!ctx.editable;
    const narrow=!!allowedPaths;
    $("mapping").hidden=narrow;
    $("claims").closest("label").hidden=narrow;
    $("template-review").hidden=narrow;
    $("preset").closest("label").hidden=narrow;
    $("preset-description").hidden=narrow;$("preset-review").hidden=narrow;
  }
  function showMapping(){
    const columns=current().columns||[];$("mapping").replaceChildren();
    for(const field of fields){
      const label=document.createElement("label"),text=document.createElement("span"),select=document.createElement("select");
      text.textContent="Map "+field;select.setAttribute("aria-label","Map template field "+field);select.dataset.source=field;
      select.append(new Option("Choose an active column",""),...columns.map(name=>new Option(name,name)));
      if(!Object.hasOwn(mapping,field))mapping[field]=columns.includes(field)?field:"";
      select.value=columns.includes(mapping[field])?mapping[field]:"";
      select.onchange=()=>{mapping[field]=select.value;reset("Mapping changed. Review the template again.");};
      label.append(text,select);$("mapping").append(label);
    }
  }
  function update(){
    if(proposalGuard&&!proposalGuard()){proposalGuard=null;reset("Journal selection changed. Review the export proposal again.",false);}
    const ctx=current(),next=String(ctx.key);
    if(next!==key){key=next;mapping=Object.create(null);reset("Current inputs changed. Review intent again.",false);showMapping();}
    const presets=ctx.presets||[],nextPresets=JSON.stringify(presets);
    if(nextPresets!==presetKey){presetKey=nextPresets;const selected=$("preset").value;$("preset").replaceChildren(...presets.map(p=>new Option(p.name,p.id)));if(presets.some(p=>p.id===selected))$("preset").value=selected;}
    if(ctx.reason)say(ctx.reason);buttons();
  }
  async function request(kind){
    if(busy||flush()===false)return;update();const ctx=current();if(ctx.busy||!ctx.editable)return;
    const guard=proposalGuard;reset("Reviewing canonical intent…",false);proposalGuard=guard;const stamp=epoch,identity=ctx.key;busy=true;buttons();onState();
    const payload={...ctx.payload,spec:ctx.spec,...(kind==="template"?{template,mapping:Object.fromEntries(Object.entries(mapping).filter(([field,target])=>target&&field!==target)),replace_claims:$("claims").checked}:{preset:$("preset").value})};
    try{
      const result=await api("/api/reuse/proposal",payload);
      if(stamp!==epoch||identity!==current().key||(proposalGuard&&!proposalGuard()))return;
      if(allowedPaths&&result.changes.some(change=>!allowedPaths.includes(change.path)))
        throw Error("The format proposal would change other settings. Review the current definition again.");
      plan=result;fields=result.fields;showMapping();$("title").textContent=result.name;
      $("policy").textContent=`Dataset, palette and output name stay bound to this editor. Claims ${result.claims_policy==="template"?"come from the template and need verification":"stay as currently authored"}. No verification result is transferred.`;
      $("changes").replaceChildren();
      for(const change of result.changes){const row=document.createElement("p"),name=document.createElement("strong"),values=document.createElement("code");name.textContent=(allowedPaths&&change.path==="/output/formats"?"Export formats":change.path)+": ";values.textContent=pretty(change.before)+" → "+pretty(change.after);row.append(name,values);$("changes").append(row);}
      for(const [id,values] of [["findings",result.findings.map(f=>`${f.severity}: ${f.message}`)],["notes",result.notes||[]]]){$(id).replaceChildren(...values.map(text=>{const li=document.createElement("li");li.textContent=text;return li;}));}
      $("review").hidden=false;$("reviewed").checked=false;
      say(result.can_apply?"Review the changes, then apply and verify.":result.changes.length?"Correct the listed findings or field mappings, then review again.":"This intent already matches the current figure. No changes to apply.");
    }catch(error){if(stamp===epoch)say(error.message);}
    finally{if(stamp===epoch){busy=false;buttons();onState();}}
  }
  $("save").onclick=async()=>{
    if(busy||flush()===false)return;update();const ctx=current();if(ctx.busy||!ctx.canRead)return;
    reset("Saving a local template…",false);const stamp=epoch,identity=ctx.key;busy=true;buttons();onState();
    try{
      const result=await api("/api/reuse/template",{...ctx.payload,spec:ctx.spec,name:$("name").value});
      if(stamp!==epoch||identity!==current().key)return;
      const file=new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json"});
      if(file.size>1024*1024)throw Error("The formatted template exceeds 1 MiB. Reduce authored text or settings before saving.");
      const url=URL.createObjectURL(file),link=document.createElement("a");
      link.href=url;link.download=(result.name.replace(/[^\p{L}\p{N}._ -]/gu,"_")||"figure")+".gu-template.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      say("Template saved locally without dataset paths, palette paths or the output name. Authored text and claims remain in the template.");
    }catch(error){if(stamp===epoch)say(error.message);}
    finally{if(stamp===epoch){busy=false;buttons();onState();}}
  };
  $("file").onchange=async()=>{
    const file=$("file").files[0];reset("Opening local template…");if(!file)return;
    allowedPaths=null;
    proposalGuard=null;
    template=null;fields=[];mapping=Object.create(null);$("loaded").textContent="";showMapping();$("claims").checked=false;
    const stamp=epoch,identity=current().key;busy=true;buttons();onState();
    try{if(file.size>1024*1024)throw Error("Choose a template no larger than 1 MiB.");const value=JSON.parse(await file.text());if(stamp!==epoch||identity!==current().key)return;template=value;$("loaded").textContent="Opened "+file.name;busy=false;await request("template");}
    catch(error){if(stamp===epoch)say(error.message);}
    finally{if(stamp===epoch){busy=false;buttons();onState();}}
  };
  $("template-review").onclick=()=>request("template");$("preset-review").onclick=()=>{allowedPaths=null;proposalGuard=null;return request("preset");};
  $("claims").onchange=()=>reset("Claim policy changed. Review the template again.");$("preset").onchange=()=>reset("Preset changed. Review it before applying.");
  $("reviewed").onchange=buttons;$("name").oninput=buttons;$("cancel").onclick=()=>{allowedPaths=null;reset("Review closed.");};
  mount.querySelector("#reuse-panel").ontoggle=event=>{if(!event.target.open&&(plan||busy)){allowedPaths=null;reset("Review closed.");}};
  $("apply").onclick=()=>{
    update();
    const ctx=current();if(busy||ctx.busy||!ctx.editable||!plan?.can_apply||!$("reviewed").checked)return;
    const candidate=structuredClone(plan.spec);allowedPaths=null;reset("Applied to the current draft. Verification is required.");apply(candidate);
  };
  update();
  return {
    update,clear:(message,notify=true)=>reset(message,notify),pending:()=>busy||!!plan,
    async reviewPdfExport(guard=()=>true) {
      if(busy||plan||flush()===false)throw Error("Finish the current intent review first.");
      update();const ctx=current();
      if(ctx.busy||!ctx.editable||!ctx.canRead)throw Error(ctx.reason||"Choose an editable current definition.");
      if(!guard())throw Error("Journal selection changed; check the current export again.");
      reset("Preparing a PDF export proposal…",false);
      proposalGuard=guard;
      const stamp=epoch,identity=ctx.key;busy=true;buttons();onState();
      try {
        const value=await api("/api/reuse/template",{...ctx.payload,spec:ctx.spec,name:"Add PDF export for journal review"});
        if(stamp!==epoch||identity!==current().key||!guard())return;
        const formats=value.intent.output.formats;
        if(formats.includes("pdf"))throw Error("PDF is already requested. Render or audit this definition,then choose its PDF export.");
        value.intent.output.formats=[...formats,"pdf"];
        template=value;fields=[];mapping=Object.create(null);allowedPaths=["/output/formats"];
        $("claims").checked=false;$("loaded").textContent="Proposed PDF export; existing formats are retained.";
        mount.querySelector("#reuse-panel").open=true;
        busy=false;await request("template");
        $("review").scrollIntoView({block:"nearest"});
      } catch(error) {if(stamp===epoch)say(error.message);}
      finally {if(stamp===epoch){busy=false;buttons();onState();}}
    },
  };
}
