import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { Session } from 'node:inspector/promises';
import assert from 'node:assert/strict';

const [file, mode] = process.argv.slice(2);
let {createCompactionExport} = await import(pathToFileURL(resolve(file)));
const source_sha256=createHash('sha256').update(readFileSync(file)).digest('hex');
const model={provider:'fixture',model:'chat'};
const summary='## Objective\n- Preserve task.\n\n## Work State\n### Completed\n- Reviewed history.\n\n## Next Move\n1. Answer.';
const cases = [
 {name:'short',n:6,estimate:null,reason:'manual',rounds:32},
 {name:'long_unmeasured',n:512,estimate:null,reason:'manual',rounds:20},
 {name:'mixed_unmeasured',n:512,estimate:null,reason:'manual',rounds:20,mixed:true},
 {name:'core_measurement',n:512,estimate:70000,reason:'manual',rounds:20},
 {name:'auto_skip',n:512,estimate:null,reason:'auto',rounds:20},
];

function fixture(s){
 let messages=Array.from({length:s.n},(_,i)=>{
   let role=i%2?'Assistant':'User'; let payload={Text:{text:'Entry '+i+' '+'hello world. '.repeat(40)}};
   if(s.mixed && i%8===2) {role='Assistant';payload={ToolCall:{call:{id:'c'+i,name:'fixture',surface:'function',args:{topic:i},raw_arguments:null}}};}
   if(s.mixed && i%8===3) {role='Tool';payload={ToolResult:{result:{call_id:'c'+(i-1),ok:true,output:'fixture text '+i,content:[{type:'text',text:'extra '+i}],error:null,metadata:null}}};}
   return {id:'m'+i,role,name:null,phase:null,tool_call_id:null,metadata:null,parts:[{part_id:'p'+i,scope:'conversation',provenance:role==='User'?'user':'model',payload}]};
 });
 if(s.bad) messages[0].parts[0].payload={Unsupported:{text:'invalid'}};
 const request={model,instructions:[],messages,tools:[],reasoning:{},limits:{},sampling:{},cache:{}};
 const input={event:{event:'before_context',input:{messages,request,token_estimate:s.estimate,window_tokens:200000,reason:s.reason},output:{messages,changed:false}}};
 const transcript=[];
 const signal=new AbortController().signal;
 const hook=createCompactionExport({slot:'hook',module_id:'opencode_compact',contract_version:'v8',composition:'ordered_many',module_config:{keep:0}});
 let calls=0;
 const deps={signal,hostCall:async(method,params)=>{
   assert.equal(method,'host.model.complete'); calls++;
   if(mode==='parity')transcript.push(params);
   if(s.hostError)throw Object.assign(new Error('no budget'),{data:{kind:'session_budget_exceeded'}});
   return {finish_reason:'Stop',tool_calls:[],messages:[{role:'Assistant',parts:[{payload:{Text:{text:summary}}}]}]};
 }};
 return {invoke:()=>hook.invoke('hook.invoke',input,deps),count:()=>calls,transcript};
}
async function run(f,reps){
 let checksum=0;const t=performance.now();
 for(let i=0;i<reps;i++){
   const out=(await f.invoke()).result;
   if(out.action==='continue')++checksum;
   else {
     const estimate=out.output.metadata.prompt_estimate;
     assert.equal(out.output.original_token_estimate,estimate.measured+estimate.estimated);
     checksum+=out.output.original_token_estimate;
   }
 }return {ms_per_call:(performance.now()-t)/reps,checksum};
}
if(mode==='parity'){
 const traces=[];
 for(const s of cases.concat([{...cases[1],bad:true},{...cases[1],hostError:true}])){
   const f=fixture(s);let terminal;
   try{terminal=await f.invoke();}catch(e){terminal={name:e.name,message:e.message,data:e.data};}
   const ids=new Map();
   const json=JSON.stringify({calls:f.count(),terminal,transcript:f.transcript}).replace(/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi,id=>{
      if(!ids.has(id))ids.set(id,'uuid-'+ids.size);
      return ids.get(id);
   });
   traces.push({name:s.name+(s.bad?'_bad_source':s.hostError?'_host_error':''),calls:f.count(),digest:createHash('sha256').update(json).digest('hex')});
 }console.log(JSON.stringify(traces));
}else if(mode==='time'){
 const rows={};
 for(const s of cases){const f=fixture(s);await run(f,s.rounds);global.gc();rows[s.name]=await run(f,s.rounds);}
 console.log(JSON.stringify({node:process.version,source_sha256,rows}));
}else if(mode==='alloc'){
 const session=new Session();session.connect();
 const f=fixture(cases[1]);await run(f,20);global.gc();
 await session.post('HeapProfiler.startSampling',{samplingInterval:65536,includeObjectsCollectedByMajorGC:true,includeObjectsCollectedByMinorGC:true});
 const {checksum}=await run(f,24);
 const {profile}=await session.post('HeapProfiler.stopSampling');session.disconnect();
 let total=0;function walk(n){total+=n.selfSize;for(const c of n.children??[])walk(c)}walk(profile.head);
 console.log(JSON.stringify({node:process.version,source_sha256,checksum,sampling_interval:65536,invocations:24,sampled_total_allocated_bytes:total}));
 }else if(mode==='paired_control'){
 const second=(await import(pathToFileURL(resolve(process.argv[4])))).createCompactionExport;
 const first=createCompactionExport;
 const controls={};
 for(const ix of [4,3]){
   createCompactionExport=first;const a=fixture(cases[ix]);
   createCompactionExport=second;const b=fixture(cases[ix]);
   await run(a,35);await run(b,35);
   const samples=[];
   for(let i=0;i<12;i++){
     const r=[];
     for(const j of (i%2?[1,0]:[0,1])){
       global.gc();r[j]=await run(j?b:a,15);
     }
     assert.equal(r[0].checksum,r[1].checksum);
     samples.push(r.map(v=>v.ms_per_call));
   }
   controls[cases[ix].name]=samples;
 }
 console.log(JSON.stringify({node:process.version,order:'base/candidate within each pair; alternating first; shared-process',controls}));
}else throw Error('usage: pinned-node --expose-gc measure.mjs path/to/compaction.mjs parity|time|alloc|paired_control [other/compaction.mjs]');
