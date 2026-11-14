# Proteus: Files rename, несколько runtime и rehost

Проверено 2026-11-13. Оба origin HEAD сверены перед прогоном, изменений относительно предыдущего прохода нет:

- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Production sources не менялись, ничего не публиковалось. Все файловые операции в сценариях выполняет **in-memory loopback fixture**, а не настоящий рабочий проект. Реальные неизменённые Rust-бинарники Files и SDK получают NDJSON. Нативное GPUI-окно и физический перенос таба не запускались.

## 1. P2: rename теряет документы, известные только соседнему Files runtime

### Наблюдение

Две поверхности одной сессии могут принадлежать разным процессам Files. У runtime B открыта панель, у A открыт `src/remote.rs`. В B выполняется штатное переименование папки `src → lib`.

- POST `/workspace/rename` успешно завершён, fixture содержит `lib/remote.rs`.
- B **не отправляет ни одного** `retarget_document`: сам B не держит документ `src/remote.rs`.
- A продолжает держать аргумент `src/remote.rs`. Сначала может показываться закешированный текст со старым заголовком.
- После обычного `run_settled` кеш очищается. Настоящий Files A запрашивает `/workspace/file?path=src/remote.rs` и показывает `Fixture file not found: src/remote.rs`.
- Если B держит другой документ `src/local.rs`, приходит только пара `src/local.rs → lib/local.rs`. Документ A по-прежнему пропущен.

Контроль: те же панель и документ в **одном runtime**, с настоящим NDJSON `rehost` документа, корректно дают пару `src/remote.rs → lib/remote.rs`; документ остаётся читаемым и после invalidation.

### Почему это достижимо

Desktop выбирает runtime по паре `(host.identity(), extension)`, у независимых окон identity различаются. Отдельно воспроизведён протокольный маршрут: A перемещает документ в окно B, в котором Files panel **уже был создан** в своём runtime. Перенос меняет runtime только у перемещаемой поверхности; готовая панель B продолжает удерживать собственный `DeclarativeView.runtime`.

