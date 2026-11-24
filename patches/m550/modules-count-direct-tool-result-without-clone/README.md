# Report direct tool-result byte lengths without cloning text

The workflow’s ordinary usage report counts the UTF-8 bytes of the selected tool-result text. Read the nonempty error or output by reference instead of cloning it. Error still wins even for successful results, whitespace is still text, and statuses/compound content still go through the same renderer. The compaction estimator is byte-identical. Input history scanning, reported category values and output serialization are unchanged.

The native default-layout proof ran exact before/after Modules accounting and actual pinned Contracts. It includes five existing tests per side and one 13-fixture ABBA check. All 52 serialized usage reports matched and retained requested bytes stayed the same. The four 8,000-byte result fixture’s gross requests fell 32,709→709 bytes per report (exactly 32,000 bytes and four requests removed). Synthetic 2 MiB direct output peak fell 2,097,217→189 bytes, and direct error peak fell 2,097,217→189. The 2 MiB structured content control and other fallbacks were unchanged. These are isolated allocator-request figures, not worker/provider/network activity, whole-process memory or timing.

The original witness was revoked unrun. A separate preregistration allowed the independent final report allocation to determine candidate peak because report creation need not overlap the otherwise temporary 8,000-byte clone. All exact savings, parity and safety guards above are from the single approved native run.

The measured composed baseline includes #688. The modified hunk applies independently and inverses exactly on both official Modules main and the Modules revision pinned by Core/Desktop without #688; those full upstream source leaves are not byte-identical to the measured composed source.
