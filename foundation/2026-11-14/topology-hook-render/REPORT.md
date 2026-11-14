# THR-1: full topology Mermaid labels a selected hook chain as missing

**P3, diagnostics only; independently source-reviewed.** Hook execution is not shown to fail. The canonical topology snapshot retains the selected chain. No Rust, Proteus, provider, fixture, CLI, HTTP server, Mermaid renderer or UI was executed. No production modification.

Baseline: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. Source hashes were verified; raw artifacts are not included. Rust toolchain remains unavailable.

## Contract and ordinary reachability

`docs/guides/inspect.md:3–6,36–44,58–62,69–79,218–223` presents topology as the graph of available/selected modules and connected tools, with a full Mermaid export and a separate shorter runtime view. This finding concerns a false absence label in the full view, not a demand that the diagram prove runtime invocation of every configured hook.

An ordinary configured nonempty hook chain is sufficient. For example, supplied `configs/opencode.config.toml:8–12` selects `opencode_prompt`, then `opencode_compact`; supplied Codex fragments also select hooks. No malformed configuration or custom invocation is needed once such a profile is successfully assembled.

* CLI `inspect topology --format mermaid` routes through `main.rs:383–395` to `render_topology_mermaid`.
* HTTP `GET /inspect/topology.mmd` routes through `app_server/http/reads.rs:111–116` to the same function, after `AppServerHandle::topology_snapshot` builds the snapshot at `app_server.rs:246–256`.
* `GET /inspect/topology.runtime.mmd` uses a different, hook-aware renderer and is a useful control.

## Source cause: singular-selection assumption at one projection boundary

1. `core/core_slots.rs:24–32` declares Hook as `pipeline` and `OrderedModulesConfig`. `ModulesConfig::iter` (`core/config.rs:401–405`) deliberately includes only singular `ModulesConfig` selections, not the ordered chain.
2. `AssemblyPlan::resolve` (`core/assembly/mod.rs:49–61,159`) constructs singular `active_modules` separately from `hooks`. `topology/slots.rs:39` therefore correctly leaves `SlotTopology.active_module` empty for Hook.
3. `build_topology_snapshot` (`core/topology.rs:34–49,68`) retains the hook order, marks selected hook modules active, and adds `ordered_hook` edges. There is no missing-chain defect in this DTO.
4. In **`topology_render/mermaid.rs:52–65`**, every pipeline slot instead derives its label and display class exclusively from `slot.active_module`. Hook therefore becomes **`hook<br/>missing`** with the `missing` class even when `snapshot.hooks` is nonempty.
5. That renderer does not read `snapshot.hooks`; its edge loop at 163–179 accepts only `runtime`/`uses`, so the correct `ordered_hook` data does not recover the chain elsewhere in this export.
6. In contrast, `topology_render/runtime.rs:161–168` explicitly formats Hook from `snapshot.hooks`, preserving order, or says `none` for an empty chain. Text/table/Markdown views also separately print the chain.

The consequence is misleading diagnostic output: a correctly selected hook chain appears missing, and its selected identities/order are absent from the full Mermaid export even though the same snapshot supports a correct runtime Mermaid view. Do not generalize this to broken hooks, lost configuration, a Desktop visual defect, or a malformed Mermaid syntax result. No rendered SVG/pixels were inspected.

## Unexecuted reproduction and regression plan

With an already valid assembled profile selecting two hooks, obtain the JSON snapshot and the full/runtime Mermaid exports. Expected source-derived comparison:

* JSON: `hooks = ["opencode_prompt", "opencode_compact"]`, active module entries and ordered edges retained; Hook's singular `active_module = null` is intentional.
* Full Mermaid: `hook<br/>missing`, missing class, neither hook identity shown in that slot.
* Runtime Mermaid: `hook<br/>opencode_prompt -> opencode_compact`.

An eventual focused regression should build one snapshot through the normal plan/topology builder with registered hook exports and a selected nonempty chain, then verify the full export shows the chain in order without the false missing marker. Include one-hook, reversed-order, empty-chain and ordinary singular-slot controls. Preserve the valid absent singular field in JSON. Extend an existing inspection boundary test where appropriate; do not create a process/GUI integration requirement for a pure projection correction.

The existing HTTP topology test reviewed independently uses an empty hook list and basic framing checks, so it is not evidence that the nonempty-chain projection already satisfies this expectation. This is a bounded test-source review, not an exhaustive search claim.

The separate abstract model (not included here) is our own small Python model of the two source label decisions. It checks one/two/reversed/empty hook cases and singular-slot controls; it does not execute the Rust renderer or validate an end-to-end profile. Only that abstract comparison was modeled.

## Practical simplification

Have the full renderer use the existing ordered selection representation for Hook. A small shared display helper for hook-chain label/presence can keep full and runtime Mermaid views consistent; the caller may retain its own node styling/source annotation. Do not fabricate a singular Hook `active_module`, choose the first hook as the whole selection, or discard chain order. No new universal slot framework or DTO migration is needed.

The systemic cause is applying a singular selection projection after Hook moved to an explicit ordered chain. Keep the chain interpretation in one small rendering helper rather than independently maintaining incompatible label logic.

## Dedup and bounded negative controls

Targeted review of published `round3-core`, `round4-core`, `round3-framing` and `hooks-replay` reports and a topology/Mermaid search in the available prior DOCX did not identify this cause. Known hook scheduling/replay/usage findings concern different boundaries and are not reused. Published PR91–100 were checked and cover different boundaries; no absolute novelty claim.

The apparent `slot:tool` ghost-edge lead was refuted for ordinary producers: `ModuleCatalog::register_process_export` stores tool/context-provider exports outside its `entries`; `entry_summaries` feeds AssemblyPlan from that map. A manually invented catalog input is not evidence of an ordinary runtime topology defect. Likewise the textual map's `dangling_nodes` is an isolated-node diagnostic, not a proven endpoint-integrity validator contract, and is not promoted.

Independent source review confirmed the bounded chain and its controls. Production tree remains unchanged. No unmeasured runtime-performance benefit is claimed.

## Pinned source anchors

Key production files were not changed by delivery PR87–89.

- [core/topology_render/mermaid.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/topology_render/mermaid.rs#L52-L65)
- [core/topology_render/runtime.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/topology_render/runtime.rs#L161-L168)
- [core/topology.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/topology.rs#L34-L68)
