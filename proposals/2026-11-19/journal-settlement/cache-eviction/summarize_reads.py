"""Compare new-revision reads against the *exact keys* written before publishing the first HEAD."""
import sys
cases={}
for line in open(sys.argv[1]):
    fields=line.split(); is_read=fields[0]=='READ'
    session,rev,key,size=fields[1:5] if is_read else fields[:4]
    rev,size=int(rev),int(size)
    old,first_rev,hits=cases.setdefault(session,[set(),None,[]])
    if first_rev is None:
        if not is_read and key.startswith('display-data-'): old.add(key)
        if not is_read and key=='display-view-v1-head': cases[session][1]=rev
    elif is_read and rev>first_rev and key in old and size:
        hits.append((key,size))
for old,rev,hits in cases.values():
    assert rev is not None
    print(f"initial_seq={rev} old_keys={len(old)} distinct_old_reread={len({k for k,v in hits})} reads_of_old={len(hits)} envelope_bytes={sum(v for k,v in hits)}")
