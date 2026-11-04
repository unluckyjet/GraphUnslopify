/** Static source proposals. The existing editor owns rendering and undo. */
export function createSourceImports({mount,api,context,apply}) {
  const node=(tag,text,parent)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;parent?.append(e);return e;};
  const section=node("details",undefined,mount);section.id="source-import";
  node("summary","Import a Python figure",section);
  node("p","Choose a Matplotlib or Seaborn script. Supported raw line, scatter and bar patterns become editable figures. Your script is read without running it; its original appearance may differ.",section).className="muted";
  const label=node("label","Python script (UTF8, up to 256 KiB)",section),file=node("input",undefined,label);file.type="file";file.accept=".py,.pyw";file.id="source-file";
  const check=(text,id,parent)=>{const l=node("label",undefined,parent);l.className="check";const e=node("input",undefined,l);e.type="checkbox";e.id=id;l.append(document.createTextNode(text));return e;};
  const map=check("Use the current CSV for references in this script","source-map",section);
  node("p","Referenced files are never opened automatically. This mapping is your declaration that the selected CSV is the intended data.",section).className="muted";
  const review=node("button","Review source import",section);review.id="source-review";review.type="button";review.className="secondary";
  const status=node("p","",section);status.id="source-status";status.setAttribute("role","status");
  const preview=node("div",undefined,section);preview.id="source-proposal";preview.hidden=true;
  const summary=node("p","",preview),details=node("details",undefined,preview);node("summary","Proposed figure and conversion report",details);const raw=node("pre","",details);
  const reviewed=check("I reviewed the source, data mapping and proposed figure","source-reviewed",preview);
  const partial=check("Use this partial extraction despite the listed unsupported behavior","source-partial",preview);
  const accept=node("button","Apply and check imported figure",preview);accept.id="source-accept";accept.type="button";
  const original=node("button","Save original source",section);original.id="source-original";original.type="button";original.className="quiet";
  const reportButton=node("button","Save conversion report",section);reportButton.id="source-report";reportButton.type="button";reportButton.className="quiet";
  const undo=node("button","Undo source import",section);undo.id="source-undo";undo.type="button";undo.className="quiet";
  node("p","Conversion reports accompany rendered exports and bundles. Original source stays separate; save it here. Applying starts the usual figure checks, which may still find problems.",section).className="muted";
  let epoch=0,pending=0,busy=false,proposal=null,base=null,undoEntry=null,report=null,sourceBytes=null,sourceName=null;
  const key=()=>{try{return JSON.stringify(context());}catch{return null;}};
  function clear(){if(proposal?.id&&base)api("/api/sources/cancel",{...base,id:proposal.id}).catch(()=>{});proposal=null;base=null;preview.hidden=true;reviewed.checked=false;partial.checked=false;}
  function eligibility(){
    let current=null;try{current=context();}catch{}
    map.disabled=busy||!current?.data_id;if(!current?.data_id)map.checked=false;
    review.disabled=busy||!file.files.length||!current;
    accept.disabled=busy||!proposal?.id||!reviewed.checked||(proposal.report.requires_partial_review&&!partial.checked);
    original.disabled=!sourceBytes;reportButton.disabled=!report;undo.disabled=busy||!undoEntry||!undoEntry.current();
  }
  function changed(){epoch++;clear();report=null;sourceBytes=null;sourceName=null;status.textContent="Review the selected source before applying it.";eligibility();}
  file.onchange=changed;map.onchange=changed;reviewed.onchange=eligibility;partial.onchange=eligibility;
  function download(bytes,name,type){const url=URL.createObjectURL(new Blob([bytes],{type}));const a=node("a",undefined,section);a.href=url;a.download=name;a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  original.onclick=()=>download(sourceBytes,sourceName,"text/x-python");
  reportButton.onclick=()=>download(JSON.stringify(report,null,2)+"\n","source-import.json","application/json");
  review.onclick=async()=>{
    const operation=++epoch;clear();busy=true;pending=operation;eligibility();status.textContent="Reading source without executing it…";
    try{
      const current=context(),before=JSON.stringify(current),selected=file.files[0];
      if(!selected||!selected.size||selected.size>256*1024)throw Error("Choose nonempty Python source of at most 256 KiB.");
      const bytes=new Uint8Array(await selected.arrayBuffer());let binary="";for(const byte of bytes)binary+=String.fromCharCode(byte);
      if(operation!==epoch||before!==key())return;
      const value=await api("/api/sources/review",{...current,source_name:selected.name,source_base64:btoa(binary),map_current_data:map.checked});
      if(operation!==epoch||before!==key()){if(value.id)api("/api/sources/cancel",{...current,id:value.id}).catch(()=>{});return;}
      proposal=value;base=current;report=value.report;sourceBytes=bytes;sourceName=selected.name;preview.hidden=false;
      summary.textContent=report.convertible?`${report.rows} raw observations · ${report.series} series · ${report.unsupported_count} unsupported statements. Review the conversion before applying. It is unverified.`:`Conversion refused: ${report.reason}. The original source and report can still be saved.`;
      raw.textContent=JSON.stringify({spec:value.spec,report},null,2);partial.parentElement.hidden=!report.requires_partial_review;reviewed.parentElement.hidden=!report.convertible;
      status.textContent=report.convertible?"Review the proposed figure and any unsupported behavior.":"No figure was applied.";
    }catch(error){if(operation===epoch)status.textContent=error.message;}
    finally{if(pending===operation)busy=false;eligibility();}
  };
  accept.onclick=async()=>{
    if(!proposal?.id||JSON.stringify(base)!==key()){clear();status.textContent="Figure changed; review the source again.";eligibility();return;}
    const operation=epoch,current=base,identity=proposal.id;busy=true;pending=operation;eligibility();
    try{
      const value=await api("/api/sources/accept",{...current,id:identity,reviewed:reviewed.checked,accept_partial:partial.checked});
      if(operation!==epoch||JSON.stringify(current)!==key())return;
      proposal=null;base=null;preview.hidden=true;report=value.report;undoEntry=apply(value.data,value.spec,value.report);
      status.textContent="Imported the reviewed source. The existing renderer now checks the figure.";
    }catch(error){if(operation===epoch){clear();status.textContent=error.message;}}
    finally{if(pending===operation)busy=false;eligibility();}
  };
  undo.onclick=()=>{try{undoEntry.undo();undoEntry=null;status.textContent="Restored the previous dataset and figure. Checks rerun.";}catch(error){status.textContent=error.message;}eligibility();};
  eligibility();
  return {refresh(){if(proposal&&JSON.stringify(base)!==key()){epoch++;clear();status.textContent="Figure changed; review the source again.";}eligibility();}};
}
