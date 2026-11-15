# Independent fresh-source review: Desktop cleanup pair

Verdict: **no blocking source issue found** in the two bounded patches on
Desktop `816cdc0b5017d0881ec0baea1edf017ce61cce93`.
**SOURCE ONLY: NOT COMPILED / NOT RUN.** Neither patch adds tests. This review
executed no Rust/project code, compiler, formatter, renderer process or GUI.

Reviewed patch SHA-256:

- `desktop-singular-reply.patch`:
  `afadde195e5e6d6c6d48e6a24e6509e8bd9d582895135a27e3cbaeb80def18e4`
- `desktop-shared-surface-adapter.patch`:
  `d47a052808842e3390cfd6885f72a88b4621ff6798a09062b40d515c2150e047`

## Freshness and verification scope

Independently recomputed the Git blob identities of the three current patch
preimages and AGENTS.md, matched them to the supplied fresh tree, and checked
their identities through pinned GitHub file reads. The reply patch is byte
identical to the previously reviewed patch. The adapter patch differs only in
hunk positions. Both delivered batch patches match the reviewed fresh bytes.

The earlier review inspected ownership and call paths on `7eaf70c`. This is a
bounded fresh revalidation, not a new full-repository audit. The fresh tree
preserves the previously inspected DeclarativeView, SurfaceView, Host,
RuntimeScope, ContentView, Activity, popup, Chat and thread source identities.
Two relevant neighboring files changed: current runtime/scopes.rs and
chat/pump.rs were fetched, hashed against the fresh tree, and compared. The
former adds initial navigation announcement handling; the latter rearms sent
images after reconnect. The inspected rehost and reply-retention paths remain
unchanged. Fresh indexed code search still returns the one replies.parts call
in thread.rs. Search coverage is not an execution guarantee.

Independent `git apply --check --whitespace=error-all` and zero-fuzz patch
application succeeded for each patch individually and for both combined
orders. All reverse applications restored the exact baseline bytes; the two
combined results were identical and matched the supplied candidate source
files. These are artifact checks, not compile or behavioral tests.

## Source judgment

`Replies::parts` previously returned exactly one Part on both creation and
reuse. The singular return and updated thread caller preserve that invariant
without the temporary one-element Vec. Renderer/language checks, source
updates, retained Entity/Arc clones, subscriptions, readonly routing, eviction
and rehost remain unchanged. The single child retains the same variant
conversion and plain-text row identifier. This removes an unnecessary source
allocation construct and clarifies cardinality; it is not measured evidence
of lower application latency, RSS or CPU. The diff is +14/-16 lines.

The adapter extracts identical wrapping from three factories: ordinary,
embedded production, and isolated settings/preview. It clones the same focus,
transfers the strong Entity into SurfaceView.view, and captures only a weak
Entity in the rehost callback. Runtime selection, isolation, embedded flags,
deferred attach/detach and rehost behavior stay outside the helper and are
unchanged. The paths remain panels/documents/pages/popups, Activity details,
and settings/preview; typed badge summaries and ContentView have different
wrappers and are correctly excluded. The benefit is one maintenance point,
not merged runtimes, fewer processes or a memory bound. The diff is +8/-18.

## Existing registry and adoption boundary

The fresh declarative module already contains the live-runtime inventory
previously proposed in PR148, including factory registration and reload
enumeration. **Do not apply that old registry patch again.** The adapter leaves
those functions unchanged. The old two-order PR148 composition check is
historical evidence only; this review instead applied the cleanup pair to the
current, already-integrated source. No claim about qualification of upstream
registry or navigation changes follows from that successful text application.

Risk is low at the inspected source level, but native behavior is unverified.
Before production adoption, compile and run focused tests on the full current
checkout, then exercise reply reuse/renderer changes/eviction and surface
focus, repeated open-close, isolated settings/preview and window rehost.
Existing or proposed PR148 tests were not run and cannot be counted as tests
of this pair. This verdict covers only these Desktop patches, not the entire
batch. No publication or upstream modification was performed by this review.
