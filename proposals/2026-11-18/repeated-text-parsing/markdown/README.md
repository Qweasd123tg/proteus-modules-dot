# Markdown: не строить отдельное дерево ради заведомо отсутствующих блоков и определений

Патч для [Proteus-desktop-extensions, a35cea08](https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/a35cea08be83ee8e5ecbfce9ef5050a1c00eb247), закреплённого в Desktop `210cc9f2`. Меняется только `packages/markdown-render/src/fences.rs`: восемь строк в рабочей функции и один регрессионный тест. Содержимое GFM компилируется как раньше; состояния, зависимостей и изменений протокола нет.

На сообщении 53 762 Б с заголовками, ссылками, inline code и strong, 64 постепенно доставленных префикса потребовали 128 входов в markdown-rs до изменения и 64 после: 3 494 422→1 747 211 байта на входе парсеров. Медиана полного обмена с нативным расширением для всех 64 обновлений на одном CPU: **624→336 мс**. На одном полном сообщении: **19,0→10,0 мс**. Это не сокращение размера текста протокола и не время UI-кадра.

## Почему можно пропустить разбор

[Document::render](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/a35cea08be83ee8e5ecbfce9ef5050a1c00eb247/packages/markdown-render/src/render.rs) вызывает отдельный [fences::parse](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/a35cea08be83ee8e5ecbfce9ef5050a1c00eb247/packages/markdown-render/src/fences.rs) на всём тексте или хвосте после проверенной границы. Из этого mdast читают **только** узлы Code и Math непосредственно в корне и рекурсивно все Definition. Это не дерево для обычного HTML. Отдельный [inlines::render](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/a35cea08be83ee8e5ecbfce9ef5050a1c00eb247/packages/markdown-render/src/inlines.rs) по-прежнему компилирует каждый нужный сегмент, включая необязательный проход для защиты нетекстовых конструкций и отдельный проход для inline math.

