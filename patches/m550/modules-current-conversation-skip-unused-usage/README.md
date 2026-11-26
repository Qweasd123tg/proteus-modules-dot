# Modules: skip the unused usage summary when reading current conversation

A fixed-prefix `ReadConversation(Current)` still visits and validates every record and returns the same history, revision and model context. It no longer builds per-request usage rows and pending-exchange bookkeeping only to discard them. Explicit usage, writer/resume, display snapshots, historical selectors and journal integrity checks are unchanged.

On the exact standalone Modules patch, 107 isolated Rust tests passed; one pre-existing manual performance test was not run. The negotiated SDK v3 workers also produced 8 identical normalized results or errors per backend across JSONL and SQLite, including old snapshots after a later append, fresh current conversation, explicit usage and writer resume. No timing, process-memory or Desktop claim was measured.

Apply one variant: `source.patch` on the exact owner preimages, or the embedded alternate in `receipt.json` when both #800 and #804 are already selected. #803 and #805 do not change these preimages; obey #805's own #803 dependency if selecting it. The embedded alternate is source-verified, not built or run. Neither selector is exact after just #800 or just #804, and do not apply both variants.
