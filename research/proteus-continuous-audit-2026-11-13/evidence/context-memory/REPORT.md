# Context, interrupted tools, and memory retrieval: confirmed findings

## Source and execution scope

- Modules HEAD and remote main rechecked 2026-11-13: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Actual Modules dependency pin used by Cargo: Core `b5fac84245b075896c24763b3aebac79b4375c2e`. No substitution of current Core main.
- Isolated checkout: `/workspace/shared/context-memory-chain`; original checkout remains clean.
- Audit modifies only test scaffolding, test modules, dev-dependencies and Cargo.lock. No production implementation changes, commit, push, PR or live provider request.
- No user data or real credentials. One HTTP fixture listens on loopback and uses a dummy key. SQLite fixture is in-memory.
- Prior native Anthropic error classification, tool-image losses, `{}` SSE arguments and rejected thinking-budget candidate are not reported as new.

## C1. Compaction preserves a synthetic aborted tool result after removing its tool call

**Confirmed, high confidence. Suggested priority P1/P2 depending on cancellation+compaction incidence.**

A resumed turn with an unresolved tool call gets a prompt-only `ToolResult("aborted")`. The compactor classifies every all-`Request` message as reusable context, so this result survives compaction while its durable assistant tool call is removed. The next provider request contains an orphan tool result. Canonical validation, checkpoint acknowledgement merging, and RequestShaper do not remove it.

### Source chain

1. `workflow/coding-workflow/src/codex_loop.rs:32-38`: prepare interrupted markers and normalize missing outputs before pre-turn preparation.
2. `workflow/coding-workflow/src/codex_recovery.rs:47-73`: synthesize the aborted result and mark its sole part `PartScope::Request`.
3. `hook/codex-context-preparation/src/history.rs:19-38,79-85`: classify it as `ephemeral_context` solely by scope, not content/role or association with a retained call.
4. `hook/codex-context-preparation/src/compaction.rs:53-61` and `history.rs:157-183`: keep real user anchors and summary, reinsert all ephemeral messages, discard durable assistant/tool history.
5. `workflow/coding-workflow/src/scaffold/preparation.rs:75-77,99-147`: a revision-bearing ACK merges request-only messages back into the accepted history. Thus a root ACK does not fix the malformed request.
6. `model/model-pack/src/adapters/anthropic/request.rs:190-218,308-325`: serializes the orphan as `tool_result` with its original `tool_use_id`.

### Reproduction and controls

`audit_interrupted_tool_result_survives_compaction_without_tool_call` runs the real `CodingCodexLoopWorkflow`, real registered `CodexPreparationHook`, actual contract `apply_hook_response` validation, revision-bearing ACK reconstruction, actual RequestShaper, and native Anthropic HTTP serialization. Input includes a durable unresolved call, `WorkflowHistoryInterruption`, and a fresh current user message. The summary model and host-side services are fixtures. A configured trigger of 1 exercises compaction without a huge payload.

| Scenario | Canonical calls/results | Real native HTTP tool_use/tool_result |
|---|---:|---:|
| Interrupted unresolved call, no compaction | 1 / 1 | 1 / 1 |
| Same history, compaction enabled | **0 / 1** | **0 / 1** |
| Completed call, compaction enabled | 0 / 0 | 0 / 0 |

The malformed HTTP body has only a `user` message beginning with `tool_result("aborted", tool_use_id="interrupted-call")`; no assistant tool-use block exists anywhere in the request. Persisted replacement history correctly contains neither call nor synthetic result, so this is specifically the working model request, not demonstrated permanent storage corruption.

Anthropic requires results to immediately follow corresponding tool uses. The captured body violates that documented requirement. This is a concrete malformed-wire reproduction, **not a live measurement of a provider rejection**. [Official tool-call formatting documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls), checked 2026-11-13.

