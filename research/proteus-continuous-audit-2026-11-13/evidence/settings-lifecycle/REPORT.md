# Proteus: профили, component update и история настроек

Исследовательский проход 2026-11-13. Только изолированные test-only изменения, без production-правок, commit, push, PR и пользовательских данных.

Проверенный upstream HEAD: Core `89997df995df7c39b713e16aba216ecb19c8f497`, Desktop `75bf201764278eac4b50d156650edcf1429101ff`. SHA повторно получены через GitHub connector, локальные checkout совпадают. Ниже три отдельных подтверждённых поведения, а не полный аудит всех строк репозиториев.

## 1. P2: два разных symlink-профиля получают общую History

**Подтверждено через реальные последовательные `AgentAppServer::set_profile_config` и `config_history`, без гонки.**

Условие: два файловых alias живут в одном profile store и ведут к разным внешним файлам с одинаковым basename:

```text
app/configs/work.toml     -> project-work/config.toml
app/configs/personal.toml -> project-personal/config.toml
```

`config_builder_target_path` канонизирует файл. Затем `config_history_dir` не может сделать target относительным к profile store и оставляет только `target.file_name()`. В обоих случаях получается `app/config-history/config.toml`.

Воспроизведение:
1. Work: исходный mode=normal, `model.fake.stream_delay_ms=1`; сохранить mode=plan.
2. Personal: исходный mode=auto, `stream_delay_ms=2`; сохранить mode=normal.
3. Запросить History каждого handle.

Оба получают одни и те же две revision, а последняя revision Work содержит прежние настройки Personal (`mode=auto`, delay=2). Текущие файлы сами по себе не смешиваются: дефект в истории/возможном последующем rollback. Desktop строит «Вернуть как было» из каждой полученной revision, без identity исходного профиля; эта UI-ветка проверена чтением, интерактивный GPUI rollback не выполнялся.

Источники:
- [Канонизация target](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/persistence.rs#L36-L47).
- [Потеря полного пути при построении history key](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_history.rs#L15-L35).
- [Desktop: загрузка revision в draft](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/revisions.rs#L70-L110).

Направление исправления: collision-free identity для внешнего canonical target, например hash полного пути, а не один basename. Сохранить осмысленную семантику нескольких alias одного и того же файла. Существующий обычный layout не демонстрирует этой коллизии; условие symlink + внешний target + равные basename существенно.

## 2. P2: unrelated Save незаметно замораживает унаследованные providers

**Подтверждено для TOML file-profile с include и для directory-profile.**

Если верхний файл/overlay ещё не содержит `[providers]`, writer при любом Save переносит в него весь effective `config.providers`. Пользователь меняет только permission mode, но получает явные копии всех provider definitions. Они затем перекрывают редактируемые fragments.

В обоих реальных server-сценариях:
1. Fragment задаёт model=`inherited-v1`; верхний profile лишь включает его (или используется directory-profile).
2. Сохранить только mode=plan.
3. Изменить provider model в fragment на `inherited-v2`.
4. Прямое чтение fragment даёт v2, чтение всего profile и явный `reload_tools()` сохраняют v1.

```text
directory=false: fragment=inherited-v2, merged=inherited-v1, runtime=inherited-v1
directory=true:  fragment=inherited-v2, merged=inherited-v1, runtime=inherited-v1
```

Это не прежний finding об удалённом `module_config`, который возвращается из include. Здесь пользователь вообще не редактировал provider definitions, но Save создаёт их overrides и ломает дальнейшее наследование. Такой формат не экзотика: поставляемые `configs/config.toml` и `configs/codex.config.toml` тоже получают providers из fragments. Это не утверждение о тестировании живого OpenAI-провайдера.

Источники:
- [Безусловная материализация отсутствующего providers в TOML](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder/persistence.rs#L104-L113).
- [Приоритет file / directory overlay](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L194-L234).

Направление исправления: не материализовать unmanaged inherited provider definitions при редактировании других областей. Инициализацию отсутствующего полного профиля отделить от записи существующего include-profile/overlay. Аналогичная вставка есть в JSON writer, но JSON-воспроизведение в этом проходе не запускалось.

## 3. P2: успешный model-component update оставляет один выбор модели live, другой после resume

**Подтверждено для изменения module_config model export и штатной операции `component_packages` replacement.**

Выбор модели сохраняется с hash привязки, включающим и model module config, и component descriptor. Hot reload принимает во внимание только provider alias/model ref и reasoning: смена executable или настроек adapter не сбрасывает live override и не перепривязывает sidecar. Cold resume уже сравнивает полную привязку и молча возвращает baseline.

Воспроизведение:
1. Profile baseline=`profile-baseline`; пользователь явно выбирает `user-selected` через `set_model_name`.
2. Выполнить одно из изменений:
   - контроль: только permission mode;
   - изменить fake adapter `stream_delay_ms` с 1 на 2;
   - заменить process model через `component_packages` на отдельную копию того же актуального reference executable. Это проверяет replacement API, registry prepare, persistence и публикацию, а не моделирует их присваиваниями.
3. После успешного Save live runtime всё ещё сообщает `user-selected`.
4. Shutdown и `launch_resumed` того же persisted session.

Контроль сохраняет `user-selected`. В обоих затронутых случаях cold runtime выбирает `profile-baseline`. При component update даже содержимое executable одинаково: для расхождения достаточно новой package path. Это демонстрирует lifecycle inconsistency, не отказ реального HTTP провайдера.

Источники:
- [Полная persisted binding](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/session_selection.rs#L49-L77).
- [Hot publication использует более узкое сравнение](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile.rs#L21-L60).
- [Сохранение старого model_ref при reload](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/reload.rs#L49-L65).
- [Cold restore](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/session_selection.rs#L265-L294).

Направление исправления: единая политика invalidation на публикации и cold restore. Либо новый binding сразу сбрасывает override к baseline, либо сохранение override сопровождается явной корректной перепривязкой. По текущей документации изменение route/component отменяет старую binding; silent delayed reset не должен зависеть от того, успел ли пользователь перезапустить чат.

## Воспроизведение и границы

Применить `repros.patch` к указанной ревизии Core. Подготовить официальный reference module обычным runner проекта; затем:

```sh
export PROTEUS_TEST_REFERENCE_MODULE=/path/to/proteus-reference-module
cargo test --offline -p proteus-core --lib app_server::config_builder -- --nocapture
cargo test --offline -p proteus-core --lib app_server::session_selection -- --nocapture
cargo test --offline -p proteus-core --lib app_server::config_history -- --nocapture
```

Тесты утверждают наблюдаемое неверное поведение как evidence. При исправлении assertions нужно заменить ожидаемыми инвариантами.

Использован отдельный target directory, чтобы исключить переиспользование тестового executable от другого audit checkout. No live model/network calls, credentials, GUI, публикации или пользовательские settings. Реальны profile writer/reader, app-server, session selection sidecar/resume, component registration и официальный process-model fixture. Все изменения только в тестах изолированной копии.

Финальные результаты: config-builder **17/17**, session-selection **9/9**, config-history **3/3**; всего **29 passed**, 0 failed. Config-builder включает 3 новые repro-проверки с несколькими вариантами и существующие component-package/atomic-save сценарии. Patch применяется к pinned чистой ревизии (`git apply --check`). Полный workspace suite не запускался, production fix не вносился.
