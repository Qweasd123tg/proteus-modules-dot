# Reuse the Mermaid palette field table

Keep one module-private ordered table of the eight palette fields and their
complete SVG variable keys. The installed worker no longer builds a keys array
or an entries array of eight pairs each time it prepares a valid theme. The
snapshot, input checks, field read order, color/variable insertion order and
rendered SVG stay the same. Cache hits are unaffected.

Apply only one variant, on an exact matching tree and checked source preimages
in `receipt.json`. Use `source.patch` on the exact owner basis. If the authenticated
scoped #789 is already applied, use the alternate below. #796 is an independent
verified worker companion; the receipt lists its exact tested trees as well.
Do not infer applicability to other combinations from patch context alone.

```sh
jq -r '.selection.after_789.patch_base64' receipt.json | base64 -d > source-after-789.patch
```

On the exact packaged Node worker files and vendor bundle (Node v24.22.3),
all 8 selected tests passed on each candidate basis, versus 7 on stock.
In each of four exact stock/candidate configurations, twelve wire replies and
fifteen direct comparisons matched exactly, including valid themes, alternate
colors/fonts, getter order, and rejected inputs. The tracked test is copied
into the package recipe, so raw source grows by 1,824 bytes. No packaged app
build, end-to-end speed, heap, RSS, PSS, or compressed package-size claim.
