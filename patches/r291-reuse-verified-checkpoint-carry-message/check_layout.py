#!/usr/bin/env python3
"""Check first writer receipts; measure only actual carry Layout and owner identity."""
import hashlib
import json
import pathlib
import sys

DIRECT={
 "mismatch-unknown":(None,[None]),
 "mismatch-other":(None,[False]),
 "mismatch-duplicate":("checkpoint received a duplicate tool result",[True,None]),
 "canonical-changed":("checkpoint result suffix was changed",[None]),
 "suffix-missing":("checkpoint result suffix was changed",[]),
 "first-duplicate-equal":(None,[]),
 "first-duplicate-unequal":("checkpoint changed a committed tool result",[]),
 "prefix-loss":("checkpoint discarded committed history without a new compaction",[]),
 "untracked-extra":("checkpoint discarded committed history without a new compaction",[]),
 "record-unbound":(None,[]),
 "record-duplicate":("checkpoint received a duplicate tool result",[]),
 "record-lost":("checkpoint history suffix was lost",[]),
 "record-bound":(None,[]),
}
FIELDS=("alloc_bytes","free_bytes","allocs","frees")
OWNERS=("output","error","canonical-parts","tool-content","structured-text")

def sha(s):
    assert type(s) is str and len(s)==64 and all(c in "0123456789abcdef" for c in s)

def count(c):
    assert all(type(c[k]) is int and c[k]>=0 for k in FIELDS),c
    assert c["net_bytes"]==c["alloc_bytes"]-c["free_bytes"],c

def rowshape(m):
    assert isinstance(m["id"],str) and len(m["id"])==36
    assert isinstance(m["part_id"],str) and len(m["part_id"])==36
    assert len(m["lengths"])==len(m["capacities"])==len(m["owners"])==len(OWNERS)
    assert m["lengths"][2]==m["capacities"][2]==1
    for i,(n,cap,a) in enumerate(zip(m["lengths"],m["capacities"],m["owners"],strict=True)):
        assert type(n) is type(cap) is int and 0<=n<=cap
        if cap:
            assert a is not None and a["requested"]>=cap and a["generation"]>0
            if i in (0,1,4): assert n==cap==a["requested"]
        else:
            assert a is None
    return m["id"],m["part_id"],m["lengths"],m["capacities"],[o and o["requested"] for o in m["owners"]]

def compare_pair(a,b,reuse):
    """reuse=None: no insertion, False: old path, True: optimized path."""
    for p in (a,b):
        assert p["prepared"] is not None
        count(p["layout"])
        count(p["prepared_layout"])
        rowshape(p["prepared"])
        if reuse is None:
            assert p["inserted"] is p["prepared_live_at_insert"] is p["prepared_owner_reused"] is None
        else:
            assert p["inserted"] is not None
            rowshape(p["inserted"])
    assert rowshape(a["prepared"])==rowshape(b["prepared"])
    assert a["prepared_layout"]==b["prepared_layout"]
    p,q=a["layout"],b["layout"]
    if reuse is None:
        assert p==q,(p,q)
        return 0,0
    assert rowshape(a["inserted"])==rowshape(b["inserted"])
    assert a["prepared_live_at_insert"]==a["prepared_owner_reused"]==[False]*len(OWNERS)
    if reuse:
        needed=[o is not None for o in b["inserted"]["owners"]]
        assert needed[2]
        assert b["prepared_owner_reused"]==b["prepared_live_at_insert"]==needed
        assert b["prepared"]==b["inserted"]
        assert a["prepared"]!=a["inserted"]
        assert rowshape(a["prepared"])==rowshape(a["inserted"])
        clone=a["prepared_layout"]
        assert p["alloc_bytes"]-q["alloc_bytes"]==p["free_bytes"]-q["free_bytes"]==clone["alloc_bytes"],(p,q,clone)
        assert p["allocs"]-q["allocs"]==p["frees"]-q["frees"]==clone["allocs"],(p,q,clone)
        assert p["net_bytes"]==q["net_bytes"]
        return clone["alloc_bytes"],clone["allocs"]
    assert b["prepared_owner_reused"]==b["prepared_live_at_insert"]==[False]*len(OWNERS)
    assert rowshape(a["inserted"])==rowshape(b["inserted"])
    assert a["prepared"]["id"]!=a["inserted"]["id"]
    assert p==q
    return 0,0

def compare(row,expected):
    s,c=(row["meters"][arm]["carries"] for arm in ("stock","candidate"))
    assert len(s)==len(c)==len(expected),(len(s),len(c),expected)
    ans=[]
    for a,b,reuse in zip(s,c,expected,strict=True):
        alloc_bytes,allocs=compare_pair(a,b,reuse)
        ans.append({"bytes":alloc_bytes,"allocs":allocs,
                    "id":b["prepared"]["id"], "part_id":b["prepared"]["part_id"]})
        # Stock uses a second generation for every originally prepared owner;
        # the observed 'live' and 'reused' booleans are point-in-time, and the
        # emitted serials independently distinguish the reacquired owner.
        if b["inserted"] is not None:
            assert all(x is None or y is None or x["generation"]!=y["generation"]
                       for x,y in zip(a["prepared"]["owners"],a["inserted"]["owners"],strict=True))
    return ans

