# Каталог сессий: кодировать имя workspace одним выходным буфером

[Патч](candidate.patch) для [Proteus-modules 9469e3b](https://github.com/Proteus-harness/Proteus-modules/commit/9469e3b12529d08b1f4a76882693e2065e842c51). Старый workspace encoder создавал по String на компонент пути, собирал их в Vec и затем строил итоговое имя через join. Новый вариант дописывает каждый компонент и разделитель в один String. Для обычного пути начальная ёмкость равна байтовой длине исходного пути, но не превышает 256 байт; при расширении escape-последовательностей остаётся обычный рост String. Для корня остаётся компактная живая строка `%2F`.

Изменение не отменяет ни одну проверку: прежняя canonicalization и fallback, допустимые компоненты и UTF-8, Unicode и percent-escape (hex в верхнем регистре), separator `|`, decode и его проверка повторным кодированием каждого компонента/полного пути сохраняются. Для decode по-прежнему отдельно формируется канонический текст компонента. Не меняются построение locator, список путей, порядок списка, revision/identity, журнал, stamps, blob inventory, проверки и запись v1.

## Проверки

- На финальном исходнике прошли [64 unit и 2 process](native-release.log), один штатный ручной тест пропущен. Release locked suite запущен с той же тестовой вставкой в SDK worker; рабочий исходник модуля и исправление совпадают. Нативный тест сравнивает точное имя при Unicode, пробелах, `%`, `|` и эмодзи, проверяет canonical symlink alias, обратное преобразование и специальный корень. Синтетические пути создаются в отдельных временных каталогах.
- [Наложение](composition.log) в двух порядках на совместимый стек [#246](https://github.com/Qweasd123tg/proteus-modules-dot/pull/246), [#253](https://github.com/Qweasd123tg/proteus-modules-dot/pull/253), [#321](https://github.com/Qweasd123tg/proteus-modules-dot/pull/321), [#326](https://github.com/Qweasd123tg/proteus-modules-dot/pull/326) и [#331](https://github.com/Qweasd123tg/proteus-modules-dot/pull/331) дало одинаковое дерево; это исходное наложение, не полный тест стека. Весь workspace и Windows не проверялись.

## Методика

Реальные release SDK workers на Linux с одинаковой внепроизводственной вставкой [instrument.py](instrument.py); счётчик только на потоке выполнения `ListCandidates` и `List`. Считаются запросы Rust-аллокатора, включая полный запрошенный размер realloc; не считаются C SQLite, генерация fixture, serde IPC до/после выполнения. Сравниваются общий и ограниченный workspace `ListCandidates`, потом строгий холодный List (перед входом нет sidecar ни у одной сессии). Каждый ряд создаётся настоящей записью. Контроль охватывает обычные короткие имена, древовидный путь и Unicode/escaping. Один SQLite-читатель на синтетический журнал удерживает нормальный read-only snapshot, чтобы создание пустого WAL не меняло поверхностные timestamps между A/B. `List` ответ сравнивается после одинаковой сериализации JSON, а каждый индекс v1 — непосредственно побайтно. Отдельно проверяются точный состав и порядок каталога.

Свежие процессы с чередованием stock/candidate. После одной непротоколируемой пары по 7 и 5 пар на сценарий и backend, CPU 6 и 7. Не измерялись RSS и сокращение времени выполнения или запуска Desktop.

## Результаты

Медианы: число запросов к Rust allocator / сумма запрошенных байтов. «=» означает точное повторение обеих медиан второй серией.

| Backend и запрос | Серия 1, до → после | Серия 2 |
|---|---:|---:|
| jsonl, 96 сессий: обычный путь, общий ListCandidates | 7 225 / 521 561 → 6 649 / 507 065 | = |
| jsonl, 128 сессий: вложенный путь, ListCandidates по workspace | 13 864 / 1 320 004 → 11 671 / 1 216 933 | = |
| jsonl, 128 сессий: вложенный путь, строгий холодный List | 60 738 / 17 113 626 → 56 369 / 16 908 283 | = |
| jsonl, 96 сессий: Unicode/escaping, ListCandidates по workspace | 9 831 / 923 626 → 8 376 / 889 191 | = |
| sqlite, 96 сессий: обычный путь, общий ListCandidates | 7 225 / 530 297 → 6 649 / 515 801 | = |
| sqlite, 128 сессий: вложенный путь, ListCandidates по workspace | 13 864 / 1 331 652 → 11 671 / 1 228 581 | = |
| sqlite, 128 сессий: вложенный путь, строгий холодный List | 57 154 / 8 366 618 → 52 785 / 8 161 275 | = |
| sqlite, 96 сессий: Unicode/escaping, ListCandidates по workspace | 9 831 / 932 362 → 8 376 / 897 927 | = |

[Серия 1](paired.csv) · [серия 2](repeat.csv). Снижение числа запросов не является измерением ускорения или пиковой памяти.

## Повторить

Применить `git apply --check candidate.patch`, затем `git apply candidate.patch` на той же базе. Нативный scope: `cargo test --locked --offline --release -p session-storage -p proteus-session-storage-module` с harness из закреплённого Core `0c1b757`. Для пробы только в отдельном stock/candidate checkout: `python3 instrument.py CHECKOUT`, затем собрать два релизных `proteus-session-storage-module` в разных target dirs. Запуск: `python3 measure.py STOCK CANDIDATE --output samples.csv`; без измерительной вставки можно добавить `--parity-only`. Нужны Linux, Python 3.11+, Rust/Cargo и закреплённые зависимости. Реальные данные не используются.
