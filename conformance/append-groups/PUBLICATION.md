# Experimental CI composition — 2026-10-26

This package preserves its reviewed source-only precursor and historical status text unchanged. This supplement records the later public-path composition, not a runtime success. The package is standalone (`[workspace]` and no local path dependencies); PR1 is the comparison base only.

Repository: `Qweasd123tg/proteus-modules-dot`. Base: `29d31fb36397008b7677cd5df4943031e24e8fdf` (`dot/harness-inspired-rust-examples-20261025`). Experimental branch: `dot/append-group-probe-20261026`.

Only the workflow and this scoped conformance package are added. No main merge, deployment, parser replacement, upstream test suite or production data is involved. The original source and lock stay byte-identical. Hosted CI must retain exact-head evidence before any runtime conclusion.

The seeded lock must resolve through `cargo fetch --locked`; no lock regeneration is permitted. The gate then requires 29 actual Core children plus 40 separate helper controls. Groups change atomicity and durable visibility even with identical final history; results cannot support a general speedup or relaxed intent/effect barriers. Requested allocator bytes are not RSS or copies.
