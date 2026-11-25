# History-scale verifier: compare canonical journal prefixes in chunks

After the agent-control measurement, compare the original synthetic seed journal with the corresponding prefix of the case journal in 64 KiB reads. A changed or truncated prefix still fails; bytes appended after the original prefix do not affect this check and still go through the existing active/replay checks. The other digest and preflight paths are unchanged.

The seed is the stable private benchmark fixture, not a concurrently changing user journal. If the prefix is already unequal, the verifier may report it without reaching later bytes or encountering an unrelated later I/O error. No failures are accepted.

This bounds working storage for the prefix comparison in the post-measurement Python verifier. It does not change or measure Proteus memory, startup, cold or warm history loading, or native replay. See the receipt for synthetic evidence.
