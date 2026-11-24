# Usage: borrow the existing request slice for the default view

For all statuses, a blank (including Unicode whitespace) query, and oldest
order, the Usage panel reads the already-scoped requests without building
another vector of the same references. The scope can already be limited to a
turn or model. Other filters, searches, orders and errors keep their original
implementation and owned results on success.

An isolated native Rust witness exercised 17 cases and 68 allocator ledgers
(stock, candidate, candidate, stock). Every output reference was checked
against the original snapshot index and order; on the borrowed path the
slice had to be the caller's exact input. For 2,048 realistic-shaped rows,
extra peak and retained requested bytes fell from 16,384 to 0 and allocation
requests from 10 to 0. For 50,000 compact entries the extra peak and retained
requested bytes fell from 524,288 to 0, gross requested bytes from 1,048,544
to 0, and allocation requests from 15 to 0. All eight non-default cases
matched all four counters and their outputs. The snapshot and scoped input
vector are made before measurement and still exist; this is not zero memory
for the panel, a GUI benchmark, a latency result, or a process memory claim.

The one-leaf patch applies and reverses on the immutable Extensions owner
and packaged Desktop pin without a prerequisite. The tested full report
file includes #693; the tested complete view source includes #673, but the
owner's actual caller already uses this API compatibly. Neither is required
to apply the patch. Full package builds were not run.
