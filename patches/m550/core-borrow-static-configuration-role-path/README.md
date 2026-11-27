# Borrow the fixed configuration role path

Configuration source projection and the parent model-choice fallback use
two named object lookups instead of decoding the same literal JSON pointer.
Both preserve role order, empty versus absent data, and exact choice and
inheritance behavior. Mutable source selection and catalogue ownership are
unchanged. The patch applies in either order with Dot #916.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`; 92 targeted release tests on each arm.
On the synthetic nested source the projection used 12 fewer allocation
requests (136 fewer cumulative bytes); parent-choice fallback saved four
requests, and direct child choice was unchanged. This is a local source
helper measurement, not full startup or process memory.
