# Terminal benchmark: stream the replay binary's report checksum

Compute the replay binary's SHA-256 after sampling, as before, but feed it through one reusable 256 KiB block instead of reading the complete binary into a bytes object. The aggregate source digest, file order, provenance format, sampling, and report order are unchanged. This does not add a Python 3.11 dependency.

With a synthetic 32 MiB regular file, the complete input and resulting SHA matched. The largest individual input block was 256 KiB instead of a 32 MiB bytes object. This is an allocation-path check for report generation, not the size of the actual replay binary, disk I/O, process memory, or terminal performance. A small file can pay the fixed input buffer cost.

Apply `source.patch` to the pinned Desktop basis in `receipt.json`. No alternate is needed.
