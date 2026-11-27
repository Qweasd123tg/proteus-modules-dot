# Borrow model identifiers while building output metadata

Serialize the provider and model as borrowed str. The result JSON
still owns both strings. Missing, empty and Unicode values, and
extra metadata override behavior retain exact output bytes.

Base: Modules f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
Four focused checks and an optimized library build per exact arm.
Short identifiers: 26→24 Rust allocator requests.
Two long synthetic identifiers: 26→24 requests, saving
20,480 cumulative requested bytes (not peak memory).
Absent model control unchanged. No app or timing measurement.
