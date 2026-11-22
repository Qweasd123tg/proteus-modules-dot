"""Demand positive scoped work under both bases; compare untouched controls."""
from pathlib import Path
import json
import sys

root=Path(sys.argv[1])
keys={"matched-loaded","matched-live-stress","matched-empty",
      "fallback-loaded","fallback-live-stress","fallback-empty"}
def records(path):
    result={}
    for line in path.read_text().splitlines():
        if line.startswith("WORK "):
            _, label, pair=line.split(" ",2)
            result[label]=json.loads(pair)
    assert set(result)==keys
    assert all(len(v)==2 and min(v)>=0 for v in result.values())
    return result
for tier in ("pin","after449"):
    old=records(root/(tier+"-baseline.work"))
    new=records(root/(tier+"-candidate.work"))
    for key in keys:
        if key.endswith("-empty"):
            assert old[key]==new[key]==[0,0]
        elif key.startswith("fallback-"):
            assert old[key]==new[key] and min(old[key])>0
        else:
            assert min(old[key])>0 and new[key]==[0,0]
    print("PASS",tier,"one populated-snapshot clone removed on matched preparation; no change to fallback or empty")
