# Reuse the owned history prefix at successful turn completion

Exact base: [Proteus-core at b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14), `crates/proteus-core/src/core/runtime/{history,turn}.rs`.

The terminal success path already owns a private history snapshot. After the existing validations, ordinary success without a history replacement reserves exactly the additional space needed and appends the same cloned suffix. It no longer clones all prefix payloads a second time. The live history and earlier workflow/checkpoint copies are untouched. Borrowed replay and failure/checkpoint paths still use their original allocation and cloning behavior; changed replacement and durable commit code are unchanged.

An owned vector with existing spare capacity retains that space. A resize may move the outer vector of headers; no outer pointer or universal capacity guarantee is made. This is a turn-completion change, not a startup change.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

## Verification

Use the pinned source files listed in `SOURCE-PROVENANCE.json` under each reproduction key plus `.ref`.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

Rust 1.95 passed 18/18 in both debug and optimized modes, including 4,096 generated preparation cases. The source lift uses the actual wrappers, preparation and compacted-user validators and the exact terminal snippet. It checks the same results and error order for stock borrowed, candidate borrowed and candidate owned paths, plus borrowed failure/checkpoint behavior. The terminal probe uses inert commit and steering-error callbacks; actual persistence, concurrency, Serde, provider and full Core integration were not run. Exact patch apply, reverse and both changed-file rustfmt checks passed.

In the synthetic ordinary-success fixture, a 262,151-byte Assistant text and 131,071-byte tool output reuse their existing owned payload pointers. The measured operation, excluding input setup, made 11 allocations and no reallocations in the borrowed path versus two allocations and one reallocation in the owned path. Summed requested bytes went from 394,414 to 675 in each build mode. A cloned exact-capacity prefix produced capacity four, like the original result; an intentionally over-reserved input preserved capacity 128. These are scoped allocator requests, not peak memory, PSS or latency.
