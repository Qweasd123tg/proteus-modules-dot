# Proteus: ошибка runtime переживает явное выключение/включение расширения

Проверено 2026-11-13. HEAD повторно сверены с origin:

- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

## Результат: P3 recovery inconsistency, подтверждённая логика

После ошибки запуска/выхода процесса пользователь выключает расширение в Settings и снова включает. Старое состояние `Runtime.error` **не очищается**. Поэтому включение не делает даже новой попытки запуска. Открытие новой поверхности того же расширения также не помогает. При этом отдельное действие **«Перезапустить»** очищает ошибку и допускает запуск.

Это не Files refresh, SDK timer starvation, утрата registry при rehost или прежний late-ACK defect. Баг ограничен восстановлением после ошибки; обычное выключение/включение здорового расширения работает. Разумная оценка P3, не P2: пользователь может восстановиться отдельной кнопкой Restart или перезапуском окна.

### Проверенная цепочка

1. Синтетическое состояние ошибки, соответствующее `Signal::Exited`: `process=None`, `error=Some(...)`.
2. Точное тело production preferences observer получает `enabled=false` и вызывает точный production `stop(Reset::Stop)`.
3. `stop` очищает process, pump, queues и нативные views, но **не error**.
4. Тот же observer получает `enabled=true`. Его guard `process.is_none() && error.is_none()` ложен, новой попытки запуска нет.
5. Точная заключительная ветка `attach` также не вызывает start, пока error существует.
6. Точный production `restart` вызывает stop, затем `error=None`, затем start. Этот контроль проходит.

Повторено также с ошибкой протокола при ещё живом процессе: выключение останавливает живой процесс, но старый error блокирует его последующее включение.

### Почему runtime не пересоздаётся вместе с переключателем

- Settings switch меняет `preferences.extensions.set_enabled`, без отдельного restart: [extensions.rs](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/extensions.rs#L275-L282).
- Workspace удерживает процессный runtime независимо от текущих поверхностей: [Host::retain_process](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/host.rs#L75-L85), [runtime registry/retention](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/mod.rs#L204-L239).
- Выключение может убрать badge/panel view, но runtime остаётся в `Workspace.extension_processes`; в production нет удаления из этой карты при toggle.

Причина: [observer](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L85-L103), [attach gate](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L138-L142), [stop](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L381-L398). Рабочий explicit restart: [restart](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime.rs#L166-L172).

## Проверки и границы

`make_probe.py` извлекает **из `git show HEAD`**, а не из изменённой рабочей копии, точные тела observer, stop, restart и attach gate. Диапазоны и SHA256 извлечений сохранены в `source-extractions.json`. Вокруг них минимальный инертный GPUI shell. `start` только считает попытки, он не имитирует успешный subprocess. Проверяем именно решение о запуске и сохранение ошибки.

- Текущий код: **4 passed**: два наблюдения сбоя и два положительных контроля.
- Desired invariant «после явного off/on сделать новую попытку» отдельно **FAIL**, exit101: 0 вместо 1.
- Локальный candidate `stop: self.error = None`: desired invariant + оба положительных контроля **3 passed**.
- Нативное GPUI-окно, реальное нажатие switch, настоящий subprocess, полная Desktop suite и portable **не запускались**. Поэтому это подтверждённый дефект state machine с source-backed UI reachability, не live-GUI observation.
- Production sources, refs, настройки и реальные данные не изменены; ничего не опубликовано.

## Кандидат исправления

`candidate-clear-stopped-error.patch` добавляет очистку прежней runtime-ошибки в `stop`. Это **не готовое к merge исправление**: здесь проверена только узкая lifecycle-логика. До публикации нужны штатный GPUI regression со switch, restart/reload/removal controls, focused Desktop tests. В частности, removal должен по-прежнему показывать своё явное «расширение удалено», выставляемое после stop.

Предпочтительный контракт: явное выключение освобождает прошлую ошибку; включение делает новую попытку. Если новый запуск опять неудачен, показывается новая актуальная ошибка. Это не означает автоматический бесконечный retry после падения.

## Дополнительный отрицательный результат

Проверена гипотеза, что восстановленный Terminal первоначально запускается в соседнем проекте до загрузки catalog, затем игнорирует исправленный cwd из Context. В рассмотренном bound-document пути она **не подтверждается**: `Host::workspace_path` возвращает None, пока нет metadata именно его root, а `Runtime::launch` не стартует без workspace. Из одного retained `id="shell"` нельзя делать вывод о неправильном cwd. Полный native restart/restore в этой проверке не запускался.

Также просмотрены scope announce/rehost, queue reset, session projection, popup retention, native field preparation и SDK context lifetime. Возможные interleaving-ошибки без доказанного штатного пути не объявлялись новыми findings.

## Повтор

```sh
python3 make_probe.py /path/to/Proteus-desktop
rustc --edition 2024 --test recovery_probe.rs -o recovery_probe
./recovery_probe --nocapture
./recovery_probe --ignored --nocapture # ожидаемо red на pinned HEAD
rustc --edition 2024 --test candidate_probe.rs -o candidate_probe
./candidate_probe --ignored --nocapture
./candidate_probe control --nocapture
```

Артефакты: `REPORT.md`, `make_probe.py`, оба `.rs` probes, source-extractions.json, verified-heads.txt, observed.log, required-red.log, candidate-green.log, candidate-clear-stopped-error.patch.
