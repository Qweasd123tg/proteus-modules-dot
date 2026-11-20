# Core: two-pass replay for history with turn lifecycle records

Source base: Proteus-harness/Proteus-core `048378da7cbe890d8bf8a0152e55eb28ecb5013d`.

Run `git apply --check <path-to-lifecycle-replay.patch>` from the Core checkout before applying. The patch is not applied to Core by this PR.

The existing two-pass renderer now accepts `TurnOpened` and `TurnSettled` in addition to history mutations. The discovery pass already captures root-thread bindings; settlement rows use their own timestamps. The second pass still visits records in journal order and obtains the earliest causal dates before rendering. No new cache, protocol changes or skipped validation. A non-live hard reset, hosted activity or any other record kind still selects the previous four-pass renderer. The append certificate pass is not part of this patch.

The journal test group passed 40/40 using `cargo test --offline --locked -p proteus-core --lib app_server::transcript::journal`. The added differential test compares projection output at every journal prefix across three live-turn choices and tests compaction, a visible vs. live reset, clock rollback, and failed/canceled turns. The history-only + lifecycle fast path takes two render scans; the visible reset still takes four.

Stock synthetic cold-attach fixtures were confirmed eligible: 1,050 archive rows had eight history mutations, four opens, and four settlements; 5,000 had 32 mutations, 16 opens and 16 settlements. Each had one compacting replace and neither contained model/tool journal records. This proves scan-count reduction on the eligible path, not a measured launch, latency, RSS or Desktop improvement.
