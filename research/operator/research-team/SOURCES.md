# Источники и границы чтения

Core `1fc3ef223d10322815dd9290a50d045bc95402bb`; Modules `7fceaebc3bed8add9b0e3091110f59deca86ba46`; Modules SDK `bee0e409e746e2df9db32748d4f8ea02201bd4af`. Все файлы проверены как точные Git objects (Git blob SHA-1 + SHA-256); current-Core working files совпали с pin. Исходники остаются в существующих snapshots, не копируются. **31 source entry не означает 31 полностью прочитанный файл или новые findings.** Ни upstream, ни Core не запускались. Поле selected_spans_read фиксирует выбранные прочитанные строки, не полное покрытие реализации.

[Машинный manifest](SOURCE-MANIFEST.json). **Обязательное уточнение времени покрытия S01:** [COVERAGE-TIMING.md](COVERAGE-TIMING.md). Исторический каталог 90 findings не изменён.

## s01

**Роли, инструкции, slots, tool/runtime settings.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/config.rs`

Прочитанные spans: [88–185](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/config.rs#L88-L185), [266–289](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/config.rs#L266-L289), [360–488](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/config.rs#L360-L488).

SHA-256 `c1abab187a38856301ba39cd62097a2462ba7f1db438cc36c20f9bb47f887086`; Git blob `cd6c912558a1e1a65a51e2a5efc0acecc0b9f274`; 16260 bytes.

## s02

**Includes, named paths, directory merge, recursive merge.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/config/loading.rs`

