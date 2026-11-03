/** Local history review. Existing data controls/native rendering own application. */
export function createExperimentImports({mount,api,context,apply}) {
 const node=(tag,text,parent)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;parent?.append(e);return e;};
 const section=node("details",undefined,mount);section.id="experiment-import";
 node("summary","Import experiment runs",section);
 node("p","Read result files or completed tracker runs, choose a metric, then review a comparison. Source files stay unchanged.",section).className="muted";
 const field=(label,tag,id)=>{const l=node("label",label,section),e=node(tag,undefined,l);e.id=id;if(tag==="input")e.type="text";return e;};
 const provider=field("History source","select","experiment-provider");
 for(const [value,label] of [["csv","CSV result folder"],["tensorboard","TensorBoard event logs"],["mlflow","MLflow completed runs"],["wandb","W&B completed runs"]])provider.add(new Option(label,value));
 const source=field("Local folder or CSV file","input","experiment-source");source.type="text";source.placeholder="/path/to/results";source.maxLength=4096;
 const step=field("CSV step column","input","experiment-step");step.value="step";
 const columns=field("Metric columns or tags (optional, comma separated)","input","experiment-columns");
 const experimentIds=field("MLflow experiment IDs (comma separated)","input","experiment-ids");experimentIds.parentElement.hidden=true;
 const endpoint=field("W&B endpoint","input","experiment-endpoint");endpoint.value="https://api.forge.coreweave.com";endpoint.parentElement.hidden=true;
 const credential=field("Tracker API key (optional for local MLflow)","input","experiment-key");credential.type="password";credential.autocomplete="off";credential.parentElement.hidden=true;
 const disclosure=node("p","",section);disclosure.id="experiment-disclosure";disclosure.className="muted";disclosure.hidden=true;
 const networkLabel=node("label",undefined,section);networkLabel.className="check";networkLabel.hidden=true;
 const network=node("input",undefined,networkLabel);network.type="checkbox";network.id="experiment-network";networkLabel.append(document.createTextNode("Allow reads from this tracker endpoint using the supplied key"));
 const list=node("button","List runs",section);list.id="experiment-list";list.type="button";list.className="secondary";
 const status=node("p","",section);status.id="experiment-status";status.className="muted";status.setAttribute("role","status");
 const runList=node("fieldset",undefined,section);runList.id="experiment-runs";runList.hidden=true;
 const metric=field("Metric","select","experiment-metric");metric.disabled=true;
 const kind=field("Comparison","select","experiment-kind");kind.add(new Option("Line across steps","line"));kind.add(new Option("Raw points (keeps duplicate steps)","scatter"));
 const review=node("button","Review selected history",section);review.id="experiment-review";review.type="button";review.disabled=true;review.className="secondary";
 const preview=node("div",undefined,section);preview.id="experiment-proposal";preview.hidden=true;
 const summary=node("p","",preview),details=node("details",undefined,preview);node("summary","Proposed figure and source evidence",details);const raw=node("pre","",details);
 const check=(text,id)=>{const label=node("label",undefined,preview);label.className="check";const input=node("input",undefined,label);input.type="checkbox";input.id=id;label.append(document.createTextNode(text));return input;};
 const reviewed=check("I reviewed the selected runs, metric and figure","experiment-reviewed");
 const exclusions=check("Use valid observations with these recorded exclusions","experiment-exclusions");
 const accept=node("button","Apply and check comparison",preview);accept.id="experiment-accept";accept.type="button";accept.disabled=true;
 const undo=node("button","Undo experiment import",section);undo.id="experiment-undo";undo.type="button";undo.className="quiet";undo.disabled=true;
 let epoch=0,catalog=null,proposal=null,base=null,undoEntry=null,busy=false,pending=0;
 const key=()=>{try{return JSON.stringify(context());}catch{return null;}};
 const remote=()=>provider.value==="wandb"||(provider.value==="mlflow"&&/^https?:\/\//i.test(source.value));
 const options=()=>({provider:provider.value,source:source.value,step_field:step.value||"step",metrics:columns.value.trim()?columns.value.split(",").map(s=>s.trim()).filter(Boolean):null,
  ...(["mlflow","wandb"].includes(provider.value)?{tracker:{endpoint:endpoint.value,experiment_ids:experimentIds.value.split(",").map(s=>s.trim()).filter(Boolean),api_key:credential.value||null,allow_remote:network.checked}}:{})});
 const selected=()=>Array.from(runList.querySelectorAll("input:checked"),input=>input.value);
 function clearProposal(){if(proposal&&base){api("/api/experiments/cancel",{...base,id:proposal.id}).catch(()=>{});}proposal=null;base=null;preview.hidden=true;reviewed.checked=false;exclusions.checked=false;accept.disabled=true;}
 function eligibility(){
  const ids=selected();const rows=(catalog?.runs||[]).filter(r=>ids.includes(r.id));
  const entries=rows.map(r=>r.metrics.find(m=>m.name===metric.value));
  const duplicate=entries.some(m=>m?.duplicate_steps>0);
  review.disabled=busy||key()===null||!rows.length||entries.some(m=>!m||!m.valid_records)||(duplicate&&kind.value==="line");
  if(duplicate&&kind.value==="line")status.textContent="These runs contain duplicate steps. Choose Raw points to keep every record.";
  accept.disabled=busy||!proposal||!reviewed.checked||(proposal.report.excluded_records>0&&!exclusions.checked);
  undo.disabled=busy||!undoEntry||!undoEntry.current();
 }
 function providerFields(){source.parentElement.firstChild.textContent=provider.value==="wandb"?"W&B entity/project":provider.value==="mlflow"?"MLflow SQLite file or tracking-server URL":"Local folder or CSV file";credential.parentElement.firstChild.textContent=provider.value==="wandb"?"W&B API key":"MLflow access token (optional)";const tracked=["mlflow","wandb"].includes(provider.value);experimentIds.parentElement.hidden=provider.value!=="mlflow";endpoint.parentElement.hidden=provider.value!=="wandb";credential.parentElement.hidden=!tracked;networkLabel.hidden=!remote();disclosure.hidden=!tracked;disclosure.textContent=remote()?`Reads completed runs and raw histories from ${provider.value==="wandb"?endpoint.value:source.value}. Credentials stay in this local session;no training writes or source uploads.`:"MLflow opens a checked owned copy. The original store is never opened through the SDK. Completed runs only.";}
 function changed(){epoch++;clearProposal();catalog=null;runList.replaceChildren();runList.hidden=true;metric.replaceChildren();metric.disabled=true;providerFields();status.textContent="List the current source before selecting runs.";eligibility();}
 for(const input of [provider,source,step,columns,experimentIds,endpoint,credential,network])input.addEventListener("input",()=>{if(input!==network)network.checked=false;changed();});
 provider.addEventListener("change",()=>{step.disabled=provider.value!=="csv";step.parentElement.hidden=step.disabled;changed();});
 for(const input of [metric,kind])input.addEventListener("change",()=>{epoch++;clearProposal();eligibility();});
 reviewed.onchange=eligibility;exclusions.onchange=eligibility;
 list.onclick=async()=>{
  if(remote()&&!network.checked){status.textContent="Review the tracker endpoint disclosure and allow its network read first.";return;}
  const operation=++epoch;clearProposal();catalog=null;busy=true;pending=operation;eligibility();status.textContent="Reading local history…";
  try{
   const value=await api("/api/experiments/catalog",options());if(operation!==epoch)return;catalog=value;
   runList.replaceChildren();node("legend","Runs",runList);runList.hidden=false;
   for(const run of value.runs){const label=node("label",undefined,runList);label.className="check";const input=node("input",undefined,label);input.type="checkbox";input.value=run.id;label.append(document.createTextNode(run.name+" · "+run.id.slice(0,8)));input.onchange=()=>{epoch++;clearProposal();eligibility();};}
   metric.replaceChildren();for(const name of [...new Set(value.runs.flatMap(r=>r.metrics.map(m=>m.name)))].sort())metric.add(new Option(name,name));metric.disabled=!metric.options.length;
   status.textContent=`${value.runs.length} runs · ${value.files.length} source files · snapshot ${value.snapshot.slice(0,12)}. ${value.ignored_total} unsupported/non-numeric source entries remain outside numeric candidates.`;
  }catch(error){if(operation===epoch)status.textContent=error.message;}
  finally{if(pending===operation)busy=false;eligibility();}
 };
 review.onclick=async()=>{
  const operation=++epoch;clearProposal();busy=true;pending=operation;eligibility();status.textContent="Preparing an unapplied comparison…";
  try{
   const current=context(),before=JSON.stringify(current);
   const value=await api("/api/experiments/review",{...options(),...current,snapshot:catalog.snapshot,runs:selected(),metric:metric.value,kind:kind.value});
   if(operation!==epoch||before!==key()){api("/api/experiments/cancel",{...current,id:value.id}).catch(()=>{});return;}proposal=value;base=current;preview.hidden=false;
   summary.textContent=`${value.report.records} raw observations · ${value.report.runs.length} runs · ${value.report.excluded_records} excluded · ${value.report.duplicate_steps} duplicate steps. No aggregation or uncertainty is inferred. This figure is unapplied and unverified.`;
   raw.textContent=JSON.stringify({spec:value.spec,import_evidence:value.report},null,2);
   exclusions.parentElement.hidden=value.report.excluded_records===0;status.textContent="Review this comparison before applying it.";
  }catch(error){if(operation===epoch)status.textContent=error.message;}
  finally{if(pending===operation)busy=false;eligibility();}
 };
 accept.onclick=async()=>{
  if(!proposal||JSON.stringify(base)!==key()){clearProposal();status.textContent="Figure context changed;review again.";return;}
  const operation=epoch,current=base,identity=proposal.id;busy=true;pending=operation;eligibility();
  try{
   const value=await api("/api/experiments/accept",{...current,id:identity,reviewed:reviewed.checked,accept_exclusions:exclusions.checked});
   if(operation!==epoch||JSON.stringify(current)!==key())return;
   proposal=null;base=null;preview.hidden=true;undoEntry=apply(value.data,value.spec,value.report);
   status.textContent="Imported the selected snapshot. The existing renderer now checks the comparison.";
  }catch(error){if(operation===epoch){clearProposal();status.textContent=error.message;}}
  finally{if(pending===operation)busy=false;eligibility();}
 };
 undo.onclick=()=>{try{undoEntry.undo();undoEntry=null;status.textContent="Restored the previous dataset and figure. Checks rerun.";}catch(error){status.textContent=error.message;}eligibility();};
 return {refresh(){if(proposal&&JSON.stringify(base)!==key()){epoch++;clearProposal();status.textContent="Figure context changed;review again.";}eligibility();}};
}
