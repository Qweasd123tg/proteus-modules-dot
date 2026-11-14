# Settings Reload × Save: новый межкомпонентный дефект

Дата проверки: 2026-11-13. Изолированный исследовательский checkout. Production-файлы не менялись; ничего не опубликовано.

## P2: старый ответ «Обновить» отменяет подтверждённое состояние в UI и подготавливает откат при следующем Save

**Подтверждено на production-методах Desktop в headless harness.** Это отдельный путь от прежнего `/sessions` → SSE race. Его результат затрагивает не только показ статуса: следующий save request содержит старую уже успешно сохранённую настройку.

### Обычный пользовательский сценарий

1. Профиль открыт, поля `a=1,b=1` внутри одного `module_config.tool.files`.
2. Нажать «Обновить». GET `/config/builder` уже получил старый snapshot, но его ответ ещё не обработан.
3. Пока обновление выполняется, изменить `a=2` и сохранить. Это разрешено: `can_save()` проверяет `saving` и `catalogs.busy`, но не `reloading`.
4. Save заканчивается первым. `accept_save` выставляет baseline/draft в `a=2,b=1`; `dirty=false`.
5. Старый GET заканчивается вторым. Его единственная защита — текущий `dirty()`. Теперь он false, поэтому `accept(old)` заменяет baseline/draft на `a=1,b=1`, удаляет editors и оставляет UI «чистым».
6. Пользователь правит только `b=2`. `Draft::changes` отправляет весь изменившийся slot map: `{"tool":{"files":{"a":1,"b":2}}}`. При обычном применении этого запроса Core заменяет slot целиком, откатывая подтверждённое `a=2`.

Сохранённый профиль **не меняется от самого запоздавшего GET**. В тесте подтверждены откат UI и ошибочный последующий outgoing request. Фактическая запись этого второго запроса отдельным живым Core/HTTP прогоном не выполнялась; её семантика непосредственно видна в Core `next_config.module_config.insert(slot, values)`.

### Фактический вывод

```text
reloading=true, dirty=true, can_save=true
first successful Save={"tool":{"files":{"a":2,"b":1}}}
delayed GET sets a=1 and dirty=false
next edit b=2 emits {"tool":{"files":{"a":1,"b":2}}}
```

### Почему этот порядок разрешён

Reload и Save запускаются независимо на background executor. Кнопка reload сама блокируется при save/reloading, но обратного guard у Save нет. Core snapshot сначала берёт runtime/config, затем ожидает `config_schemas()`, то есть нельзя считать начало GET и завершение GET одной атомарной точкой. Сеть/планирование ответов тоже не гарантируют тот же порядок. Конкретная живая задержка config-schema не инъецировалась: воспроизведение управляет порядком callback delivery.

### Источники

- [Reload и его dirty-only guard](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mod.rs#L231-L274).
- [Save допускается при reloading](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/mod.rs#L292-L298).
- [Реальный Save использует этот guard и принимает ACK](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/save.rs#L52-L82).
- [Кнопки reload/save](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/frame.rs#L315-L351).
- [Draft отправляет весь slot map](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/settings/draft.rs#L226-L246).
- [Core заменяет slot map](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L199-L200).
- [Core фиксирует config до асинхронного schema lookup](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L42-L63).

## Воспроизведение и границы

`make_probe.py` извлекает без изменения тела `accept`, `accept_save`, `dirty`, `can_save`, `has_errors`, update/reset helpers и **весь reload completion callback** из текущего Desktop. `Draft`, `addons`, `mcp` подключаются напрямую через `#[path]`, а не переписываются в модель. Использован именно закреплённый Desktop `proteus-contracts@5e8b6ae63fd6f50611129b19687b158621359706`, не незаметная подмена текущим Core.

GPUI `Context`, notification/feedback и контейнеры UI представлены минимальными заглушками, поскольку проверяется state-machine, а не paint/layout/input. MCP отсутствует; используются валидные JSON-поля. Порядок GET/POST completion задаёт тест. **Это не native UI smoke, не весь Desktop suite и не полный end-to-end HTTP тест.**

- Основной запуск: **6 passed**, из них 4 новые state-race проверки и 2 существующие addons tests.
- Новые 4 проверки повторены трижды: **4/4 × 3**.
- Контроль GET до ACK: локальная правка остаётся, ACK устанавливает новое чистое состояние.
- Контроль более нового dirty edit до старого GET: старый snapshot отвергается.
- Отдельный regression на недопуск Save во время reload: **red на оригинале (exit 101), green при одном guard (exit 0)**.

## Узкое направление исправления

`candidate-reloading-save-guard.patch` добавляет `&& !self.reloading` в `can_save`. Это согласует Save с уже существующим `catalog_idle`, который блокирует catalog-save при reload. Пользователь может продолжать редактировать: завершившийся GET при dirty=true будет отброшен; после него Save снова доступен.

Вариант без запрета параллельного сохранения: reload request должен запоминать поколение и отклоняться после нового принятого Save, независимо от текущего dirty. Тот же generation design стоит проверить для `load_history`, однако отдельная порча history в этом проходе **не доказана**.

Patch — только кандидат, не production-изменение. Проверен в source-extracted harness. Перед переносом нужны настоящий GPUI unit test и штатный focused Desktop gate.

## Версии

- Desktop main: `75bf201764278eac4b50d156650edcf1429101ff`, remote перепроверен.
- Core main для проверки setter/GET: `89997df995df7c39b713e16aba216ecb19c8f497`, remote перепроверен.
- Desktop Cargo contracts pin: `5e8b6ae63fd6f50611129b19687b158621359706`, именно он скомпилирован в harness.
- Desktop portable manifest фиксирует другой Core `8652804d29e44901236b5a209823fb975dca6ad3`; поведение готового portable не заявляется проверенным. Откат state/UI воспроизводится внутри текущего Desktop независимо от setter implementation.

## Другие рассмотренные пути

- Смена контекста Settings: профиль закреплён в `SettingsContext`, не берётся из текущего активного чата; нового cross-profile бага не найдено.
- Manual Save при новых правках: существующий edit_revision сохраняет новые buffers. Не повторён как новый дефект.
- Catalog-save во время reload: защищён `catalog_idle`; это полезный отрицательный контроль.
- Attachments async load/send/restore: send и restore блокируются на attachments_loading, generation защищает задержанный file-picker. Нового дефекта не заявлено.
- Multiwindow concurrent Save без revision/CAS и запоздалая history list: оставлены кандидатами, не объявляются подтверждёнными дефектами.

## Артефакты

- `make_probe.py`, `probe/src/{lib,tests}.rs`, `probe/Cargo.{toml,lock}`.
- `extraction.txt`: диапазоны и SHA256 извлечённых методов.
- `verification.txt`: SHA, remote verification, file hashes.
- `test.log`, `repeat-{1,2,3}.log`.
- `regression-before.log`, `regression-after.log`, `regression/src/tests.rs`.
- `candidate-reloading-save-guard.patch`.

Внешние провайдеры, пользовательские профили, реальные сессии и production filesystem не использовались.
