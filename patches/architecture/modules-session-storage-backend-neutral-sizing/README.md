# Modules: keep shared storage sizing and preparation out of the JSONL codec

Base: `Proteus-harness/Proteus-modules@b476a8cca8f0906455753014622d8fbdc08e7899`.

Both storage backends now reach generic compact-JSON sizing through the existing I/O module, and shared entry preparation stays at the commit entry point. The JSONL codec still uses the same sizing guard for its own inline entries. No change to raw validation, redaction, limits, fold/write order, JSONL or SQLite formats, cache envelope, page budgets, or external-body witness checks. This removes dependencies for generic sizing and preparation, not the remaining JSONL-specific witness dependency.

Apply in the Modules checkout with `git apply --check source.patch`, then `git apply source.patch`. `sha256sum -c SHA256SUMS` checks the packet. Forward and inverse apply on current main and the refreshed cumulative verification overlay, with native storage libtests on both using temporary local stores.
