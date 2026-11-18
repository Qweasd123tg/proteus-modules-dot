# OpenCode compaction: reuse the original native token estimate

On a 512-message history (~68k native-estimated tokens) with no prior/host usage measurement, completing the actual pinned OpenCode compaction hook with a local deterministic summary took **14.72 → 8.97 ms**, and allocated an estimated **14.64 → 9.79 MiB per invocation**. This removes one transcript conversion from completed compactions; it does not accelerate the model, change trigger thresholds or promise faster ordinary turns.

## Exact change and bounds

The [upstream hook](https://github.com/Proteus-harness/Proteus-modules/blob/37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979/workflow/opencode-runtime/compaction.mjs) runs native `estimateContext(context)` before compaction, then separately runs `estimatePrompt(context)` after completion for reporting. At pinned @opencode/core 2.0.22, the first function calls the second and returns the sum of `measured` and `estimated`; the latter rebuilds the transcript from the last usage anchor and estimates its tail. We now compute the two-component result once **at the original preflight point** and report its total and the components from that snapshot. The stock SDK still owns all estimates, limits, decisions and callbacks. The extra regression compares the reported total against the upstream helper even for a partial anchor plus a nonempty estimated tail. The JS object with two numbers crosses the await; there is no persisted cache.

The benefit is greatest when a nontrivial history must be estimated. The Core-supplied whole-request token count ordinarily adds a final anchor, leaving little work to avoid. A skipped compaction always made only one wrapper estimate. No new early exit bypasses validation.

Source: Proteus-modules main and stated Desktop pin `37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979`. Production Git blob `25d2005ad14d740204eb36b2eb2f974d5cfe792b` → `15ba0998c7a04a14ecbfa008dff760e3fb9f72b1`; baseline lockfile blob `e94a0ffa90651d071820222e761a680fd943b808`. The patch clean-applied to these original source/test bytes; both resulting files matched the tested copies. Targeted PR and patch searches on proteus-modules-dot (main `6e357a1b97cd4831b31769f845fb4fa54ab42852`) found no matching estimate reuse; unrelated #214 stream collector is untouched.

## What ran

- Locked Linux Node **24.12.0**, @opencode/core and @opencode/ai **2.0.22**, actual Effect layers and native compaction service. Only the model callback was replaced with a local fixed summary. No live provider, network latency, production trace or Desktop memory was measured.
- Entire stock `workflow/opencode-runtime/tests/compaction.test.mjs`: **17/17** unchanged tests passed before and after. With the new partial-anchor regression: **18/18**. Other repository suites not run for this patch.
- Seven parity fixtures compared **complete returned results, all callback requests in order, callback counts and error results** with just fresh UUIDs normalized; all digests match. Includes short, long, mixed, Core anchor, skipped, unsupported source before any callback, and host error after one callback. Serialized input/output remains the same.
- Numbers below: medians of five fresh process pairs; order alternated between pairs. Warm each fixture, then time batches of 20 invocations (32 for short). Each fixture and returned totals were identical across variants. The text fixture has 512 alternating user/assistant messages of ~530 chars each; the mixed fixture replaces two per eight with inert canonical call/result history. No historical call is executed.

| Whole hook; local model callback | Baseline → patched ms / invocation |
|---|---:|
| Complete, 512 messages, no usage anchor | **14.72 → 8.97** |
| Complete, mixed 512-message history, no anchor | **14.07 → 10.84** |
| Complete, six messages | 1.22 → 1.02 |
| Complete, Core measurement anchor | 4.70 → 4.13 |
| Below threshold, skipped | 9.39 → 11.14 |

The skipped fresh-process control was noisy and initially slower, despite removing no estimator pass there. A second, same-process alternating control (12 pairs × 15 calls per side) reversed its sign: medians 10.09 → 8.52 ms, median **paired** difference −0.24 ms. Core-anchored control was 5.42 → 5.27 ms in that second run. **No reliable gain or loss is claimed on either control.** Raw samples including slow outliers are retained.

Separate V8 heap sampling (64 KiB interval, include objects collected by both minor/major GC) over 24 long unmeasured completed hooks, three fresh process pairs: median cumulative estimated allocated bytes divided by count, **14.64 → 9.79 MiB per hook** (−4.85 MiB, ~33%). This is churn across the whole in-process operation, not live or peak heap, exact byte counts, idle RSS or PSS.

## Reproduce

Use two checkouts of the pinned source with the locked OpenCode runtime already installed in each. From this evidence directory:

```sh
E="$PWD"
B=/path/to/baseline
C=/path/to/candidate
P=workflow/opencode-runtime/compaction.mjs
N="$B/workflow/opencode-runtime/node_modules/node-linux-x64/bin/node"
(cd "$C" && git apply --check "$E/compaction-reuse-estimate.patch" && git apply "$E/compaction-reuse-estimate.patch")
"$N" --test "$B/workflow/opencode-runtime/tests/compaction.test.mjs"
"$N" --test "$C/workflow/opencode-runtime/tests/compaction.test.mjs"
for mode in parity time alloc; do
  "$N" --expose-gc measure.mjs "$B/$P" "$mode"
  "$N" --expose-gc measure.mjs "$C/$P" "$mode"
done
"$N" --expose-gc measure.mjs "$B/$P" paired_control "$C/$P"
```

For the published sample counts run five process pairs for time and three for alloc, alternating the first side across pairs. Source hashes on every row identify which variant ran.
