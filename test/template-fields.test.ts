import {test} from "node:test";
import assert from "node:assert/strict";
import {RECIPES} from "../src/recipes.ts";
import {FigureSpec,FIGURE_KINDS} from "../src/schema.ts";
import {templateFields,remapTemplateFields} from "../src/template-fields.ts";

const base = {x:{field:"epoch",label:"Epoch"},y:{field:"score",label:"Score"}};
test("portable field identities cover every kind without mutating bindings or calculation choices",()=>{
  const cases:unknown[]=[...RECIPES.map(r=>r.spec),{kind:"violin",...base},{kind:"table",...base}];
  const kinds=new Set<string>();
  for(const value of cases){
    const spec=FigureSpec.parse(value),before=structuredClone(spec);kinds.add(spec.kind);
    const refs=templateFields(spec),mapping=Object.fromEntries(refs.map(r=>[r.field,"mapped_"+r.field]));
    const actual=FigureSpec.parse(remapTemplateFields(spec,mapping));
    assert.deepEqual(spec,before);assert.deepEqual(actual.data,spec.data);assert.deepEqual(actual.output,spec.output);
    assert.deepEqual(actual.style,spec.style);assert.equal(actual.x.label,spec.x.label);assert.equal(actual.y.label,spec.y.label);
    assert.ok(templateFields(actual).every(r=>r.field.startsWith("mapped_")),spec.kind);
  }
  assert.deepEqual([...kinds].sort(),[...FIGURE_KINDS].sort());
});

test("wide virtual outputs stay virtual while real columns and their series identities remap",()=>{
  const spec={kind:"line",...base,y:{field:"value",label:"Score"},series_from_columns:{fields:["ours","base"],series_name:"method",value_name:"value"},series_order:["base","ours"],emphasis:{series:"ours"},legend:{labels:[{series:"ours",text:"Our model"}]},claims:[{kind:"beats_everywhere",subject:"ours",reference:"base"}]};
  assert.ok(!templateFields(spec).some(r=>r.field==="value"));
  const result=remapTemplateFields(spec,{epoch:"step",ours:"model_a",base:"model_b"}) as any;
  assert.equal(result.y.field,"value");assert.deepEqual(result.series_from_columns.fields,["model_a","model_b"]);
  assert.deepEqual(result.series_order,["model_b","model_a"]);assert.equal(result.emphasis.series,"model_a");
  assert.equal(result.legend.labels[0].series,"model_a");assert.equal(result.claims[0].reference,"model_b");
  assert.throws(()=>remapTemplateFields(spec,{value:"real_column"}),/no source field/);
});

test("column remapping preserves literal filter values and safely handles prototype-like names",()=>{
  const spec={kind:"line",...base,x:{field:"__proto__",label:"Literal"},group:"method",filter:[{field:"method",op:"eq",value:"method"}],claims:[{kind:"beats_everywhere",subject:"method",reference:"base"}]};
  const mapping=JSON.parse('{"__proto__":"actual_x","method":"model"}');
  const result=remapTemplateFields(spec,mapping) as any;
  assert.equal(result.x.field,"actual_x");assert.equal(result.filter[0].field,"model");assert.equal(result.filter[0].value,"method");assert.equal(result.claims[0].subject,"method");
  assert.equal(({} as any).actual_x,undefined);
});
