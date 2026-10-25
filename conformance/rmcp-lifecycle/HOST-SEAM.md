# Proposed consumer seam: explicit host lifecycle selection

This is a design proposal, **not implemented or valid current Proteus config**.
Its justification is the pinned source and passed scoped SDK probe; Core integration
remains a distinct next gate. Do not install another extension process manager.

## Existing boundary

At Core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`:

- `crates/proteus-contracts/src/domain/addons.rs::ConfiguredMcpServerConfig`
  supplies a known `protocol_version` string, default `2025-11-25`, but no lifecycle
  mode. Unknown config fields are rejected.
- `crates/proteus-core/src/tools/mcp/client.rs::ClientState::connect` uses `.serve`.
  `McpStdioHost::new` checks the version against rmcp `KNOWN_VERSIONS`, which
  already includes `2026-07-28`. Thus changing only the date does not select
  modern discovery. rmcp 3.3.0 already has `serve_with_lifecycle`.
- Core retains child/process authority, bounded transport and a shared outer
  connection-plus-list deadline. One admitted tool call is one request; a
  non-completed result is rejected and the connection invalidated. The probe's
  `call_tool_once` demonstration does not replace this Core path.

## Minimal proposal

Add an explicit host-owned `lifecycle` enum, default **Initialize** for backwards
compatibility. Prefer a discriminated configuration rather than contradictory
free-standing flags:

| Mode | Required configuration | Meaning |
|---|---|---|
| Initialize | existing `protocol_version` | existing behavior |
| Discover | nonempty ordered supported `preferred_versions` | modern only, no legacy retry |
| Auto | nonempty `preferred_versions`, explicit `legacy_version` | deliberate modern probe and classified fallback |

Reject empty/unsupported versions and incompatible mode-specific fields before
spawning the child. Canonicalize and snapshot the selected lifecycle with the
configured server identity and process spec. A new generation must not inherit a
previous client's negotiated era or cached tool identity merely because its
server-reported name matches. Defaulting a new global policy to Auto is not
required for interoperability.

Use the SDK lifecycle API **inside** the existing connection owner. Keep outer
Core admission, transport byte bound, deadline, cancellation and settlement
ownership unchanged. Do not expose the SDK's private discovery timeout helper.
An outer budget shorter than its public 10-second default may deliberately expire
before fallback; report that as the host timeout, not an unsupported protocol.
An adjustable separate probe budget would require an explicit upstream/public
API decision, not an undocumented copied implementation.

Preserve exact initialization error classes in diagnostics. Matching-ID and
omitted-ID legacy-shaped errors may fall back in this SDK; wrong nonempty IDs,
modern capability/header refusals, bad result shape, and transport closure do
not. A failed legacy fallback should retain both phase errors. Future unknown
modern error codes remain a pinned-version compatibility limitation, not grounds
for a broad claim that all future codes are safely classified.

## Metadata is an orthogonal small change

`crates/proteus-core/src/tools/mcp/discovery.rs::mcp_tools_from_list` receives typed
Tools. It can preserve existing `output_schema` and namespaced tool metadata with
current ToolSurface/ToolSpec contracts; it cannot reconstruct legacy `execution`
or unknown Tool fields that the SDK has already discarded. Keep configured
server identity and raw tool name as host-owned provenance, separate from remote
`_meta`. Do not let a remote hint lower safety or grant authority.

Schema preservation, schema validation, remote domain failure handling and
provider exposure are four distinct policies. Copying `outputSchema` is not
result validation. Core's canonical public-name collision checks must also remain
in force: no SDK lifecycle change solves alias ambiguity or registry transactions.

## Why not a reusable module now?

A hook/tool module cannot choose the already-owned MCP handshake or repair a
canonical catalog after typed decoding. A second MCP process manager would split
authority/cancellation ownership. A universal metadata DTO would have no new
consumer. The reusable artifact here is instead an executable compatibility gate
that can accompany a narrowly reviewed future Core change without modifying Core
in this batch.

Pinned Codex illustrates why mode and date should be explicit rather than copied:
its default is Legacy, its fallback proposal is `2025-06-18`, and modern stdio
requires both feature-selected mode and the exact `CODEX_MCP_PROTOCOL_VERSION`
marker. That is a host policy example, not a requirement to import the marker or
Codex's custom modern stdio transport into Proteus.

## Next acceptance gates

1. The locked SDK probe passed all 33 authored cases; retain its exact source and
   artifact receipts as a regression gate. This does not substitute for Core tests.
2. Execute accepted portable-skills provider+tool against actual pinned Core;
   confirm separate-slot config, context-to-load identity and default output cap.
3. If a Core lifecycle patch is separately authorized, test the actual custom
   transport/config path with these authored scenarios plus reconnect changing
   era, outer deadline cleanup, generation invalidation, and non-completed-result
   refusal. Reuse protocol vectors, not assertions that bypass Core ownership.
4. Separately stage metadata preservation and namespace generation changes with
   whole-catalog collision checks and authority/revocation-aware publication.
   Keep-old on availability refresh is not permission to retain revoked authority.
