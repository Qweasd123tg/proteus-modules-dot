#!/usr/bin/env python3
"""Additional deterministic synthetic RPC controls; reports a reproducible failure as an AssertionError.
Both stores use temporary dirs and a fresh worker; no live sessions, model providers, host tools or network."""
import argparse
import hashlib
import os
from pathlib import Path
from worker_controls import fixture, Worker, msg

def append(f, i, text=None):
    return f.write([msg(i, text if text is not None else f"text {i} á 😀")])[1]["record"]

def page(w,s,records,after,limit,n=None):
    p=w.do("read_records",snapshot=s,after_seq=after,limit=limit)["page"]
    selected=records[after:after+(limit if n is None else n)]
    assert p["snapshot"]==s and p["records"]==selected,(after,limit)
    last=after+len(selected)
    assert p["next_after_seq"]==(None if last==len(records) else last),(after,limit,p["next_after_seq"])

def interleaved_cuts(f):
    # Chunks cross BufReader's window before and after the saved cut yet stay inline.
    data=[]; earlier=f.snap()
    for i in range(1,7): data.append(append(f,i,"é😀/"*(1900+i*17)))
    cut=f.snap()
    for i in range(7,11): data.append(append(f,i,"多α"*(1700+i*11)))
    head=f.snap()
    assert f.cmp(head,cut) and f.cmp(head,earlier)
    for after,limit in ((6,1),(7,2),(6,4),(2,3),(6,2),(8,2),(10,1),(0,2)):
        page(f.w,head,data,after,limit)
    assert f.hist(head,kind="revision",history_revision=3)==[r["entry"]["payload"]["messages"][0] for r in data[:3]]
    page(f.w,head,data,6,4)
    f.w.do("read_usage",snapshot=head); page(f.w,head,data,6,2)
    assert not f.cmp(head,dict(cut,content_sha256="0"*64)); page(f.w,head,data,6,4)
    assert not f.cmp(head,dict(cut,revision=dict(cut["revision"],history_revision=5)))
    warm=f.snap(); assert f.cmp(warm,cut)
    page(f.w,warm,data,6,4); page(f.w,head,data,6,4); page(f.w,cut,data[:6],5,2)
    assert f.w.do("read_records",fail=True,snapshot=head,after_seq=2**64-1,limit=2)
    page(f.w,head,data,6,4)

def empty_then_append(f):
    old=f.snap(); page(f.w,old,[],0,7)
    data=[append(f,1)]
    head=f.snap(); assert f.cmp(head,old)
    page(f.w,old,[],0,1); page(f.w,head,data,0,1); page(f.w,head,data,1,1)
    assert f.cmp(head,head); page(f.w,head,data,1,2)

def independent_writer(f):
    r=Worker(f.binary,f.kind)
    try:
        data=[append(f,i) for i in range(1,10)]
        old=r.do("open_snapshot",session=f.session)["snapshot"]
        data.extend(append(f,i) for i in range(10,15))
        pinned=r.do("open_snapshot",session=f.session)["snapshot"]
        assert r.do("compare_snapshots",snapshot=pinned,prefix=old)["matches"]
        page(r,pinned,data,9,1); page(r,pinned,data,9,1)
        after=append(f,15)
        page(r,pinned,data,10,1); page(r,pinned,data,9,6)
        r.do("read_usage",snapshot=pinned); page(r,pinned,data,9,5)
        head=r.do("open_snapshot",session=f.session)["snapshot"]
        page(r,head,data+[after],9,6); page(r,pinned,data,9,6)
    finally: r.close()

def partial_tail(f):
    data=[append(f,i) for i in range(1,4)]
    old=f.snap()
    data.extend(append(f,i) for i in range(4,8))
    path=f.dir/"journal.jsonl"
    full=path.read_bytes()
    with path.open('ab') as out: out.write(b'{"partial":"never visible')
    head=f.snap(); assert f.cmp(head,old); page(f.w,head,data,3,12)
    path.write_bytes(full)
    page(f.w,head,data,3,1); page(f.w,head,data,3,12)
    path.write_bytes(full[:-9])
    assert f.w.do("read_records",fail=True,snapshot=head,after_seq=3,limit=1)
    path.write_bytes(full)
    page(f.w,head,data,3,12)