- [Выбор и регистрация runtime](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/mod.rs#L193-L250).
- [Rehost переносит одну attachment](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/scopes.rs#L307-L357).

Физическое действие мышью не проверялось. Достижимость описана по production sources, а последствия выбранной последовательности проверены на реальных процессах.

### Причина

[Files::moved_documents](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/operations.rs#L125-L156) строит пары только из `self.document_views`, то есть локальных владельцев этого instance/process. Возвращаемая карта не включает документы других runtime. Rename сначала успешно меняет файловую систему и только после этого вызывает данный retarget.

Desktop уже умеет рассылать точную пару другим runtime, но сравнивает аргументы **точно**, без folder-prefix семантики. Он не может восстановить отсутствующую пару из нулевого/неполного сообщения:
[retarget_document и retarget_arguments](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/documents.rs#L5-L65).

В harness этот exact-pair fanout смоделирован, не исполняется в GPUI. Главный факт подтверждён независимо от модели host: отсутствуют сами нужные outgoing пары, поэтому штатному host нечего доставлять.

### Дополнительный P3-эффект: diff-режим теряется, даже если пара есть

Другой сценарий: оба процесса знают `src/remote.rs`, соседний A переключён на Changes/diff. B переименовывает папку и отправляет правильную пару. После штатного host render с новым аргументом A отображает **File** вместо diff. В одном runtime тот же сценарий сохраняет diff.

Это также воспроизведено настоящими бинарниками, не имитацией Files. `moved_documents` переносит `modes` только у отправителя. Соседний runtime получает просто `render(argument=new)`, его `track_document_view` освобождает старый документ, но не переносит mode; `document()` использует для нового пути default `file`.
[Документ и его mode](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/document.rs#L14-L49).

Это не потеря содержимого файла. Не считать дополнительным P2; это меньший эффект неполной межпроцессной передачи rename-состояния.

### Направление исправления

Разделить успешную файловую операцию и доставку переименования всем живым экземплярам пакета в той же connection/session. Нужен общий source of truth открытых аргументов либо scoped package rename-notification, после которого каждый Files instance переносит собственные документы и modes. Просто всегда отправлять `from → to` поможет для файла, но **не покрывает документы-потомки при rename папки**. Не добавлять скрытую Files-specific prefix семантику в общий opaque-document контракт.

## 2. P2-кандидат с подтверждённым состоянием: rehost выбрасывает живой старый runtime из broadcast targets

Это отдельный дефект host registry, не повтор Git History/global-tab.

1. В `Runtimes` есть `(window A, files) → runtime A` и `(window B, files) → runtime B`.
2. Открытая панель B продолжает владеть runtime B через `DeclarativeView.runtime`.
3. Перенос документа A в B вызывает `rehost_runtime(A, host B)`.
4. Обычный HashMap insert **заменяет** запись `(B, files) → B` на `(B, files) → A`.
5. `invalidation::runtimes("files")` перечисляет только реестры, дедуплицирует A и возвращает `[A]`, хотя B всё ещё жив и обслуживает существующую панель.

Выполнены **точные неизменённые тела трёх production функций** `rehost_runtime`, `targets`, `runtimes` с минимальными подстановками GPUI Entity/WeakEntity/Globals. Это проверка реальной логики реестра и владения через Rc/Weak, не полноценный GPUI-тест. `registry-extractions.json` фиксирует диапазоны/хеши извлечённого кода.

- Observation: targets `[101]`, существующий panel runtime `202` жив.
- Required invariant «включить живой 202» падает.
- Контроль: если у B остался другой зарегистрированный alias, возвращаются A+B; unrelated package исключён, aliases корректно дедуплицируются.

**Подтверждено:** живой runtime пропадает из набора адресатов. **По коду следует:** такой runtime пропускается при `invalidate_content`, `invalidate_surfaces` и `retarget_document`. Реальную потерю refresh на нативном экране в этом проходе не наблюдали. В частности, Files retarget может обновить layout/workspace, но не attached argument вытесненного runtime; end-to-end проявление этой дополнительной цепочки пока не тестировалось.

Источники:

- [Перезапись регистрации](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/mod.rs#L242-L250).
- [Выбор всех runtime только из реестров](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/runtime/invalidation.rs#L10-L83).
- [Существующая view сохраняет Entity runtime](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/view.rs#L35-L64).

Направление исправления: не смешивать индекс «какой runtime выбрать для новой поверхности в этом host» с реестром **всех живых runtime** для broadcast/reload/retarget. Второй индекс может содержать слабые ссылки по runtime identity и чистить мёртвые. Отказ от overwrite без согласованной политики открытия/переноса тоже меняет поведение, поэтому это не готовый локальный patch.

## Проверки и ограничения

- Штатные Files: **24 passed**, без production edits.
- NDJSON: 4 сценария path ownership + 2 сценария mode = **6 подтверждённых observations/controls**.
- Exact-source registry: **2 passed**, отдельный desired invariant ожидаемо red.
- Всего три desired проверки отдельно падают: missing remote document, lost diff mode, missing live runtime. Это regression assertions, не compilation failures.
- SDK per-session Instances/scopes/close/rehost прочитаны. InputBaseState автоматически вызывает `rehost` из render: отсутствие явного вызова для declarative inputs **не выдано за новый дефект**. EventCursor использует глобальный atomic ChatEvent projection id, а не per-chat счётчик: предполагаемый cross-session low-id drop опровергнут.
- Не проверены: нативное окно, GPUI event dispatch, full Desktop test suite/build/portable, живой Core, ОС filesystem rename, реальные пользовательские проекты. Свойства HTTP rename симулирует fixture; путь Files→SDK и NDJSON transport настоящий.
- Git global tab, short/full hash, прежний SDK late ACK и render-error-on-rehost не повторялись как findings.

## Артефакты и повтор

`repro_files_views.py`, `repro_files_mode.py`, шесть JSON traces с input/output/API, `observed.log`, `mode-observed.log`, отдельные `*-required-red.log`, `files-baseline.log`, `verified-heads.txt`, `source-provenance.json`, `registry_probe.rs`, `make_registry_probe.py`, `registry-extractions.json`.

В каталоге evidence собрать неизменённый Extensions checkout указанного SHA:

```sh
CARGO_TARGET_DIR="$PWD/target" cargo build --locked --manifest-path /path/to/Proteus-desktop-extensions/Cargo.toml -p extension-files
python3 repro_files_views.py
python3 repro_files_mode.py
python3 repro_files_views.py --require-fixed  # ожидаемо red
python3 repro_files_mode.py --require-fixed   # ожидаемо red
CARGO_TARGET_DIR="$PWD/target" cargo test --locked --manifest-path /path/to/Proteus-desktop-extensions/Cargo.toml -p extension-files
python3 make_registry_probe.py --desktop /path/to/Proteus-desktop
rustc --edition 2024 --test registry_probe.rs -o registry_probe
./registry_probe --nocapture
./registry_probe --ignored --nocapture       # ожидаемо red
```

Бинарник и Cargo target не включены в ZIP. Build source identity и binary hash сохранены в provenance. Никакого production-патча или заявления о готовности к merge нет.
