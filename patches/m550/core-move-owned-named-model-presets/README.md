# Move owned named model presets

The normalizer already owns the parsed named-model map. Consume its entries
and move the owned profile/reasoning maps and alias keys into the existing
normalization path rather than clone them first. Validation, error order,
alias ordering, output and the legacy providers route stay unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`; 92 targeted release tests on each arm.
The two rich synthetic presets saved 48 allocation requests and
3,748 cumulative bytes. The 128-preset synthetic catalogue saved
3072 requests and 240,164 cumulative bytes. Empty
catalogue allocation unchanged, exact typed catalogue hashes match. The
isolated empty-call timer was about 2–3 ns slower; nonempty controls improved
in both timing cohorts. Applies and reverses
alongside #916–918. Local helper measurements only, not startup or process PSS.
