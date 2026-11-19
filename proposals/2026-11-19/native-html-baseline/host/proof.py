"""Validate complete state and counters separately on stock, default and owned RichText paths."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("bin",type=Path)
parser.add_argument("corpus",type=Path)
parser.add_argument("out",type=Path)
args=parser.parse_args()
groups={}
push={}
digests={}
for side in ("stock","after"):
    for label, suffix in (("default","default"),("rich_text","time")):
        exe=args.bin/(side+"-"+suffix)
        name=side+"_"+label
        digests[name]=hashlib.sha256(exe.read_bytes()).hexdigest()
        groups[name]=json.loads(subprocess.check_output([exe,args.corpus,"proof"],timeout=45))
        push[name]=json.loads(subprocess.check_output([args.bin/(side+"-push-"+label),args.corpus],timeout=45))

def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

# Entire default path is unchanged: not just final outputs but each call count,
# parsed input byte count, callback execution, and immediate/parked snapshot.
assert groups["stock_default"] == groups["after_default"] == groups["stock_rich_text"]
assert push["stock_default"] == push["after_default"] == push["stock_rich_text"]
base=groups["stock_default"]
scoped=groups["after_rich_text"]
assert len(base)==len(scoped)==24
n=0
for stock,candidate in zip(base,scoped):
    assert stock["case"]==candidate["case"]
    if "fg" in stock:
        for k in ("immediate","idle","selected"):
            assert stock[k]==candidate[k],(stock["case"],k)
            n+=1
        size=stock["idle"]["source_bytes"]
        assert stock["fg"]==candidate["fg"]
        if size<=4096:
            assert stock["bg"]==[1,size,0,0] and candidate["bg"]==[0,0,0,0]
        else:
            assert stock["bg"]==candidate["bg"]==[1,size,0,0]
    else:
        assert len(stock["steps"])==len(candidate["steps"])
        for x,y in zip(stock["steps"],candidate["steps"]):
            assert (x["step"],x["state"],x.get("hook_calls_total"))==(y["step"],y["state"],y.get("hook_calls_total"))
            n+=1
assert n==96
for x,y in zip(push["stock_default"],push["after_rich_text"]):
    assert x["name"]==y["name"] and x["ast"]==y["ast"]
    if x["name"]=="plain-4097":
        assert x==y
    else:
        assert x["before_append_worker"][0]==1 and x["append_worker"]==[1,11]
        assert y["before_append_worker"]==[0,0] and y["append_worker"]==[2,x["before_append_worker"][1]+11]
out={"scenarios_per_branch":24, "matched_state_observations_per_branch":n,
     "elf_sha256":digests,"serialized_observations_sha256":{k:digest(v) for k,v in groups.items()},
     "default_full_parity_including_counts":True,"scoped_semantic_parity":True,
     "first_explicit_push_counts":push,"stock":base,"scoped":scoped}
args.out.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
