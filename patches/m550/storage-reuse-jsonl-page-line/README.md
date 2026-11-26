# Reuse one JSONL line buffer while reading a canonical page

The canonical page loop lends the existing bounded scratch buffer to
ordinary and cursor-deferred source reads. It does not retain scratch
between requests. Record order, byte budget, cursor rewind and
fixed-prefix verification remain unchanged. SQLite uses its old reader.
The display-projection page is not changed.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`; full-index apply and reverse verified.
Prepared for this current main only. Older #853 and #857 packages touch
the same source file and are not composed here. Two unmasked optimized
storage libraries built. Passed 117 component tests per arm,
with one ignored. On one verified canonical read of 12 long inline
records, Rust allocator requests went 453→430, with cumulative
requested bytes 2678150→1182783. Same bytes decoded, same 12 records,
and identical results for smaller pages and retries. The earlier
cold snapshot opening was outside the measurement.
No elapsed time, physical I/O or process memory measurement.
