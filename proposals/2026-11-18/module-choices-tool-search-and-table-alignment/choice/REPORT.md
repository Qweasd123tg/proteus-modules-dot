# Share checkbox inputs for mixed/numeric enum arrays

**Result:** The Desktop Settings checkbox grid retained a deep copy of *every* option (including every title) and the whole selected array **in every checkbox**. For 128 ordinary numeric choices with half selected, two dependency builds independently reported 16,898 → 259 allocation requests while constructing the real renderer in a native capture. Live bytes at return were 3,033,746 → 36,786 in one build and 2,045,586 → 29,106 in the other. These are fixture measurements, not live application memory figures.

## What is established

- Core's [public schema declarations](https://github.com/Proteus-harness/Proteus-core/blob/c2cbadee518788f306ffb2b5271036b2658ea8cc/crates/proteus-contracts/src/domain/config_schema.rs#L46-L76) define tagged array/enum schemas and `ConfigChoice { value: Value, title: String }`. A non-string JSON value is representable. The test actually deserializes invented descriptors with the pinned types. It does **not** run Core's configuration validation, or establish that a default profile has such a descriptor.
- Desktop's ordinary settings [field classifier](https://github.com/Proteus-harness/Proteus-Desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/settings/schema.rs#L66-L118) returns MultiChoice for an array of enum items. The [tags check](https://github.com/Proteus-harness/Proteus-Desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/ui/settings/tags.rs#L21-L32) diverts all-string enum arrays; an array with any numeric option instead reaches [the checkbox renderer](https://github.com/Proteus-harness/Proteus-Desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/ui/settings/fields.rs#L94-L124). The grid is part of the shipped renderer, not a control provided only in an SDK. I did not identify a bundled module using a 128-choice numeric grid, or measure how often such a form appears. Do not advertise a particular stock configuration or typical latency.
- The [old implementation](https://github.com/Proteus-harness/Proteus-Desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/ui/settings/fields.rs#L239-L281) deep-cloned the choices via `options.to_vec()` and the selected values via `selected.clone()` for each row. The patch freezes just the option *values* and the selected values once in two immutable reference-counted slices. A row gets two shared owners and its existing index; it does not retain other rows’ titles. Each label still owns its own title. Comparing to the value at the current index, rather than comparing indices, is deliberate: equal values at multiple indices keep the original behavior.
- Existing results remain in option order; duplicate option values may produce duplicate results, unlisted saved values are omitted on a click as before, and selected duplicates do not multiply results. Stored value vs default, missing/non-array values, same-looking string and number, null, nested values and repeated clicks are covered. The fixture captures the exact callback's emitted JSON in memory, without reading/writing any profile.

## Focused native results

Both versions: **972** forms from three option families (all rotations, nine current shapes × nine default shapes), **5,994** checkbox titles/states/IDs, **23,976** callback values. Each was compared to an independently computed result. Two controls confirm that empty and all-string arrays take the tag route instead.

Integer options numbered 0…n−1, distinct nonempty UTF-8 titles, every other option selected. In a single-threaded fixture the same counting allocator measured creating the real Rust `multi_choice` with an in-memory substitute for visual nodes and the settings-result sink. Core deserialization, fixture preparation, dispatch, and paint are outside that interval. Requested bytes count allocations and reallocations; live bytes are the net allocated bytes remaining just after return, **not peak RSS**. Each capture released all its live bytes when dropped.

First local dependency build (serde_json::Value: 72 bytes):

| Options | Allocation requests, old → patched | Requested bytes, old → patched | Live bytes at return, old → patched |
| ---: | ---: | ---: | ---: |
| 8 | 98 → 19 | 14,000 → 2,320 | 13,712 → 2,320 |
| 32 | 1,154 → 67 | 196,502 → 9,206 | 195,350 → 9,206 |
| 128 | 16,898 → 259 | 3,038,354 → 36,786 | 3,033,746 → 36,786 |
| 256 | 66,562 → 515 | 12,106,130 → 73,650 | 12,096,914 → 73,650 |

Second build (serde_json::Value: 32 bytes; full numeric matrix in `checks/results-default.txt`): the same 128-option fixture requested 2,047,634 → 29,106 bytes (2,045,586 → 29,106 live). Semantic checks and allocation **counts** are identical in the two builds at every tested width. A native `size_of::<serde_json::Value>()` probe against the exact rlibs returned 72 vs 32; at 128/64 this 40-byte difference exactly accounts for the observed requested-byte gap: before, 40 × (128² + 128×64 + 128 + 64) = 990,720; after, 40 × (128 + 64) = 7,680. Absolute bytes are build-specific. Both fingerprints identify the same rustc but the Cargo feature sets and profiles differ. The tests did not isolate a single causal feature.

| Library pair | serde rlib SHA256 | serde_json rlib SHA256 | serde_json fingerprint features |
| --- | --- | --- | --- |
| A (72-byte Value) | `ece729f620863ecbbe16f22ba39497d6fc148d1cd2ee7fe8cc9318f26fb46cbb` | `4be82f7b5461323c77ddd10d206efb531903428da2f4bc7420896d730d910fa5` | alloc,default,float_roundtrip,indexmap,preserve_order,raw_value,std |
| B (32-byte Value) | `6cea74ad7bd8ba80f2c3e45f052f7a11e3d34e26c483646c9b35221761d6d88b` | `42cd69265b34e1dd3f9769fc16b21907c3c979fbecf3a320e47009f4ae651c0f` | default,std |

The reduction concerns repeated copies. Rendering checked states still uses linear membership tests over the selected array, and a click can still traverse the options and search selected values. No claim of linear total running time, screen latency, or end-to-end memory savings. No additional cross-frame cache, deduplication or behavior change is proposed.

Separate reviewer approved the exact patch: 800 forms, 2,080 controls and 8,320 callback values; on a different 128-option nested-JSON fixture, 149,385 → 1,418 allocation requests and 18,334,823 → 187,655 requested bytes.

## Reproduction and scope

Desktop base `2307e9c67125bbe66f15ced51317a2dfcc437aa4`; file blob `e038818a96da61e8ce5e52a8b66ce513cbf37e20`. Core `c2cbadee518788f306ffb2b5271036b2658ea8cc`; Modules `0fe8e3b4dfb64ca2e07df8af016d7ccc3a7de45f`; dot index `1f0e058b52209d5f0f056ef1a91e58401de3b683`. The dot history through #208 and patch inventory showed no earlier patch for this checkbox path: #199's shared snapshots were for declarative list rows, not Settings `multi_choice`; #201 and #206 changed string-tag routing or readout, not retention of numeric checkbox data. Plain upstream tests for array editability do not prove that this exact route occurs in a specific default module.

`share-checkbox-values.patch` SHA256 `1f8c33475c0686b912227ed1bdfd99c4fb36af4fb31cf2d34666d55f1a8b6000`. Replay only needs the following two checks files, the exact patch, source checkouts, Python 3, patch, matching local serde and serde_json rlibs plus transitive dependencies in their directory, and a compatible rustc (tested 1.95.0). It checks source identity and reads only public declarations from Core.

```sh
python3 checks/replay.py PATH_TO_DESKTOP PATH_TO_CORE share-checkbox-values.patch \
  /path/to/libserde-HASH.rlib /path/to/libserde_json-HASH.rlib --rustc /path/to/rustc
```

No changes published or applied to either upstream; no GUI, backend, project subprocesses, live settings, or full-workspace build/test. The patch changes one function only.
