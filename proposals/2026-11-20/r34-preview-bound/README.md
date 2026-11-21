# Session storage: bounded text preview

Source: Proteus-harness/Proteus-modules `cf999371f6e564376565738bebc3416aad12f908`. Before applying, run `git apply --check <preview-bound.patch>` in Modules. This proposal does not change upstream.

Copy only the display preview, not the entire selected text. Keeps Unicode trimming, user-message priority, fallback part selection and the first 160 Unicode scalar values plus literal `...` only when truncated. The existing ToolResult conversion still runs as before. No changes to persistence, worker protocol or checks.

Pinned fixture with 16 MiB of already-owned ASCII source text: the isolated preview function requested 16,777,856 total allocation/reallocation bytes before the change and 163 bytes after (4 requests versus 1). A short 64-byte result still requested one 64-byte allocation. These are per-operation allocation requests, not worker peak RSS, I/O or launch time. Stock and candidate outputs match across size and Unicode controls. Targeted package tests: 60 unit and 2 process tests passed; one manual performance test remained ignored. Regression test covers 160/161 Unicode scalar boundaries, trimming and fallback.
