# Core: keep profile target selection outside the atomic writer

Base: `Proteus-harness/Proteus-core@550603155239238fdf73777d53d77f327d1e7a71`.

Settings snapshots and config-builder operations call the same target-path rule from the existing path helper module, not from atomic persistence. The rule is unchanged: directory aliases keep their spelling and append the overlay filename, file aliases resolve the physical file before restoring any role suffix, and a missing target keeps its original spelling. Write-lock keys and persistence are unchanged.

Verify with `sha256sum -c SHA256SUMS`, and choose only one: `source.patch` for main or `source-after-stack.patch` for cumulative tree `7ea7650fa3f26bc85eda80249ccdcbfd0b6404dd`. First run `git apply --check` on the chosen patch. The receipt records exact stock and cumulative trees and four local temporary-file tests per base; no model, tool or module subprocess ran.
