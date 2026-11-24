# Mermaid: allocate style scratch only when a tag emits it

The native Mermaid Node worker converts Pele styles to supported SVG
presentation attributes. The previous materializer made a Map and CSS array
for every tag, including tags with no style or only inherited aliases. Share
an immutable empty declaration list for absent/empty styles, and allocate the
extra-attribute map and CSS array only when their first entry survives the
existing conversion. Empty, ordinary CSS, local alias, repeated rx/ry and
font-size override cases still use exactly the same output ordering. No changes
to source or output limits, errors, theme validation, cache, vendor, protocol,
and no new dependencies.

**Base:** exact 151-file Extensions M362 input archive, already including
#596/#598/#601, plus #607 read back from the published head. This is the complete
native Extensions projection at M368. Only the JavaScript
`packages/mermaid-render/svg-theme.mjs` changes. Exact original/changed blobs,
archive/patch/lock digests and scope in receipt.json. The Rust binary is compiled
once in the proof, then used unmodified for both JS implementations.

**Verified:** all 12 existing Node tests in each arm, including malformed and
oversized input; 12 Rust unit + existing error integration test, skipping only
the known missing-/proc child-list case. The separate real Rust→Node renderer
test uses the actual vendored worker and checks cache/theme/addressed errors,
visual output, and child teardown. Nine real protocol replies total 8,828
byte-identical bytes. Standalone real Pele theme-materialization proof compares
26,873 identical bytes across real diagrams, mixed and duplicate declarations,
inherited/current colors, Unicode labels, escaped attributes and three exact
first-error cases.

The witness counts actual Map constructor invocations inside the JS theme
materializer; vendored rendering and result serialization are outside this
meter. The five actual Pele SVGs had counts 20→5 (branch), 32→7 (sequence),
13→4 (Gantt), 17→3 (pie), 248→44 (40-edge flowchart); mixed style
composition control 12→4. CSS arrays also become lazy by construction but
were not separately counted. These are fixture-specific logical operation
counts, not measured V8 allocations, live bytes, latency, GUI, or app RSS/PSS.

**Reproduce:** with Rust/Cargo 1.95.0, Node ≥20, the exact source archives
and the 27-package locked local vendor:

    python3 proof.py --baseline /path/Extensions-M362-native-inputs.tar.gz       --references /path/607/source.patch --vendor /path/vendor --work /path/scratch

The proof verifies both source checks and exec tests in a temporary copy and
fully reverses the production patch. Test-only proof files are not product
changes. The recorded run used Node v24.22.3.
