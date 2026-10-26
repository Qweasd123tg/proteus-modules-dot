# planning.ready_steps

Самостоятельный Rust process module для Proteus: wire v3, `tool/v6`, SDK
`0.1.0-alpha.2` закреплён на Core commit
`3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.

## Что делает

Проверяет небольшой DAG и вычисляет следующий набор допустимых **рекомендаций**.
Все статусы поступают от вызывающего. Они не подтверждены журналом, тестами или
host: `status_source = "caller_supplied_unverified"`, `advisory_only = true`.
Ни один узел не запускается, не авторизуется и не сохраняется. Нет retry,
checkpoint, фонового процесса, сетевого доступа, чтения файлов или скрытого
`previous_state`. Это не durable runtime и не замена существующего `update_plan`.

Вдохновение — разделение task graph, waiting/terminal states и join policy в
[Pi task graph](https://github.com/earendil-works/pi/blob/d5b3de22d0e24a3e9c38a9410d3329b099717283/packages/durable/src/harness/task-graph.ts).
Реализация новая и существенно уже: Pi строит graph из durable commit publications;
этот инструмент анализирует только переданный JSON. Семантика policy ниже является
контрактом этого примера, не обещанием полной совместимости с Pi.

## Вход и policy

```json
{
  "nodes": [
    {"id": "inspect", "dependencies": [], "status": "succeeded"},
    {"id": "patch", "dependencies": ["inspect"], "status": "pending"},
    {"id": "check", "dependencies": ["patch"], "status": "pending"}
  ],
  "failure_policy": "fail_fast"
}
```

`ready = ["patch"]`; `check` ждёт `patch`. Все поля обязательны, неизвестные
поля отклоняются. Статусы: `pending`, `running`, `succeeded`, `failed`, `canceled`.

- `fail_fast`: любой `failed`/`canceled` в графе блокирует **все** новые
  рекомендации, включая независимые ветки. Уже `running` не отменяется.
- `all_settled`: pending узел готов, когда все непосредственные dependencies
  terminal, даже если среди них есть failed/canceled. Это удобно для cleanup/
  review-планов, но **не** утверждает, что продолжать после ошибки безопасно.
  Исполнитель обязан отдельно проверить authority, prerequisites и evidence.
- `failed_dependencies` содержит transitive failed/canceled ancestors для pending
  узлов. Это annotation: при `all_settled` такой узел может одновременно быть ready.
- `blocked.waiting_for` перечисляет только непосредственные nonterminal deps.
  `terminal` включает succeeded/failed/canceled; `unsuccessful` — failed/canceled.
- Списки стабильны по ID, topological order использует лексикографический выбор.
  Порядок входных nodes/dependencies не влияет на успешный результат.

Историю переходов статусов проверить невозможно: анализатор не доказывает,
что `succeeded` действительно выполнялся после его dependencies. Структурный
граф валидируется полностью, включая terminal nodes.

## Границы ресурсов

Не более 256 nodes, 4096 edges, ID длиной 1–64 ASCII bytes (`A-Z a-z 0-9 _ . -`).
Duplicate IDs/dependencies, self-loops, dangling deps и циклы отклоняются без
частичного ответа. Нерекурсивная топологическая сортировка и bounded transitive
annotations. На каждый graph node проверяется отмена; ошибка host callback
останавливает операцию. JSON-результат не более 64 000 bytes: превышение даёт явную
ошибку, не обрезанный JSON. В host должен оставаться output budget не ниже этого
предела; меньший host budget может независимо обрезать строку.

Schema limits защищают входные поля; общий wire-frame limit и память первичного
JSON parsing остаются ответственностью SDK/host. `ReadOnly` — классификация этого
инструмента, а не доказательство безопасности произвольного executable.

## Сборка и подключение

```bash
cargo test --locked
cargo build --locked --release
```

Нужен Rust/Cargo 1.95.0 и доступ к pinned SDK. `Cargo.lock` зафиксирован.
25 октября 2026 на Rust 1.95.0 выполнен `cargo test`: **11 passed, 0 failed**;
release build и protocol smoke этим результатом не подтверждаются.
Никаких local path dependencies.

Добавьте к существующему профилю, не дублируя уже объявленную `[tools]`:

```toml
[tools]
enabled = ["planning.ready_steps"]

[components.ready_steps]
command = "/absolute/path/proteus-pi-ready-steps"

[components.ready_steps.exports.tool."planning.ready_steps"]
timeout_ms = 10000

[module_config.tool."planning.ready_steps"]
```

Export ID и tool name: `planning.ready_steps`. Конфигурация — строго пустой
объект. Tool returns ordinary JSON **text** in `ToolResult.output`; это не новое
typed result extension и не замена канонического host-контракта.

`tools.enabled` содержит **tool name**, не component ID. Для отдельного offline
профиля есть [proteus.offline.example.toml](proteus.offline.example.toml): замените
два executable path. Он использует официальный `proteus-reference-module`
([Modules commit 04114bbe](https://github.com/Proteus-harness/Proteus-modules/tree/04114bbe85f179895e2b8553b6169a284caaeae3))
для fake model/workflow/context/policy, без API keys. Эти reference executables
не поставляются с примером. Проверка профиля:

```bash
proteus --config /absolute/path/proteus.offline.example.toml inspect plan
proteus --config /absolute/path/proteus.offline.example.toml tools list
```

Полный профиль пока проверен только по исходному config contract, не запускался.
Fake model не гарантирует генерацию произвольного вызова этого tool; именно
detached protocol smoke ниже проверяет invocation независимо от модели.

## Проверки

Pure Rust tests покрывают deterministic readiness, две policy, transitive failed
deps, cycles/dangling/self/duplicates, terminal subgraph validation, node/edge/ID/
output limits, cancellation и unknown fields. Protocol smoke проверяет реальный
executable через публичный Core conformance CLI:

```bash
python3 smoke.py --module target/release/proteus-pi-ready-steps \
  --conformance /absolute/path/proteus-component-conformance
```

Проверяются handshake/list, detached invocation, invalid graph как ToolResult
error, schema rejection, authoritative `raw_arguments`, wrong export/config.
Negative probes требуют конкретную error category и диагностический текст/path,
а не произвольный nonzero exit. Для factory rejection дополнительно отправляется
прямой wire-v3 initialize: host conformance намеренно не передаёт worker stderr,
поэтому smoke сам проверяет `unsupported export tool/wrong` / unknown config field.
Composition и host features берутся из положительного conformance report.
Проверено 25 октября 2026: **11 unit tests PASS, 0 failed/ignored**. Включён валидный DAG с превышением output budget. Обновлённый protocol smoke через настоящий SDK ComponentBroker **PASS**, включая конкретные negative diagnostics. Отдельно direct wire smoke из общего runner прошёл 14 проверок. [Общий результат](../../validation/results.json).
Process cancellation/reentrancy остаются
отдельной host/SDK conformance проверкой; pure cancellation callback тест не
выдаётся за end-to-end cancel test.
