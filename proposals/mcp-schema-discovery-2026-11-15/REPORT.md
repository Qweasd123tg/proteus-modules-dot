# MCP input schemas: complete discovery before registry publication

Status: isolated source-only prototype for the existing PR85 `mcp-schema` finding. Not a new runtime reproduction or a production-ready fix. No real MCP server, external model, user profile or upstream repository was changed or run.

## Source applicability and invariant

Core main is `bcbda4435534a296c707a1daa250813d692f68e1`; delivery main after PR138 is `148385938d05fa4f508e0dac2da3cd3322bf4b84`. The MCP registration, discovery conversion and shared schema-validator source files are byte-identical to their historical `89997df995df7c39b713e16aba216ecb19c8f497` versions underlying the prior report. The historical cold-launch/server reproduction was NOT RERUN.

`register_mcp_tools` already isolates failed discovery per server. It obtains the complete converted list before registering any tools. However, `mcp_tools_from_list` currently accepts a JSON object that is not a valid input schema. Validation then fails in global ToolRegistry registration outside the server-local error boundary, rejecting the whole assembly.

The candidate calls the existing `tool_validation::validate_tool_input_schema` on each final ToolSpec inside discovery conversion. Its String diagnostic is preserved through `anyhow::Error::msg`. The complete Result<Vec<_>> must succeed before global registration starts. An invalid first or later schema therefore rejects the whole discovery batch, not just that tool or a remaining suffix. No valid prefix from that rejected batch reaches registration.

Production change: one existing-validator call and its import, +2/−1 lines, net +1. The structural gain is an existing shared semantic rule applied before the already established commit boundary. There is no new registry transaction API, error-string classifier, schema dialect, dependency or framework. The global registry still validates independently for every producer; its other checks are not caught or relaxed.

## Explicit staged precedence

This proposal defines the following order, rather than promising that every hypothetical collision is always diagnosed:

1. A server's discovery must produce an entirely valid list, including non-empty names and valid input schemas.
2. Only a successful batch enters global registration. Name collisions within that valid batch or against previously registered tools remain fatal assembly errors.
3. If a batch contains both an invalid schema and a potential collision, discovery rejects the server first. No tools from that batch are registered and its potential collision is not checked.

The third case is a deliberate change from the old invalid-schema registration path. It follows the existing staging for conversion/empty-name failures and is documented and given a proposed regression explicitly. There is no catch-all around registration. This is not a general all-or-none registry implementation: a collision in a valid batch can still abort its temporary assembly after earlier registration work. No stronger transaction guarantee is claimed.

The same isolation applies to later assembly preparation used by settings updates: an invalid-schema server can become a configured server with a visible local discovery error instead of causing global preparation failure. This follows the existing malformed-discovery behavior. Actual settings Save/HTTP persistence behavior is not exercised by the proposed cold-assembly tests and remains an additional qualification gate.

## Cost and boundaries

Valid input schemas are compiled once during discovery preflight and again when their fresh registry cache is initialized. This duplicate preparation work is explicit; no cache, allocation, CPU, latency or memory improvement is claimed. The validator and registry use the same underlying schema compiler, but this patch does not transfer compiled validators between them. A prepared-tool/cache-transfer API would be a wider change and is not introduced to avoid one extra validation pass.

Output-schema semantics, name sanitization, annotations, tool execution, transport, server launch and generation lifecycle remain unchanged. The test fixture extension only adds controlled tools/list responses. Existing execution branches are not changed. No tests exercise actual remote tool side effects or live MCP services.

## Proposed integration regressions, NOT RUN

Three new functions live in the cohesive `tests/mcp_client/discovery.rs` module and reuse the existing MCP fixture and public Core APIs. The main test file only registers the module. The fixture adds one optional list-mode selector; its default preserves the existing paginated response.

- Invalid nested input schema first and last, empty-list control and disabled malformed server. Each is paired with an independent healthy fixture. Proposed assertions use actual AgentAppServer assembly, addon status and Config Builder's registry-derived tool snapshot: the failed server has no prefix, its diagnostic names the invalid tool, and the healthy tool remains registered. Empty/disabled states have no discovery error.
- A wholly valid list with duplicate public names, and two valid servers whose distinct names sanitize to the same public prefix, still fail actual ModuleCatalog tool-surface preparation with the registry collision error.
- A list containing duplicate valid entries followed by an invalid schema produces a server-local schema error and no registered prefix, explicitly covering staged mixed-error precedence.

These are future real stdio/Core integration checks, not an executed abstract model. They do not invoke a model or remote tool. All three tests, the existing MCP suite and Rust compilation were NOT RUN. The source arrangement and assertions being plausible do not establish passing behavior.

## Verification and remaining gates

Twenty-two baseline source/document files were Git-blob and SHA256 verified against the pinned Core commit. Independent architecture and exact-patch reviews accompany the candidate. Strict git apply whitespace/check, isolated application and exact candidate-byte comparison succeeded. An initial surplus blank line at the end of the new test file was removed after the whitespace check rejected it; no semantic workaround was used.

The exact published #86 config-validation, #137 provider-preservation and #138 instruction-bootstrap patches were blob-verified. This candidate applies before and after that fixed three-patch sequence, producing byte-identical combined files. These two orders are not a claim that all 24 permutations were tested. The patches are complementary, not prerequisites; mechanical composition does not transfer their test evidence to this tree. Desktop #134–136 proposals and the separate rmcp SDK lifecycle probes are not Core schema-isolation qualification.

Actual Python 3.12.14 AST parsing succeeded for the baseline and candidate fixture files. This is syntax parsing only: no fixture import, handler, process launch or Python behavioral test was executed. Python otherwise performed file/hash/diff bookkeeping. There is no substitute schema validator or server model used as runtime evidence.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. Required qualification is formatting plus targeted Core discovery/MCP integration tests with actual dependencies, followed by the applicable settings-update/HTTP invalid-schema scenario and adjacent existing lifecycle tests. No whole-Core gate, live server test, full-runtime closure or installation is claimed.

Patch SHA256: `ba4ab8b9fbb8bfe9f658ea40123091461188b12e50792a1c4e209cab2a063669`. Publication of this package would distribute a reviewed source proposal, not an installed or tested production change.

