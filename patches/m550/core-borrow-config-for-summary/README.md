# Borrow snapshot config for the configuration summary

The reader already owns an immutable runtime snapshot. Borrow its AppConfig
instead of deep-cloning it before building the local or discovered summary.
This keeps the same epoch and data source and does not hold the runtime
state lock through a catalog request.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 107 targeted release tests passed per arm.
The fake-catalog picker still shows configured defaults locally, without
starting discovery, and preserves both provider routes in the discovered
summary. Local summaries match across arms after normalizing only fixture
paths. With no extra instructions this removes 164 allocation
requests and 24,230 cumulative requested bytes per fixture read.
The 64 KiB inline-instruction control removes 89,822 cumulative
requested bytes without returning that instruction in the summary.
The patch also passes strict apply and reverse checks with the preceding
configuration and replay stack. This does not measure process PSS or
whole-app startup.
