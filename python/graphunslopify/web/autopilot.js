/** Review local dataset/question proposals; compare every real native outcome before applying. */
export function createAutopilot({mount, resultsMount, api, context, dataset, apply, fileURL}) {
  const node=(tag,text,parent)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;parent?.append(e);return e;};
  const section=node("details",undefined,mount);section.id="autopilot";
  node("summary","Start from a research question",section);
  node("p","Use your selected dataset to review three local figure options, then generate and check all three. You choose what to use.",section).className="muted";
  const questionLabel=node("label","Research question",section),question=node("textarea",undefined,questionLabel);
  question.id="autopilot-question";question.rows=3;question.maxLength=2000;question.placeholder="Compare loss between models";
  const choices=node("details",undefined,section);node("summary","Fields, units and question type",choices);
  const select=(label,id)=>{const l=node("label",label,choices),e=node("select",undefined,l);e.id=id;return e;};
  const intent=select("Question type","autopilot-intent");
  for(const [value,label] of [["auto","Choose from the question"],["comparison","Compare groups"],["distribution","Explore a distribution"],["relationship","Explore a relationship"],["trend","Explore a trend"]])intent.add(new Option(label,value));
  const target=select("Measured field","autopilot-target"),group=select("Grouping field","autopilot-group"),predictor=select("Predictor / time field","autopilot-predictor");
  const input=(label,id)=>{const l=node("label",label,choices),e=node("input",undefined,l);e.type="text";e.id=id;e.maxLength=32;return e;};
  const targetUnit=input("Measured-field unit (optional)","autopilot-target-unit"),predictorUnit=input("Predictor unit (optional)","autopilot-predictor-unit");
  const check=(label,id,parent)=>{const l=node("label",undefined,parent);l.className="check";const e=node("input",undefined,l);e.type="checkbox";e.id=id;l.append(document.createTextNode(label));return e;};
  const temporal=check("Treat the selected predictor as dates/times","autopilot-temporal",choices);
  node("p","Units are your labels; no conversion, independence or uncertainty is inferred. Numeric-looking model IDs may need explicit field choices.",choices).className="muted";
  const review=node("button","Review three figure options",section);review.id="autopilot-review";review.type="button";review.className="secondary";
  const status=node("p","Choose a dataset and describe your question.",section);status.id="autopilot-status";status.setAttribute("role","status");
  const proposalBox=node("div",undefined,section);proposalBox.id="autopilot-proposal";proposalBox.hidden=true;
  const summary=node("p","",proposalBox),options=node("div",undefined,proposalBox);
  const exclusions=node("details",undefined,proposalBox);node("summary","Sample, exclusions and normalization",exclusions);const sample=node("pre","",exclusions);
  const reviewed=check("I reviewed the question, fields, units and all three options","autopilot-reviewed",proposalBox);
  const accepted=check("Use the listed joint-sample exclusions for all three drafts","autopilot-exclusions",proposalBox);
  const generate=node("button","Generate and check all three",proposalBox);generate.id="autopilot-generate";generate.type="button";
  const reportButton=node("button","Save review / results",section);reportButton.id="autopilot-report";reportButton.type="button";reportButton.className="quiet";
  const cancel=node("button","Discard draft review",section);cancel.id="autopilot-cancel";cancel.type="button";cancel.className="quiet";
  const undo=node("button","Undo applied draft",section);undo.id="autopilot-undo";undo.type="button";undo.className="quiet";
  node("p","Draft comparisons expire after 10 idle minutes. Save them before closing the editor. Your original dataset stays unchanged.",section).className="muted";

  resultsMount.hidden=true;resultsMount.className="autopilot-results";
  node("h3","Compare the checked drafts",resultsMount);
  const resultSummary=node("p","",resultsMount);resultSummary.id="autopilot-result-summary";resultSummary.setAttribute("role","status");
  const cards=node("div",undefined,resultsMount);cards.id="autopilot-cards";cards.className="autopilot-cards";
  const use=node("button","Apply selected draft",resultsMount);use.id="autopilot-apply";use.type="button";
  const include=check("Include normalized observations in the comparison download","autopilot-include-data",resultsMount);
  const download=node("button","Save all three drafts",resultsMount);download.id="autopilot-download";download.type="button";download.className="secondary";
  const fileDetails=node("details",undefined,resultsMount);node("summary","Programs, reports and exports",fileDetails);const files=node("ul",undefined,fileDetails);

  let epoch=0,pending=0,busy=false,applying=false,proposal=null,proposalBase=null,result=null,resultBase=null,selected=null,stale=false,undoEntry=null,columnKey="";
  const key=()=>{try{return JSON.stringify(context());}catch{return null;}};
  const same=base=>!!base&&JSON.stringify(base)===key();
  function available(){let value=null;try{value=context();}catch{}return !!value?.data_id;}
  function fields(){
    const info=dataset(),signature=JSON.stringify([info?.id,info?.columns?.map(c=>c.name)]);
    if(signature===columnKey)return;columnKey=signature;targetUnit.value="";predictorUnit.value="";temporal.checked=false;
    for(const control of [target,group,predictor]){
      const old=control.value;control.replaceChildren(new Option("Choose automatically","auto"));
      if(control===group)control.add(new Option("One sample (no groups)","none"));
      for(const column of info?.columns||[])control.add(new Option(column.name,"field:"+column.name));
      if([...control.options].some(o=>o.value===old))control.value=old;
    }
  }
  function eligibility(){
    review.disabled=busy||!available()||!question.value.trim();
    generate.disabled=busy||!proposal?.id||!same(proposalBase)||!!result||!reviewed.checked||((proposal.report.excluded_count||0)>0&&!accepted.checked);
    accepted.parentElement.hidden=!(proposal?.report.excluded_count>0);
    reviewed.disabled=accepted.disabled=busy||!!result;
    use.disabled=busy||stale||!result||!selected||!same(resultBase);
    download.disabled=busy||!result;
    reportButton.disabled=!(result||proposal);cancel.disabled=busy||!(proposal||result);
    undo.disabled=busy||!undoEntry||!undoEntry.current();
    for(const radio of cards.querySelectorAll('input[type="radio"]'))radio.disabled=busy||stale||radio.dataset.passed!=="true";
  }
  function abandonPending(){
    if(proposal?.id&&proposalBase&&proposal.id!==result?.id)api("/api/autopilot/cancel",{...proposalBase,id:proposal.id}).catch(()=>{});
    proposal=null;proposalBase=null;proposalBox.hidden=true;reviewed.checked=false;accepted.checked=false;
  }
  function changed(){
    epoch++;pending=0;busy=false;abandonPending();include.checked=false;
    if(result){stale=true;resultSummary.textContent="These saved drafts belong to earlier settings. Review again before applying. All three outcomes remain available.";}
    status.textContent="Review the question and current dataset again.";eligibility();
  }
  function clearResults(){
    if(result&&resultBase)api("/api/autopilot/cancel",{...resultBase,id:result.id}).catch(()=>{});
    result=null;resultBase=null;selected=null;stale=false;resultsMount.hidden=true;cards.replaceChildren();files.replaceChildren();include.checked=false;
  }
  for(const control of [question,intent,target,group,predictor,targetUnit,predictorUnit,temporal])control.addEventListener(control===question||control===targetUnit||control===predictorUnit?"input":"change",changed);
  reviewed.onchange=accepted.onchange=eligibility;
  function chosenField(control){return control.value.startsWith("field:")?control.value.slice(6):null;}
  function requestedChoices(){
    const value={};if(intent.value!=="auto")value.intent=intent.value;
    for(const [name,control] of [["target",target],["group",group],["predictor",predictor]]){const field=chosenField(control);if(field!==null)value[name]=field;}
    if(group.value==="none")value.group="";
    if(temporal.checked)value.predictor_temporal=true;
    const units={};for(const [control,unit] of [[target,targetUnit],[predictor,predictorUnit]])if(unit.value.trim()){
      const field=chosenField(control);if(field===null)throw Error("Choose a field explicitly before adding its unit.");units[field]=unit.value.trim();
    }
    if(Object.keys(units).length)value.units=units;return value;
  }
  function saveJson(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+"\n"],{type:"application/json"}));const a=node("a",undefined,section);a.href=url;a.download=name;a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  reportButton.onclick=()=>saveJson(result||proposal,result?"autopilot-results.json":"autopilot-review.json");
  cancel.onclick=()=>{epoch++;abandonPending();clearResults();status.textContent="Discarded the draft review. The current figure is unchanged.";eligibility();};
  review.onclick=async()=>{
    const operation=++epoch;abandonPending();clearResults();busy=true;pending=operation;eligibility();status.textContent="Reading your selected data and question locally…";
    try{
      const base=context(),before=JSON.stringify(base),value=await api("/api/autopilot/review",{...base,question:question.value,choices:requestedChoices()});
      if(operation!==epoch||before!==key()){if(value.id)api("/api/autopilot/cancel",{...base,id:value.id}).catch(()=>{});return;}
      proposal=value;proposalBase=base;proposalBox.hidden=false;
      const report=value.report;
      summary.textContent=report.ready?`${value.source_name} · ${report.selected_rows} retained observations · ${report.excluded_count} excluded. These options are not rendered yet.`:`No drafts proposed: ${report.reason}`;
      options.replaceChildren();
      if(report.choices){const c=report.choices,units=Object.entries(c.units||{}).map(([field,unit])=>`${field}: ${unit}`).join(", ")||"not declared";node("p",`Measured field: ${c.target||"unresolved"}. Groups: ${c.group||"one sample"}. Predictor: ${c.predictor||"none"}. Units: ${units}. Review these choices against your study.`,options);}
      for(const draft of value.drafts){const article=node("article",undefined,options);node("strong",draft.name,article);node("p",draft.why,article);node("p","Trade-off: "+draft.tradeoff,article);const list=node("ul",undefined,article);for(const assumption of draft.assumptions)node("li",assumption,list);}
      sample.textContent=JSON.stringify({normalization:report.normalization,exclusion_policy:report.exclusion_policy,excluded_count:report.excluded_count,excluded_records_shown:(report.excluded_records||[]).slice(0,100),excluded_display_limit:100,normalized_sample:value.normalized_sample,sample_limit:value.sample_limit},null,2);
      node("p","The display shows up to 100 exclusions and 20 normalized records. Save the review for the complete exclusion list.",options).className="muted";
      reviewed.parentElement.hidden=!report.ready;status.textContent=report.ready?"Review all three options and the actual sample before generating.":"Resolve the question or field choices and review again.";
    }catch(error){if(operation===epoch)status.textContent=error.message;}
    finally{if(pending===operation)busy=false;eligibility();}
  };
  function showResults(){
    resultsMount.hidden=false;cards.replaceChildren();files.replaceChildren();
    const passed=result.drafts.filter(d=>d.status==="passed").length;
    resultSummary.textContent=`${result.question} · ${passed} of 3 drafts passed strict checks. These checks do not certify scientific appropriateness.`;
    for(const draft of result.drafts){
      const card=node("article",undefined,cards);card.dataset.draft=draft.id;card.dataset.state=draft.status;
      node("h4",draft.name,card);node("p",`Checks: ${draft.status}`,card).className="badge";
      if(draft.preview_url){const image=node("img",undefined,card);image.src=fileURL(draft.preview_url);image.alt=`${draft.name}; native checks ${draft.status}`;const full=node("a","Open full-size draft",card);full.href=fileURL(draft.preview_url);full.target="_blank";full.rel="noopener noreferrer";}
      else node("p","No preview was produced. The execution outcome is retained below.",card);
      node("p",draft.why,card);node("p","Trade-off: "+draft.tradeoff,card);
      const assumptions=node("details",undefined,card);node("summary","Assumptions and verification",assumptions);const list=node("ul",undefined,assumptions);for(const item of draft.assumptions)node("li",item,list);
      node("pre",JSON.stringify({status:draft.status,error:draft.error,report:draft.native_report},null,2),assumptions);
      const label=node("label",undefined,card);label.className="check";const radio=node("input",undefined,label);radio.type="radio";radio.name="autopilot-draft";radio.value=draft.id;radio.dataset.passed=String(draft.status==="passed"&&result.source_unchanged&&result.materialized_data_unchanged);label.append(document.createTextNode("Choose this draft"));radio.onchange=()=>{selected=draft.id;eligibility();};
    }
    for(const file of result.files){const item=node("li",undefined,files),a=node("a",file.name,item);a.href=fileURL(file.url,true);a.setAttribute("download","");}
    status.textContent=!result.source_unchanged||!result.materialized_data_unchanged?"The source or plotting data changed. Review again before applying; native outcomes remain available.":passed?"Compare every outcome, then choose a passed draft. Failed drafts remain in this comparison.":"No draft passed. Save the results to review the failures; no figure was applied.";
  }
  generate.onclick=async()=>{
    if(!proposal?.id||!same(proposalBase))return;
    const operation=++epoch,base=proposalBase,identity=proposal.id;busy=true;pending=operation;eligibility();status.textContent="Generating and strictly checking all three drafts…";
    try{
      const value=await api("/api/autopilot/generate",{...base,id:identity,reviewed:reviewed.checked,accept_exclusions:accepted.checked});
      if(operation!==epoch||!same(base)){api("/api/autopilot/cancel",{...base,id:identity}).catch(()=>{});return;}
      result=value;resultBase=base;selected=null;stale=false;include.checked=false;proposalBox.hidden=true;showResults();
    }catch(error){if(operation===epoch){status.textContent=error.message;abandonPending();}}
    finally{if(pending===operation)busy=false;eligibility();}
  };
  use.onclick=async()=>{
    if(!result||stale||!selected||!same(resultBase))return;
    const operation=++epoch,base=resultBase;busy=true;pending=operation;eligibility();
    try{
      const value=await api("/api/autopilot/select",{...base,id:result.id,draft_id:selected});
      if(operation!==epoch||!same(base))return;
      applying=true;undoEntry=apply(value.data,value.spec,value.report);applying=false;stale=true;fields();
      resultSummary.textContent=`Applied ${selected}. All three original outcomes are retained here and in the selected figure's ancestry.`;
      status.textContent="Applied the checked draft. The editor is now checking the selected figure.";
    }catch(error){if(operation===epoch)status.textContent=error.message;}
    finally{applying=false;if(pending===operation)busy=false;eligibility();}
  };
  download.onclick=async()=>{
    if(!result)return;const identity=result.id,base=resultBase,operation=epoch;busy=true;pending=operation;eligibility();
    try{const value=await api("/api/autopilot/packet",{...base,id:identity,include_data:include.checked});if(operation!==epoch||identity!==result?.id)return;const a=node("a",undefined,resultsMount);a.href=fileURL(value.url,true);a.download="figure-draft-comparison.zip";a.click();a.remove();}
    catch(error){if(operation===epoch)status.textContent=error.message;}
    finally{if(pending===operation)busy=false;eligibility();}
  };
  undo.onclick=()=>{try{applying=true;undoEntry.undo();undoEntry=null;stale=true;fields();resultSummary.textContent="Restored the previous figure. All three generated outcomes remain available as earlier drafts.";status.textContent="Restored the previous dataset and figure. The editor checks rerun.";}catch(error){status.textContent=error.message;}finally{applying=false;eligibility();}};
  fields();eligibility();
  return {refresh(){fields();if(!applying&&((proposalBase&&!same(proposalBase))||(resultBase&&!same(resultBase)&&!stale)))changed();else eligibility();}};
}
