# Share retained Desktop reply text with its renderer

One standalone Desktop production patch, identical at exact `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 through Desktop #407. Four exact-source headless arms passed. No native GPUI, extension process, live FIFO, wall-time, RSS/PSS, or remote work.

## Retained and admitted owners

The live transcript already owns the body's immutable `Arc<str>`, and Reply retains it. Mounting an extension-backed user or assistant body formerly made a second full independent `Content.source` buffer. Each source update that changed the rendered revision did the same. The ContentView and attached renderer already share one immutable `Arc<Content>`; on an admitted render the runtime clones its Content to inject the window theme before serializing another owned frame. That themed clone copied the full source text again.

Represent local source as existing `Owned(String)` for unrelated content or `Shared(Arc<str>)` for the chat body. Both serialize as exactly one JSON string and compare by text, not variant or pointer. Keep ordinary owned/nested/preview behavior, move existing String storage when supplied, and do not construct a new buffer before the existing byte+language+context no-op check. Keep prior immutable snapshots for source reveal/copy, unchanged fallback text, and no queue/admission or transport changes. Previously rejected/superseded revisions still do not produce Render frames. A distinct but byte-equal transcript Arc can coexist with an older accepted source Arc, since the no-op branch still deliberately leaves the view revision unchanged. Encoded frames, theme/context JSON, eventual extension-owned data and transcript text itself still own their original bytes. Source storage is not a promise about a process-wide memory budget.

## Focused proof

The harness executes the pinned transcript DTO reset and exact `Replies::part`, update/equality, raw-source and frozen copy expressions, actual `Runtime::render`/`set_content`/ACK paths, `ContentQueue`, `Outgoing::Render`, and encoded-size/JSON line writes. The GPUI mounts, icon subset, viewport/theme source and process reservation/dispatch are modeled. No real native fallback drawing, cross-window renderer, process execution, clipboard or transport queue is exercised.

| Measured backing-store witness | Stock → patch |
|---|---:|
| Retained independent source buffers, 40 mounted 52 KiB transcript rows | 40 → 0 |
| Duplicate retained text bytes at that exact ownership boundary | 2,129,920 → 0 |
| Independent themed source buffers at the 40 mount admissions | 40 → 0 |
| Independent themed source buffers across five evolving/control admissions | 5 → 0 |
| Inline `Content` value size on the test host | 136 → 136 bytes |

Both tiers exercised unchanged warm user/plain and assistant/Markdown bodies, distinct-but-equal input Arc without a revision bump, 32 rapid source replacements behind pending content, stale/wrong ACKs, latest-source/old-source proof, context-only revision, same-revision theme invalidation and queue reset admission, frozen fallback text, release of retired source holders, and a separate nested owned String plus Preview/absent-revision test. The test counts only backing stores observed via pointer identity at live source/sent boundaries, not allocator calls or total retained objects. Ordinary encoded buffers were not removed.

All 47 exact newline-framed Render messages (2,416,545 total bytes) matched on stock/composed baseline/candidate. Frame SHA `d8d450324256a5ffdd4c3f1785f85fd345f83052f1c719c247e34e888647ecb6`; behavior trace SHA `bd47d8306b5ba6855111add9442b308728ab4a57bae1d2616dfc33f986a6b73e`. The full synthetic stream is reproducible from the fixture and stays out of the packet. This did not test a maximum-size frame, although the existing limit and writer code are byte-unchanged. Cargo JSON bound each fresh executable, extracted sources, lock, fixtures and output. The verifier rechecked 42 prior Desktop patch hashes, #405's independent same-file registration hunks, and matching exact queue/admission/serialization neighborhoods in both tiers.

## Reproduce

Use the shared warm offline cache and target, common exclusive lock, one Cargo job, both mounts above 512 MiB and a +200 MiB net growth cap. Set absolute `CARGO_HOME`, `CARGO_TARGET_DIR`, `R84_BUILD_LOCK`, `R84_RAW_CARGO_DIR` and create the raw output directory. The final run sampled maximum growth of +14,172 KiB on the target mount and +12,456 KiB on the temporary mount, including raw fixture wire copies. This is a build resource check, not process memory.

    bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS
    bash verify.sh --run WORKSPACE_WITH_PINNED_INPUTS
