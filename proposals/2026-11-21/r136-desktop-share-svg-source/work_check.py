"""Gate actual isolated retained requests/bytes, including the decode-only cost."""
from pathlib import Path
import json
import sys

root=Path(sys.argv[1])
keys={"decode-live","prepare-live","drop-root","drop-images","renderer-refusal",
      "decode-tiny","prepare-tiny","equal-redecode-live"}
def records(path):
    result={}
    for line in path.read_text().splitlines():
        if line.startswith("WORK "):
            _, label, values=line.split(" ",2)
            result[label]=json.loads(values)
    assert set(result)==keys
    assert all(len(v)==4 and all(type(n) is int for n in v) and min(v[:3])>=0
               for v in result.values())
    return result
for tier in ("pin","after451"):
    old=records(root/(tier+"-baseline.work"))
    new=records(root/(tier+"-candidate.work"))
    assert all(old[key][0]==new[key][0] for key in keys)
    n=old["decode-live"][0]
    dec, new_decode=old["decode-live"][1:],new["decode-live"][1:]
    pre, new_prepare=old["prepare-live"][1:],new["prepare-live"][1:]
    assert dec[2]>=n and 0<new_decode[2]-dec[2]<=64, (dec,new_decode)
    assert new_decode[0]-dec[0]==1 and 0<new_decode[1]-dec[1]<=64
    assert old["drop-root"][3]==-n and new["drop-root"][3]==0
    assert old["drop-images"][3]<0 and new["drop-images"][3]<0
    assert (dec[2]+pre[2])-(new_decode[2]+new_prepare[2])>=n*3//4
    assert (dec[1]+pre[1])-(new_decode[1]+new_prepare[1])>=n*3//2
    assert old["renderer-refusal"][3]==new["renderer-refusal"][3]
    assert 0<new["decode-tiny"][3]-old["decode-tiny"][3]<=64
    tiny_total_before=old["decode-tiny"][3]+old["prepare-tiny"][3]
    tiny_total_after=new["decode-tiny"][3]+new["prepare-tiny"][3]
    assert tiny_total_after-tiny_total_before<=64
    old_equal,new_equal=old["equal-redecode-live"],new["equal-redecode-live"]
    assert new_equal[3]-old_equal[3]<=128 and old_equal[2]-new_equal[2]>=n
    print("PASS",tier,"ordinary retained payload/double copy removed, small decode-only overhead and no refusal retention increase")
