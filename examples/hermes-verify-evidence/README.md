# hermes.verify_evidence — ограниченный Rust hook для Proteus

**Исследовательский пример, не готовая система доказательства корректности.**
Он переносит из Hermes идею ограниченной проверки перед завершением, а не его
API или Python runtime. Использует существующие `wire/v3`, `hook/v6` и Rust SDK.
Ни команды, ни тесты, ни модель этот hook сам не запускает. Core не меняется.

## Что именно проверяется

Stateless-функция читает `BeforeStop.history`, полученную от доверенного host.
После вызова настроенного mutator требуется завершённый вызов настроенного
verifier **из более позднего сообщения**, с положительной metadata receipt.
Вызовы одной model batch не доказывают порядок исполнения даже при разных
порядках поступления результатов. Неуспешный mutator тоже мог изменить файлы.
Последующий неуспешный verifier отменяет прежнее положительное свидетельство.
Pending calls, неоднозначные одновременно используемые CallId, повторные
canonical PartId и повторные результаты relevant calls не позволяют выдать положительный
результат. Последовательное повторное использование уже закрытого CallId допустимо
и опирается на корректность host occurrence mapping: отдельной гарантии против
подмены или replay старого результата этот пример не даёт.

**Область свидетельства — только сохранённая canonical history, не весь текущий
turn и не снимок файловой системы.** Полный turn-boundary/receipt контракт не
выдумывается. Compaction, пропущенные mutator tools, внешние изменения файлов,
нечестный verifier или подмена host history могут сделать вывод неполным.
Положительный результат условен на корректную canonical history и доверие
host/verifier. Metadata и provenance enum не являются криптографической подписью.
Непроверенная старая мутация может вызвать nudge и в более поздней read-only задаче.
Отсутствие видимой мутации означает «политика не применяется», а не «всё проверено».

## Receipt — локальная конвенция примера, не стандарт SDK/Hermes

Verifier должен вернуть `ToolResult.ok == true`, `error == null`, а в `metadata`:

```json
{
  "proteus.example.verification": {
    "schema_version": 1,
    "status": "passed",
    "cwd": "/exact/host/workspace/path",
    "checks_executed": ["unit:parser"]
  }
}
```

Требуются exact configured tool name, связанная call/result пара, равенство
cwd по Rust `Path` components без filesystem canonicalization (не побайтовое
равенство строк: лишние separators и внутренние `.` нормализуются; symlinks не
разрешаются) и непустые идентификаторы реально выполненных
проверок. Свободный текст «tests passed», `shell` exit 0 и receipt от другого tool
не принимаются. Список проверок здесь не сверяется с независимой спецификацией:
это доверенное утверждение verifier, а не доказательство покрытия или корректности.

**Реального receipt-emitting verifier в пакете нет.** `tests/wire.rs` создаёт
детерминированные in-memory fixtures, прямо помеченные как synthetic; они нужны
для проверки gate/protocol, не утверждают запуск реальных тестов. Для применения
нужен отдельный доверенный adapter конкретного test runner с честной семантикой
«checks actually executed», включая zero-tests/skipped/failed/canceled случаи.
Не настраивайте обычный shell как verifier и не включайте шаблон профиля без adapter.

## Решения и границы надёжности

* Только `BeforeStop`; прочие события — `Continue`.
* Уже выбранный предыдущим hook `continuation` не заменяется.
* `ContinueTurn` просит продолжение, но не выдаёт разрешения запускать tools.
* Обязательный `on_exhaustion = "error"` явно выбирает ошибку workflow после
  `max_nudges`. `"continue"` выбирает advisory release, не положительную проверку.
  В `hook/v6` нет отдельного `StopWithFailure`; ошибку нельзя выдавать за обычный stop.
* `attempt` — host-owned общий счётчик, не собственное число nudges этого модуля.
  Host cap продолжений (8 на изученном pin) остаётся независимым и неизменным.
* Ограничены число частей history, число/длины tool names и, **после разбора receipt**,
  число/длины check identifiers. Receipt клонируется/десериализуется до этих проверок;
  отдельного раннего byte cap для receipt/cwd/status нет. Общий allocation/input
  bound принадлежит SDK/host wire-frame limits. Отмена проверяется при обходе;
  SDK/host всё ещё владеют deadline и lifecycle.
* Нет дискового состояния, callback tool execution, сети, новых прав или sandbox.
  Пример не защищает от злонамеренного host/verifier и не заменяет admission policy.

## Сборка, проверка, подключение

SDK закреплён exact Git revision; это самостоятельный Cargo workspace.
`profile.fragment.toml` — **неполный шаблон**: добавьте hook после существующих,
не заменяя их, задайте абсолютный executable path и реальные имена tools.

```sh
cargo test --locked
cargo build --locked --release
```

`tests/policy.rs` проверяет stale/reordered/failed/spoofed/ambiguous evidence,
exhaustion, cancellation и bounds. `tests/wire.rs` запускает только собранный
собственный executable: handshake, synthetic missing/fresh evidence и strict
payload rejection. Для реального Core integration отдельно нужны transcript
из настоящего host, настоящий verifier adapter и end-to-end cancellation tests.

Проверено 2026-10-25 на Rust/Cargo 1.95.0: **23 policy tests + 1 actual-executable
wire test прошли; 0 failed, 0 ignored**. SDK собран с указанного official Git pin,
`Cargo.lock` включён. [Результаты общего запуска](../../validation/results.json).
Это не настоящий Core end-to-end run и не запуск реального verifier: wire smoke
проверяет только собственный процесс с synthetic host/receipt fixtures. Отдельно
не проверены real-host integration, real check execution и полномасштабные
cancellation/replay сценарии.

Источники и отличие от Hermes: [SOURCES.md](SOURCES.md).

Дополнительно пройден handshake с настоящим `ComponentBroker` через закреплённый SDK conformance CLI. Это не заменяет полноценный Core workflow или реальный verifier.