def atomic_after_cut(f):
    data=[append(f,i,f"label-{i}-A") for i in range(1,7)]
    cut=f.snap()
    data.append(append(f,7)); data.append(append(f,8))
    head=f.snap(); page(f.w,head,data,6,2)
    path=f.dir/"journal.jsonl"; old=path.read_bytes()
    peer=path.with_name("replacement-records.tmp")
    peer.write_bytes(old.replace(b"label-2-A",b"label-2-B"));os.replace(peer,path)
    # Absolute same-size path replacement does not alter the old FD.
    page(f.w,head,data,6,2)
    new=f.snap(); assert new["revision"]==head["revision"]
    assert not f.cmp(new,cut) and f.cmp(head,cut)
    changed=new["content_sha256"]; assert changed!=head["content_sha256"]
    page(f.w,new,data,6,2); page(f.w,head,data,0,8)

def mid_suffix_change(f):
    data=[append(f,i,f"hold-{i}-X") for i in range(1,7)]
    cut=f.snap()
    data.extend(append(f,i,f"hold-{i}-X") for i in range(7,10))
    head=f.snap(); assert f.cmp(head,cut); page(f.w,head,data,6,1)
    path=f.dir/"journal.jsonl"; raw=path.read_bytes(); stamp=path.stat()
    for part in (b"hold-2-X",b"hold-8-X"):
        path.write_bytes(raw.replace(part,part.replace(b"X",b"Y"))); os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        assert f.w.do("read_records",fail=True,snapshot=head,after_seq=6,limit=1)
        assert f.w.do("compare_snapshots",fail=True,snapshot=head,prefix=cut)
        path.write_bytes(raw); assert f.cmp(head,cut); page(f.w,head,data,6,3)

def blobs_at_cut(f):
    data=[append(f,1,"aaa"*100000),append(f,2)]
    cut=f.snap()
    data.extend([append(f,3,"bbb"*100000),append(f,4)])
    snap=f.snap(); assert f.cmp(snap,cut); page(f.w,snap,data,2,2)
    paths=list((f.dir/"blobs").glob("*.json")); assert len(paths)==2
    for b in paths:
        content=b.read_bytes()
        for mode in ("missing","changed"):
            if mode=="missing": b.unlink()
            else:
                part=b"aaaa" if b"aaaa" in content else b"bbbb"
                new=content.replace(part,b"zzzz",1); assert new!=content and len(new)==len(content)
                b.write_bytes(new)
            assert f.w.do("compare_snapshots",fail=True,snapshot=snap,prefix=cut)
            assert f.w.do("read_records",fail=True,snapshot=snap,after_seq=2,limit=2)
            b.write_bytes(content)
            page(f.w,snap,data,2,2); assert f.cmp(snap,cut)

def byte_budget_pending(f):
    # Each page fits two of these; passing the same cut twice must not duplicate
    # the pending lookahead, and an unrelated comparison discards it safely.
    data=[append(f,1),append(f,2)]
    cut=f.snap()
    for i,ch in enumerate("xyz",3): data.append(append(f,i,ch*1500000))
    head=f.snap(); assert f.cmp(head,cut)
    page(f.w,head,data,2,9,n=2); page(f.w,head,data,2,9,n=2)
    assert f.cmp(head,cut); page(f.w,head,data,4,9,n=1)
    page(f.w,head,data,2,9,n=2); page(f.w,head,data,4,9,n=1)

def main():
    p=argparse.ArgumentParser();p.add_argument("worker",type=Path);a=p.parse_args()
    binary=str(a.worker.resolve(strict=True)); cases=0
    with open(binary,"rb") as b: sig=hashlib.sha256(b.read()).hexdigest()
    print("worker.sha256",sig,flush=True)
    for kind in ("jsonl","sqlite"):
        tests=[empty_then_append,interleaved_cuts,independent_writer,byte_budget_pending]
        if kind=="jsonl": tests += [partial_tail,atomic_after_cut,mid_suffix_change,blobs_at_cut]
        for test in tests:
            with fixture(binary,kind) as f: test(f)
            print("PASS",kind,test.__name__,flush=True); cases+=1
    print(f"{cases} additional scenario/backend pairs passed")
if __name__=="__main__": main()
