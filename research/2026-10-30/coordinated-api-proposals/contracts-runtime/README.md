# Contracts runtime feature: отдельный согласованный source proposal

**Не drop-in Desktop optimization и не проверенная integration.**
[Core patch](contracts-runtime-feature.patch) рассчитан на
`befd30516aefa6f0a0ad5db9924ad4957160b8dc`. Desktop root и client-common пока
закреплены на `925de0fc5ee5995409b11e42b216a15ca12f76d0` без feature boundary. Новый dependency SHA
не придуман, pins и lockfiles не изменены.

## Один coherent feature boundary

`proteus-contracts` получает **default-enabled `runtime` feature**. Только
`jsonschema` становится optional; APIs, которым он необходим, отсутствуют при
отключении runtime целиком, а не заменяются успешными validation-off stubs:

- `domain::tool_validation` и `validate_tool_call_args`;
- `ToolRegistry` и `register_provider_tools`;
- `ExecutionContext`, `AgentWorkflowContext`, `WorkflowInvocationContext`
  вместе с invocation module, `Workflow` и runtime `AgentControl`;
- `apply_hook_response` и его private context/composition helpers.

Canonical `app_protocol`, `domain`, `model_standard` DTOs, strict serde и их
structural checks остаются доступны. Process wire traits/DTOs, `ExecutionScope`,
`ToolContext`, `Tool`, cancellation и capability interfaces без registry также
остаются. Crate не объявляется dependency-free; не каждый сохранённый trait
является DTO. Второго владельца типов, crate split или compatibility aliases нет.

## SDK validation обязательна

Core и `proteus-module-sdk` **явно запрашивают `runtime`**. SDK ToolExport как
прежде валидирует schema при construction и arguments на каждом invocation.
Default implementations и validators не заменены и не ослаблены. Этот feature
не является способом отключить validation в исполняющем host/worker.
Cargo features additive: другой consumer с runtime включит его обратно.

Strict DTO tests остаются активны без runtime. Only-runtime tests gated отдельно;
strict Continue response parsing вынесен из runtime test, чтобы не потерять его
no-runtime coverage. Четыре conditional compile-fail doctests фиксируют отсутствие
представительных runtime APIs. Canonical testing guide изменяется в самом patch,
без второго test runner или параллельного guidance framework.

## Потребители и provenance

[SOURCES.json](SOURCES.json) содержит 106 pinned baseline identities и final
candidate hashes; patch меняет 14 файлов. Current contracts/SDK closure проверен
по исходникам, включая сохранение schema-backed SDK calls.

[DESKTOP-INVENTORY.json](DESKTOP-INVENTORY.json) перечисляет 269 tracked Rust
files из Desktop `src/` и `crates/client-common/` на
`a28cc7f507424a570e86dc44230ee323156fdf6c`, а также семь Cargo manifests.
В этом Rust scope нет потребителей перечисленных исключаемых APIs. Desktop
использует approval/user-input DTOs, app/domain/model DTOs, image helpers и
config shape validation; client-common — StdioOutput, app session/events и IDs.
Из проверенных Cargo manifests только root и client-common зависят от contracts.
Vendor/examples не входят в Rust inventory; фактический dependency graph после Cargo resolution ещё
не вычислялся. Source inventory не подменяет Cargo feature resolution.

## Реальная последовательность интеграции

1. Review и executable validation Core proposal на указанной base, затем
   **реальный доступный Core commit**, содержащий эту feature boundary.
2. Только после его появления обновить **оба** Desktop dependency entries на
   один reviewed commit и задать `default-features = false` в root и client-common.
   При прежнем pin этот флаг не устраняет `jsonschema`: там ещё нет feature.
   Поэтому misleading Desktop patch с fake revision здесь не приложен.
3. Штатно регенерировать lockfiles штатным Cargo workflow. Проверить реальные
   selected features и normal dependency trees Desktop/client-common. Lockfile
   может сохранять optional dependency даже без неё в выбранном normal build graph.
4. Выполнить полный Core gate с runtime, отдельные contracts tests/doctests
   `--no-default-features`, существующие schema/hook и SDK invocation tests,
   затем canonical Desktop/client-common gates. Workspace feature unification
   не заменяет отдельный no-default target.
5. Если нужен численный выигрыш, измерить сопоставимые clean/incremental builds.
   Здесь доказана возможность убрать dependency edge, а не wall-time/RSS gain.

Все actual pins, manifest identities и gate prerequisites записаны в
[DEPENDENCIES.json](../DEPENDENCIES.json). Typed workflow proposal изменяет
process DTO helper, а не runtime `WorkflowInvocationContext`; оба механизма
сохраняют единственный canonical источник типов.

## Статическая проверка

[VALIDATION.json](VALIDATION.json) фиксирует hash/application checks;
[COMPOSITION.json](../COMPOSITION.json) — exact composition и её ограничения.
Единственный доставленный patch имеет SHA-256 `dcb6de94…`, полный hash указан в
[SHA256SUMS](SHA256SUMS). Другой snapshot diff с иным оформлением здесь не доставляется.
Прямой установленный formatter разобрал исходники; это не type-check.

Успешных результатов compilation, tests, builds, runtime, CI или benchmarks
для proposal не заявлено. **Открыто:** real Core revision → Desktop pins/lock → executable
gates. Upstreams не изменены; source proposal не является ready-to-merge integration.
