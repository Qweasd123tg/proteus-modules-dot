#!/usr/bin/env python3
"""Compact synthetic benchmark: sum only simultaneous process records."""
import argparse
import json
from statistics import median
from pathlib import Path

def load(path):
    return json.loads(path.read_text())

def table(sample):
    rows={p["pid"]:p for p in sample["processes"]}
    if not rows or any("Pss" not in p or "SwapPss" not in p for p in rows.values()):
        raise ValueError("incomplete observed row")
    driver=[p["pid"] for p in rows.values() if p["parent"] not in rows]
    if len(driver)!=1:
        raise ValueError("ambiguous process tree (possible teardown)")
    root=driver[0]
    peer_ids={p["pid"] for p in rows.values() if p["parent"]==root and p["name"]=="core-stock"}
    vals={"driver":0,"driver_modules":0,"peer_cores":0,"peer_modules":0,"peer_storage":0}
    for pid,p in rows.items():
        v=p["Pss"]+p["SwapPss"]
        if pid==root: k="driver"
        elif pid in peer_ids: k="peer_cores"
        elif p["parent"] in peer_ids:
            k="peer_storage" if p["name"]=="worker-stock" else "peer_modules"
        elif p["parent"]==root: k="driver_modules"
        else:raise ValueError("unexpected deeper descendant")
        vals[k]+=v
    total=sample["pss_swap_kib"]
    assert sum(vals.values())==total
    return {**vals,"total":total,"peers":len(peer_ids),"processes":len(rows)}

def mib(x):return round(x/1024,3)
def reduce_arm(p):
    all_results=load(p/"report.json")
    output=[]
    for row in all_results["runs"]:
        n=row["peers"]; k=row["repeat"]
        d=p/f"peers-{n}-repeat-{k}"
        samples=load(d/"samples.json")
        events=[json.loads(x) for x in (d/"events.jsonl").read_text().splitlines()]
        completed=[e for e in events if e["phase"]=="peer_finished"]
        assert len(completed)==n*row["rounds"]
        assert all(j["replay_matched"] for j in row["journals"])
        peak_row=max(samples,key=lambda s:s["pss_swap_kib"])
        active=[s for s in samples if s["phase"] in
                ("round_start","peer_model_entered","all_models_entered","peer_finished")]
        peak_active=max(active,key=lambda s:s["pss_swap_kib"])
        idle=[]
        expected=n if row["idle_cap"]>=n else 0
        for s in samples:
            if s["phase"]!="resident_idle":
                continue
            try:
                split=table(s)
            except ValueError:
                continue
            if split["peers"]==expected and split["processes"]>=expected*6+1:
                idle.append(split)
        assert len(idle)>=3
        pick=min(idle,key=lambda s:abs(s["total"]-median(i["total"] for i in idle)))
        residency=row["resident_pss_swap_mib"]
        obs=lambda ph:round(next(e["elapsed_ms"] for e in events if e["phase"]==ph),1)
        ready=[e["elapsed_ms"] for e in events if e["phase"]=="peer_model_entered"]
        output.append(dict(arm=p.name,peers=n,idle_cap=row["idle_cap"],
                           overlap=row["model_overlap"],settled_turns=sum(j["settled_turns"] for j in row["journals"]),
                           resumable=sum(x["data"]["metadata"].get("resumable") is True for x in completed),
                           all_entered_ms=obs("all_models_entered"),ready_from_first_ms=round(max(ready)-min(ready),1),
                           fully_settled_ms=obs("round_settled"),rounds=row["rounds"],
                           peak_mib=mib(peak_row["pss_swap_kib"]),peak_active_mib=mib(peak_active["pss_swap_kib"]),
                           peak_phase=peak_row["phase"],peak_processes=len(peak_row["processes"]),
                           peak_swap_mib=mib(sum(p["SwapPss"] for p in peak_row["processes"])),
                           live_peer_pids_observed=len({(p["pid"],p["start_ticks"]) for s in samples
                                                        for p in s["processes"] if p["name"]=="core-stock"}),
                           idle_samples=len(idle),idle_mib=round(residency,3),teardown_mib=round(row["teardown_pss_swap_mib"],3),
                           idle_at_median={k:(v if k in ("peers","processes") else mib(v)) for k,v in pick.items()},
                           idle_complete_median_mib=mib(median(i["total"] for i in idle))))
    return output

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("arms",nargs="+",type=Path)
    arr=[r for p in arg.parse_args().arms for r in reduce_arm(p)]
    print(json.dumps(arr,indent=2))
