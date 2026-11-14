# Files: видимый split-документ ошибочно приравнен к скрытому

Проверено 2026-11-13, без публикации и production-правок.

- Extensions HEAD: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Desktop HEAD: `75bf201764278eac4b50d156650edcf1429101ff`.
- Оба удалённых HEAD непосредственно сверены в этом проходе.

## Результат: одна новая функциональная проблема, рекомендуемый P2

Files фоново перечитывает лишь файл из **focused pane**. При split layout соседний документ остаётся видимым, но получает политику скрытой вкладки: старый снимок сохраняется, пока пользователь не переведёт туда фокус или не придёт инвалидирующее событие.

Практический случай: пользователь смотрит чат/терминал слева и файл справа, который меняется снаружи приложения. Документ справа остаётся на экране, но фоновые проверки его не обновляют. Если изменение сделано агентом, `run_settled` в конце хода сбросит снимок; это не обеспечивает обновление во время хода или для независимых внешних изменений.

Это **не** известная ошибка отсутствующего `active_document` после startup/restart. В воспроизведении все штатные navigation events отправлены явно и корректно; механизм не выражает видимость нескольких pane вообще. Обе описанные конфигурации являются одним недостатком focus/visibility, а не двумя отдельными багами. Нынешняя реализация явно обещает poll только «активного» документа; результат следует квалифицировать как функциональную лакуну многопанельного режима, а не утверждать, что она нарушает уже существующий plural-visible протокол.

## Проверенное поведение

1. Настоящий, неизменённый crate `proteus-tabs` создал валидный layout:
   - `left.rs` и `right.rs` присутствуют в `TabLayout::visible()`;
   - focused pane показывает `left.rs`;
   - `hidden.rs` открыт, но не видим.
2. Реальный Files+SDK бинарник получил `hello → context → render` для трёх документов и **явный** `navigation_changed(document="left.rs")`.
3. Loopback fixture изменил тексты всех трёх файлов с OLD на NEW.
4. После двух настоящих 5-секундных poll (около 10 секунд):
   - левый видимый документ: NEW, **3 HTTP-чтения** включая начальное;
   - правый видимый документ: OLD, **1 HTTP-чтение**;
   - скрытый документ: OLD, **1 HTTP-чтение**. Это правильный контроль ленивого обновления действительно скрытой вкладки.
5. Перевод фокуса на правую pane обновил `right.rs` сразу до NEW.
6. Настоящий TabLayout переключил левую pane на чат. `right.rs` по-прежнему входит в visible, но выбор `Host::active_document` теперь даёт null. После повторного изменения правого текста до NEWER и ещё одного реального poll он остался NEW.
7. Контроль `run_settled`: все три снимка перечитаны, правый стал NEWER. Повреждения API, cache entry или способа отображения текста нет.

Полные NDJSON input/output и HTTP query сохранены в `split-refresh.json`. `tabs-layout.json` содержит реальные layouts и результаты `visible()`/focused selection. Сценарий выполнен повторно для desired-regression проверки.

## Причина и источники

Native host выбирает ровно `layout.active(layout.focused)`, затем отбрасывает вкладку, если она принадлежит не Files:
[host.rs L453–465](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/extensions/host.rs#L453-L465).

Но модель вкладок отдельно определяет visible как активную вкладку **каждой** pane:
[layout.rs L132–142](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/crates/tabs/src/layout.rs#L132-L142).
Нативный renderer действительно строит содержимое каждой pane по `pane.active`, не ограничиваясь focused:
[render_pane L219–253](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/view.rs#L219-L253).

Files проверяет давность уже существующего снимка только при точном равенстве `host.active_document == path`:
[document.rs L56–82](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/files/src/document.rs#L56-L82).
Таким образом при исправно работающем таймере видимый, но unfocused документ никогда не проходит условие stale. Нынешнее событие протокола передаёт одно поле document, поэтому у расширения нет данных, чтобы отличить его от действительно скрытого retained view.

## Направление исправления

Разделить focused/selected document для навигации и набор **видимых** document surfaces для обновления. Передавать видимость из Desktop через согласованное расширение публичного контракта и использовать её для Files cache freshness. Нельзя просто перечитывать все retained documents: это отменит существующее намеренно ленивое поведение скрытых вкладок.

Regression должен проверять одновременно:
- две видимые document panes обновляются независимо от focus;
- focused chat + соседний document обновляет видимый документ;
- truly hidden retained document по-прежнему не вызывает HTTP reads;
- закрытие/смена pane убирает прежнюю видимость;
- startup/restart получают актуальную видимость, но это отдельная уже известная ветка.

В этом проходе исправление не вносилось.

## Что исполнено, а что нет

**Исполнено:**
- реальный `proteus-tabs` из свежего `git archive HEAD`, отдельный Cargo target;
- настоящий ранее чисто собранный Files+SDK binary, SHA-256 повторно проверен по build provenance;
- все участвующие Files/SDK source blobs сверены с текущим HEAD;
- реальные HTTP, stdin/stdout и таймеры 5 секунд; время не подменялось;
- Files baseline: **24 passed**;
- tabs baseline: **62 passed**, doctests 0;
- observation assertions: passed;
- desired regression `--require-fixed`: **expected failed** по содержимому правого видимого документа, не по timeout или сбою сборки.

**Не исполнено:** native GPUI окно, реальные клики/drag split, настоящий Core, OS file watcher или модель. В маленьком headless probe выполнены реальные operations/visible/active/split_document crate tabs; выбор document повторяет точное выражение Native Host после его ownership/lifetime checks. Сам GPUI Host не объявляется исполненным. Static source связывает этот результат с native renderer и outgoing event. Синтетический сервер подменяет только файловое API; пользовательские файлы/аккаунты не использовались.

## Повтор

```sh
cargo run --offline --manifest-path tabs-probe/Cargo.toml > tabs-layout.json
python3 repro_split_refresh.py --binary /path/to/unchanged/files
python3 repro_split_refresh.py --binary /path/to/unchanged/files --require-fixed # expected red
```

Для сборки Files на указанном SHA: `cargo build --locked -p extension-files`.

`source-provenance.json` фиксирует исходники и binary hash. Build targets/binaries не включаются в ZIP. Публикаций, commits/PR, изменений пользовательского репозитория нет.
