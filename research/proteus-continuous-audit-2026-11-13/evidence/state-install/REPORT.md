# Proteus: profile / installation / recovery trace

**Обновление:** после первых двух находок подтверждён третий catalog↔history дефект. См. `ADDENDUM-plugin-history.md`. Итоговый Core suite: 10/10; основной текст ниже фиксирует первоначальный проход.

Изолированный исследовательский проход, 2026-11-13. Новые production-изменения и публикации не выполнялись. Локальный diff Core содержит только три воспроизводящих теста; Desktop production-код не изменён. Это не утверждение о полном построчном покрытии всех репозиториев.

Проверенные ревизии:
- Core: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Desktop: `75bf201764278eac4b50d156650edcf1429101ff`.

## 1. P2: успешный Save удаляет унаследованный module_config только до следующего Save или перезапуска

**Подтверждено, высокая уверенность.** У file-profile с `include` Config Builder и reader имеют разные семантики. Builder заменяет весь выбранный slot map в `next_config`, возвращает успешный snapshot и публикует сборку без удалённого ключа. Writer сохраняет этот объект в верхний файл, оставляя `include`. Reader затем рекурсивно объединяет его с include, возвращая удалённый ключ. Следующее изменение другого поля загружает файл заново, поэтому незаметно возвращает удалённую настройку в runtime.

Это не просто претензия к документированной recursive-merge семантике include: **подтверждённое состояние после Save расходится с тем, что тот же Core прочитает с диска и применит при следующем Save**.

### Воспроизведение

Настоящие `AgentAppServer`, `set_profile_config`, reader, writer и официальная reference-module fixture, без провайдера/API/network calls:

1. `base.toml` задаёт process-model `fake` и `module_config.model.fake.stream_delay_ms=1`.
2. `profile.toml` содержит `include=['base.toml']`.
3. Через `set_profile_config` заменить model slot map на `{"fake":{"implementation":"fake"}}`.
4. ACK содержит только `implementation`, но `AppConfig::load(profile)` возвращает также `stream_delay_ms`.
5. Сохранить только `permission_mode=Plan`: принятый snapshot снова содержит удалённый ключ.

```text
accepted={"implementation":"fake"}
on_disk={"implementation":"fake","stream_delay_ms":1}
after_unrelated_save={"implementation":"fake","stream_delay_ms":1}
```

Дополнительный тест writer+reader на произвольном tool-module object подтверждает ту же потерю удаления: intended `{"kept":1}`, reloaded `{"kept":1,"removed":2}`.

### Источники

- [Применение module_config и публикация профиля](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L155-L238).
- [Запись module_config без изменения include-семантики](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/persistence.rs#L145-L152).
- [Рекурсивный merge includes](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L214-L234).
- [Отдельная replace-семантика только directory overlay](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L194-L208).

**Граница проверки:** TOML file-profile подтверждён. JSON writer выглядит подверженным тому же механизму, но отдельного JSON repro нет, поэтому он не включён в подтверждённый охват. Автоматический watcher не использован в итоговом сценарии. `reload_tools` загружает только tools и не является полным reload профиля: первоначальная проверка через него была отрицательной, сохранена в `include-roundtrip.log`; правильный reproducer использует следующее независимое сохранение. Перезапуск следует из фактического результата `AppConfig::load`, но отдельный restart-process не нужен для основного доказательства.

**Направление исправления:** обеспечить один контракт для persisted managed sections при include, не ломая наследование unmanaged fields. Полезный инвариант regression-test: состояние, возвращённое успешным Save, равно управляемой части повторно загруженного config. Не стоит просто удалять include/flatten весь профиль: это меняет независимые пользовательские наследования.

## 2. P2: History предлагает откат к model-free состоянию, но он не сохраняется

**Подтверждено, высокая уверенность для headless/UI logic; интерактивный GPUI не запускался.** Core поддерживает `active_provider=None`. Реальный app-server успешно сохраняет переход `None → Some("fake")` и записывает старое `None` в history. Desktop `Draft::from_revision` честно восстанавливает `None`, но `changes()` записывает его в `Option<String>`, где `None` означает «не менять». Когда это единственное различие, `is_dirty()` возвращает false и кнопка Save недоступна. При других изменениях provider всё равно не сбрасывается.

### Воспроизведение

- Реальный Core: стартовать валидный model-free профиль с доступным provider `fake`, затем выбрать его через `set_profile_config`; `config_history()` содержит предыдущий provider `None`.
- Headless probe компилирует **не переписанную модель**, а существующие `src/settings/draft.rs` и `src/settings/addons.rs` Desktop вместе с настоящим `proteus-contracts`.
- Вызвать `Draft::from_revision(snapshot, old_state)` и `changes(baseline)`.

```text
Core: current provider=Some("fake"); replaced history provider=None
Desktop: baseline.provider=Some("provider-a"), restored.provider=None,
         restored != baseline, dirty=false,
         request.active_provider=null
```

History UI включает «Вернуть как было» при `before != baseline` и передаёт результат в `replace_draft`. Решение о доступности сохранения затем использует `dirty()`.

### Источники

- [History restore action](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/revisions.rs#L77-L120).
- [Восстановление provider=None и потеря его в save request](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/draft.rs#L183-L188), [changes/is_dirty](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/draft.rs#L249-L274).
- [Контракт None = no change](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/app_protocol/http.rs#L88-L105).

**Направление исправления:** явный tri-state/update operation для no-change / set / clear provider, затем согласовать dirty detection, Core validation и history replay. До появления такого контракта UI не должен представлять неподдерживаемый rollback как восстановленный.

## Прогоны и ограничения

- Core config-builder suite: **9 passed**, из них 3 новые repro-проверки и 6 существующих.
- Все 3 новые Core repro повторены ещё **3 раза**, без нестабильности.
- Headless Desktop probe: **3 passed** (новая проверка + 2 существующих addons tests). Целевая history-проверка повторена отдельно с последовательным выводом.
- Tests намеренно утверждают наблюдаемое дефектное поведение, чтобы предъявить воспроизводимое доказательство. Для regression после production-fix ожидания нужно инвертировать.
- Нет live-провайдеров, пользовательских профилей, production filesystem, PR, push или установок в пользовательский Proteus home.

Исключённые кандидаты: process module removal не предлагается UI; non-source catalog checkout защищён lock+revision в `with_files`; SettingsContext привязан к профилю, а install callback проверяет target_path; отсутствие записи бинарных версий в config history пока расценено как ограничение scope, не отдельный баг.

## Файлы доказательств

- `core-repros.patch`: три теста к Core.
- `core-config-builder-tests.log`, `core-repeat-{1,2,3}.log`.
- `include-repro.log`, `include-roundtrip-corrected.log`.
- `history-repro-clean.log`; исходники `desktop-probe/{Cargo.toml,Cargo.lock,src/lib.rs}`.
- `verification.txt`, `coverage.tsv`.
