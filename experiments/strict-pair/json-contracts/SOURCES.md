# Source pins and boundary decisions

## Proteus SDK/Core

Repository: `https://github.com/Proteus-harness/Proteus-core`

Commit: `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` (the exact Cargo SDK revision).

* [SDK tool adapter](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-sdk/src/tool.rs): tool/v6 schema/raw-argument normalization and call-result matching.
* [SDK callbacks](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-sdk/src/hosts.rs): invocation-bound `host.operation.execute_tool` bridge and cancellation polling.
* [DelegatingToolHost](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/extension_operations.rs): active tool supplies lineage/cancellation; nested calls delegate through BoundTools.
* [BoundTools](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools.rs): policy/approval, recording, output truncation metadata. The producer must not replace these boundaries.
* [Invocation settlement](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/invocation.rs): child cancellation and timeout settlement remain host-owned.
* [AfterTool chain](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs): returned bytes may differ from raw tool effect; only the former are hashed/checked by this producer.

## Inspected reference reader/controller

Repository: `https://github.com/Proteus-harness/Proteus-modules`

Commit: `04114bbe85f179895e2b8553b6169a284caaeae3`.

* [read_file](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/tool/file-tools/src/read.rs): path-only full read returns unadorned UTF-8 text and explicit completeness/line metadata; source full-read size limit is 2 MiB. This producer accepts a smaller 64 KiB body.
* [project_check](https://github.com/Proteus-harness/Proteus-modules/blob/04114bbe85f179895e2b8553b6169a284caaeae3/workflow/coding-workflow/src/project_check.rs): existing controller correctly delegates commands to host tools but reports domain `passed` based on `test_result.ok`. It supplies neither independently verified test counts nor a complete runner-event protocol. Reusing it as proof that arbitrary tests executed would overclaim, so this module does not do that.

These are independent inspected pins, not a claim that this reference pack was
built against the selected SDK. The tests use authored reader-result fixtures.
The gate counterpart is the already published `hermes-verify-evidence` example
from draft PR1 at `29d31fb36397008b7677cd5df4943031e24e8fdf`, with its unchanged local
v1 receipt shape. No upstream Hermes API compatibility is claimed.

## Inspected file SHA256

Paths below are relative to the repository named above.

| Repository | Path | SHA256 |
|---|---|---|
| Core | `crates/proteus-module-sdk/src/tool.rs` | `1c3f95f6c0fec45105c040addcaf2d4b1538c9672afe9c231d23c0d72580452e` |
| Core | `crates/proteus-module-sdk/src/hosts.rs` | `17f27c01c2e9c955d226c2e4d222f23d0b9e8813eaf2a6638b1e6a2f9990e7e6` |
| Core | `crates/proteus-core/src/core/extension_operations.rs` | `8c76a24b14a1d030efadb2cdb954c91369bae765ce823ec9d7bb31868dba4a3e` |
| Core | `crates/proteus-core/src/core/bound_tools.rs` | `cf06626469f876616ba0fd42f0e29a0453d72f1d36e74238af0ea917a79e7e04` |
| Core | `crates/proteus-core/src/core/bound_tools/invocation.rs` | `99b509a26fbc7348ec9d154f29b527107a74e23dc705927422825932645824ea` |
| Core | `crates/proteus-core/src/core/bound_tools/hooks.rs` | `d3e620e4b5bec30f4b85eb07b59e44f39635de5cae9601edeab486c14fd4a7b2` |
| Modules | `tool/file-tools/src/read.rs` | `c5e2e34a158b5eaa35a05ad65debb789ec63ffc613f8e23ecd26e07d58e4e6df` |
| Modules | `workflow/coding-workflow/src/project_check.rs` | `237bd65e5350e555540471e472621a1e4b3ba13b3e249db6da9dff8a4c6f4e6d` |
