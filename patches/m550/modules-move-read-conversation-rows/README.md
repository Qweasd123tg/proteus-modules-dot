# W18: move large ReadConversation texts into the SDK response value

Exact M414 historical Modules base
`4cc5824a807dd27558afebb4f5f6e00e90c6a0ec`, including accepted #655. Independent
whole 610-path forward/reverse source gate matched only the two worker files;
post tree `42d90c9875077980626b5d8676ab3e6de14ae594`. The existing
`0c1b7572313230e5d123e95c722e1258a2e9ecd6` Core contract/semantics/SDK pin is
unchanged. This is not an official Go or Windows qualification. No remote
action or Node tooling.

M414 Core `RemoteSessionStore::conversation_snapshot()/load_messages()`
actually use `OpenSnapshot → ReadConversation(Current)`, including from its
runtime and AppServer conversation route. The legacy SDK builds a `Value`
from the owned DTO and Serde's string serializer copies the text. Other
accepted patches covered display state, record pages or hydrated cache docs,
not the independent full conversation endpoint.

Route only this operation through the existing typed worker helper, using
the same method, strict deserialization, request validation and service call.
Serialize the real DTO shell in its original key order; fill the existing
`conversation.messages` array with the same helper as display pages so owned
Text buffers transfer rather than copy. Non-Text contents keep the original
serializer. No change to SDK/frame budget, negotiation, fixed-prefix
validation, history, model context, directory access, durable data or writer
authority.

## Actual Linux gates

- Four uninstrumented real legacy-SDK pairs (JSONL and SQLite, both Serde map
  layouts): Current 50k wire response **32,689,059 B**, exact digest matches
  old worker for the same fixture and layout. Exact cap succeeds in all
  four; one byte below emits no response prefix and the same size-budget
  error. Empty/history point, model-rich small output, malformed/invalid
  future revision and post-release error are unchanged with relevant
  negotiated and legacy variations.
- Seven historical point controls in each backend/map arm from actual
  Append → compaction Replace → explicit reset, including old pinned
  Current, BeforeReplacement, Revision, exact empty and no resurrection
  after reset. Typed mixed Text/Opaque/ReasoningSummary byte/map-order
  checks, empty array and owned Text pointer identity pass. Two existing
  real worker durability tests pass per layout.
- Same-native-worker ABBA on the actual 50k JSONL response, limiting the
  instrumented phase to Serde `Value` construction **after native storage
  returns and before SDK framing**. Each layout avoids exactly 50,000
  Rust allocation/reallocation requests and 19,688,894 B of cumulative
  requested allocations. Maximum net live requested bytes above conversion
  entry: default 157,890,876 → 130,202,142 B; preserve_order
  137,889,864 → 108,201,170 B. Final net live delta unchanged, exact
  actual output bytes in all instrumented runs. This is not a whole worker,
  UI/product PSS/RSS, or latency claim.

Compile used the exact pinned historical native dependencies, CPU2–3 for
14.3 s, disk floor 200 MiB tmp / 100 MiB workspace with no trip. The sole
slot was released before serial runtime/measurement verification. Test
instrumentation and proof code are not part of the production patch.
