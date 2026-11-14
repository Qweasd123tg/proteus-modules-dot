# Proteus Desktop: input echo race and retained field composition

Проверено 2026-11-13. HEAD повторно сверены с origin в `verified-heads.txt`:

- Desktop `75bf201764278eac4b50d156650edcf1429101ff`.
- Extensions `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.

Это новые findings, не повтор Git-tree keyboard, Steps traversal/action или Core question-input. Production checkout не менялся. Патч ниже существует только как отдельный кандидат и в изолированной probe-копии. Ничего не публиковалось. **Нативное окно, OS keyboard dispatch и screen reader не запускались.** Проверки точного тела production Input-ветки используют записывающие подстановки GPUI; отдельно запущен реальный Rust package Git с его синтетическим loopback API.

## 1. P2: быстро стёртый текст возвращается из запоздавшего echo расширения

Реальный затронутый контрол поставляемого пакета: шестистрочное поле сообщения Git-коммита. Тот же общий обработчик используется для обычных однострочных inputs/search и текстовых полей страниц.

Последовательность:

1. Последний accepted tree содержит `Input.value=""`.
2. Пользователь вводит `x`: InputEvent::Change отправляет action `message="x"`, action_sequence становится 1.
3. До ответа процесса пользователь удаляет `x`. Native input уже пустой, но **action с пустой строкой не отправляется**, sequence остаётся 1.
4. Git возвращает tree с `value="x"`, sequence=1. View не считает его устаревшим.
5. Reconciliation вызывает `set_value("x")`: стёртый текст появляется снова.

Причина: [Input Change guard](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/fields.rs#L345-L395) сравнивает новое native-значение с **последним accepted tree**, а не с последним отправленным значением. Возврат к ещё не обновлённому accepted value ошибочно принимается за отсутствие изменения. [Sequence guard](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/view.rs#L221-L234) помогает только если второе действие реально отправлено. Здесь оно подавлено раньше.

Проверка:

- Извлечена **вся** production match-ветка `Node::Input` (включая создание двух видов inputs, подписки, обработчик и retained update), без изменения тел. `make_probe.py`, `extractions.json`.
- Один и тот же сценарий `"" → "x" → ""` проверен для `lines=1` и `lines=6`: записано ровно одно действие `"x"`; локальный input пустой до echo; после принятия `"x"` он вновь содержит `"x"`.
- `native-actions.json` записан из результата этой exact-source пробы, не составлен вручную. Реальный Git package потребил trace своим `Extension::action`, затем создал настоящий `Git::panel`. Его commit input и `Git.message` равны `"x"`. Дополнительный clear-action успешно очищает оба: это дефект Desktop, не Git.
- Git fixture не исполняет commit, не меняет рабочий проект, после прогретого Fake не делает HTTP-запросов на действия message. Исходный Fake работает только с loopback и синтетическими данными.
- Контроли: `"" → "x" → "y"` отправляет оба значения; удаление **после** принятия первого echo отправляет clear; программный `set_value` не создаёт action.

Логи: `observed.log`, `git-trace.log`, `git-full.log`, `required-red.log`.

### Кандидат исправления

`candidate-send-all-input-changes.patch` убирает сравнение Change с stale accepted value и ненужный capture `identity`. На отдельной копии этого же exact-source harness desired clear-тест стал зелёным, четыре контроля также зелёные. `candidate-green.log`.

Обоснование: настоящие InputState и TextareaState являются разными специализациями InputBaseState; [его `set_value`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/vendor/gpui-base/src/input/base/state.rs#L1299-L1328) явно подавляет InputEvent::Change. Для предотвращения echo loop этот guard не нужен. Если позднее потребуется dedup, сравнивать следует с последним локально отправленным значением и не терять возврат к accepted value.

Это **не готовая к merge production-правка**: полный Desktop build/gate и native typing/reconnect/close сценарии не запускались. Нужен нативный regression с удержанным ответом процесса и быстрым вводом/удалением, в том числе Undo и очисткой search.

## 2. P2/P3: изменение `Input.lines` при сохранённом id не меняет тип/режим input

Это подтверждённый дефект динамического публичного widget-контракта. Стандартный пакет, который уже меняет lines того же id таким образом, в этой проверке не найден. Поэтому текущий охват поставки ограничен; разумный приоритет P3, P2 для поддерживаемой динамической формы SDK.

### Из multiline в search: контрол исчезает

- Первый валидный tree: `id=message`, `lines=6`, `search=false` → создаётся `Text::Area`.
- Второй валидный tree: **тот же id**, `lines=1`, `search=true` → остаётся `Text::Area`.
- [Search render](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/render.rs#L280-L306) принимает только `Text::Line`, для Area возвращает `None`, затем пустой div. Свежий mount второго tree корректно создаёт Line.

Это не недопустимый `search=true, lines=6`: оба tree проходят настоящие serde parser и `Node::validate()`. Отдельно штатный schema-test `compact_search_is_an_explicit_single_line_input` подтверждает, что исходно нелегальную комбинацию schema действительно отвергает.

### Из 2 строк в 6: высота устаревает, а после синхронизации снова откатывается

- При неизменном value `lines=2 → lines=6` сохраняет min_rows=2: `layout_changed` сравнивает только grow/value, не lines.
- Изменение value заставляет retained branch вызвать resize с новыми 6 строками.
- Следующий настоящий пользовательский Change вызывает сохранённую подписку с **захваченным при создании `min_rows=2`**, и размеры снова становятся 2.

Обе части воспроизведены exact-source Input-веткой и exact-source `textarea::resize`. Контроль первоначального mount с lines=6 держит 6. Отдельные desired regressions красные. Геометрия нативного окна не измерялась: доказаны state/type/rows и дальнейший render-выбор, не визуальный screenshot.

Причина и направление исправления: [retained branch](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/fields.rs#L335-L362) не хранит актуальный lines и не меняет вариант Line/Area; [подписка](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/declarative/fields.rs#L396-L421) использует старый min_rows. Хранить актуальные параметры у retained field; при переходе через границу 1↔multi согласованно менять entity и Enter policy, сохраняя текст/фокус/selection насколько возможно. При изменении только числа multiline-строк не пересоздавать поле, а обновлять размер и брать текущий min_rows при дальнейших событиях. Патч для этого дефекта не заявляется подготовленным.

## Проверенный объём и границы

- Baseline: **8 observations/controls + 1 исходный schema control + 36 Git tests = 45 passed**.
- Отдельно **3 desired regressions намеренно красные**; это не compilation failures.
- Кандидат для finding 1: **1 desired regression + 4 controls = 5 passed** на отдельном target.
- В GPUI-shim Textarea preview возвращает None; длинные disclosure previews, OS focus, геометрия и native event loop здесь не проверялись. Фактический native `set_value` сверялся по исходнику, не исполнялся в GUI. Unrelated icon validation заменена stub, fixtures не содержат иконок. Поэтому полный schema-suite не заявляется.
- Реальный Git package не использует GPUI-shim, но его действия вызываются in-process стандартным тестовым Fake, не через полный NDJSON Desktop↔process transport.
- Проверялись сохранение Input state, callbacks и режимов; видимость/фокус в контейнерах, retained tree/list/lanes/code, связанные production producers. `coverage.tsv` указывает прочитанные диапазоны, не обещает полный построчный аудит всех файлов.
- Известные Steps/action и Git-tree keyboard проблемы не пересчитывались. Другие видимые retained-action/callback места в Graph/Tree/List не выданы за новые самостоятельные findings.
- Production `git diff --check` чистый, tracked-файлы Desktop не изменены. Нет GUI/full Desktop/portable gate.

## Повтор

Поместить `audit-ui-composition` в корень Desktop checkout указанного SHA:

```sh
python3 audit-ui-composition/make_probe.py
CARGO_TARGET_DIR="$PWD/audit-ui-composition/target" cargo test --locked --manifest-path audit-ui-composition/probe/Cargo.toml audit:: -- --nocapture
CARGO_TARGET_DIR="$PWD/audit-ui-composition/target" cargo test --locked --manifest-path audit-ui-composition/probe/Cargo.toml audit:: -- --ignored --nocapture # ожидаемо 3 red
python3 audit-ui-composition/make_candidate.py
CARGO_TARGET_DIR="$PWD/audit-ui-composition/fixed-target" cargo test --locked --manifest-path audit-ui-composition/fixed-probe/Cargo.toml audit::required_clear_before_echo_is_sent -- --ignored
CARGO_TARGET_DIR="$PWD/audit-ui-composition/fixed-target" cargo test --locked --manifest-path audit-ui-composition/fixed-probe/Cargo.toml audit::control_
```

Git: pinned Extensions HEAD разместить в `audit-ui-composition/extensions`, применить `git-native-trace-repro.patch`; `native-actions.json` должен находиться рядом с extensions. Запускать `cargo test --locked --manifest-path audit-ui-composition/extensions/Cargo.toml -p extension-git` с отдельным CARGO_TARGET_DIR. Базовые source fixtures и библиотеки не изменять. Для каждого изменённого checkout использовать отдельный target, чтобы не принять чужой cached test executable за новый прогон.
