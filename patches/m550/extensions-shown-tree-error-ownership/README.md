# SDK: show the prior view on error without cloning its tree twice

A non-content extension failure displays a notice above the last successful
root. The host previously made one deep copy into the fallback children, and
then another while serializing those children into the JSON Value envelope.
Temporarily move the exact prior root into the envelope used by synchronous
send, then restore ownership before returning. No extension callback occurs
between the move and restore. The testing sink still records a Value copy; the
real writer serializes the original tree by reference. A missing prior root
still differs from an explicitly shown JSON null.

Error and success envelope equality, original prior tree identity,
source revision, session, action sequence, close/reopen and `is_shown`
semantics are preserved. The content-error branch still emits no prior root
and keeps all original error fields. No validation, protocol, cache policy,
dependencies, HTTP policy, or limits change.

**Base:** exact 151-file Extensions M376 native input archive, after #615.
All 151 input bytes/modes of the original local stock (M372 plus read-back
#615) match the independently verified M376 archive. Only
`sdk/src/host.rs` changes. Full pin, patch, exact source blobs and lock digest
in receipt.json.

**Verified** using Rust/Cargo 1.95.0 x86_64 Linux, original locked vendor:
71 original SDK unit tests + 19 original Analysis unit tests + one SDK
doctest per arm. A real Analysis process with a synthetic loopback read-only
report server returned eight byte-identical native protocol frames (8,086,057
bytes, SHA-256 `b2f82b2e65b2ace748c2614dc94481aab6a8ec45fa7f992ee1cdf7dc7d2826cc`).
The sequence checks a large complete panel, two invalid actions with distinct sequences,
server-reported rendering failure, successful refresh, close, a
cold error with no prior tree, and an independent content-error with revision.

Native allocator proof on the SDK helper's test sink: for a 1,215,000-byte
retained text, requested bytes at the first repeatable failure go from
3,655,186 → 1,222,799 and allocation requests (excluding reallocations)
from 137 → 100; the second repeatable failure shows the same two body
copies eliminated, and the content-error control remains 2,238 bytes in both
arms. Both failures preserve the exact allocation pointer, bytes, and old
root rather than nesting previous error notices. These are caller-thread
cumulative allocator requests, including the one intentionally cloned test
capture. No claim about live heap, process memory, wall time or Desktop GUI.

**Reproduce** from the exact M376 inputs with Rust/Cargo 1.95.0, a verified
off-line Cargo source, and loopback available:

    python3 proof.py --baseline /path/Extensions-M376-native-inputs.tar.gz       --vendor /path/vendor --work /path/scratch

Only source.patch is the product change. Temporary proof restores all 151
input bytes and modes after reversing candidate, checking the Cargo lock.
