# Desktop: share immutable rooted tab layouts across window snapshots

One production patch against exact Desktop M406. Workspace startup
copies restored preferences, owns its active layout, and registers a
window snapshot with the window group. That used to copy every
inactive area's pane tree each time. Preferences and persistence
also copied the same trees. Keep rooted layouts behind an internal
`Arc<TabLayout>`, and detach an area before mutating it. Public
`ChatSpaces` methods still take and return the same types. The
unrooted layout remains inline; startup still takes a separately
owned active layout. `serde/rc` serializes the existing layout
object, so saved preferences need no schema or migration change.

## Native evidence

The full native headless `proteus-tabs` crate is exercised against
Desktop's pinned Cargo closure. The test replays the ownership
operations at `Preferences::spaces_for`, `Workspace::empty`,
`WindowGroup::register/persist` and the preferences writer, with
those exact call sites pinned. It does not build GPUI or claim
process startup or PSS.

Results are identical in default and insertion-order JSON modes
(74 stock / 75 candidate tests per mode):

| Scoped owner chain | Stock net bytes / requests | Candidate net bytes / requests |
| --- | ---: | ---: |
| First window, saved 64 rooted areas × 24 documents | 468,084 / 4,665 | 16,396 / 185 |
| First window, one saved rooted area | 8,280 / 51 | 2,200 / 21 |
| First window, empty saved workspace | 0 / 0 | 0 / 0 |
| Live republish, 50 areas plus visit and closed-tab history | 771,450 / 8,127 | 15,696 / 177 |

For the 64-area decode in isolation, the candidate requested
260,380 cumulative bytes versus 255,452 and retained 231,196
versus 237,020. The Arc headers do change allocation grouping.
The first actual rename after sharing detaches only the selected
root: its isolated net increment changes from −153 bytes to
+4,797. Copy-on-write delays the work, so an all-area cleanup
may still copy every shared area; the table does not claim a general
edit or deserialize speedup.

The saved JSON bytes, root/pane/focus/preview/pins, hidden child
context, closed stacks, mutator callback order, and results of
overlapping window merge, cross-area delete and rename are checked.
Detached roots still retain ownership without reopening their chat.
`composition.json` proves exact M406 inputs and inverse; #648
commutes in both orders. No changes to Core, Codex driver/Node,
graphics, app-server or authentication.

Run with the pinned Rust toolchain and a verified vendor directory:

```sh
sha256sum -c SHA256SUMS
python3 verify.py --vendor /path/to/vendor
```
