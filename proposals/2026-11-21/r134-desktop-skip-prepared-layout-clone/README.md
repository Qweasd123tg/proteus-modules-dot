# Desktop: skip the fallback layout copy when startup was prepared

## Product change and boundary

The window cloned its saved `ChatSpaces` before checking for a matching
startup-preparation receiver. A buffered reply uses the deferred before-paint
update; a matched pending/closed receiver uses the existing async wait/error.
Neither needs a second complete layout snapshot. Make the copy synchronously only
when the existing receiver match failed or there was no preparation. The pending
task placeholder is a default empty inline pane with empty collections and is
never passed to fallback boot. No change to receiver lookup, try-receive,
deferred-vs-spawn order, closure options or drop of unmatched receiver, async
result/error handoff, or underlying boot work. The assertion is about each state
at the scripted poll; no claim that real first paint always sees the same race
winner. Making less work precede `try_recv` can move the observation earlier.

`Self::empty` only borrows `spaces` for the active-layout clone and clones it
for the window-group registration before moving the same value into
`Workspace.spaces`. The fallback pulls that original value's exact copy
before spawning, never rereads window state after a yield. The two other
layout/registration copies are still present. This is a multi-root restart
change, not a 50,000-message first-start change.

## Focused gate

- Exact Desktop pin `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and exact
  cumulative Desktop through #449. Hash every Desktop predecessor; only
  the relevant real `proteus-tabs` overlays #440, #444, #449 apply above
  the verified sealed M150 anchor. No complete M200/native assembly.
- Compile exact `Workspace::new` and `Preparation::for_workspace` from
  the pinned product files and the real `proteus-tabs` closure with 11
  pinned dependency identities. App/UI/context operations, mailbox,
  preferences and boot are deterministic inert model boundaries, not a
  real backend or GPUI. The exact changed clone expression is also lifted
  into an isolated same-thread allocation/requested-byte probe.
- Check all ordinary real tabs unit tests and four focused tests in four
  arms. Ten byte-equal schedule/result records cover buffered and delayed
  Ok/Err, already-closed and delayed-close, dropping a pending task,
  absent/wrong workspace preparations, and fresh fallback. Real 72-tab
  fixtures contain four rooted areas plus loose tabs. Ordinary loaded
  measurements use a deserialized snapshot; populated MRU/closed history
  is a separate in-memory stress/control. Compare derived equality and
  full JSON/Debug for fallback; mutate the live tree before polling to
  prove capture was not delayed. Fresh/empty and unprepared measurements
  are controls. Positive allocation claim is local to the omitted
  copy, not whole startup time, RAM, PSS, or a native session.
- No native process, actual app startup, Core backend, network, model,
  terminal, PTY, or graphics execution. Run only on separate explicit
  sole warm admission. See the runner's exact compiler and cache pins,
  common lock, one locked offline Cargo job, 512/256 MiB floors plus
  32/8 MiB prelink reserves and 200 MiB maximum drawdown.
