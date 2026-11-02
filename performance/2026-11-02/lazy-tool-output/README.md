# Lazy full tool-output construction

Source-only candidate for Proteus-harness/Proteus-desktop at `da07942cf91cfec20940fcc5a7cea2c18792f84b`.

## Change
Long tool results and subject arguments keep their bounded preview, but no longer clip and build the full text element while “Show more” is settled closed. The common preview_reveal helper accepts an immediately consumed FnOnce builder, samples animation progress once, and constructs full content only when open or animating. All four call sites adopt the closure signature. Existing guards in settings, textarea and plain-code remain unchanged.

No cache, retained-state policy, source lifetime, output limit, preview label, copy action, theme or element ID is changed. The content wrapper remains present with the same ID even when its child is omitted. Opening, closing and reversal still construct both endpoints for measurement. Full text is not retained in a new closure: the closure is called or dropped before preview_reveal returns.

## Source evidence
- tool_row.rs:155–174 and 233–243 previously built both bounded preview and full clipped content eagerly.
- tool_row.rs:351–361, 380–384, 435–436 builders construct code surfaces and SelectableText; no registration, notification or persistent state mutation.
- motion/reveal.rs:148–155 selects Flow::Preview at settled-closed state; its prepaint/paint branches do not touch the full child.
- The full clip limits remain 400 lines / 40,000 characters. Counting lines for “ещё строк” remains; this is not a whole-input scanning removal.
- Four callers were located by pinned GitHub code search: tool_row, settings/editors, extensions/declarative/fields/textarea, extensions/declarative/plain_code.

## Validation boundary
Baseline Git blob hashes match the pinned upstream files. Patch forward application exactly reproduces after/; reverse application exactly restores baseline/. Whitespace checks passed. Direct rustfmt 1.95.0 with edition 2024 and skip_children=true parsed/formatted all five changed files; its subsequent --check passed. These are static checks, not compilation or behavioral tests.
No project code, project scripts, tests, Cargo, build, CI or GUI was executed. No latency, RSS/PSS or application-wide improvement is claimed. Compilation and actual open/close/reversal, selection, copy and error styling remain runtime validation work for the owning checkout.

Apply from Desktop root: `git apply lazy-tool-output.patch`.
This artifact does not modify upstream automatically.
