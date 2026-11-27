# Keep persisted model-context observations owned by the read view

Store persisted context as the vector it already is. View construction
moves it, incremental saving can borrow it, and the two runtime recovery
paths build the same execution tracker only when they install live state.
Cache schemas, observation order and journal validation stay the same.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. In the nonempty context fixture the direct view
reuses the original vector instead of copying it. The 4,096-element
fixture avoids copying 65,536 bytes of vector contents (not a peak
memory or startup latency measure). Cache read-back matched exactly.
Both release arms passed 33 targeted view, clear, resume and journal tests.

The prior #906 patch operates on the separate usage field and composes
with this change on the same source base. For strict full-index tooling
after #906, replace only the `view.rs` index line with the one in the
receipt; the hunks are unchanged.
