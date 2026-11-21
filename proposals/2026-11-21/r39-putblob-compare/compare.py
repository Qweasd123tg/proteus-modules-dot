"""Check complete on-disk and response parity; emit paired allocation results."""
import csv
import re
import sys
from pathlib import Path
output = Path(sys.argv[1])
def extract(p):
    data = {}
    for line in p.read_text().splitlines():
        if m := re.search(r'PUT,(Jsonl|Sqlite),(\d+),(create|replay|reuse),(\d+),(\d+),(\d+),([0-9a-f]{64}),([0-9a-f]{64})$', line):
            key = m.groups()[:4]
            assert key not in data
            data[key] = m.groups()[4:]
    assert len(data) == 2*5*3*3 and "2 passed; 0 failed" in p.read_text()
    return data
before, after = [extract(output/f"{name}.log") for name in ("before","after")]
assert before.keys() == after.keys()
with (output/"results.csv").open("w", newline="") as stream:
    csvout = csv.writer(stream,lineterminator="\n")
    csvout.writerow("backend,size,operation,pass,alloc_calls_before,alloc_calls_after,requested_bytes_before,requested_bytes_after,content_sha256,receipt_sha256".split(","))
    for key, (old_n,old_b,h,r) in before.items():
        n,b,h2,r2 = after[key]
        assert (h,r) == (h2,r2)
        if key[2] != 'create' and int(key[1]) >= 256*1024:
            assert int(old_b) - int(b) >= int(key[1])
        csvout.writerow([*key, old_n,n,old_b,b,h,r])
print("90 paired results; exact content and receipt hashes agree.")
