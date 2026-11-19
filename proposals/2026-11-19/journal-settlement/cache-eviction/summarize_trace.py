"""Print compact groups for the completed-turn fixture (one owner; no concurrent cache mutations)."""
import collections, sys
groups=collections.defaultdict(list)
for line in open(sys.argv[1]):
    session,rev,key,size,count,total,us=line.split()
    groups[session,int(rev)].append((key,int(size),int(count),int(total),int(us)))
for (_,rev),events in groups.items():
    print(f"seq={rev} writes={len(events)} files_seen={sum(x[2] for x in events)} cache_bytes_written={sum(x[1] for x in events)} last_cache_bytes={events[-1][3]} evict_us={sum(x[-1] for x in events)}")
