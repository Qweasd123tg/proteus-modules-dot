# Loop observer — реальный opt-in Rust process module

`hook/loop_observer.repeated_result`, **hook/v6, component wire v3**.
Сигнализирует о последовательных одинаковых запросах к выбранному tool с
одинаковым видимым результатом. В следующем обычном model request появляется
короткое advisory с call IDs. Модуль **не** блокирует tool, не завершает turn,
не повторяет действия и не вызывает модель. Это самостоятельный executable,
а не библиотека, требующая будущего host adapter.

**Статус:** исходники и regression sources подготовлены и просмотрены.
Компиляция, тесты, запуск executable, conformance, CI и benchmarks **не
выполнялись**. `Cargo.lock` не создавался. Source review не является compile pass
или подтверждённой поставкой. Existing profiles и upstreams не изменены.
Установленный rustfmt 1.95.0 применён напрямую как static source formatter;
parse/format check выполнен. Это не компиляция и не исполнение модуля.

## Полезный механизм, а не новый agent framework

У [PydanticAI DetectLoops](https://github.com/pydantic/pydantic-ai/blob/fb04437121e9e84cda129a3db394ce8e27ae95f0/src/pydantic_ai_harness/pydantic_ai_harness/detect_loops/_capability.py)
наблюдения calls/results собираются до очередного model request; доступны
repeated call/result, чередование и text repetition, затем nudge/error/callback.
Источник перепроверен 30 октября 2026: официальный main
`fb04437121e9e84cda129a3db394ce8e27ae95f0`, commit 04:29:05 UTC,
blob `d3b2fdf845b107928e7be0da8bf91287a587f77e`.
Предыдущее исследование Proteus лишь предлагало такой hook.

Здесь **собственный ограниченный режим, вдохновлённый механизмом**, не порт
и не совместимость с PydanticAI. Не копируются исходники донора. Реализован
только самый консервативный сигнал: три последовательных одинаковых
hook-visible возврата по умолчанию. Нет grow-only списка steps, text-pattern
или автоматического error action. Статeless-пересчёт по BeforeModel history
не выбран: сокращение истории убирает часть facts, а полный scan повторяет
работу на каждом запросе. AfterTool даёт маленькую актуальную границу capture;
сохраняется лишь одна bounded signature на scope, не копия истории.

Наблюдаемый результат — advisory в canonical `ModelContext`/hook trace:
например, после трёх одинаковых `read_file(path=a.txt)` можно сменить запрос
или метод поиска вместо четвёртого повтора. Улучшение поведения модели,
экономия токенов и latency пока **не измерены**. Для маленьких workloads
стоимость дополнительного hook process/JSON может перевесить пользу.

## Точный контракт и authority

- SDK и canonical types закреплены на реальный Core
  [`925de0fc5ee5995409b11e42b216a15ca12f76d0`](https://github.com/Proteus-harness/Proteus-core/commit/925de0fc5ee5995409b11e42b216a15ca12f76d0).
  Используется `proteus_module_sdk::contracts`, без второй source identity DTO.
- Factory принимает только `slot=hook`, указанный module ID, `v6` и
  host-owned `ordered_many`. `Export::manifest` публикует canonical
  `ModuleConfigSchema`; `invoke` принимает только `hook.invoke` и возвращает
  `ProcessHookResponse`. `main` запускает существующий SDK runtime.
- [HookInput/HookResponse](https://github.com/Proteus-harness/Proteus-core/blob/925de0fc5ee5995409b11e42b216a15ca12f76d0/crates/proteus-contracts/src/contracts/hook.rs):
  AfterTool → `Continue`; Direct BeforeModel → `ModelContext` с неизменёнными
  messages и прежними instructions плюс одной advisory. Auxiliary model calls
  не получают и не потребляют advisory. Другие события → `Continue`.
- BeforeTool не меняет args/block, AfterTool не меняет output. Policy, grants,
  approval, ToolSafety, model choice и лимиты остаются у существующего host.
  Единственный используемый метод HostBridge — `is_cancelled`; нет callbacks,
  фоновой работы, файлового I/O, сети или прямой связи с другими modules.
- Scope — полная `ExecutionAttribution`: ExecutionId и optional
  session/thread/turn. Detached invocation не получает выдуманных chat IDs.
  TurnStarted и TurnSettled удаляют только точный scope. Новый process забывает
  всё. Это не durable tracker и не механизм дедупликации внешних эффектов.

## Что именно сравнивается

Одна bounded byte signature содержит имя, surface, raw_arguments, canonical
JSON args, затем tuple `ok/output/content/error/metadata` без result.call_id.
Объекты args сортируются по ключу рекурсивно; массивы сохраняют порядок.
Сравнение точное, без hash collisions и без truncated-prefix equality.
Порядок вложенных объектов в **result** остаётся текущим serde JSON порядком:
разный порядок либо volatile metadata могут пропустить сигнал, но не
превращают разные сериализованные results в равные.

`AfterTool` в Core приходит [после host truncation](https://github.com/Proteus-harness/Proteus-core/blob/925de0fc5ee5995409b11e42b216a15ca12f76d0/crates/proteus-core/src/core/bound_tools/hooks.rs).
Равенство означает только равенство доступных здесь данных, **не** полных
файлов/вывода или отсутствия реального прогресса. Synthetic denied/blocked
results также возможны; модуль не выводит из результата факт выполненного
эффекта. Неизвестный исход действия не становится основанием его повторить.

Серия разрывается при другом результате/аргументах/tool, не включённом tool,
слишком большом/сложном наблюдении либо несовпадении call.id/result.call_id.
В том числе удаляется уже готовая, но ещё не отправленная advisory, чтобы
она не переживала явный прогресс/пробел. Повторная доставка одного CallId
в окне последних 32 принятых IDs не считается ещё раз; несовпадение её
signature с текущей серией также удаляет stale advisory. Повторное использование ID
может недосчитать наблюдения; после eviction дедупликация не гарантируется.
После advisory нужны новые distinct IDs и новая полная серия.

Concurrent events сериализуются mutex; это порядок наблюдения, не обещание
порядка физического завершения операций. Поздний результат после cleanup
может создать новое bounded наблюдение, но не восстановить прошлый scope.
Потеря notification, LRU/TTL и restart только забывают evidence.

**Polling не останавливается.** Allowlist точный и обязательный; status/wait
не выбираются автоматически. Даже если их включить, notice прямо сохраняет
инструкции пользователя ждать/мониторить. Повторения могут быть правильными.

## Подключение

`profile.fragment.toml` — шаблон дополнения, не самостоятельный профиль.
Сохраните все существующие `modules.hooks`; добавьте
`"loop_observer.repeated_result"` **после** output-transforming/context-compaction
hooks, чтобы наблюдались принятые предыдущими участниками результаты и
advisory не удалялась следующей compaction. Если более поздний hook меняет
output/instructions, этот observer этого не видит.

Например, было `hooks = ["codex_compact", "tool_selection.dynamic"]`, стало
`hooks = ["codex_compact", "tool_selection.dynamic", "loop_observer.repeated_result"]`.
Массивы не являются append: слепой импорт fragment может убрать прежние hooks.
Имена `read_file`/`rg_search` в примере замените на реальные tool names выбранного
профиля. Наличие имени не выдаёт tool права и не включает сам tool.

Пакет — отдельный `[workspace]`; менять Modules `Cargo.toml`, package.py,
Core registry или reference executable не нужно. После разрешённой проверки
собранный `target/release/proteus-example-loop-observer` копируется в выбранный
каталог и его абсолютный путь записывается в `components.loop-observer.command`.
SDK factory/manifest — runtime source of truth, отдельного export registry нет.
Настройки доступны через manifest schema; malformed/unknown config отвергается
factory. Cross-field memory cap дополнительно проверяется `Config::validate`.
OS-права остаются правами явно выбранного host launch mode: process ≠ sandbox.

Когда исполнение будет разрешено, из каталога этого примера:

```bash
cargo generate-lockfile
cargo fmt --all -- --check
cargo test --locked
cargo build --release --locked
```

Первая команда выполняет dependency resolution: lock не выдуман и не включён
в source-only поставку. Прямые registry версии взяты из закреплённого Core
Cargo.lock; это не доказательство lock/ABI совместимости. Сохраните проверенный
lock перед распространением бинарника. Руководство общего SDK и conformance:
[канонический guide](https://github.com/Proteus-harness/Proteus-core/blob/925de0fc5ee5995409b11e42b216a15ca12f76d0/docs/guides/rust-module-sdk.md).

`tests/process.rs` использует **существующий ComponentBroker и настоящий binary**:
handshake → три AfterTool → Direct BeforeModel → одна advisory → следующий
BeforeModel без неё. Test не запускает cargo/install/сеть. Остальные regression
sources проверяют actual `apply_hook_response`, isolation, changing results,
dedupe, TTL/LRU, cleanup/restart, caps, cancellation и schema. Они не запускались.

## Стоимость, лимиты и ошибки

- Defaults: 32 scopes × 32 KiB byte limit одной signature = **1 MiB только
  суммарный payload limit retained signatures**, не total RAM. Cross-field максимум — 8 MiB.
  Ещё одна bounded signature временно строится под общим mutex; старую заменяют
  только после успешного полного encoding.
- CallId: 1–128 bytes; ring ≤32 IDs/scope (до 4096 payload bytes), evidence
  ≤16 IDs (до 2048 bytes), pending notice <4096 bytes из bounded labels.
  Scope identity — fixed-size UUIDs; конфигурация ≤64 имён ×128 bytes.
  Raw initialization/config JSON не удерживается; ID копируются только в
  пределах длины, без удержания потенциально большой capacity входной строки.
  Vec/String capacities, allocation headers, mutex, JSON/SDK state идут сверху.
  Вход уже decoded SDK; абсолютный RSS bound здесь не обеспечивается.
- Args: ≤4096 JSON nodes, depth ≤32; byte cap ограничивает всю signature,
  включая rich result. Serialization работает по borrowed data, полной копии
  ToolResult/Value не создаётся. Есть bounded temporary массивы ссылок для sort.
  Содержимое signature хранится в памяти, но не помещается в logs/advisory.
- TTL по monotonic time удаляет idle scopes при следующем hook invocation;
  без нового события cleanup не просыпается. Max scopes и LRU работают даже
  при потерянном TurnSettled. Неполное наблюдение не блокирует пользовательскую
  работу и не обещает «петли нет».
- Размер/complexity overflow: `Continue`, сброс серии/старой advisory.
  Malformed config/method/input, poisoned mutex и cancellation: ошибка hook;
  применяются обычные failure semantics host, а не скрытый fallback.
  Ошибка AfterTool не отменяет уже случившийся эффект и не разрешает retry.
- Cancellation проверяется при входе/после получения mutex и на writes.
  Это не bound на CPU или мгновенный отклик: serde может сканировать длинную
  строку до очередного write, а sorting и ожидание mutex не прерываются внутри.
  Пока строится signature, другие события этого export ждут общий mutex.
  Deadline/принудительное завершение generation остаются у process host.
- Advisory best-effort: если RPC/turn отменён после потребления notice или
  downstream hook/prepare_request отверг ответ, notice может быть потеряна.
  Exactly-once delivery нет. Accepted responses записывает обычный Core trace.

Это модуль наблюдения, не ограничитель числа rounds, не planner и не memory
index. Для новых patterns сначала нужны отдельные evidence/семантика, а не
расширение authority либо автоматическая остановка полезной долгой работы.
