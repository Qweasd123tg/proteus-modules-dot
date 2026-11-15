# Checks actually performed

2026-11-15. Source-only candidate. No project execution.

- Start/end remote main refs matched REFS.json; 15 source/doc blobs exactly
  matched pinned Git blob SHA-1 and retained SHA-256, reverified at completion.
- Production patch changes one Desktop file, +12/-1 lines. No Extensions
  implementation is changed. No upstream/production repository was edited.
- Independent design review and exact-patch/source-generator review preceded
  text extraction. Python -I -B -S regression/generate.py generated text only.
- Two generated Rust fixture files match extraction.json; the three methods
  were independently compared verbatim against their appropriate source.
- Ten extracted-method controls and three separate SDK consumer controls are
  NOT COMPILED and NOT RUN. No baseline-red or candidate-green result exists.
- patch --batch --fuzz=0 -p1 succeeded in an owned apply-check copy; cmp matched
  the exact candidate. Forward and reverse git apply --check
  --whitespace=error-all both returned exit 0.
- git diff --no-index --numstat returned +12/-1 and its normal difference exit
  code 1. That is a text diff, not a test or runtime failure.
- Text whitespace check found no trailing whitespace in report, README, both
  proposed test sources or the generator. Relative report/README links resolve.
- cargo/rustc were absent from PATH. No install, formatter, Rust compilation,
  SDK binary, HTTP, provider, GUI, file actions or behavioral Python model ran.
- No benchmark, latency/RSS/CPU, complete native gate or release claim.
