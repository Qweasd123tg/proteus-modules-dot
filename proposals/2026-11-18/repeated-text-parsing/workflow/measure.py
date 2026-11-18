"""Run from the same working directory for both builds; no remote actions."""
import argparse, csv, json, os, statistics, subprocess
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("baseline", type=Path)
p.add_argument("candidate", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--pairs", type=int, default=12)
p.add_argument("--cpu", type=int)
opt = p.parse_args()
if opt.cpu is not None:
    os.sched_setaffinity(0, {opt.cpu})
bins = {"base": opt.baseline.resolve(), "after": opt.candidate.resolve()}
checks = ["invalid","schema","plan","recursive","hidden","authority","noraw","describe","small","large","workflow-small","workflow-large"]
def run(arm, case, iters):
    env = {**os.environ, "PROTEUS_CASE":case, "PROTEUS_REPEATS":str(iters)}
    cmd = [bins[arm],"--exact","tests::dynamic_tool_surface::round4_deferred_call_probe","--ignored","--nocapture","--test-threads=1"]
    s = subprocess.run(cmd,env=env,stdout=subprocess.PIPE,text=True,check=True).stdout
    r = json.loads(next(l.split("PROBE ",1)[1] for l in s.splitlines() if "PROBE {" in l))
    assert (r["case"], r["iters"]) == (case, iters)
    return r
opt.output.mkdir(exist_ok=True,parents=True)
parity={}
for case in checks:
    results = [run(arm, case, 1) for arm in bins]
    assert results[0]["result"] == results[1]["result"], case
    assert results[0]["raw_bytes"] == results[1]["raw_bytes"]
    parity[case] = results[0]["result"]
(opt.output/"parity.json").write_text(json.dumps(parity,indent=2,ensure_ascii=False)+"\n")
iterations={"small":640, "large":72, "workflow-small":128, "workflow-large":7, "describe":768}
data = {case: {"base":[],"after":[]} for case in iterations}
with (opt.output/"paired.csv").open("w",newline="") as f:
    w=csv.writer(f,lineterminator="\n"); w.writerow(["pair","order","case","arm","raw_bytes","repeats","total_ns","us_per_call"])
    for pair in range(-1,opt.pairs):
        cases=list(iterations)
        cases=cases[pair%len(cases):]+cases[:pair%len(cases)]
        for case in cases:
            order=["base","after"] if (pair+list(iterations).index(case))%2==0 else ["after","base"]
            for k, arm in enumerate(order):
                s=run(arm,case,iterations[case])
                assert s["result"] == parity[case]
                if pair < 0: continue
                us=s["ns"]/s["iters"]/1000
                w.writerow([pair+1,k+1,case,arm,s["raw_bytes"],s["iters"],s["ns"],f"{us:.6f}"]); f.flush()
                data[case][arm].append(us)
for case, arms in data.items():
    paired=[a/b for a,b in zip(arms["after"],arms["base"])]
    print(f'{case} median us {statistics.median(arms["base"]):.2f} => {statistics.median(arms["after"]):.2f}; med paired delta {(statistics.median(paired)-1)*100:.1f}%; {sum(v<1 for v in paired)}/{len(paired)} faster')
