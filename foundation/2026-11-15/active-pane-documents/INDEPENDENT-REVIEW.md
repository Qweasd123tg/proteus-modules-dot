# Independent source review

## Design boundary

The common per-context projection is justified for the known focus-versus-split gap, but logical active panes and actually mounted tab-area visibility are different contracts. The prototype deliberately chooses the former, retains focused event.document, and does not promise zero reads under Settings/occlusion. The displayed-space and extension-ownership filters, whole-list replacement including empty, initial context bootstrap, context-local ownership and shared session cache are essential.

## Exact candidate review

Reviewed patches:

- Desktop: `cd54347ee4896f9912a502d29aab6721d524d001aa103b57a94e941567aac597`.
- Extensions: `85cb64b8739cfc60e70fbaf5b31fb1d2b696df8e340123627fccf50357afad3d`.

No blocking source defect found. This is approval as an **uncompiled source proposal**, not production/runtime qualification.

- Paired projection preserves the old native lifetime/displayed-space gates and focused semantics, reading the same layout once.
- All three inspected event producers and the existing event test literal are updated.
- SDK moves the Vec between contexts, not sessions. Two local resets prevent inheritance of the new field without changing existing routing or focused-field behavior.
- Files changes only cached-refresh eligibility. Cold reads, invalidation, shared cache keys and the polling schedule remain as before.
- Four layout and five SDK controls look consistent. They do not execute native Host gates/bootstrap or real native rehost.
- wire.py only adds the advertised feature, not a complete producer model of the list. Do not call it wire qualification.
- Renaming the native helper means the old PR146 extracted harness must be updated separately; DESIGN-DECISION records that caveat.
- Costs include strings/Vec per event, per-context storage, membership scans per cached render and more eligible reads, including under Settings.
- A present malformed list returns a deserialization error; an absent field is empty. This typed contract does not fall back to focus.

The reviewer did not edit files, compile or run code/tests/native UI.

## Closing prose review

Confirmed REPORT.md `3a828cd6fd258fc7615bc0ad216de99724a43d32cd21aaf237908e479540f98f`, DESIGN-DECISION.md `ecb98d9827e0c1040e19b07a10d08bbceeb5b9b3ba98ce2ef4442f02e67dee71` and README.md. No corrections required. Logical projection is not represented as actual visibility; grouped reads, Settings, old focused cleanup, feature gating and PR146 dependency remain appropriately limited. All new and adapted controls are NOT COMPILED / NOT RUN. This check ran no project code.