def check_direct(row):
    mode=row["direct"]
    err,keep=DIRECT[mode]
    o=row["outcome"]
    assert o["error"]==err,(mode,o)
    if mode=="record-unbound":assert o["index"] is None
    if mode=="record-bound":assert o["index"]==1
    if "wire_sha256" in o:sha(o["wire_sha256"])
    if mode=="mismatch-unknown":
        assert o["result_ids"]==[] and len(o["subsequent_ids"])==1
    if mode=="mismatch-other":
        assert len(o["result_ids"])==1 and len(o["subsequent_ids"])==2
        assert o["subsequent_ids"][1:]==o["result_ids"]
        assert o["subsequent_ids"][0]!=o["result_ids"][0]
    compare(row,keep)

ROUTES=("strict","live")
SHAPES=("output","error","structured")
CONTROL=("carry","partial-ack","ack-all","none","changed-ack","delete-binding",
         "changed-binding","changed-pending-binding","compacted","equal-prefix","before-revision")
SIZES=(1<<20,4<<20,8<<20)
ERRORS={
 "changed-ack":{"strict":"changed after it was recorded","live":"checkpoint changed a committed tool result"},
 "delete-binding":{"strict":"checkpoint discarded a committed tool result","live":"checkpoint discarded a committed tool result"},
 "changed-binding":{"strict":"checkpoint reuses a previously recorded result part identity","live":"checkpoint changed a pending tool result binding"},
 "changed-pending-binding":{"strict":"checkpoint changed a pending tool result binding","live":"checkpoint changed a pending tool result binding"},
 "before-revision":{"strict":"history revision mismatch","live":"stale context preparation target"},
 "late-active":{"strict":"active history contains duplicate message id"},
}
BODY={"output":0,"error":1,"structured":4}
UUID=lambda n: f"00000000-0000-0000-0000-{n:012x}"

def run(path, controls_only=False):
    payload=path.read_bytes()
    raw=[json.loads(s) for s in payload.splitlines()]
    expected={(173,m,s,t) for m in CONTROL for s in SHAPES for t in ROUTES}
    expected|={(173,"late-active",s,"strict") for s in SHAPES}
    expected|={(0,"carry","output",t) for t in ROUTES}
    if not controls_only:
        expected|={(n,"carry",s,t) for n in SIZES for s in SHAPES for t in ROUTES}
    seen=set()
    direct=set()
    large=[]
    exact_carries=0
    matched_no_carry=0
    rejected=[]
    for r in raw:
        if "direct" in r:
            d=r["direct"]
            assert d not in direct
            direct.add(d)
            check_direct(r)
            continue
        n,m,s,t=key=tuple(r[k] for k in ("n","mode","shape","route"))
        assert key in expected and key not in seen,key
        seen.add(key)
        state=r["state"]
        error=ERRORS.get(m,{}).get(t)
        if error is None:
            assert state["error"] is None, (key,state)
        else:
            assert error in state["error"],(key,state)
            rejected.append({"route":t,"shape":s,"mode":m,"error":state["error"]})
        assert state["rows"]>=2 and state["revision"]>0
        sha(state["history"])
        if t=="strict":
            assert r["physical_bytes"]>1000
            assert state["seq"]>11
            if "checkpoint_physical_bytes" in r:
                assert r["checkpoint_physical_bytes"]>0
        else:
            assert r["physical_bytes"]==0
            sha(state["ack_progress"])
            assert "model_context" in state
            assert state["checkpoint_locks_confirmed"] is (n==173 and m=="carry" and s=="output")
            want_events=[[tag,id_] for id_ in "abcd" for tag in ("request","resolve")]
            recorded="" if m=="none" else ("cab" if m in ("partial-ack","ack-all") else "b")
            want_events.extend([["final",id_] for id_ in recorded])
            assert state["sink_trace"]==want_events,(key,state["sink_trace"])
        wanted={"carry":["b"],"partial-ack":["b","c"],"late-active":["b","c"]}.get(m,[])
        assert r["carry"]==wanted,(key,wanted,r["carry"])
        difference=compare(r,[True]*len(wanted))
        exact_carries+=len(wanted)
        matched_no_carry+=not wanted
        for i,(id_,report) in enumerate(zip(wanted,difference,strict=True)):
            member="abcd".index(id_)
            assert report["id"]==UUID(600+member)
            assert report["part_id"]==UUID(1600+member)
            lengths=r["meters"]["candidate"]["carries"][i]["inserted"]["lengths"]
            assert lengths[BODY[s]]==(n if id_=="b" else 31),(key,id_,lengths)
            assert report["bytes"]>=(n if id_=="b" else 31)
        if n in SIZES:
            assert len(difference)==1
            report=difference[0]
            assert report["bytes"]>=max(n,2<<20 if n>=4<<20 else 0)
            sample={"n":n,"route":t,"shape":s,"physical_bytes":r["physical_bytes"],**report}
            if "checkpoint_physical_bytes" in r:sample["checkpoint_physical_bytes"]=r["checkpoint_physical_bytes"]
            large.append(sample)
    assert seen==expected,(sorted(expected-seen),sorted(seen-expected))
    assert direct==DIRECT.keys(),sorted(DIRECT.keys()-direct)
    assert len(large)==(0 if controls_only else 18)
    return {"passes":True,"raw_sha256":hashlib.sha256(payload).hexdigest(),
            "case_count":len(raw),"actual_routes":len(seen),"direct_edge_cases":len(direct),
            "active_carry_pairs":exact_carries,"no_carry_pairs":matched_no_carry,
            "large":large,"protected_rejections":rejected}

if __name__=="__main__":
    if len(sys.argv) not in (2,3) or (len(sys.argv)==3 and sys.argv[2]!="--controls"):
        raise SystemExit("usage: check_layout.py FILE.jsonl [--controls]")
    print(json.dumps(run(pathlib.Path(sys.argv[1]),len(sys.argv)==3),indent=2,sort_keys=True))
