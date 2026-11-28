# Modules: one bounded filesystem read for the two context decoders

Base: `Proteus-harness/Proteus-modules@b476a8cca8f0906455753014622d8fbdc08e7899`.

The two bounded workspace readers now share one private function for canonicalization, workspace checks and the bounded byte read. Both retain their existing decoding semantics. One replaces invalid UTF-8; the other returns a valid prefix and charges all bytes read, including the start of any truncated character. No change to path admission, the caps, error handling, or the instruction budget.

Verify with `sha256sum -c SHA256SUMS`. Run `git apply --check source.patch` in Modules before applying. One diff verified forward and backward on the exact stock and cumulative trees, and four focused native tests per base with synthetic temporary files only.
