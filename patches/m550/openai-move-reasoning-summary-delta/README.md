# Move a parsed OpenAI reasoning-summary delta into its event

The dispatcher owns its parsed envelope. Transfer the string for both
reasoning-summary aliases and keep the surrounding handling, tool identity,
and terminal output unchanged. Empty strings still emit an empty event; an
absent or non-string delta remains ignored.

Apply to exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`, already including #831. Strict
indexed apply and reverse passed; both optimized native model-pack
libraries and 24 focused tests per arm passed.

For each alias, the synthetic 86016-byte decoded string used one fewer
allocation request inside translation. Empty controls did not change.
No live provider or whole-app memory/latency measurement.
