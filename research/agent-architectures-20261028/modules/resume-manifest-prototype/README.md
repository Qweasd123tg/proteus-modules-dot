# Resume manifest: диагностический Rust-прототип

**Статус: отдельная opt-in библиотека, НЕ подключена к Proteus Core.**
Не меняет runtime, snapshots, journal, policy, grants, scheduler или checkpoint store.
Не выполняет resume, migration, recovery, tools и внешние действия. Код и пример
написаны, но сборки, тесты, CI и benchmarks **не запускались** по указанию пользователя.
Это исходный прототип для самостоятельной проверки, не готовая гарантия совместимости.

## Что здесь есть

- `src/lib.rs`: типизированный manifest, ограниченное canonical encoding, SHA-256,
  чистая функция `compare(saved, candidate)` и объяснимые решения.
- `examples/diagnose.rs`: декларативный пример с **искусственными digest**. Он не
  измеряет настоящие артефакты и не является тестом; его не запускали.
- `Cargo.toml`: самостоятельный crate с `publish = false`; единственная прямая
  зависимость — `sha2 = 0.10.9` без default features. Dependencies не скачивались;
  Cargo.lock не создавался, транзитивные версии здесь не закреплены.

## API и смысл решений

`ResumeManifest` требует явно представить:

| Группа | Входные идентичности |
| --- | --- |
| Формат | Версия canonical encoding этой библиотеки — **не** версия Core snapshot |
| Protocol | Явная protocol version, которая сама по себе недостаточна |
| Engine/host | Contract ID, semantic version поведения, SHA-256 артефакта host |
| Workflow | Contract ID, semantic version поведения, выбранные module ID + export ID |
| Состояние | State schema ID, version и digest канонической схемы |
| Модули | Module ID → artifact SHA-256 → export ID → contract version + schema digest |
| Topology | Версия правил graph signature, версия topology, shape digest, node IDs |
| Reducers | Reducer ID → явная semantic version |

Значения версий — непрозрачные labels, не диапазоны SemVer. `1.0.0 → 1.0.1`
также является изменением: minor/patch, одинаковый module ID, protocol или topology
не дают права предположить совместимость поведения.

Каждое существенное поле использует `Evidence<T>`:

- `Known(value)` — host явно передал значение; библиотека **не удостоверяет** его;
- `Missing` — значение не было сохранено;
- `Unknown` — значение явно не установлено.

`Unknown == Unknown` и `Missing == Missing` **никогда не дают `Exact`**.
Отсутствующий список modules/reducers/node IDs нельзя заменять пустым.
`Known(empty)` означает осознанно полный пустой набор, а не «не знаем». Выбранный
workflow export обязан присутствовать в известном module/export inventory.
Конструктор `Inventory::try_new` отвергает дубликаты вместо скрытого last-wins.
Публичного mutable map или небезопасного конструктора у inventory нет.

| Решение | Значение и запреты |
| --- | --- |
| `Exact` | Все требуемые декларации известны и canonical bytes равны. Не разрешение и не доказательство полноты/достоверности manifest. |
| `ExplicitMigrationRequired` | Декларации полны, но изменились semantics, artifacts, выбранный export, state schema, modules, topology или reducers. Нужен отдельный разбор либо прежний артефакт; наличие и безопасность миграции **не установлены**. Никакая миграция не выполняется. |
| `Incompatible` | Missing/Unknown, неизвестный format, превышенный лимит, отсутствующий выбранный export либо другой protocol/engine contract/workflow contract. Прототип не умеет переводить эти границы. |

`changes` — упорядоченные typed `Dimension`; `blockers` указывают сторону
`Saved`/`Candidate`, путь и причину. При невалидном формате/превышении размера
сравнение полей не делается и `changes` пуст; это **не** означает равенство.
При многих причинах есть `DiagnosticsTruncated`, решение остаётся `Incompatible`.

## Детерминированный digest и границы

Canonical v1 не зависит от порядка вставки в inventory. Порядок map — порядок
точных UTF-8 идентификаторов; case folding и Unicode normalization не делаются.

Encoding:

1. Raw domain `proteus.resume-manifest\0`, затем `format_version` как big-endian u32.
2. Поля строго в порядке объявления `ResumeManifest`; внутренние структуры —
   в порядке `encode_fields!` в конце `src/lib.rs`.
3. Evidence tag: `0 = Missing`, `1 = Unknown`, `2 = Known`, затем значение для Known.
4. Строка: длина UTF-8 bytes (big-endian u32), затем bytes. Digest: ровно 32 bytes.
5. Inventory: число записей (big-endian u32), затем отсортированные `(id, value)`.
   Unit-значение node ID кодируется нулём дополнительных bytes.
6. SHA-256 вычисляется над всеми этими bytes; hex-представление lowercase.

Неизвестные значения имеют собственные tags, поэтому incomplete manifest можно
хешировать для диагностики, но digest **не является проверкой полноты**. `compare`
сначала проверяет полноту, а равенство устанавливает по самим canonical bytes,
не только по hash. Изменение encoding требует новой версии, а не переиспользования v1.

Лимиты: identity ≤ 1024 UTF-8 bytes, inventory ≤ 4096 записей, canonical manifest
≤ 1 MiB; максимум 256 подробных blockers + маркер усечения. Пустые identity,
начальные/конечные пробелы и управляющие символы отвергаются. Конструкторы принимают
уже выделенные caller-owned данные: эти пределы не заменяют лимиты внешнего parser
и транспорта. Два manifest кодируются отдельно; неизвестный format не угадывается.