**Expected user impact:** a cancelled/failed tool round followed by automatic compaction can make the next model request invalid just when context preparation should recover it. The precise live error text and incidence were not measured. Other adapters receive the same malformed canonical input but were not wire-tested in this pass.

**Fix direction:** distinguish durable workspace/request context from prompt-only tool-repair artifacts. Retain a synthetic result only if its matching call remains, or regenerate repair artifacts after compaction instead of carrying them as context. Do not persist the synthetic result as a workaround. Add the combined cancellation→normalization→compaction→ACK→provider invariant test, with normal workspace-context retention as a negative control.

## C2. SQLite memory joins punctuation-separated search terms into a different token

**Confirmed functional retrieval defect, suggested P2.**

`context_provider/sqlite-memory/src/lib.rs:175-187` splits only on whitespace, then deletes other punctuation inside each item. It therefore joins code/path components that SQLite's actual index treats as separate words. A verbatim query for a newly saved fact can return no memories.

`audit_exact_saved_developer_terms_do_not_recall_after_punctuation_merging` uses the actual store `remember` and `recall` against fresh in-memory SQLite databases:

| Saved fact and exact query | Generated match expression | Exact results | Control query | Control results |
|---|---|---:|---|---:|
| `src/config.rs` | `"srcconfigrs"*` | 0 | `src config rs` | 1 |
| `Config::load` | `"Configload"*` | 0 | `Config load` | 1 |
| `v1.2.3` | `"v123"*` | 0 | `v1 2 3` | 1 |

This is independent of semantic-search quality or language-model behavior. Nothing is deleted from storage. The provider delegates directly to the same recall method (`src/provider.rs:16-22`), while automatic context recall forwards task text (`context/context-pack/src/retrieval.rs:9-14`). Both explicit memory-tool queries and automatic recall can therefore encounter this mismatch.

**Fix direction:** tokenize separators consistently with the configured FTS tokenizer; do not delete separators in a way that merges adjacent indexed words. Preserve the intended literal-query/prefix behavior and avoid exposing FTS syntax unintentionally. Include code identifiers, paths, versions and punctuation-only/empty queries in tests. The probe is store-level, not a full process-boundary test.

## Checks and artifacts

- `workflow-compactor-tests.log`: 115 passing unit tests (22 compactor + 93 workflow), including C1 with revision-bearing ACK.
- `memory-context-tests.log`: 31 passing unit tests (23 context + 3 JSONL memory + 5 SQLite memory), including C2.
- `final-cross-component-probe.log`: C1 rerun after adding the explicit interruption record and formatting the new fixture; passed all three scenarios.
- `reproduction.patch`: audit-only scaffolding and two probes. It applies cleanly to the pinned original checkout (`git apply --check` passed); `git diff --check` passed.
- `coverage.tsv`: source-level review scope, not a claim of full-repository line coverage.

The diagnostic probes deliberately assert the observed broken behavior to document it. Permanent regression tests accompanying fixes should assert the intended invariants instead.

Commands:

```bash
source /workspace/shared/proteus-toolchain/env.sh
cd /workspace/shared/context-memory-chain
export CARGO_TARGET_DIR=/workspace/shared/proteus-review-20261112/modules/target
cargo test -p coding-workflow -p codex-context-preparation --offline -- --nocapture
cargo test -p sqlite-memory -p memory-pack -p context-pack --offline -- --nocapture
cargo test -p coding-workflow --offline audit_interrupted_tool_result -- --nocapture
```

## Limits and non-findings

No full Core/worker/desktop end-to-end run, no live LLM, no stress/concurrency run. The remote main is pinned only at the recorded check; later changes need retesting. This pass does not claim every repository line was reviewed. Whole-task substring/AND recall quality was not promoted to a bug; evidence here is the stronger exact-query tokenizer mismatch. Byte-budget/project-instruction admission and JSONL basic reopen/zero-limit behavior had no new confirmed finding in this pass. Earlier low-level JSONL I/O-corruption investigation was not resumed.
