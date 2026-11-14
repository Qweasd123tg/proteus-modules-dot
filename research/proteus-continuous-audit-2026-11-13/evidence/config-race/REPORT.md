# Proteus: потеря внешней правки профиля во время частичного Save

Исследование 2026-11-13. Core main повторно проверен через `git ls-remote`:
`89997df995df7c39b713e16aba216ecb19c8f497`.
Только изолированная копия, test-only patch и временные профили. Production-код,
пользовательские файлы и remote не изменялись; commit/push/PR не выполнялись.

## Новый P2: Save одного поля затирает конкурирующую правку другого поля

**Подтверждено на настоящем AppServerHandle, штатном writer, действующем watcher
и штатном Python process fixture Core, отдельно для TOML и JSON.** Модель,
внешняя сеть и исполнение инструментов не требуются.

Последовательность:

1. Профиль содержит `tools.enabled = ["probe_command"]` и mode `normal`.
2. UI/API начинает Save **только** `permission_mode = plan`. `tools_enabled`
   в запросе отсутствует (`None`), карты modules/module_config пустые.
3. После чтения профиля новый component задерживается перед handshake. Это
   детерминированно увеличивает реальное окно `prepare_assembly`, не меняя
   production-код и не подменяя writer.
4. Внешний редактор записывает `tools.enabled = []`; обычный AppConfig reader
   подтверждает, что на диске уже пустой список. Mode остаётся `normal`.
5. Разрешается завершение component startup. Save возвращает успех.

Наблюдение в обоих форматах:

```text
UI requested: permission_mode=plan, tools_enabled=None
external edit completed: tools.enabled=[]
Save response: tools.enabled=["probe_command"]
on disk: mode=plan, tools.enabled=["probe_command"]
live config: tools.enabled=["probe_command"]
Config History: no revision with tools.enabled=[]
active watcher after 3.5 seconds: no reload error, lost value not restored
cold launch: tools.enabled=["probe_command"]
```

Итак, это не только краткая рассинхронизация runtime и disk. Изменение,
внесённое до commit Save и не конфликтующее с запрошенным mode, физически
перезаписывается. Встроенная History также не сохраняет именно потерянное
состояние. Внешний редактор может иметь собственный undo/backup; отсутствие
любых способов восстановления не утверждается.

Контроль для TOML/JSON: если тот же external edit закончить **до начала** Save,
пустой список сохраняется и на диске, и live. Значит, пустой список допустим,
а UI-запрос действительно не требовал включать `probe_command`.

## Причина и точные границы

- [Чтение next_config и replaced_state происходит один раз до assembly preparation](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L148-L164).
- [Долгая prepare_assembly, затем publish/commit без проверки актуальности исходника](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L220-L238).
- [TOML writer записывает все managed поля, включая tools.enabled, из старого next_config](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/persistence.rs#L121-L162).
- [JSON writer делает то же](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/persistence.rs#L245-L259).
- [path_lock является in-process Mutex и не координирует внешний редактор](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/transaction.rs#L8-L32).

Сама watcher refresh-ветка уже [перечитывает и сравнивает fingerprint после
подготовки](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile_watch.rs#L164-L178).
Аналогичной проверки у UI Save нет. После перезаписи watcher больше нечего
восстанавливать. Потеря History имеет ту же причину: `replaced_state` захвачен
до конкурентного edit. Это одно finding, не два.

### Отличие от прежних findings

Не дублирует Save -> быстрый external revert: там disk сохранял новое значение,
но watcher ошибочно оставлял старое live. Здесь disk-значение уничтожает
**следующий commit ещё не законченного Save**. Также не требует stale UI GET,
включённых fragments/overlay, сохранённого model selection, event_log или
approval_timeout.

## Направление исправления

После подготовки сборки проверять, что исходное resolved состояние/входные
файлы не изменились. При изменении либо возвращать conflict до записи, либо
заново применять только поля исходного запроса к свежему профилю, готовить
согласованную сборку и ограниченно повторять попытку. История должна фиксировать
состояние, действительно заменяемое commit, а не предшествующий snapshot.
Атомарный rename не решает semantic lost-update. Простое расширение Mutex также
не синхронизирует обычный редактор или второй процесс.

Production fix в этом проходе не реализован. Assertions воспроизводящего теста
пока фиксируют наблюдаемое неверное поведение; для regression после исправления
их следует заменить ожиданием сохранения внешней правки либо явного conflict.

## Проверки

- 2 новых теста прошли: 4 основных случая (race/control × TOML/JSON), плюс два
  cold launch. `final-repros.log`.
- Race повторён ещё 3 раза, по TOML и JSON каждый раз; все прошли.
  `repeated-repro.log`.
- 3 существующих controls прошли: directory overlay precedence, сохранение
  symlink при atomic write, сохранение unmanaged JSON fields.
  `existing-controls.log`.
- `git diff --check` и `git apply --check` к чистому pinned checkout прошли.
- Target dependencies переиспользованы, но Core пересобран из изолированного
  checkout. Уникальные `audit_round11_*` имена и явные маркеры в логах проверены;
  `test-list.log` подтверждает именно эти два теста, не пустую выборку.

Воспроизведение на чистом pinned Core после применения `repros.patch`:

```sh
cargo test --offline --locked -p proteus-core --lib audit_round11_ -- --nocapture
```

Нужны Rust 1.95, Python 3 и подготовленные Cargo dependencies. Не нужен
`PROTEUS_TEST_REFERENCE_MODULE`: используется штатный
`crates/proteus-core/tests/fixtures/process_commands.py` и временная startup-gate
обёртка. GUI/HTTP transport здесь не запускались: вызван ровно app-server method,
который обслуживает Config Builder. Полный workspace gate не выполнялся.

## Дополнительный просмотр, без новых claims

Проверены кодом publication/reload, binding runtime timeout-ов через новую
registry и snapshot-границы. Наследование snapshot queued follow-up уже явно
закреплено штатным steering test и не объявлено новой ошибкой. Session approval
cache также имеет документированные session semantics; без отдельного
нарушенного инварианта он не включён в findings. Это не заявление полного
построчного покрытия проекта и не полный live прогон всех runtime параметров.
