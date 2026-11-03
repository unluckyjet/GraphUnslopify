/** Supported renderer-owned targets; edits stay in the existing canonical form. */
export function createContextInspector({current, controls, deactivate}) {
  const $=id=>document.getElementById(id),image=$("preview"),layer=$("inspector-targets");
  const toggle=$("inspect-element"),panel=$("element-inspector"),picker=$("inspector-element");
  let binding=null,targets=[],active=false;
  const svgNS="http://www.w3.org/2000/svg";
  function same() {
    try {const now=current();return !!binding && now.revision===binding.revision && now.dataId===binding.dataId &&
      now.result?.run_id===binding.runId && now.result?.report.spec_hash===binding.hash && JSON.stringify(now.spec)===binding.spec;
    } catch {return false;}
  }
  const ready=()=>image.complete&&image.naturalWidth===binding?.width&&image.naturalHeight===binding?.height&&image.dataset.phase==="final"&&image.dataset.runId===binding?.runId;
  function position() {
    toggle.disabled=!same()||!ready();
    layer.hidden=toggle.disabled||!active;
  }
  function hide() {
    active=false;panel.hidden=true;toggle.setAttribute("aria-pressed","false");controls.scope();position();
  }
  function clear() {
    binding=null;targets=[];layer.replaceChildren();layer.hidden=true;panel.hidden=true;toggle.disabled=true;
    picker.replaceChildren();controls.scope();toggle.setAttribute("aria-pressed","false");
  }
  function name(target) {
    if(target.role==="figure")return "Whole figure";
    const panel=`Panel ${target.panel+1}`;
    return target.role==="axis" ? `${target.visual_axis==="x"?"Horizontal":"Vertical"} axis · ${target.source} · ${panel}` : `Uncertainty · ${panel} · shared policy`;
  }
  function select(index) {
    if(!controls.flush()||!same()||!ready()||!targets[index])return;
    const target=targets[index];picker.value=String(index);
    controls.scope(target.role==="axis"?target.path[0]:target.role);
    $("inspector-context").textContent=target.role==="figure" ? "Figure wording, style and exports. Select an axis or interval for its controls."
      : target.role==="axis" ? `${name(target)}. These settings apply wherever this source binding is shared.`
        : "Summary and uncertainty settings apply across this figure. Review the observation unit and estimator before changing them.";
    for(const element of layer.querySelectorAll("[data-target]"))element.classList.toggle("selected",Number(element.dataset.target)===index);
  }
  function valid(target,spec,width,height) {
    if(!Array.isArray(target.bounds)||target.bounds.length!==4||!target.bounds.every(Number.isFinite))return false;
    const [x,y,w,h]=target.bounds;
    if(x<0||y<0||w<=0||h<=0||x+w>width+.001||y+h>height+.001||!Array.isArray(target.path))return false;
    if(target.role==="figure")return target.path.length===0;
    if(!Number.isInteger(target.panel)||target.panel<0)return false;
    if(target.role==="axis")return target.path.length===1&&["x","y"].includes(target.path[0])&&spec[target.path[0]]?.field===target.source&&["x","y"].includes(target.visual_axis);
    return target.role==="uncertainty"&&target.path.length===1&&target.path[0]==="uncertainty"&&typeof spec.uncertainty?.kind==="string";
  }
  function mount(result) {
    clear();const map=result.edit_map,now=current();
    const png=result.report?.outputs?.find(o=>o.format==="png"&&o.path.split(/[\\/]/).pop()===map?.image?.name);
    if(!map?.available||map.schema_version!==1||map.coordinates!=="pixels_top_left"||map.run_id!==result.run_id||map.spec_hash!==result.report.spec_hash||!png||png.sha256!==map.image.sha256||map.elements?.schema_version!==1||!Array.isArray(map.elements.targets)||map.elements.targets.length>513||![map.image.width,map.image.height].every(v=>Number.isSafeInteger(v)&&v>0&&v<=32768))return;
    binding={revision:now.revision,dataId:now.dataId,runId:result.run_id,hash:map.spec_hash,spec:JSON.stringify(now.spec),width:map.image.width,height:map.image.height};
    const svg=document.createElementNS(svgNS,"svg");svg.setAttribute("viewBox",`0 0 ${binding.width} ${binding.height}`);svg.setAttribute("aria-label","Selectable figure elements");
    for(const target of map.elements.targets) {
      if(!valid(target,now.spec,binding.width,binding.height))continue;
      if(target.role==="uncertainty"&&(!Array.isArray(target.shapes)||!target.shapes.length||target.shapes.length>512||!Array.isArray(target.clip)||target.clip.length!==4||!target.clip.every(Number.isFinite)))continue;
      const index=targets.length;targets.push(target);picker.add(new Option(name(target),String(index)));
      if(target.role==="figure")continue;
      const group=document.createElementNS(svgNS,"g");group.dataset.target=String(index);group.classList.add("inspector-mark");
      group.setAttribute("role","button");group.setAttribute("tabindex","0");group.setAttribute("aria-label",`Inspect ${name(target)}`);
      group.onclick=()=>select(index);group.onkeydown=e=>{if(["Enter"," "].includes(e.key)){e.preventDefault();select(index);}};
      const [x,y,w,h]=target.bounds;
      if(target.role==="uncertainty"&&Array.isArray(target.shapes)&&target.shapes.length<=512) {
        if(!Array.isArray(target.clip)||target.clip.length!==4||!target.clip.every(Number.isFinite))continue;
        const clip=document.createElementNS(svgNS,"clipPath"),rect=document.createElementNS(svgNS,"rect");clip.id=`inspector-clip-${index}`;
        ["x","y","width","height"].forEach((key,i)=>rect.setAttribute(key,String(target.clip[i])));clip.append(rect);svg.append(clip);group.setAttribute("clip-path",`url(#${clip.id})`);
        for(const shape of target.shapes) {
          if(!Array.isArray(shape.points)||shape.points.length>20000||!shape.points.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)))continue;
          const path=document.createElementNS(svgNS,"path");path.setAttribute("d",shape.points.map((p,i)=>`${i?"L":"M"}${p[0]},${p[1]}`).join(" ")+(shape.closed?" Z":""));
          path.setAttribute("fill",shape.closed?"transparent":"none");path.setAttribute("stroke-width",String(Number.isFinite(target.hit_width)?target.hit_width:6));group.append(path);
        }
      } else {
        const rect=document.createElementNS(svgNS,"rect");Object.entries({x,y,width:w,height:h}).forEach(([k,v])=>rect.setAttribute(k,String(v)));group.append(rect);
      }
      svg.append(group);
    }
    layer.append(svg);toggle.disabled=!targets.length;
    $("inspector-coverage").textContent="Only supported tagged axes and intervals are selectable. Other marks and secondary axes remain in All settings or Advanced JSON."+(map.elements.gaps?.length?` ${map.elements.gaps.length} geometry gaps were recorded.`:"");
    if(active){panel.hidden=false;toggle.setAttribute("aria-pressed","true");select(0);}position();
  }
  toggle.onclick=()=>{if(!same())return;if(active){hide();return;}if(!controls.flush()||!same())return;deactivate();active=true;panel.hidden=false;toggle.setAttribute("aria-pressed","true");select(0);position();};
  picker.onchange=()=>select(Number(picker.value));$("inspector-all").onclick=hide;
  image.addEventListener("load",()=>{position();if(active&&same()&&ready())select(Number(picker.value||0));});image.addEventListener("click",()=>{if(active&&same())select(targets.findIndex(t=>t.role==="figure"));});
  return {mount,clear,hide};
}
