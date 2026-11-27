# Copy only the exports used in inherited model scope

Keep the same model-only binding projection, but construct it directly at
the original exports key position instead of copying an entire exports map
and immediately replacing it. Root exports, nested launch fields, model
value shapes and the existing validation order are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 92 targeted release tests per arm.
The standalone model-only fixture saves 17 allocation
requests, and the small mixed fixture saves 73 requests
and 12,932 cumulative bytes. The empty profile control is
unchanged. Ordered JSON matches on all prepared inputs including actual
checked-in Codex and Codex Task TOML after parsing (no subprocess started).
Coexistence with earlier Core configuration patches through #924 checked.
This measures local normalization, not product startup or PSS.