**Hash не доказывает:** происхождение данных, подпись, корректность кода, полноту
dependency closure, реальное совпадение установленных bytes или безопасность resume.
Библиотека не читает бинарники/исходники, credentials, файловую систему или сеть.
Host обязан получить digest из доверенного своего inventory и включить все
влияющие на выполнение плагины, exports, native libraries, runtime/engine changes,
schemas, reducer behavior и конфигурацию в соответствующие version/digest inputs.
Если это невозможно установить, поле остаётся Unknown; одинаковая версия без
своевременного version bump не обнаружит скрытое изменение поведения.

Topology digest должен покрывать структуру с семантически существенным порядком,
edges, branch conditions, вложенными workflows и правилами fan-out. Сам этот crate
не строит graph signature; identity её encoding задаёт host. Имена condition/reducer
без явно поддерживаемых behavior versions не заменяют semantics identity.

## Как подключать — только отдельным решением host

1. Host формирует manifest из доверенного runtime inventory в момент сохранения
   и связывает его с **существующим** durable snapshot/journal identity, revision
   и workflow execution. Атомарность этой связи должна обеспечиваться host;
   в прототипе нет record ID, persistence adapter или собственной базы событий.
2. При cold resume host получает актуальные identities, вызывает `compare` и
   сначала использует его как diagnostic-only сигнал. Здесь никакой gate Core
   не устанавливается и незаметного отказа действующим пользователям не добавляется.
3. Отдельная явно включённая host policy может блокировать cold resume на обоих
   не-Exact исходах. `Exact` всё равно не обходит policy, approval, safety,
   cancellation, resource admission и проверку lifecycle/ownership.
4. Отсутствие старого manifest означает отсутствие доказанных identities, а не
   совместимость по текущему protocol/schema number. Legacy adapter должен
   представлять недоступные значения как Missing, не достраивать их догадкой.
5. Миграция, если позже будет спроектирована и разрешена, остаётся самостоятельной
   операцией с явными from/to identities. Этот crate не имеет migration registry,
   callback, execution token или возможности восстановить grants.

Нельзя просто вставить новые поля в текущие DTO: прочитанные Core структуры имеют
`deny_unknown_fields`. Здесь намеренно нет патча Core, нового checkpointer, payload
произвольного стека, handoff capsule или дублирования canonical journal.

## Основание в прочитанных исходниках

Проверены конкретные части официальных исходников 28 октября 2026 года; вывод
ограничен этими границами, а не утверждением о полном аудите Core:

- Proteus Core [`SessionConfigSnapshot`](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-core/src/core/config_snapshot.rs):
  `SCHEMA_VERSION = 8`, настройки, modules, tools и permission/approval configuration.
  Это snapshot конфигурации, не отдельное доказательство workflow semantics или
  artifact identity. Значение 8 не переносится в `FORMAT_VERSION` или protocol input.
- Proteus Core [`WorkflowHistoryCheckpoint`](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/workflow_checkpoint.rs):
  cumulative history, tool-result bindings и preparation target. Это не сохранённый
  стек произвольного алгоритма. Binding также прямо не предоставляет authority.
- MAF [`_compute_graph_signature`](https://github.com/microsoft/agent-framework/blob/c2a8f91b3070596c30723f74f303a124332bbb77/python/packages/core/agent_framework/_workflows/_workflow.py#L1319-L1384):
  сортированная structural signature из executors, edges, condition names и вложенных
  workflow; source semantics она не хеширует. Отсюда раздельные topology и behavior.
- MAF [`restore_from_checkpoint`](https://github.com/microsoft/agent-framework/blob/c2a8f91b3070596c30723f74f303a124332bbb77/python/packages/core/agent_framework/_workflows/_runner.py#L288-L327):
  restore отвергается при несовпадении graph signature. Здесь заимствован принцип
  явного сравнения, не checkpoint API, не storage и не обещание совместимости MAF.
- MAF Durable Extension [Python runtime contract](https://github.com/microsoft/agent-framework-durable-extension/blob/de35f65e5245086701a5dc3b8ba328a5b4a1849f/python/packages/durabletask/README.md#L80-L170):
  на прочитанной **unreleased** ветке workflow protocol `2` не изменился, однако
  replay action graph/child IDs изменились и старые in-flight v2 histories не
  поддерживаются. Документ отдельно предупреждает, что upgrade Durable Task SDK
  может изменить выбор ветки старой race history. Поэтому protocol, schema,
  topology и engine/workflow semantics представлены раздельно; переносимой
  гарантии совместимости этой ветки здесь не заявляется.
- [Документация RustCrypto sha2 0.10.9](https://docs.rs/sha2/0.10.9/sha2/) подтверждает
  используемый `Sha256::digest`. Собственная реализация SHA-256 не вводилась.

Исследовательский контекст: `../../reports/durable-workflows.md`.
Исходники доноров не копировались и не выполнялись; репозитории не клонировались,
remote/PR/CI не изменялись. `cargo`, `rustc`, formatter, tests, benchmarks и пример
не запускались. Подтверждены только создание файлов и статическое чтение кода;
компиляция, поведение, crash recovery и производительность остаются непроверенными.
