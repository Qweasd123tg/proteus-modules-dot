# Core: borrow the selected direct tool text before making a session preview

The private Core summary preview trims and keeps at most 160 Unicode scalar values. Borrow the two direct ToolResult inputs (nonempty error first, then nonempty output) rather than cloning them whole before truncation. Keep the existing Contracts formatting path for compound/image/binary/JSON content or a status fallback. Whitespace-only but nonempty higher-priority fields still win before trimming; no role/preference, formatting, wire, cache schema, compiler profile, or request path change.

One leaf, strict forward/inverse against the exact composed Core input. The isolated native default-layout proof executes both full private preview bodies and canonical Contracts types/serde_json with synthetic in-memory sessions. Four original lifted test invocations and one differential test (17 named shapes, 68 measured ABBA calls) passed. Exact capped results and their serialized preview digests match. Each direct large selected field removes one request: 2,097,152 B on output, 2,097,153 B on error, and 2,097,152 B when an empty error falls through to output. These local requested-byte peaks/gross decreases keep the same retained preview size. They are not process RAM, PSS, wall time, application paths, preserve-order, persistence, or a claim for compound results. The proof leaves plain_history's unused signature stubbed and does not exercise it.

Owner source application order: if Core preview.rs is still at blob
`17dd44df` (including the observed Core main and the packaged harness pin),
apply [#667](https://github.com/Qweasd123tg/proteus-modules-dot/pull/667) first.
This patch is independently applicable on the M439 delivery source, which
already contains that prerequisite. The earlier append-certificate experiment
is not required.
