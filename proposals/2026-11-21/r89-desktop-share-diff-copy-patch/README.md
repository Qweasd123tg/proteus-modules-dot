# Desktop: share the per-file diff copy snapshot

One production patch for Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`, verified on stock and the sealed M150 Desktop stack through #411.

Rebuilding a diff file header previously made a deep copy of the file's entire raw patch for the Copy button. This happened before a click and independently of whether the file body was shown. The read-only diff parser still builds the same raw file blocks, then moves each nonempty block into a small immutable shared owner. The Copy handler captures only that raw snapshot, not the parsed file, and creates the same clipboard-owned string only on click. A callback from an older render keeps its original bytes even after files are replaced or reordered. Metadata-only files still disable copy. Copy All, fold/layout/highlighting behavior, dependencies and wire fields are unchanged.

The owner adds a small allocation per nonempty raw block. Parsing still allocates its normal source strings and row structures, and a retiring handler can keep the original raw String's spare capacity until it drops. This does not remove the clipboard's owned string, full-diff source, or parsed lines. There is no native clipboard, frame-rate, latency, process-memory, or full-suite claim.

## Focused verification

* The exact local diff unit suite passed 13/13 for both stock runs and 15/15 for both cumulative runs. The cumulative tests retain inherited #245/#264 changes. The source gate checked the 45 previous Desktop patch hashes, seven registry dependency identities, apply/reverse checks, rustfmt, and the unchanged Copy All and surrounding file header/body source.
* Four headless probes compiled the exact per-file disabled check, hint, and callback chain, with only button and clipboard effects modeled. They tested exact CRLF, UTF-8, interior skipped wrapper lines, a final line without a newline, consecutive plain headers, Git binary metadata, and metadata-only/empty cases. Old and new callbacks for duplicate paths or different indices wrote their own exact bytes and stopped propagation. Retired parsed files were released while old copy callbacks remained callable. Repeated clicks still produced independent owned strings.
* Across twelve synthetic header rebuilds with a 50,589-byte patch and no clicks during the counted interval, the copied raw payload fell from **607,068 bytes to zero**. The isolated callback seam received **24 to 12** allocation requests (607,356 to 96 requested bytes, including the modeled callback box). This is not a measurement of total viewport or application allocation.
* The eight fresh Cargo JSON artifacts (four unit binaries and four callback probes) bind the exact manifest/source paths, locked inputs and before/after executable SHA-256. The callback behavior trace matches byte-for-byte across all four probes.

## Reproduce

From this directory, run `sha256sum -c SHA256SUMS`. Use `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` for the exact source checks without building. Use `--run` with a locked offline warm cache/target and shared compiler lock (`CARGO_HOME`, `CARGO_TARGET_DIR`, `R89_BUILD_LOCK`, and a fresh private `R89_RAW_CARGO_DIR`). The verifier runs one Cargo job, checks minimum disk reserves, caps additional disk use and does not fetch dependencies. `unit-results.log` contains timing-free unit output, `behavior.trace` and `work.log` contain the probe outputs, and `cargo-provenance.json` binds each output to its executable.
