# letta.evidence_blocks — пример Rust context_provider/v4

Выборка ограниченных read-only блоков справочных данных. Вдохновлена идентифицируемыми
блоками памяти Letta, но **не является Letta-клиентом, совместимым форматом Letta,
хранилищем долговременной памяти или удостоверенной базой знаний**.
[Описание исходного паттерна Letta](https://docs.letta.com/v1-sdk/memory/memory-blocks).

## Подключение

Используется существующий `proteus-module-sdk::run`: component wire v3,
`context_provider/v4`, id `letta.evidence_blocks`, host-owned `ordered_many`.
`provide` принимает `ProcessContextProviderRequest`, возвращает
`ProcessContextChunksResponse`; `catalog` возвращает отсутствие каталога skills.
SDK закреплён на Proteus-harness/Proteus-core
`3f36a003b4f3fde2242fc80f7aedac00dd127d1d`. Пакет самостоятельный, Core не изменяет.

`host.example.toml` — полная offline-конфигурация, без API key и сетевой модели.
Она требует уже установленные совместимые `proteus`, `proteus-reference-module`
(Proteus-modules `04114bbe85f179895e2b8553b6169a284caaeae3`) и собранный executable
этого примера в `PATH`. Запуск из папки примера:

```sh
cargo test
cargo build
PATH="$PWD/target/debug:$PATH" proteus --config host.example.toml "Explain storage database"
```

Fake model проверяет возможность локальной композиции, но его ответ **не доказывает**,
что реальная модель использовала данные. Для host smoke нужно дополнительно проверить
завершение `provide` и включение ожидаемого chunk в подготовленный model request.
`module-config.json` отдельно показывает только объект `module_config`, не целый host
config. Реальный `repo_aware` вызывает external providers с null metadata; этот путь
поддержан. Другие схемы query/metadata не заявлены и отклоняются явно.

## Семантика

Scope обязателен в owner config и у каждого блока. Сравнение точное, регистрозависимое;
нет wildcard, default scope или выбора прав из текста задачи/metadata. В пределах
`(scope,id)` сначала выбирается наибольшая supplied revision, затем применяются поиск
и бюджет. Одинаковые копии одной revision объединяются; конфликтующие версии с одним
`scope/id/revision` отклоняют конфигурацию. Последний tombstone подавляет более старые
записи даже без совпадения с запросом. Более поздняя явно заданная живая версия может
восстановить блок. Это **не удаляет старые prompts, журналы, кеши или ответы**.

Запрос — текст задачи: Unicode alphanumeric слова, lowercase, точное пересечение с
словами content/labels. Это не fuzzy/semantic search. Пустой запрос ничего не выбирает.
Равенства разрешаются по id, без времени, случайного порядка или модели. Блоки выдаются
целиком: слишком большой пропускается, меньший релевантный блок всё ещё может пройти.

Бюджет считает JSON escaping, видимое предупреждение/происхождение и фиксированный
`SourceAnnotated` envelope в model-pack `04114bbe...`, `adapters/context_render.rs`.
Metadata разделяет `payload_bytes` и `projected_renderer_bytes`. Это бюджет **данного
renderer**, не универсальный token/request budget; последующие изменения context
builder и provider framing не входят в гарантию. У внешнего builder в примере отдельный
больший бюджет, чтобы он не обрезал выбранные блоки при обычном ограниченном запросе.

## Доверие и надёжность

Source, scope и revision — supplied claims, не удостоверенные host факты. Произвольные
значения находятся внутри JSON; chunk source фиксирован, path не задаётся. Видимое
предупреждение повторяется в content, потому что metadata может не доходить до модели.
`provenance_verified=false`; `SourceAnnotated` **не повышает доверие**. JSON escaping
не является защитой от смысловой prompt injection. Не превращать блоки в system
instructions или approval/effect receipts. Здесь нет multi-tenant ACL: principal
не аутентифицируется этим слотом. Права инструментов, история, эффекты и admission
остаются у host.

Модуль не вызывает callbacks, сеть, subprocess, filesystem, secrets или модель;
не пишет память/историю. Проверяет cooperative cancellation через SDK HostBridge.
SDK/host управляют timeout и terminal classification. Immutable selection безопасна
для параллельных вызовов. Это свойство исходного кода, не обещание OS sandbox:
запуск executable и его OS-права по-прежнему определяет host.

Ограничения: 1 MiB сериализованной конфигурации; 256 блоков; 16 KiB content на блок;
16 labels; по 256 bytes на id/source/scope/label; query 4096 bytes и 64 различных слова;
1–64 результата; 1–65536 model-facing bytes; params 64 KiB; response 256 KiB.
SDK проверяет transport frame раньше этих domain checks.

## Проверка

Написаны 14 unit tests: порядок, revision conflicts, дедупликация, tombstones,
точный scope, Unicode/escaping, точные бюджеты, oversize skip, provenance attacks,
лимиты, cancellation и неверные slot/version/composition. Компиляция и 14 unit tests **PASS** на Rust 1.95.0 с pinned SDK (0 failed/ignored).
Также **PASS 1 wire integration test**: настоящий executable и synthetic-host
initialize/provide/catalog/error/late-cancel frames, 0 failed/ignored. Полный Core
host smoke и in-flight wire cancellation пока не проверены. TOML/JSON разобраны
стандартной библиотекой Python, поля вручную сопоставлены с pinned `AppConfig`,
`ProcessComponentConfig`, `ModulesConfig` и `RepoAwareContextConfig`. Это не заменяет
исполняемую проверку config schema/assembly и полноценного Core runtime с model request.

Дополнительно пройден handshake с настоящим `ComponentBroker` через SDK conformance CLI. [Общие результаты](../../validation/results.json), [дополнительные handshake результаты](../../validation/supplemental-broker-handshakes.json).
