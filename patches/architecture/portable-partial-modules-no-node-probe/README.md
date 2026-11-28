# Keep the Node preflight at the full portable build boundary

Standalone Desktop patch for `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS` and `git apply --check source.patch` in the matching Desktop checkout before applying. The same patch also applies after the verified Desktop stack through #958.

A partial rebuild of the built-in modules group no longer launches Node merely to copy the opt-in hook assets. `--full` and explicit selection of all four groups still run the same Node ≥22.18 probe before copying. The copied Hook SDK comes from Core and is still verified against the Modules pin. Launchers, runtime prerequisites, DCP, release metadata and smoke checks are unchanged.

Verified 66 Python tests on a PATH without Node. Exercised the real CLI transaction and the asset copy using inert synthetic build outputs. Compared 34 files and modes against stock, and confirmed that a mismatching SDK is rejected and a failed full probe preserves the destination. No complete Rust/portable build or hook execution was performed. See the receipt for exact inputs and test hashes.
