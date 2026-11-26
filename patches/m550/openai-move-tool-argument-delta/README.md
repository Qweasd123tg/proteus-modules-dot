# Move parsed OpenAI argument deltas into their events

Transfer only accepted argument strings for both function and custom
tool streams. Keep call ID mapping precedence and exact payload bytes,
including whitespace, and suppress absent, non-string or empty values.

Apply `source.patch` on exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`, already
including #831. If #847 is already selected, use only the embedded
`after_847` alternate from `receipt.json`. Do not apply both variants.
Strict indexed forward/reverse checked. All four unmasked optimized
native libraries built; 24 scoped tests per arm.

Each alias used one fewer request (exactly 86016 bytes for the large
synthetic fixture). No live model, tool execution or whole-app claims.
