import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
const [bp, ap] = process.argv.slice(2);
const files=[bp,ap];
for(const [i,file] of files.entries()){
  const s=readFileSync(file), hash=createHash('sha256').update(s).digest('hex');
  assert.equal(hash,['c4cf7de25f2322393097362b28b144062952490f923bc94dfe619bde7cfcdbbc','cb1e3bb5b081b5db9a4c94135b649218dbd57f18a96c077236719fad2aa256c6'][i]);
}
const [a,b]=await Promise.all(files.map(f=>import(pathToFileURL(resolve(f)).href)));
const theme={foreground:'#222222',background:'#aaaaaa',muted:'#999999',border:'#444444',accent:'#333333',danger:'#ff0000',surface:'#eeeeee',surface_alt:'#bbbbbb'};
const nativeMap=globalThis.Map;
function check(fn,svg){
 let count=0, entries=0;
 globalThis.Map=class extends nativeMap{constructor(x){super(x);if(x instanceof nativeMap){count++;entries+=x.size;}}};
 try{return {out:fn(svg,theme),count,entries};}finally{globalThis.Map=nativeMap;}
}
const token=i=>'#'+(0x123450+i).toString(16);
const read=(id)=>'<path id="'+id+'" fill="var(--x, var(--pele-fg))" stroke="currentColor"/>';
// Nine sibling + descendant scopes. No engine, files, stylesheets or user input.
let checked=0,rows=0,oldcopy=0,newcopy=0,olddelta=0,newdelta=0;
for(let mask=0;mask<512;mask++){
 const shapes=[];
 const tag=(i,child,parentX,parentC)=>{
   const custom=(mask&(1<<i))!==0, color=i%2===1;
   const x=custom?token(i):parentX, c=color?x:parentC;
   let css=custom?'--x:'+token((i+2)%9)+';--x:'+token(i)+';':'';
   if(color)css+='color:var(--x,var(--pele-fg));';
   shapes[i]=[x,c];
   return '<g'+(css?' style="'+css+'"':'')+'>'+read(i)+child(x,c)+'</g>';
 };
 const noop=()=>'';
 const svg='<svg>'+tag(0,(x,c)=>tag(1,(y,d)=>tag(2,noop,y,d)+tag(3,noop,y,d),x,c)+tag(4,(y,d)=>tag(5,noop,y,d),x,c),theme.foreground,theme.foreground)+tag(6,(x,c)=>tag(7,noop,x,c)+tag(8,noop,x,c),theme.foreground,theme.foreground)+'</svg>';
 const before=check(a.materializeSvg,svg),after=check(b.materializeSvg,svg);
 assert.equal(before.out, after.out);
 for(const [i,[ink,stroke]] of shapes.entries()){
  assert.ok(after.out.includes('<path id="'+i+'" fill="'+ink+'" stroke="'+stroke+'"/>'));rows++;
 }
 assert.equal(before.count,19);assert.equal(after.count,mask.toString(2).replaceAll('0','').length);
 checked++;oldcopy+=before.count;newcopy+=after.count;olddelta+=before.entries;newdelta+=after.entries;
}
const wide='<svg><g style="--x:#aa7733">'+Array.from({length:80},(_,i)=>read(i)).join('')+'</g><g>'+read(90)+'</g></svg>';
const p=check(a.materializeSvg,wide),q=check(b.materializeSvg,wide);assert.equal(p.out,q.out);
assert.ok(q.out.includes('<path id="90" fill="#222222" stroke="#222222"/>'));
const decl='<svg style="--x:#aa0010"><g style="--x:#bb0011"><path style="--x:#cc0012" fill="var(--x)"/></g></svg>';
const c=check(a.materializeSvg,decl),d=check(b.materializeSvg,decl);assert.equal(c.out,d.out);assert.equal(c.count,d.count);
console.log({synthetic_trees:checked,checked_colors_and_strokes:rows,old_inherited_map_copies:oldcopy,new_inherited_map_copies:newcopy,old_source_entries:olddelta,new_source_entries:newdelta});
console.log({sparse_shapes:81,old_copies:p.count,new_copies:q.count,baseline_entries:p.entries,candidate_entries:q.entries,all_tags_override_before:c.count,all_tags_override_after:d.count});
