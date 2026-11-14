# Files / SDK: активность другой сессии отменяет периодическое обновление

Проверено 2026-11-13. **Один новый P2**, не повтор split-focus, startup navigation, Expand All или временной ошибки list. Production-код не менялся, публикации нет.

## Версии и границы

- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Оба HEAD совпали с `git ls-remote origin HEAD` в этом проходе.
- Extensions взят через `git archive HEAD`, Files собран в новом отдельном Cargo target. Работает настоящий неизменённый Files+SDK бинарник с JSON Lines stdin/stdout. HTTP API подменён только синтетическим сервером на `127.0.0.1`.
- Пятисекундный таймер не ускорялся и не подменялся. Нативный GPUI-клиент и живой Core в этом проходе не запускались. GUI-достижимость описанного маршрута проверена по коду, не кликами.

## Сценарий и результат

В source-окне есть Files panel и открытый документ сессии A. Документ имеет отдельный стабильный context, как в Desktop. Он переносится через штатный `rehost` в detached context, прежний document context закрывается. В detached явно передаётся `navigation_changed(document="watched.rs")`, поэтому документ A корректно известен как активный.

Затем source panel переключается на сессию B. Синтетический файл A меняется `OLD → NEW`. В source B в течение 11 секунд поступают обычные `navigation_changed` раз в 0.5 секунды, например при переключениях вкладок. Detached context A не получает этих событий.

| Режим | HTTP-чтений файла A за всё окно, включая исходное | Новых document view | Обновление |
|---|---:|---:|---|
| Две сессии, 22 события в source B | 1 | 0 | Нет, остаётся OLD |
| Две сессии, source B без событий | 3 | 2 | NEW на первом штатном poll |
| Одна сессия, те же 22 события | 3 | 22 | NEW после истечения срока кэша |

Как только трафик B прекращается, очередной настоящий poll примерно через 4.7 секунды после конца окна перечитывает файл A и выдаёт NEW. От момента последнего входящего сообщения до этого poll проходит около пяти секунд. API всё время доступен; файл не закрывается и не перестаёт быть активным. Это исключает прежние дефекты отсутствующего `active_document`, split focus, отказа API и closed-cache.

Факт измерен на 11-секундном окне. Неограниченное продление задержки при непрерывном потоке с интервалами менее пяти секунд следует из control flow SDK, а не из бесконечного замера. У двух независимо запущенных процессов такого общего таймера нет, поэтому результат не надо обобщать на любые два окна.

## Причина

[SDK `run`, строки 812–827](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host.rs#L812-L827) на каждой итерации вызывает `recv_timeout` с полной длительностью `poll`. Любое входящее сообщение заново начинает ожидание, даже если относится к другой сессии. `render_every_context` вызывается только при полной тишине на протяжении интервала.

При этом обычное событие вызывает [рендер только текущей сессии](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/sdk/src/host.rs#L555-L574). Такое ограничение нужно для изоляции, но в сочетании с process-wide idle timer оставляет другую сессию без единственного пути refresh. [Проверка возраста кэша Files](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/document.rs#L56-L82) находится внутри render, поэтому сама ничего не исправляет: до render выполнение не доходит.

Комментарий SDK определяет poll как перерисовку «без сообщений клиента». Для старого односессионного цикла это работало: входящее событие само обновляло нужные виды. После поддержки нескольких сессий отсутствие тишины в одной уже не означает обновления остальных. Это дефект взаимодействия двух механизмов, а не отдельная ошибка таймера ОС.

## Достижимость общего процесса в Desktop

1. [Один runtime на workspace и extension](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/mod.rs#L192-L239). `session_dir` не входит в process key.
2. [`for_space` закрепляет документ за root без нового процесса](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/host.rs#L249-L258), а [context session](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/host.rs#L400-L428) предпочитает этот root динамически выбранному чату. Панель без `space` следует за выбором source.
3. [`detach_tab` создаёт окно и переносит существующий document entity](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/workspace/windows.rs#L344-L408).
4. [Runtime rehost](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L307-L352) не перезапускает процесс; он добавляет context и посылает Rehost существующему runtime. [Регистрация в новом окне](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/mod.rs#L242-L248) сохраняет этот же runtime.
5. [Scope events](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L263-L288) направляют session_opened/navigation_changed в context соответствующего окна. Поэтому source B и закреплённый detached A могут одновременно жить в одном process.

Нативный маршрут приведён как source trace. Проверенный wire начинается с тех же Context/Render/Rehost/Event сообщений, но не утверждает проверку оконного менеджера или GPUI defer ordering.

## Направление исправления

Отделить срок обновления от глобальной тишины stdin: хранить монотонный deadline и не отодвигать его из-за сообщений другой сессии. При истечении срока обслуживать нужные live contexts, сохраняя ограничение работы без live views и запрет production poll в Preview. Альтернатива: per-session deadlines. Не стоит безусловно рендерить все сессии на каждое чужое событие: это повышает нагрузку и разрушает полезную изоляцию.

Регрессия должна покрыть минимум: busy B / active A, busy same-session, спокойный процесс, close последнего view, Preview, изменение poll interval. Последние три здесь не проверялись как новая реализация, поскольку production-исправления не вносились.

## Проверки и воспроизведение

- `cargo build --offline --locked -p extension-files`: PASS.
- `cargo test --offline --locked -p extension-files -p proteus-extension`: 24 + 51 исходных теста PASS.
- `python3 repro_poll_starvation.py`: PASS как фиксация текущего дефектного поведения и двух положительных контролей.
- `python3 repro_poll_starvation.py --case busy --require-fixed`: ожидаемый FAIL по отсутствию refresh, не timeout/ошибка сборки.

На чистом checkout указанного Extensions SHA:

```sh
cargo build --locked -p extension-files
python3 /path/to/evidence/repro_poll_starvation.py --binary /path/to/checkout/target/debug/files
python3 /path/to/evidence/repro_poll_starvation.py --binary /path/to/checkout/target/debug/files --case busy --require-fixed
```

Полный прогон занимает около 40 секунд. `--case busy` около 17 секунд. Скрипту нужен соседний `wire_fixture.py`. Все пути, содержимое и credential marker синтетические. `busy-multisession-repro.json`, `idle-multisession-control.json`, `same-session-control.json` содержат полные входы/выходы и API-трассы, логи подтверждают сборку и baseline. `source-provenance.json` фиксирует исходники и бинарник.
