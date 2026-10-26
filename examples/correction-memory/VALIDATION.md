# Experimental raw-compatible correction memory

This public candidate contains **69 authored Rust tests, all uncompiled/unrun** at
initial publication. The historical 58-test revision refused normal retained raw
arguments; it is not this 69-test candidate and has no borrowed runtime result.

SDK/Core pin remains `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`; `rusqlite =0.33.0`
with bundled SQLite and `ring =0.17.14` remain fixed. The evidence-spans dev
dependency has unchanged Rust/Cargo/helper bytes; only its relative public path
changes to `../evidence-spans`. No real Core invocation is included.

An earlier offline lock resolution failed because rusqlite was unavailable. The
first experimental hosted phase generates a lock, records the lock plus locked/offline no-deps package metadata,
and stops **without compile/tests**. The resolved lock must be separately reviewed
and committed before a second locked/offline runtime gate. Failure remains failure;
no pin relaxation, dependency replacement, implicit lock regeneration, user database
or upstream suite is allowed.

The later intended gate covers 69 exact Rust names, including six own-binary wire
cases plus one pure framing helper. SQLite/callback/module/restart cases remain
separate from actual Core authorization/routing, which is not exercised.
