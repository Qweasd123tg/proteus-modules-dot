# Desktop: восстановление догрузки истории

Патч для `Proteus-harness/Proteus-desktop` на точной базе
`5748ac04f78eaffa1f4ea6102bd349ca61412e8d`.
Это отдельный пакет изменений для просмотра в
`Qweasd123tg/proteus-modules-dot/performance/2026-10-26/desktop/`,
а не изменение исходников модулей и не публикация в upstream Desktop.
Контекст патча сохраняет лицензию исходных файлов Desktop (GPL-3.0-or-later).

## Исправление

Снимок сессии мог отменить выполняющуюся загрузку старой страницы, оставив
верхний край списка защёлкнутым. Даже неизменившийся reconnect snapshot
останавливал догрузку до прокрутки вниз и обратно.

* Production-used `HistoryRequests` выдаёт уникальный ticket каждому запросу.
  Отмена и запоздавший/дублированный ответ не освобождают слот нового запроса.
* Снимок повторно разрешает запрос у текущего верхнего края **только если**
  действительно отменил выполнявшийся запрос. Положение списка не меняется.
* Ошибка HTTP или несовместимая страница не запускают автоматический повтор
  при render или при idle snapshot. Существующее уведомление становится
  постоянным, с явным «Повторить»; обычные уведомления сохраняют свой таймер.
  Новый запрос очищает только уведомление истории. Double click остаётся
  single-flight. Dismiss сознательно убирает уведомление; выход за порог
  верхних строк и возврат остаются альтернативой для повторной попытки.
* Revision/cursor, смежность страницы, порядок строк, проверка префикса и
  prepend/scroll-anchor алгоритм не изменены. Нет новых таймеров, фонового
  retry-loop, изменения протокола, CI-триггеров или renderer-оптимизаций.

Retry повторяет существующий компактный notice/kit-button стиль; поведение
подтверждено по Zed `crates/ui/src/components/banner.rs`, commit
`2c335b81dc94d109bfcf05e8e54aba208837b33a`, строки 177–183.
Прочитаны upstream `AGENTS.md` и `DESIGN.md`; дочерних `AGENTS.md` в дереве нет.

## Применение в отдельном проверочном checkout

```sh
test "$(git rev-parse HEAD)" = 5748ac04f78eaffa1f4ea6102bd349ca61412e8d
git apply --check "$BUNDLE/desktop-pagination-retry.patch"
git apply "$BUNDLE/desktop-pagination-retry.patch"
```

`BUNDLE` — абсолютный путь к этой папке. Скрипт тестов ниже ничего не получает
из сети, не меняет checkout и проверяет SHA всех семи patched source files.

## Целевые проверки

1. Лёгкий semantic gate: Rust 1.95, только standard library, без Cargo/GUI/API.
   Он компилирует **реальный production helper из применённого патча**, а не
   отдельную копию state machine:

   ```sh
   python3 "$BUNDLE/tests/run_flow_tests.py" "$UPSTREAM"
   ```

   Четыре теста: отмена и повтор на том же краю; ошибка + 100 redraws + idle
   snapshot без auto-retry; уход пользователя от края; несколько отменяющих
   снимков до следующего render. Также проверяются stale/duplicate completion
   и single-flight при повторном клике.

2. Native source unit gate из patched Desktop checkout:

   ```sh
   python3 scripts/test.py ui::chat::history -- --nocapture
   ```

   Фильтр включает четыре helper-теста, три новых History regression tests и
   два существующих теста префикса. Нужны Rust 1.95, разрешённые Cargo/Git
   зависимости и Linux build packages GPUI (xcb, xkbcommon-x11, fontconfig,
   freetype и остальные зависимости upstream). Display server для этих
   обычных `#[test]` не требуется. Canonical runner также готовит закреплённые
   extensions и выполняет license check перед Cargo workspace test. Для
   диагностики только native binary: `cargo test --locked -p proteus-native
   ui::chat::history -- --nocapture`. Никаких реальных сессий/API-ключей.

3. До принятия upstream всё ещё нужны полный `python3 scripts/test.py` и
   native-window QA по AGENTS: медленная страница → unchanged reconnect →
   late reply; ошибка → idle snapshot → Retry; двойной Retry; уход от края
   до reconnect; стабильный якорь при prepend; revision rewrite/clear.
   Сборка portable и native UX в этой подготовке не выполнялись.

## Что реально проверено здесь

* Git blob SHA каждого исходника совпал с точной upstream базой.
* `git apply --check`, применение к изолированному подмножеству исходников и
  сравнение patched Git blob SHA выполнены успешно.
* `rustfmt 1.95 --edition 2024 --check --config skip_children=true` выполнен
  для шести изменённых Rust-файлов.
* Python runner проверен синтаксически; **не запускался**.
* Rust unit tests, Cargo build, полный gate, native UI и скорость **не запускались**.

Исполняемого fail-before/pass-after результата пока нет. Старый baseline
не содержит извлечённого helper/API этих тестов; его compile failure не будет
выдаваться за доказательство регрессии. Первоначальная ошибка установлена
по source control flow. CI должен отдельно сообщить фактические результаты.
Точные source SHA и checksum патча находятся в `provenance.json`.
