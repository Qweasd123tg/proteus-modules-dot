from pathlib import Path
import sys

expected = {"crossing": (50, 35), "changed": (50, 28), "nonoverlap": (50, 0), "near": (50, 45)}
arms = []
for filename in sys.argv[1:]:
    report = {}
    for line in Path(filename).read_text().splitlines():
        if line.startswith("WORK "):
            _, case, *columns = line.split()
            assert case not in report
            report[case] = tuple(map(int, columns))
    assert report.keys() == expected.keys()
    arms.append(report)
assert len(arms) == 2
stock, candidate = arms
for name, (rows, reused) in expected.items():
    stock_rows, stock_reuse, old_count, wire, reusable, old_copy = stock[name]
    new_rows, new_reuse, new_count, new_wire, new_reusable, new_copy = candidate[name]
    assert (rows, reused, wire, reusable) == (stock_rows, stock_reuse, new_wire, new_reusable)
    assert (new_rows, new_reuse) == (rows, reused)
    assert (old_count, new_count) == (rows, rows - reused)
    assert (old_copy, new_copy) == (wire, wire - reusable)
    print(f"PASS {name}: rows={rows} shared={reused} conversions={old_count}->{new_count} "
          f"UTF-8 payload bytes copied into Arc<str>={old_copy}->{new_copy}")
