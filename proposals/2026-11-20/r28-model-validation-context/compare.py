"""Compare allocation probe rows. Counts are bytes requested, not live heap/RSS."""
import json, re, sys
from pathlib import Path

def read(path):
    rows = re.findall(r"R28ALLOC path=(\w+) fixture=(\d+) bytes=(\d+) calls=(\d+)", Path(path).read_text())
    assert len(rows) == 6, rows
    return {(p, int(size)): (int(n), int(c)) for p, size, n, c in rows}

base, after = [read(path) for path in sys.argv[1:]]
assert base.keys() == after.keys() == {(p,n) for p in ("replay","service") for n in (1024, 1<<20, 8<<20)}
summary = []
for path,size in sorted(base):
    b,c = base[path,size],after[path,size]
    if size >= 1 << 20:
        assert b[0] - c[0] >= size, (path,size,b,c)
        assert c[0] < 1 << 17, (path,size,b,c)
    summary.append(dict(path=path,user_text_bytes=size,before_bytes=b[0],after_bytes=c[0],before_calls=b[1],after_calls=c[1]))
print(json.dumps(summary, indent=2))
