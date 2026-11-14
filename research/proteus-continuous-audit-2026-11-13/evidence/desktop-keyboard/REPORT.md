# Proteus Desktop: keyboard/accessibility and composed-widget audit

Проверено 2026-11-13. Удалённый HEAD совпадает с checkout:
- Desktop: `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Точный вывод: `verified-heads.txt`.

Production-исходники не менялись, коммитов/PR/публикации нет. Проверки синтетические, без настоящих пользовательских сессий, провайдеров и Git-операций над рабочим проектом. **Нативное окно и screen reader не запускались.** Ниже не утверждается полный GUI-pass.

## 1. P2: индивидуальные Git-checkbox недоступны через клавиатуру дерева

Путь пользователя: сфокусировать Changes tree, выбрать нужный файл стрелками, нажать Space. Вместо stage/unstage клиент открывает preview файла.

Причины в связке:
- [`Tree::key`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/tree.rs#L278-L336) для Space всегда отправляет `select`; ни одна поддержанная клавиша не отправляет `check`.
- [`toggle::checkbox`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/toggle.rs#L13-L47) рисуется кастомным `Div` без focusable/tab stop/checkbox role/checked semantics. Callback `check` подключён только к его `on_click` в `tree_row.rs`.
- Запасной item-menu привязан к mouse-right в [`ContextMenu`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/context.rs#L195-L205). Код не регистрирует Shift+F10/context-menu action для текущей строки дерева.
- Реальный [`Git::tree`](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/list.rs#L28-L49) превращает `check` в `/workspace/stage` или `/workspace/unstage`, а `select` в browse_document.

Проверка:
1. Из production-файла без изменения тела извлечены `Tree::key`, `step`, `act`, `act_at`. Headless stubs записывают исходящие события. Space на checked/unchecked/обычной строке даёт `select`; перебор поддержанных клавиш не даёт `check`.
2. Реальный package Git + SDK + его loopback Fake: событие `select` выдаёт `open_document` с `preview:true`, **0 stage/unstage HTTP**. Контроль `check` делает **1 `/workspace/stage` для b.py**.
3. Все тесты isolated `extension-git`: **36/36**, в том числе новый уникальный audit-test.

Логи: `observed.log`, `git-keyboard.log`, `git-full.log`. `required-red.log` содержит отдельно намеренно красный тест желаемого Space→check, не ошибку сборки.

Что исправлять: дать check отдельный реальный клавиатурный путь; для checkable row естественный вариант Space→check, Enter оставить открытием. Добавить корректные checkbox role/name/checked/mixed semantics и доступ к row menu с клавиатуры. Проверить в native-окне и со screen reader. Отдельный Stage All остаётся возможным и **не заменяет** индивидуальный stage/unstage. Это не утверждение, что весь Git недоступен с клавиатуры.

## 2. P2: валидный Steps внутри SettingRow молча исчезает

Минимальная fixture: `steps-setting-row.json`.

Связка:
- [`Node::SettingRow::check`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/declarative/widget.rs#L588-L604) валидирует вложенный `control`; допустимый `Steps` проходит реальный serde parser и `validate()`.
- `Node::visit` обходит этот `control`, поэтому `prune_fields` знает о Steps-id и оставляет старый экземпляр, если он был.
- Но [`prepare_steps`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/view.rs#L585-L641) перечисляет контейнеры вручную и **не обходит SettingRow**.
- [`render Steps`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/render.rs#L441-L446) рисует только `self.steps.get(id)`. Нет prepared state → пустой контрол без validation error.

Воспроизведение на настоящей схеме и неизменённом `prepare_steps`:
- Top-level Steps: prepared controls = 1.
- Тот же Steps в SettingRow: schema validate OK, visit видит 1 Steps, prepared controls = 0.
- Если сначала создать top-level id, затем переместить его в SettingRow и прислать новые options/selected: сохранённый экземпляр остаётся со **старыми** options и selected, хотя новый root валиден.

Логи: `steps-observed.log` и `steps-required-red.log`; оригинальный schema-test `settings_rows_visit_and_validate_their_one_control` тоже проходит (`schema-controls.log`).

Граница: это подтверждённая композиция разрешённых SDK nodes в синтетической extension-форме. Не утверждается, что текущий стандартный model popup уже выдаёт именно такую форму. Нативная отрисовка не запускалась: отсутствие подготовленного child подтверждено headless, итоговая пустая область следует из render ветки.

Исправление: обходить `SettingRow.control` при подготовке Steps; лучше согласовать ручные обходы с единым `Node::visit`, не нарушая локальное состояние. Тестировать first mount и reparent существующего id.

## 3. P2/P3: сохранённый Steps-id отправляет старый action после обновления дерева

Отдельный от №2 дефект в той же функции. Без SettingRow:
1. root Steps `id=effort`, `action=old_action`, selected=0.
2. Новый валидный root с тем же id: `action=new_action`, selected=1.
3. Удержанный контрол показывает новую selected=1.
4. Вызов его changed callback отправляет **old_action**, не new_action.

[`prepare_steps:601–618`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/view.rs#L601-L618) обновляет только options/selected. Замыкание с action создаётся единственный раз. Это нарушает соответствие актуального widget tree и реального действия. В соседнем Picker путь уже обновляет callback через `set_pick` на каждом accepted tree.

Подтверждено exact-source `prepare_steps` и callback-recording entity stubs. Fixtures `steps-action-before.json`/`steps-action-after.json`; наблюдение зелёное, требование new_action красное. Никакого реального внешнего действия тест не совершает.

Граница: синтетическая динамическая extension-форма; стандартный пакет с меняющимся action того же Steps-id не найден в этой проверке. Поэтому приоритет P2 для публичного UI-контракта, P3 по подтверждённому текущему охвату поставляемых пакетов.

Исправление: обновлять handler вместе с состоянием, как Picker, либо диспетчеризовать актуальный action по id. Не пересоздавать весь контрол без необходимости, чтобы не терять drag/focus state.

## Кандидат: Enter на следующем вопросе оставляет фокус старого input

В `request_user_input` ввели свободный ответ в q1 из двух вопросов и нажали Enter. Подписка InputEvent вызывает `next_question`; она меняет page на q2, но фокус перенаправляет только после **последнего** вопроса. Старый input сохраняется в `UserInputDrafts.texts`, но больше не монтируется.

Exact-source `next_question` + `advance` с recording Window показывают page=1 и прежний focused handle `input:r:q1`. Контроль последнего вопроса явно возвращает composer focus. См. [`question_card:224–239`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/question_card.rs#L224-L239), `user_input.rs:88–111`, `observed.log`.

**Не считать доказанным живой keyboard-lock:** автоматическое восстановление фокуса внутри GPUI не тестировалось. Нужен native-сценарий q1→Enter→ввод в q2, обратные/прямые pager-кнопки, затем Tab/Shift+Tab. Это не старый rehost-finding: здесь окно одно, меняется текущий вопрос.

## Метод и проверяемый объём

- `make_probe.py`: извлекает 6 production методов. `extractions.json` хранит диапазоны и SHA256 тел. Только GPUI окружение заменено минимальными recording stubs; OS key dispatch и focus tree не имитируются как доказательство native поведения.
- `make_steps_probe.py`: настоящие schema modules, validate/visit; `prepare_steps` без правки тела. GPUI Entity/Context и Stepper-хранилище заменены recording stubs. Для unrelated icon validator stub; в fixtures нет иконок. Единственная адаптация копии `widget.rs`: явный path к его существующим tests.
- `extensions/`: изолированный archive pinned Extensions HEAD, один audit-test добавлен к Git test module. `git-keyboard-repro.patch` воспроизводит добавление. Уникальный CARGO_TARGET_DIR, не общий stale target.
- Итог: **6 source-method observations/controls + 4 schema/prepare observations + 1 исходный schema-control + 36 Git tests = 47 passed**. Отдельно **4 намеренно красных desired regressions**. 23 прочих schema/related tests не заявляются пройденными. Full Desktop/portable/GUI не запускались.
- Проверены текущие keyboard routes: общие search/picker/Pressable, settings page navigation/dismiss, session list, Core question-card, declarative tree/list/lanes/Steps и вложенность SettingRow. `coverage.tsv` указывает реально прочитанные диапазоны; полный построчный аудит всего репозитория этим отчётом не заявляется.

## Повтор

В Desktop checkout той же ревизии:

```sh
python3 audit-accessibility/make_probe.py
rustc --edition=2024 --test audit-accessibility/probe.rs -o audit-accessibility/probe-tests
audit-accessibility/probe-tests --nocapture
audit-accessibility/probe-tests --ignored --nocapture # ожидаемо 2 red
python3 audit-accessibility/make_steps_probe.py
CARGO_TARGET_DIR="$PWD/audit-accessibility/steps-target" cargo test --locked --manifest-path audit-accessibility/steps-probe/Cargo.toml audit::
CARGO_TARGET_DIR="$PWD/audit-accessibility/steps-target" cargo test --locked --manifest-path audit-accessibility/steps-probe/Cargo.toml audit:: -- --ignored # ожидаемо 2 red
```

Для Git: отдельный Extensions checkout указанного SHA, применить только `git-keyboard-repro.patch`, выполнить `cargo test --locked -p extension-git` с собственным target. Внешний Core не нужен: используется штатный синтетический loopback Fake.
