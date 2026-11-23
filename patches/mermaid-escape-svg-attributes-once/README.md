# Mermaid: escape SVG attribute values in one pass

`source.patch` changes only `packages/mermaid-render/svg-theme.mjs` in
`Proteus-harness/Proteus-desktop-extensions` at
`f3adb160083161a2e5db1ee720160c04cd1d212e`.

One fixed character class plus a fixed entity lookup replaces four literal
passes over each emitted attribute value. Only `&`, `"`, `<` and `>` are
replaced, exactly as before, and replacement text is not rescanned. Existing
entities, apostrophes, Unicode and control characters retain their old byte
behavior. Parsing, attribute and style ordering, variable/error paths, limits,
renderer, wire framing and permissions are untouched. This is independent of
#480's attribute-fragment change and #475's stdin framing change.

The existing Node suite passed **12/12** in all four lanes: stock/candidate,
each with and without #475 + #480. Exact paired checks covered 7 direct
escape controls, 5 SVG fixtures, 8 failure cases, 10 real Pele renders across
two themes and 15 byte-identical JSONL replies in each lane. The exact vendored
Pele 1.12.0 file was used. Both lanes passed no-fuzz apply/reverse readback.

## Scoped Node 24.22.3 evidence

In one local warmed, alternating paired run, the materialize-and-byte-count
step over **168 real-Pele SVG inputs per batch** (12 generated fixtures repeated)
won 10/10 pairs in each tier:

| Tier | Stock median | Candidate median | Median paired delta |
| --- | ---: | ---: | ---: |
| Standalone | 89.050 ms | 80.240 ms | −9.258 ms (−10.34%) |
| With #475 + #480 | 81.366 ms | 74.053 ms | −7.572 ms (−9.42%) |

The ordinary corpus had no escapable values among 5,330 observed attribute
values. The deliberate escape-dense standalone control was about +0.5 ms per
18 materializations in each tier (under +1%); the isolated escape callback
was 14–16% slower on dense input. This isn't render generation, Desktop
latency, allocator, or RSS/PSS evidence; figures are for the local scoped arm.

For the existing native vendor tests, use a disposable local copy of the
pinned tree and run:

```sh
sha256sum -c SHA256SUMS
patch --dry-run --fuzz=0 -p1 -d "$EXTENSIONS" < source.patch
patch --fuzz=0 -p1 -d "$EXTENSIONS" < source.patch
(cd "$EXTENSIONS" && TZ=UTC LANG=C node --test packages/mermaid-render/tests/worker.test.mjs)
```

No Rust, installs, external requests, or release publication.