Прочитанные spans: [14–64](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/config/loading.rs#L14-L64), [127–303](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/config/loading.rs#L127-L303), [328–338](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/config/loading.rs#L328-L338).

SHA-256 `344433e0e7dc87adb2b6651d8c70b0160f62fed2cfca17e2ccc4937b8b0b6307`; Git blob `72eeb82a9e5774fff3dc9ea8be702703b06a2505`; 12985 bytes.

## s03

**Role validation: absence means None; only worktree literal.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/process/config.rs`

Прочитанные spans: [1–80](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/config.rs#L1-L80).

SHA-256 `18967dd8a146a6582489a7a33c8d77f1a9e3f0221e6a465f9728d82d636496ab`; Git blob `099ec47dc72e8d95788e1f362324258cc9b4fa36`; 2735 bytes.

## s04

**Existing read-only peer example, not reused as an unrestricted base.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `configs/fragments/codex-explore-peer.toml`

Прочитанные spans: [1–27](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/configs/fragments/codex-explore-peer.toml#L1-L27).

SHA-256 `d28c81bffe6408dfb396ee74511f9b7d8826447cb9cfca69e2ca597409ef8040`; Git blob `a655ad57d539245c4f4756f36e8d256e1a3c6e80`; 658 bytes.

## s05

**Registration, role admission, immediate receipt, wait, interrupt.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/collaboration/mod.rs`

Прочитанные spans: [53–205](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/mod.rs#L53-L205), [229–307](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/mod.rs#L229-L307), [325–382](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/mod.rs#L325-L382).

SHA-256 `58523b1e3b32e535fcf6316e93052dc78bf649ecdf9057520a5bf647b4b0edf2`; Git blob `87d835691c320b55754725dc6729a6baef0d6bd2`; 13576 bytes.

## s06

**Actual model-facing argument schemas.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/collaboration/spec.rs`

Прочитанные spans: [1–140](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/spec.rs#L1-L140).

SHA-256 `634a2845fad1e0bf745a3535f4c249cdddde4a52d351be648b43aff5fb30d2d6`; Git blob `108947f5eef09a67bacdcb3e230588a4ac2c578e`; 4953 bytes.

## s07

**Child --config/--cwd, stdio and kill boundary.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/process/child.rs`

Прочитанные spans: [1–74](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/child.rs#L1-L74), [77–135](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/child.rs#L77-L135).

SHA-256 `84ad71a783fff5a7e3faf2664586e124a235339ad1155d1f21121b6fc6584b5d`; Git blob `08d8c5a13e4aada5b6929269c431924cce2990e6`; 5490 bytes.

## s08

**Role service, fresh history, prompt transport, permits, deadline, results.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/process/mod.rs`

Прочитанные spans: [104–233](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/mod.rs#L104-L233), [262–332](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/mod.rs#L262-L332), [361–411](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/mod.rs#L361-L411), [445–486](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/mod.rs#L445-L486), [529–599](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/mod.rs#L529-L599).

SHA-256 `9a47becc4dd6b4f06f9852c3415d2f6b6ed20e1dcfa1b5cd180c31af291d9f6e`; Git blob `acbe549b4566759b2ff59a77ee09b738d5927b58`; 23104 bytes.

## s09

**Bounded in-memory state, completion consumption, status projection.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/collaboration/control.rs`

Прочитанные spans: [19–55](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L19-L55), [115–159](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L115-L159), [236–309](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L236-L309), [455–475](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L455-L475), [484–500](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L484-L500), [566–608](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/collaboration/control.rs#L566-L608).

SHA-256 `3d6ab1ce1be021e8205be89ac9ff826bc25a6a2a81b965692b8632e6fdab12d9`; Git blob `4e741b9e88893df0d34ecd0fe99977d63b641870`; 20944 bytes.

## s10

**Canonical identity, generation, lifecycle/wait DTOs, role ownership.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-contracts/src/contracts/agent_control.rs`

Прочитанные spans: [20–189](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/agent_control.rs#L20-L189), [210–258](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/agent_control.rs#L210-L258), [284–382](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/contracts/agent_control.rs#L284-L382).

SHA-256 `598c0229c80ab863cde1bc6afc785992e3e8e94ab4b3186b237a0effe7b96e37`; Git blob `a270d128c785f3d1dd3daa3b49374b953ac6a65b`; 17199 bytes.

## s11

**Summary truncation without separate truncation flag.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/process/outcome.rs`

Прочитанные spans: [1–24](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/outcome.rs#L1-L24).

SHA-256 `cc08abc55993a7a04fad3b41b6d61d98a244985bd4a1da7be6f1168192943f91`; Git blob `e72867c430b984f7b3fc8d0de1d400931703a5f5`; 1441 bytes.

## s12

**Service versus surface; per-child cancellation/grant context.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/mod.rs`

Прочитанные spans: [1–7](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/mod.rs#L1-L7), [44–140](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/mod.rs#L44-L140).

SHA-256 `1838b55b356a63c80568dd66561c4c96426a627ae8611d98d87b681afda10fac`; Git blob `0afd5589a666c340ab4aa50b193ad43b41c6dd6e`; 4913 bytes.

## s13

**Ordinary tool selection, MCP registration, unknown-name error.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/module_catalog/tools.rs`

Прочитанные spans: [40–103](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/module_catalog/tools.rs#L40-L103).

SHA-256 `d8141386a5d1752b147cc21d885842cf6a0c3386765fcdf8373fce0b4d69a95d`; Git blob `c2d58bdb0ca309ab3027ad5e3994120f5f030c6c`; 3833 bytes.

## s14

**Actual runtime registry: collaboration and provider-hosted additions.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/registry.rs`

Прочитанные spans: [92–155](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/registry.rs#L92-L155).

SHA-256 `ab2073e7ddf6c985e4b38ac53fb65c5325b49e86497b0038c69f7315151c7821`; Git blob `69a71f0f8e77e523c7671b7c8a15eee3345a2105`; 15198 bytes.

## s15

**Runtime-managed tool reporting.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/topology/tools.rs`

Прочитанные spans: [11–63](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/topology/tools.rs#L11-L63).

SHA-256 `7a51e5994219cb9324ec1432650b201c8c35945f50cd85414b5a47d960a97ff7`; Git blob `86694e4f6487bc23509ca7b2b360003e962958a6`; 3728 bytes.

## s16

**Explicit plugin config defaults.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-contracts/src/domain/addons.rs`

Прочитанные spans: [10–27](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/domain/addons.rs#L10-L27).

SHA-256 `1a97c9176ec8dd79f239c4b68e63abd4d10bc624232d9e285d40eeb99b9aa687`; Git blob `7a5816954de81db5367986f986557083c83c15e5`; 3733 bytes.

## s17

**Codex context config fields.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `context/context-pack/src/config.rs`

Прочитанные spans: [72–123](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/context/context-pack/src/config.rs#L72-L123).

SHA-256 `2d3f49c5f41f8db87d8e3bb0ce933406fb4dfe4b668f4c0f3e0154470aa5ef11`; Git blob `f845a2b00699d0de6995e9b7cacc1a3ac6844fb0`; 9287 bytes.

## s18

**Codex policy deny/allow/Ask and ReadOnly fallback.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `policy/policy-pack/src/lib.rs`

Прочитанные spans: [74–152](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/policy/policy-pack/src/lib.rs#L74-L152), [178–210](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/policy/policy-pack/src/lib.rs#L178-L210), [247–285](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/policy/policy-pack/src/lib.rs#L247-L285).

SHA-256 `4c278076237760752fcc881cf6d13e0f8916f074483d3e0a7e1a9294f317ac89`; Git blob `60a75b088bdabed069ed4ea2c4eebabd62dce378`; 19633 bytes.

## s19

**Read args, workspace helper, 2MiB full read versus range.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `tool/file-tools/src/read.rs`

Прочитанные spans: [17–141](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/tool/file-tools/src/read.rs#L17-L141).

SHA-256 `c5e2e34a158b5eaa35a05ad65debb789ec63ffc613f8e23ecd26e07d58e4e6df`; Git blob `7cb16cfbc2f014200aa38902b89dd0adcd74b720`; 8862 bytes.

## s20

**workspace_path imported from actual SDK.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `tool/file-tools/src/util.rs`

Прочитанные spans: [1–15](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/tool/file-tools/src/util.rs#L1-L15).

SHA-256 `1f038d5d4b185ea45274b27b4afc6ac1e48b04487308c9f28ef98361e9fa5b3a`; Git blob `7f537bcc07ee9c1fa178c1628a995f17b2901fe7`; 4420 bytes.

## s21

**Canonical workspace containment; whole blob equal at Core1fc.**

`Proteus-harness/Proteus-core` / `bee0e409e746e2df9db32748d4f8ea02201bd4af` / `crates/proteus-contracts/src/tool_support.rs`

Прочитанные spans: [127–141](https://github.com/Proteus-harness/Proteus-core/blob/bee0e409e746e2df9db32748d4f8ea02201bd4af/crates/proteus-contracts/src/tool_support.rs#L127-L141).

SHA-256 `831c87876f7d79d52495ecbd67e9a747afc21fd41239d631bc177df49f7a7132`; Git blob `885a26b4c8c49367a4e5e6406e2b05df43753583`; 11687 bytes.

Whole-file Git blob byte-identical at Modules SDK bee0e409 and Core1fc; это не проверка совместимости всего SDK/worker.

## s22

**Review phase clears tools.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `workflow/coding-workflow/src/plan_execute_review.rs`

Прочитанные spans: [197–237](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/workflow/coding-workflow/src/plan_execute_review.rs#L197-L237).

SHA-256 `1fa79213a8c1a5d18ba1049ff9f8116ab1cb67ab75a2c07738792f312990b728`; Git blob `06d5dc373e5d3b0a606f76c9ed41b78bdae3aec9`; 10706 bytes.

## s23

**Tool-capable loop and final response lifecycle.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `workflow/coding-workflow/src/codex_loop.rs`

Прочитанные spans: [55–90](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/workflow/coding-workflow/src/codex_loop.rs#L55-L90), [138–180](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/workflow/coding-workflow/src/codex_loop.rs#L138-L180).

SHA-256 `d46eeab6437d814a64f3cfeb7e4fcd1beabf09d92a32cce05ee2a10ebf333ffc`; Git blob `73a63786001c6ad6d24b92f36a088808a5f94104`; 6699 bytes.

## s24

**Only configured context providers are built.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `context/context-pack/src/codex.rs`

Прочитанные spans: [1–48](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/context/context-pack/src/codex.rs#L1-L48).

SHA-256 `32003228fd7d36d8daa970e84927f2e11e9a4be7e0d24621ec554b926007eb35`; Git blob `42f8337a43dd2f99f7cdc104af10e648f643036b`; 9378 bytes.

## s25

**stream_max_retries config, not provider-attempt budget.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `workflow/coding-workflow/src/codex_sampling.rs`

Прочитанные spans: [21–39](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/workflow/coding-workflow/src/codex_sampling.rs#L21-L39).

SHA-256 `c8ca7ea9366956a07f0899df8a1e1cb5cf1ea90e8c85c34ed9f6299a0ee2873b`; Git blob `08eeebb82ceea614415a3e10703f79d1aeb5e8e0`; 4521 bytes.

## s26

**Worker provides several implementations; ordinary tools opt-in.**

`Proteus-harness/Proteus-modules` / `7fceaebc3bed8add9b0e3091110f59deca86ba46` / `tool/file-tools/src/lib.rs`

Прочитанные spans: [1–80](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/tool/file-tools/src/lib.rs#L1-L80).

SHA-256 `f583864ab4a8357105ce16ffd2460b89d0693ef90b61886b3bc7ab53a6e301a3`; Git blob `c6fc259699c87a90240b10ea3859c48f0760c230`; 2728 bytes.

## s27

**Actual existing component/export shape and child surface example.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `configs/fragments/codex-peer-runtime.toml`

Прочитанные spans: [1–77](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/configs/fragments/codex-peer-runtime.toml#L1-L77).

SHA-256 `e9dc4c1c8340d3e04f10f636263da80c553daca702526c3ca8062d4168986b5c`; Git blob `a48b00274b8e72d6baee98dd9b6da1b795cde8d9`; 2251 bytes.

## s28

**Existing ordered include example.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `configs/codex-explore.config.toml`

Прочитанные spans: [1–8](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/configs/codex-explore.config.toml#L1-L8).

SHA-256 `8ebf160c1d7ae359fb2a2984f7dca465ced45ca1861e599c2719bb9ab90defdf`; Git blob `003bc1faa3834cb2167f8ef5ec27719cfd0d97d4`; 161 bytes.

## s29

**Host session state separate from model tool writes.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/session_store.rs`

Прочитанные spans: [50–79](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_store.rs#L50-L79).

SHA-256 `5279640172fd89a217d8a816ed808c97abf432247b92bc7e988949b398359d58`; Git blob `fc2f94fc2ffe2e06ad0ff7815103b3ce901240f3`; 10720 bytes.

## s30

**Plugin resolution iterates configured plugins.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_plugins/mod.rs`

Прочитанные spans: [57–95](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_plugins/mod.rs#L57-L95).

SHA-256 `738b46efc2f20c22948e61792c07e0f7f268f0339267696dc3d15e1cb73b8e51`; Git blob `4f4ea5e4482eaee988c8d37637997787caa70d8b`; 7584 bytes.

## s31

**Cancel + cooperative grace then child kill, not external effect rollback.**

`Proteus-harness/Proteus-core` / `1fc3ef223d10322815dd9290a50d045bc95402bb` / `crates/proteus-core/src/core/agent_control/process/turn.rs`

Прочитанные spans: [160–171](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/turn.rs#L160-L171), [295–307](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/turn.rs#L295-L307), [408–455](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/agent_control/process/turn.rs#L408-L455).

SHA-256 `908ab3737e62f6d0d3ded483e5edf98b2d4119482c8fbe7692d9f1e18080d8a1`; Git blob `7f07b73a5c8f92996372bb5727642d90d3c5ba96`; 16713 bytes.
