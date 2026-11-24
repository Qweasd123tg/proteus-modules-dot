#!/usr/bin/env python3
"""Independent oracle for R273's typed shifted HistoryMutated benchmark.

This deliberately scans every byte with the pre-optimization Gear recurrence,
not by importing either Rust arm. It is a fixture expectation, not a proof of
filesystem behavior, memory use, or deployment.
"""
import hashlib
import json

MASK=(1<<64)-1
MIN,MAX=16*1024,64*1024
MAGIC=b'PROTEUS-SHARED-BLOB-1\n'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def compact(obj, sorted_keys=False):
    return json.dumps(obj, sort_keys=sorted_keys, separators=(',',':'), ensure_ascii=False).encode()

def initial_text():
    s=7
    out=bytearray()
    for _ in range(1<<20):
        s^=(s<<13)&MASK
        s^=s>>7
        s^=(s<<17)&MASK
        out.append(97+s%26)
    return out.decode('ascii')

def payload(text,n):
    uid=lambda k:f'00000000-0000-4000-8000-{k:012x}'
    message=dict(id=uid(1+2*n),role='User',phase=None,
                 parts=[dict(part_id=uid(2+2*n),provenance='user',scope='conversation',payload={'Text':{'text':text}})],
                 name=None,tool_call_id=None,metadata=None)
    return dict(previous_revision=n,new_revision=n+1,mutation='append',messages=[message],compaction=None,tool_results=[])

def gear_entry(i):
    n=(i+0x9e3779b97f4a7c15)&MASK
    n=((n^(n>>30))*0xbf58476d1ce4e5b9)&MASK
    n=((n^(n>>27))*0x94d049bb133111eb)&MASK
    return n^(n>>31)

def splits(data):
    table=list(map(gear_entry,range(256)))
    pos=0
    while pos<len(data):
        h=0
        end=min(pos+MAX,len(data))
        for i in range(pos,end):
            h=((h<<1)+table[data[i]])&MASK
            if i+1-pos>=MIN and not h&0x7fff:
                end=i+1
                break
        yield data[pos:end]
        pos=end

def report():
    s=initial_text()
    out={}
    for mode,sort in [('default',True),('preserve_order',False)]:
        a,b=[compact(x,sort) for x in (payload(s,0),payload('new prefix'+s,1))]
        x,y=[[(sha(chunk), len(chunk)) for chunk in splits(raw)] for raw in (a,b)]
        combined=set(x)
        hits=[]
        for identity in y:
            if identity in combined:
                hits.append(identity)
            combined.add(identity)
        manifests=[MAGIC+compact(dict(bytes=len(raw),sha256=sha(raw),chunks=[dict(sha256=h,bytes=n) for h,n in chunks]))
                   for raw,chunks in ((a,x),(b,y))]
        out[mode]=dict(payload_sizes=list(map(len,(a,b))),payload_sha256=list(map(sha,(a,b))),
                       manifest_sizes=list(map(len,manifests)),manifest_sha256=list(map(sha,manifests)),
                       chunk_counts=list(map(len,(x,y))),second_hits=len(hits),
                       second_new_chunks=len(y)-len(hits),second_existing_bytes=sum(n for _,n in hits),
                       first_matched=hits[0],max_matched=max(n for _,n in hits))
    return out
if __name__=='__main__':
    print(json.dumps(report(), indent=2))
