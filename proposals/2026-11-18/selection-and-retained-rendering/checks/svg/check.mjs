// Pure SVG materialization only. No Pele, worker, host, GUI, files from user, or network.
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const modules = await Promise.all(process.argv.slice(2,4).map(x => import(pathToFileURL(resolve(x)))));
if (modules.length !== 2) throw new Error("check.mjs BASE_SVG_THEME.mjs CANDIDATE_SVG_THEME.mjs")
const themes=[
 {foreground:'#112233',background:'#ffffff',muted:'#667788',border:'#334455',accent:'#0055ee',danger:'#cc1122',surface:'#f4f4f4',surface_alt:'#e0e0e0',font_family:'Noto Sans',font_family_mono:'Fira Code'},
 {foreground:'#e1e8efff',background:'#1a1c20',muted:'#aabbcc',border:'#667788',accent:'#66ccff',danger:'#ff9977',surface:'#282c30',surface_alt:'#353940',font_family:'Inter',font_family_mono:'monospace'}
];
const digest = str => createHash('sha256').update(str).digest('hex');
function measure(lib,svg,theme){
 const NativeMap=globalThis.Map;
 let copies=0,entries=0;
 class CountedMap extends NativeMap {
  constructor(it){
   super(it);
   if(it instanceof NativeMap){copies++;entries+=it.size;}
  }
 }
 globalThis.Map=CountedMap;
 try{
   const output=lib.materializeSvg(svg,theme);
   return {output,copies,entries};
 } finally {globalThis.Map=NativeMap;}
}
function fixture(count) {
 let edges='',nodes='';
 for(let i=0;i<count;i++){
   if(i)edges+=`<g class="pele-edge" data-id="E${i}"><path d="M0 0 L${i*10} 20"/></g>`;
   nodes+=`<g class="pele-node pele-shape-rect" data-id="N${i}" transform="translate(${i*10},10)"><rect width="44" height="30" fill="var(--_s)" stroke="var(--_b)" style="rx:var(--_r)"/><text fill="var(--_fg)">Étape ${i}</text></g>`;
 }
 return `<svg viewBox="0 0 800 400" style="--_fg:var(--pele-fg);--_s:var(--pele-surface);--_b:var(--pele-border);--_l:var(--pele-line);--_r:4px;color:var(--_fg);font:14px sans-serif;font-family:var(--pele-font)" fill="var(--_fg)"><g class="pele-edges" fill="none" stroke="var(--_l)">${edges}</g><g class="pele-nodes">${nodes}</g></svg>`;
}
function assertSame(svg,t) {
 const a=measure(modules[0],svg,t),b=measure(modules[1],svg,t);
 assert.equal(b.output,a.output);return [a,b];
}
for(const [label,n] of [['small',2],['medium',32],['large',256]]){
 const svg=fixture(n);const [a,b]=assertSame(svg,themes[0]);
 assert.equal(b.copies,1);
 assert.ok(a.entries>b.entries);
 console.log(`${label} ${n} node labels | input ${Buffer.byteLength(svg)} UTF-8 bytes | inherited-map constructors ${a.copies}->${b.copies} | sum of source entries ${a.entries}->${b.entries} | output sha256 ${digest(b.output)}`);
}
// Independent golden: local override on a scoped group, on a self-closing child
// and a nested group may not affect the nearest sibling or the outer subtree.
for(const t of themes){
 const scoped='<svg style="--paint:var(--pele-fg)"><g style="--paint:var(--pele-accent);--alias:var(--paint)"><text fill="var(--alias)">var(--paint)</text><rect style="--paint:var(--pele-critical)" fill="var(--paint)"/><rect fill="var(--paint)"/></g><circle fill="var(--paint)"/></svg>';
 const [a,b]=assertSame(scoped,t);
 assert.equal(b.copies,3);
 assert.equal(b.output,`<svg><g><text fill="${t.accent}">var(--paint)</text><rect fill="${t.danger}"/><rect fill="${t.accent}"/></g><circle fill="${t.foreground}"/></svg>`);
 assert.equal(measure(modules[1],'<svg><g><circle/></g></svg>',t).copies,0);
}
let cases=0,maxOld=0,maxNew=0;
// Vary lawful local declarations/aliases at 6 sites. Both branches are visited:
// no locals / locals; 2 declarations on the same element; nested / siblings.
for (const t of themes) for(let mask=0;mask<64;mask++) {
 let attrs=i=>(mask&(1<<i))?` style="--paint:${['#001122','#224466','#556600','#998800','#9900ee','#7700bb'][i]};--alias:var(--paint)"`:'';
 let s=`<svg${attrs(0)}><g${attrs(1)}><text${attrs(2)} fill="var(--alias,var(--pele-fg))">var(--paint)</text><path${attrs(3)} stroke="var(--alias,var(--pele-muted))"/></g><g${attrs(4)}><circle${attrs(5)} fill="var(--alias,var(--pele-accent))"/></g></svg>`;
 let [a,b]=assertSame(s,t); assert.equal(b.copies,mask.toString(2).replaceAll('0','').length);
 maxOld=Math.max(a.copies,maxOld);maxNew=Math.max(b.copies,maxNew);cases++;
}
console.log(`${cases} nested/sibling declaration-mask comparisons byte-identical; explicit color/text/override golden passed on 2 themes. All-changing controls retain ${maxNew}/${maxOld} copies.`);
