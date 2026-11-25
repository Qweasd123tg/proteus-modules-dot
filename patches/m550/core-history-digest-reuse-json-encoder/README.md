# History-scale verifier: reuse the message JSON encoder within each digest

Keep one configured JSON encoder local to `message_digest` instead of creating one for every row. Each row is still serialized independently with the same character encoding, key order, separators and length-prefixed hashing. No cache or state is shared between digests.

In a synthetic 50,000-row digest, encoder constructions fell from 50,000 to one. All 50,000 serializations remain, and the digest agrees byte for byte. An empty digest now constructs one encoder instead of none. This is post-measurement fixture verification, not product history loading; it does not show an application latency or memory change.

Use the owner patch on the exact blob in `receipt.json`. If the file instead matches the exact postimage of scoped #781, use only the alternate in the receipt. Never apply both or reapply already integrated #767/#777.
