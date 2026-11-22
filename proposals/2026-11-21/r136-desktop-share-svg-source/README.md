# Desktop: share decoded SVG source with image cache keys

An accepted SVG originally owns a decoded String in a widget node; image
preparation clones the text into its transient liveness set and allocates
a separate complete copy in the parsed cache and raster-key family. Move the
exact decoded String into one immutable shared handle, and clone only the
handle in those existing places. Keep textual equality, hashing, borrowed
str lookup and Debug formatting. No global interning or new retention table.
Separately decoded identical roots may still retain two backings when an old
equal key is reused. Untouched image parse/dimension/lease/error decisions and
size charges use the exact original UTF-8 bytes, not pointer identity.

The extra Arc control allocation happens at decode, even when there is no
cache/paint or the view is rejected later. The retained result applies to
newly parsed nontrivial diagrams; a tiny SVG can instead pay a small fixed
overhead. To test that tradeoff without mapping or claiming native RSS,
we require scoped requested-live and allocation figures for the original
decode, first prepared medium source, equal re-decode, tiny source, inert
renderer error and owner release. We require ordinary positive results
on both exact bases, no material retained regression on tiny or equal
re-decode, and actual one-backing pointer proof. Direct production wire is
decoded from serde_json text buffers; the stock root release must correspond
to exactly the source's requested bytes on the normal medium case. Keep
accepted byte limits and source-lifetime rules; this is not a source
capacity, process-memory or renderer-memory budget change.

## Admission and proof

- Exact pinned Desktop b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and
  cumulative selected Desktop through #451. Verify 64 predecessor patch
  identities and sealed anchor. Only the six overlays intersecting this
  tiny source projection need actual application; #451 is disjoint.
- Execute real serde Node and real selected Incoming decode and parse
  with its pinned Core Settings DTO, actual XML validator, diff crate,
  asset preparation/cache/raster lookup and cache-only/resolve effect,
  geometry and primitive cache bounds. Assert native widget sizing, cache,
  paint/lease and error/acceptance source spans unchanged. The native SVG
  renderer, bitmap and icon inventory are deterministic inert boundaries;
  only controlled synthetic data, no native renderer, GPU surfaces,
  subprocess, extension executable, network or untrusted SVG is used.
  Route invalid JSON and inert invalid XML only through genuine validation,
  never through a render. Exact layout/error/text traces must match in all
  four arms; savings are branch-local requested allocations.
- Locked Cargo with 13 registry crate identities, real Diff source from
  each arm, serde default map mode. No full registry copy or mutation:
  when separately admitted, initialize a fresh private Cargo home from
  only 13 archive/index pairs and the pinned registry config. The verified
  inputs total 2,720,290 bytes before Cargo extraction; exactly one new
  needed XML archive comes from the independently pinned existing offline
  cache. Use the inherited warm target but budget for recompiling the
  small closure if private paths miss reuse. Same shared build lock,
  one offline locked job, 512 MiB available target/workspace and 256 MiB
  separate temp floors, +32/+8 MiB prelink reserves and 200 MiB drawdown
  cap, exact compiler pins and no competing runtime.
