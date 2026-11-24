# Decide turn-footer copy eligibility in one backward scan

Exact base: [Proteus-desktop at f8cc4017](https://github.com/Proteus-harness/Proteus-desktop/tree/f8cc40177ad3ab3d8ec36447a899332778f03268), `src/ui/chat/thread.rs`.

The first decisive row in the existing displayed prefix now determines copy eligibility: a User row ends the search unsuccessfully, and an Assistant row with nonblank text succeeds. If neither is present, the prefix has no loaded User row and stays eligible, as before. The scan still runs only when a footer exists. Tool and reasoning text do not qualify as an answer. The prefix cutoff, folded or moving chain boundaries, timestamp, footer visibility, copied payload and action wiring are unchanged.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

[#403](https://github.com/Qweasd123tg/proteus-modules-dot/pull/403) is already included: the current stamp file matches its postimage, and the current thread calls the combined boundary/time helper. Do not reapply it.

## Verification

Use the pinned source files from `SOURCE-PROVENANCE.json` under the listed `*.ref` names.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

Rust 1.95 passed 6/6 in debug and optimized modes. The exact source lift compares 228,762 prefix/footer decisions to an independent oracle and runs the same chain-end selection, timestamp calculation and footer gate with inert hidden-row and UI inputs. It covers no timestamp, no footer, earlier replies beyond the last User, Unicode whitespace, and open/closed/moving chains. The full file applied and reversed byte-for-byte in private scratch and passed rustfmt. No Desktop app or UI was run.

A scoped iterator counter recorded 100,000 to 50,000 eligibility visits on 50,000 loaded blank Assistant rows with no User, and 50,001 to 2 when the same prefix ends in a User followed by one blank Assistant. An immediately decisive answer stays 1 to 1; no footer stays 0 to 0. These are visits in this one predicate, not whole rendering cost, time or memory.
