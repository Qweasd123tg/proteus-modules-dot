# Reuse the terminal record of a pinned SQLite snapshot

The backend's open read transaction pins the data. Capture the terminal
record while validating the whole prefix, and reuse it only after the
existing backend confirmation. The digest, checks, budget and response
contract stay unchanged. This does not enable reuse for JSONL sources
whose external payloads cannot be confirmed.

Exact Modules `5377853779ae499b03ff152b97eb1c11eaa64ed2`; full-index apply and reverse verified.
Two unmasked optimized storage libraries built. In scoped native tests
116 passed and one was ignored on each arm. The first read of the last
record from a pinned eight-record snapshot used 8 decodes instead of 16,
even after a newer append. The old and fresh handles returned their
respective views; retry and nonterminal controls unchanged. No whole-app
latency or RAM measurement. This patch targets current Modules directly,
not the older #853 historical-conversation variant.
