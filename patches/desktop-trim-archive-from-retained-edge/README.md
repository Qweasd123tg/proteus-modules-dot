# Count archived history rows from the retained edge

For Core-backed history, count payloads from the edge being kept and
stop when the next row no longer fits. If the page minimum or visible
range requires more rows, keep them regardless of budget. The 50-row
page minimum, 200-row and 8 MiB limits, visible range, absolute start
and splice behavior are unchanged.

Rust 1.95.0 source-lifted fixtures passed 18 tests in each build profile,
including six unmodified test bodies per version, a paired paging and
live-tail merge sequence, 16 labelled controls and 900 generated
windows. Both directions kept the same 85 of 200 rows with 96 KiB
charges, while payload-accounting calls fell from 315 to 86. An
all-protected case kept all 200 rows and needed no payload walk.

This measures how many rows were charged, not memory retained, wall
time, startup, or native RSS. The proof uses inert owned fixtures with
representable charges, without Cargo, a GUI, or a real backend.
