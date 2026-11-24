# Analysis: move model disclosure text into its final widget

The model detail renderer already owns assembled instruction, request-message,
tool-name and answer strings. It used to pass each through a temporary JSON
string and copy it again into the display block. Pass ownership explicitly
instead, reusing the established compact-owned policy in the common disclosure
builder. Tight strings move; overreserved strings are still compacted.
Borrowed strings, pretty-printed JSON and empty text follow the old paths
and keep the same content, wrapping, height, keys, ordering, and disclosure
state. No protocol, validation, caches, dependency locks or limits change.

**Base:** exact full 467-entry Extensions M387 source archive (includes #627),
whose 151 native inputs each match the local M384 plus published #627
projection (bytes, modes and symlinks). Two source paths, one ownership
change. Prior #573 avoided a copy inside borrowed disclosures and #627
removed copies in page wrappers. This change avoids the remaining
formatted-model-text copy before the widget wrapper.

**Verified:** all 19 native Analysis package tests per arm, paired allocation
witness, and an additional candidate identity test for tight/loose and empty
strings. The actual Analysis process received synthetic reports from a
read-only loopback server. Its eight replies are exactly 23,527,645 identical
bytes (SHA256
`fca723aeed6d4c533423008d5fd3a3f349cf29b719489d3924c6dcd747cea5d3`).
The fixture verifies instruction, request, tool names and answer output
including Unicode, NUL, CR/LF and whitespace trimming, plus address/sequence,
failed actions and reads, successful refresh and close/reopen.

Native allocation meter around actual `details::step_card`: 20,749,325 →
17,581,282 cumulative requested bytes (exactly 3,168,043 assembled bytes
and four requests removed). The completed widget retains the same
6,923,634 net live requested bytes, and the logical allocation peak of the
whole step remains 11,116,053 bytes. The witness verifies that the raw JSON
block still emits complete unchanged source; stage-local savings are
not process RSS/PSS, a peak improvement, or a timing claim.

**Reproduce** using Rust/Cargo 1.95.0 x86_64 Linux, loopback and verified locked
Cargo vendor:

    python3 proof.py --baseline /path/Extensions-M387-source.tar.gz       --vendor /path/vendor --work /path/scratch

Only source.patch is the product change. The proof compares both native
protocol outputs and allocator counts, tests ownership policy, and reverses
all exact input bytes/modes including the original Cargo.lock.
