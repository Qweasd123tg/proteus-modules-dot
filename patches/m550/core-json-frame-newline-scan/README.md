# ProcessHost: skip scalar LF search on large newline-free continuations

For a continued line and a fragment of at least 1,024 bytes, the optimized
byte-slice containment predicate can prove there is no LF. In that case the
existing scalar position search is unnecessary. On a positive match, the
original search still finds the precise first LF. Initial or short buffers
still use the old position search. No dependency or lockfile change.

The delimiter-inclusive frame bound, overflow/consumption behavior,
malformed UTF-8 before JSON, allowed EOF/CR behavior, multiple-frame order
and error strings stay the same. No byte allowance moves upstream: transport
compact receive accounting, queue limits, lifecycle, JSON value ownership,
renderer and authorization are unchanged. A large continued fragment that
does contain LF now does an extra containment check before locating it;
the win is for long runs of newline-free fragments.

## Native outcome

Exact M368 source archive (hash in source-replay.json), strict whole-tree
apply and reverse. Production changes only the newline permission-neutral
byte search; matching content-length and transport code are left unchanged.
Release Rust 1.95.0 tests ran on newly compiled, exact separate target paths:
baseline 8 framing tests, candidate 9, plus the genuine 29 ProcessHost
subprocess session tests per arm in both map modes. The candidate's new
test covers limit crossing with long fragments, bad UTF-8, late CRLF and the
following JSON frame. A distinct native A/B compiled both true source
functions side by side: 270 long-frame validity/error/consumption
comparisons per JSON map mode. It also fed projected and strict 50k
serialized fixtures made with exact M368 product Contracts, validated against
their actual SessionStorage request and response checks, through the full
native reader. A 128 MiB frame limit and normal 8 KiB BufReader are identical
between arms. Input bytes, output values and entire accepted consumption
match. The proof is in-process I/O, not a launcher/display or worker benchmark.

10 alternating-order pinned release thread-CPU pairs per shape. Table
reports the median of paired candidate/baseline ratios and marginal
baseline/candidate CPU medians per call (different summary statistics):

| Frame | Default paired CPU change | preserve_order paired CPU change |
|---|---:|---:|
| 50k ×4 projected, 32,689,494 wire B | −4.1% (171.63 → 165.17 ms) | −2.4% (215.39 → 205.83 ms) |
| 50k ×5 strict, 37,389,613 wire B | −5.4% (183.56 → 173.58 ms) | −2.9% (217.60 → 210.41 ms) |
| 8 MiB plain string | −36.1% | −37.3% |
| 1 MiB escaped string | −10.9% | −12.8% |
| 47-byte already-buffered control | +3.6%, about +20 ns marginal | +2.6%, about +10 ns marginal |

This does not shorten the lifetime of the frame Vec or change retained
space, and does not measure whole-startup latency, cross-process PSS/RSS
or the user's 695 MiB peak. A separate experiment to apply the writer's
compact byte counter to receive passed parity but was slower; no part of it
is selected.

## Reproduce

Under a disposable layout, place exact framing.rs in
baseline/proteus-process-host/src/ and the patched file in
work/proteus-process-host/src/. Place native-proof.rs/proof-Cargo.toml/
proof-Cargo.lock at proof/main.rs, proof/Cargo.toml and proof/Cargo.lock.
Point the Cargo input path for proteus-contracts at exact M368 Contracts
(the M362 copy used in the workspace is verified byte-identical), leaving
registry versions and features unchanged. Pin an idle Linux CPU and compare
release locked runs with and without the ordered feature. Run the actual
framing and session tests in separate Cargo target directories across
arms so that equal workspace-relative package paths cannot alias cached
artifacts. See verified.json for exact samples and tests.
