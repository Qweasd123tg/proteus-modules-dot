# Reuse bounded JSONL scratch during strict snapshot folds

Borrow one raw-line scratch buffer through a strict snapshot fold and
release it before final fingerprint/version checks. The existing JSONL
cursor still discards oversized scratch. SQLite's default behavior,
validation, history, and durable formats are unchanged.

Apply `source.patch` to exact Modules `345585a91d9f7bac7cef971db68e41569f97a672`, whose
snapshot source already contains the historical #804/#807 changes.
Do not reapply those. This is not based on the prior Desktop manifest's
pinned Modules SHA.

Both unmasked optimized libraries built on the exact current storage
source. Each passed 115 native unit tests, with no failures
and one pre-existing ignored test. An owned `ReadConversation(Current)`
with repeated cross-buffer JSONL rows made 1038 → 1021 allocator
requests and requested 1033397 fewer aggregate bytes. History and
journal fingerprints matched. Opening the snapshot was measured separately;
this does not claim improved display startup, PSS, or elapsed time.
