import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
const parse=f=>readFileSync(f,"utf8").trim().split("\n").map(JSON.parse);
const [oldP,newP,plainOld,plainNew]=process.argv.slice(2).map(parse);
assert.equal(oldP.length,96);assert.equal(newP.length,96);
for(let i=0;i<oldP.length;i++){
  const old=oldP[i],after=newP[i];let [a,b,depth,mix,fail]=old.shape;
  let levels=["project"],order=[];
  for(let d=0;levels.length&&d<=32&&order.length<256;d++){
    const room=256-order.length;const visit=levels.slice(0,room);order.push(...visit);
    if(d===32||d>=depth||order.length===256)break;
    levels=visit.filter(p=>!fail||d===0||Number(p.split("/").at(-1).slice(1))%fail!==1)
       .flatMap(p=>Array.from({length:d===0?a:b},(_,j)=>j).filter(j=>!mix||j%mix!==1).map(j=>p+"/d"+j));
  }
  for(const r of [old,after,plainOld[i],plainNew[i]]){
    assert.deepEqual(r.shape,old.shape);assert.deepEqual(r.reads,order);assert.deepEqual(r.expanded,["",...order].sort());
  }
  assert.equal(after.clones,order.length-1);assert.ok(after.peak<=255);
  assert.ok(after.clones<=old.clones&&after.peak<=old.peak);
  if(i<6)console.log(`shape=${old.shape} reads=${order.length} child-path clones=${old.clones}→${after.clones} frontier peak=${old.peak}→${after.peak}`);
}
console.log(`${oldP.length}/${oldP.length} exact ordered-listing and expanded-set matches in both unmodified and instrumented builds`);
