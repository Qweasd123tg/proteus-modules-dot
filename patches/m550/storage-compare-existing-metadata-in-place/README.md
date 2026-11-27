# Compare an existing metadata object without loading a second copy

Use the existing bounded byte comparator on an occupied content-addressed
object. The entire file is still checked, the size and regular-file errors
still apply, and the bytes, etags and repeat-operation receipts are unchanged.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`; full-index apply and reverse verified.
Two optimized libraries built. For each arm 117
component tests passed and one was ignored. Storing a 131110-byte
value under another key without duplicating the object made 63→49
allocator requests and requested 1055353→531097 bytes in the whole transaction.
Mismatched, oversized and nonregular objects still reject without changing
the ledger. No change to read pass, wall time, or process memory measurement.
