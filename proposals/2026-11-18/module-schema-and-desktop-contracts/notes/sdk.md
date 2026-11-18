# Два расхождения в справке Rust SDK: выбор строки и обязательные ячейки

**Предложение:** `sdk-list-and-lanes-contract.patch`; SHA-256 `717416b720aa8b11e3406a3d4e996b2764a3745d1bbe6aecbbba0ecd9aba279e`. Меняются только строки rustdoc двух публичных построителей в Extensions, без изменений протокола, данных и обработки действий. Патч чисто накладывается; все строки, кроме rustdoc, совпадают.

**Как это влияет на автора.** Обработчик, написанный в расчёте на обещанное SDK `open` после одиночного клика в `list`, не получит этого события: придёт `preview`. А вызов `lane_row` без добавления «опциональных» ячеек создаёт строку, которую Desktop не может прочитать. Даже для единственной графической колонки нужен массив из одной пустой строки, не пустой массив.

| Публичная функция | Было в справке | Фактический контракт |
|---|---|---|
| [`list`](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/ef064381d2194d95faef2b85f6cc3a1c34c6b975/sdk/src/ui.rs#L318-L323) | Клик или Enter дают `open`. | Одиночный клик даёт `preview`. Двойной клик и Enter дают `open`. Перемещение стрелками, Home/End, PageUp/PageDown только двигает курсор. [Протокол](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/ef064381d2194d95faef2b85f6cc3a1c34c6b975/PROTOCOL.md#L555-L569), [тип строки](https://github.com/Proteus-harness/Proteus-desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/ui/extensions/declarative/list.rs#L30-L48), [общая обработка списка](https://github.com/Proteus-harness/Proteus-desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/ui/extensions/declarative/rows.rs#L109-L155). |
| [`lane_row`](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/ef064381d2194d95faef2b85f6cc3a1c34c6b975/sdk/src/ui.rs#L290-L303) | `cells` перечислено среди опций; построитель это поле не добавляет. | Добавить `cells` через `Node::with`: массив строк в порядке колонок, по одной строке на колонку. Для графической колонки протокол указывает `""`. Native schema требует поле и совпадение длины с числом колонок; при проверке **не** утверждается, что валидатор сам проверяет пустоту графической строки. [Протокол](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/ef064381d2194d95faef2b85f6cc3a1c34c6b975/PROTOCOL.md#L540-L554), [структура и проверка](https://github.com/Proteus-harness/Proteus-desktop/blob/2307e9c67125bbe66f15ced51317a2dfcc437aa4/src/declarative/lanes.rs#L35-L113). |

**Проверка:** на исходнике и с исправленными комментариями исполнены те же настоящие тела чистых функций Rust. Для `list` 30 различных row IDs × (два значения click count + семь клавиш), **270** проверок адресата, события и позиции. Для `lanes` проверены **28** корректных схем из 1–7 колонок, во всех возможных положениях единственной графической. Во всех 28 случаях отсутствующее поле даёт именно ошибку `missing field \`cells\``; в 28 случаях корректные данные приняты; ещё **56** ошибок ширины (±1) обнаружены. Отдельно дословно извлечён, скомпилирован и выполнен **пример из новой справки**, его результат прошёл тот же Desktop schema check. Правки отражают уже существующее поведение; не заявляется изменение пользовательского интерфейса.

Режим теста: действительные `ui::Node/list/list_row/lane_row/lanes`, структуры и проверки `declarative::lanes`, `ListRows::clicked/MOVED` и `Rows::key/act_at`. Вместо GPUI используются ID-коллектор, счётчик положения и пустые оболочки прокрутки/контекста. Меню пусты, chip tones не используются; их независимые проверки не воспроизводятся. Не проверялись пиксели, распознавание системой реального двойного клика, фактическое открытие документа, Cargo workspace/полный SDK, расширение или приложение.

**Повторение:** из каталога отчёта; нужны подготовленные исходники и Rust с уже собранными serde, serde_json и anyhow. Использовались rustc 1.95.0 и serde_json 1.0.151.

```sh
python3 checks/sdk/replay.py "$EXTENSIONS_BASE" "$DESKTOP" "$CARGO_DEPS" --rustc "$RUSTC"
python3 checks/sdk/replay.py "$EXTENSIONS_PATCHED" "$DESKTOP" "$CARGO_DEPS" --rustc "$RUSTC"
```

Ревизии: Extensions `ef064381d2194d95faef2b85f6cc3a1c34c6b975`, Desktop `2307e9c67125bbe66f15ced51317a2dfcc437aa4`, dot `36473954b15f518654909ea8d78a298cdb4a29be`. Проверены названия PR #1–205 и относящиеся к спискам/SDK пути в текущем дереве. #193 касался первой боковой панели, #204 — заголовков tree и привязки текущего действия. Здесь не меняются клавиатурная навигация, удерживаемые действия, Git-граф и другие ранее затронутые механизмы. Это дедуп по публичным материалам, а не просмотр каждого архива.
