# Session-projection benchmark: measure the snapshot wire bytes without encoding twice

The documented synthetic snapshot uses printable ASCII values. Encode it once for the private renderer transport and report the number of payload bytes before checking or writing to the peer, as before. The framing newline is not counted. If the peer has already exited or writing fails, the partial report still contains the snapshot size. Unmeasured calls keep their existing poll, audit and encoding order; the redacted event format, nonblocking writes and deadlines are unchanged.

This affects the synthetic session-projection benchmark, not renderer protocol admission, startup time or memory in the application. The full case sends three independent snapshots of 4,195,666 bytes (plus framing) each. The fixture dropped from six full encodes to three; the bytes sent and the redacted trace still match. Proof checks actual Python driver and transport control flow with inert local peers. Only test-source fingerprint fields are normalized for report comparisons.

Apply `source.patch` to the pinned Extensions revision.