Патч ищет **необходимые**, не достаточные признаки, без собственного парсера и без учёта позиции маркеров. В закреплённом [markdown 1.0.0](https://docs.rs/crate/markdown/1.0.0/source/src/):

* [raw_flow](https://docs.rs/crate/markdown/1.0.0/source/src/construct/raw_flow.rs) для начала fenced code требует минимум три смежных backtick или tilde, для display math минимум два смежных доллара.
* [code_indented](https://docs.rs/crate/markdown/1.0.0/source/src/construct/code_indented.rs) требует четырёх колонок ASCII-отступа: в сырой строке тогда есть либо четыре смежных пробела, либо таб.
* [definition](https://docs.rs/crate/markdown/1.0.0/source/src/construct/definition.rs) непосредственно после закрывающей скобки [partial_label](https://docs.rs/crate/markdown/1.0.0/source/src/construct/partial_label.rs) проверяет двоеточие. Литерал `]:` обязателен и для вложенных/многострочных определений. Ссылка без определения не требует отдельного дерева: обычный GFM-компилятор остаётся.

Если найден хоть один признак **где угодно** в срезе, выполняется исходный разбор: случайные четыре пробела в предложении, последовательности в inline code и невалидная разметка могут дать ложноположительное совпадение. Это потеря ускорения, не изменение результата. При расширении набора извлекаемых узлов или обновлении грамматики условие необходимо пересмотреть.

## Фактические парсеры и измерения

В отдельных инструментированных release-процессах `instrument.py` добавляет запись имени этапа и точного `str::len()` непосредственно перед каждой реально достижимой точкой входа `to_mdast` / `to_html_with_options`. Каждая функция в [этой версии библиотеки](https://docs.rs/crate/markdown/1.0.0/source/src/lib.rs) вызывает внутренний `parser::parse` один раз. Не подсчитываются токены, внутренние проходы компиляции, трафик памяти или байты протокола. Размеры передаются после действительных изменений сегментов (например, подстановка для HTML); отдельные тестовые счётчики самого проекта не использованы. Полный журнал по каждому кадру, типу этапа и длине: [counts.json](counts.json).

Время: *другие*, обычные release ELF; Rust/Cargo 1.95.0, Linux x86-64, Python 3.12.14. В каждом образце новый процесс, hello+разминка в отдельном view, одинаковый заранее закодированный ввод; время с записи кадра до чтения полной строки ответа. Интервал **включает** JSON/рендер в процессе, запись/чтение pipe, но не запуск процесса, Python-декодирование и не Desktop/GPUI. Для ряда указана медиана суммы за всё расписание, шесть A/B-пар с порядком AB, BA, …, процессы наследуют CPU 7; миллисекунды ориентировочны. [Сырые пары, включая последнюю доставку](timing-cpu7.json); [первый прогон без affinity](timing.json) в период общей нагрузки.

| Сценарий | Кадры | Маршрутизация: вызовы до→после | Вход маршрутизации Б, до→после | Остальные вызовы guard / inline / HTML, обе версии | Медиана суммы, мс до→после |
|---|---:|---:|---:|---:|---:|
| prose-prefix-1 | 1 | 1→0 | 53 762→0 | 0 / 0 / 1 | 18,95→10,02 |
| prose-prefix-4 | 4 | 4→0 | 134 403→0 | 0 / 0 / 4 | 46,58→24,98 |
| prose-prefix-16 | 16 | 16→0 | 456 963→0 | 0 / 0 / 16 | 223,79→92,78 |
| prose-prefix-64 | 64 | 64→0 | 1 747 211→0 | 0 / 0 / 64 | 623,85→335,50 |
| prose-static-repeat | 5 | 1→0 | 53 762→0 | 0 / 0 / 1 | 23,26→10,85 |
| late-definition | 16 | 16→1 | 457 733→53 852 | 0 / 0 / 16 | 149,64→85,81 |
| gfm-inline-math-html | 16 | 16→0 | 10 512→0 | 16 / 16 / 16 | 13,93→11,19 |
| closed-fence-display-math | 16 | 16→2 | 13 023→2 727 | 18 / 18 / 18 | 16,72→13,95 |
| multi-static-repeat | 5 | 5→1 | 8 713→3 753 | 3 / 3 / 3 | 6,08→5,09 |
| unclosed-code | 16 | 16→7 | 17 209→11 520 | 10 / 10 / 10 | 11,60→10,08 |
| unclosed-math | 16 | 16→1 | 10 601→1 248 | 16 / 16 / 16 | 15,65→12,90 |

* Одинаковый одиночный сегмент уже имел точное сравнение текста и языка. В `prose-static-repeat` парсер работает только при первом ответе; оставшиеся четыре доставки в обеих версиях дают **ноль** вызовов. Сериализация ответа остаётся. Здесь форсируется доставка, хотя Desktop может отсеять повтор ещё до процесса.
* Позднее определение меняет ссылку в начале текста. На последнем кадре исходный route снова обязателен в обеих версиях: 17,50→18,29 мс (не выигрыш); ранние префиксы всё ещё дешевле. У незакрытых code/math последняя доставка также не демонстрирует выигрыша. На документе с ранним маркером на каждом нужном участке улучшение не обещается, а поиск подстрок может добавить работы.
* Даже без одного лишнего дерева обычный GFM-компилятор читает каждый изменившийся префикс. Это не общий инкрементальный Markdown, не ускорение plaintext и не кэш сообщений. Память и время GUI здесь не измерялись.

## Регрессии

Проверены **175** кадров по 11 расписаниям и отдельно **678** детерминированных входов с заменой текста/языка/четырьмя view, CR/LF/CRLF, 0–4 пробелами, табами, смешанными и Unicode отступами, пустыми и частичными ограждениями, GFM, escaped/ложными/вложенными определениями, HTML, math. На одинаковых запросах совпали SHA-256 всего stdout, не только типы узлов. Драйвер также проверяет тип ответа, текущую ревизию и тип корня. [Полные хеши](parity.json). Все 175 кадров имеют те же хеши и в инструментированных сборках.

Штатные тесты пакета: 47 unit + 3 native integration до, 48 + 3 после (новый тест удерживает необходимые маркеры и CR/LF/CRLF); штатные 2 Python wire streaming tests на собранных через package.py ZIP прошли с обеих сторон. [Результаты](tests.txt). Независимая проверка полных ответов на официальных CommonMark 0.31.2 и публичных документах Proteus вынесена в соседний отчёт; набор синтаксических примеров не является статистикой реального чата.

## Воспроизведение

Нужны локальная копия исходного Git репозитория `Extensions`, Python 3 и Rust/Cargo с зависимостями по Cargo.lock. Из свежей отдельной рабочей папки:

```sh
R=$PWD; REPORT=/absolute/path/to/this/report; EXT=/absolute/path/to/Extensions
PIN=a35cea08be83ee8e5ecbfce9ef5050a1c00eb247
for d in before after count-before count-after; do
  mkdir "$d"; git -C "$EXT" archive "$PIN" | tar -x -C "$d"
  case "$d" in *after) (cd "$d" && git init -q && git apply "$REPORT/routing-prefilter.patch");; esac
  case "$d" in count-*) python3 "$REPORT/instrument.py" "$d";; esac
  (cd "$d" && CARGO_TARGET_DIR="$R/target-$d" cargo build --release --locked -p extension-markdown-render)
done
for d in before after; do
  (cd "$d" && export CARGO_TARGET_DIR="$R/target-$d" &&
    cargo test --locked -p extension-markdown-render &&
    python3 -m unittest discover -s tests -p 'test_markdown_streaming.py' -v)
done
b=target-before/release/markdown-render; a=target-after/release/markdown-render
python3 "$REPORT/run.py" parity "$b" "$a" > parity-local.json
python3 "$REPORT/run.py" counts target-count-before/release/markdown-render target-count-after/release/markdown-render > counts-local.json
python3 "$REPORT/run.py" time "$b" "$a" > timing-local.json
# On Linux optionally prefix the time command with taskset -c <available_cpu>.
```

`fixtures.py` builds the exact shared deterministic GFM body and late-reference control; the driver cuts `floor(bytes*i/N)`, moving incomplete UTF-8 endpoints down. Each run stores its ELF hashes and SHA-256 of the complete reply sequences. Toolchains/paths may change binary hashes across machines; compare input and full-answer digests.

Контрольные SHA-256 исходных тел: prose (53 762 Б) `a26645d9e976f9729c7b2b59306f0a12244b3c2ffc0b393e773f7d0005158a90`; late-ref (53 852 Б) `bf45b2c8460486d759ec6a2a0ca4e0ac9869769a3c7795f3f85cc35c969e10b8`. Применение патча в независимой чистой копии дало тот же исходный файл, что использован в тестах и сборке.
