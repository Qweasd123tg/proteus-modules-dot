# Move model request controls through context preparation

Move the request into the existing preparation DTO. Restore the original
sampling metadata and replace the material only after the same validation
and report construction succeeds. The estimate-source annotation remains
preparation-only. History already moved in the old implementation.

Exact Modules basis: f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
The synthetic six-tool/long-instruction fixture saved 101
Rust allocations (38719 requested bytes) in local DTO construction.
Five typed cases preserve original null, scalar, array and object metadata,
outer material, empty inner message list and returned controls. Seven
focused checks and an unmasked optimized standalone library per arm.
No whole-turn timing, provider, or peak-memory claim.
