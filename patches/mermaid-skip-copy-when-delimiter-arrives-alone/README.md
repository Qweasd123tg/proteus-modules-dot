# Mermaid: reuse a buffered frame when its final chunk starts with LF

When a request body is already buffered and LF is the next input byte, the
ending chunk contributes no bytes to that frame. Decode the pending buffer
directly rather than copying it with an empty suffix. Non-empty fragments,
empty lines without pending data, and the existing complete-frame path are
unchanged. So are the byte guard before decoding, CR and UTF-8 handling,
request ordering, error replies, and the pending/start reset.

This is **one logical patch with two mutually exclusive files**:

- Use `source.patch` on unpatched Extensions
  `923077d3967ae7063a6556bc378c09f97abc2854`.
- Use `composed.patch` after #475. It is also verified after #475 → #480 →
  #482 → #489 → #494. **Do not apply both**, and do not apply #475 after the
  stock variant without rebasing their shared framing hunk.

Both variants change only `packages/mermaid-render/worker.mjs`; zero-fuzz
forward/reverse replay reproduces the exact six-file worker closure for each
of the three supported preimages.

## Verification

- The exact shipped tests using vendored Pele 1.12.0 passed 12/12 in each of
  six arms: before/after on stock, after #475, and on the full selected chain.
- Eleven deterministic framing layouts per pair preserve raw JSONL, stderr,
  and exit status, including coalescing, split UTF-8, exact caps and EOF. Ten
  additional real Pele renders across two themes and 15 raw JSONL replies
  agreed across stock and fully selected arms.
- In the isolated-LF witness, a 3,732-byte Unicode flowchart request body has
  already been buffered when the one-byte LF arrives. Each variant removes
  exactly one assembly concat of those 3,732 bytes. The same holds with an
  immediately following sibling frame and with a pending CR preceding LF.
  A nonempty final fragment, entire frame in one chunk, and blank LF with
  no pending body show unchanged assembly counts in each pair.

This is structural evidence at the changed copy site, not a benchmark of
framing, memory, native Desktop, or installed portable launch.
