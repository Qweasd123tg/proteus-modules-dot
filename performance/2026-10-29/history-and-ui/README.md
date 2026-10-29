# Меньше повторной работы: история, выбор tools и UI

Независимые source-only патчи к четырём репозиториям. Это продолжение [первого пакета](https://github.com/Qweasd123tg/proteus-modules-dot/blob/401b56f6bde97660af5a0e7492a754a23c1ff51d/performance/2026-10-29/repeated-work/README.md) из [PR #58](https://github.com/Qweasd123tg/proteus-modules-dot/pull/58), а не его копия. PR #58 не требуется для применения этого набора; совместное применение проверено на закреплённых исходниках.

## Что меняется

- **Core — `core/01-history-binding-lookups.patch`.** Временные индексы вместо повторного поиска calls/results по истории для каждого binding и повторных поисков при rebase. Сохраняются неоднозначность, первый найденный message, точное равенство binding, порядок записи и приоритет ошибок. Индексы требуют временной памяти пропорционально индексируемым записям; это не persistent cache и не ускорение полного journal replay. Инварианты добавлены в существующий runtime guide.
- **Modules — `modules/01-tool-query-scoring.patch`.** Запрос поиска токенизируется один раз на вызов. Hook переиспользует найденный priority и хранит статические reason labels до выбора. Весовые коэффициенты, Unicode, фильтры, порядок и метаданные ответа сохранены. Не добавлены кэш schemas или новый selector.
- **Desktop — `desktop/01-patch-summary.patch`.** Постоянная строка tool получает только числа добавлений/удалений, без создания полного diff body и форматирования путей. Один классификатор строк используется для summary и полного просмотра; permissive-разбор остаётся прежним. Проход по входу остаётся линейным, кэша нет.
- **Desktop — `desktop/02-content-snapshots.patch`.** Неизменённый content сравнивается без предварительного копирования текста; retained UI и runtime разделяют immutable snapshot. Удаляется лишняя копия между shell и runtime до допуска очередью. Owned wire payload и раньше формировался после допуска; эта граница сохранена. При изменении короткоживущий входной текст всё ещё нужно один раз сохранить. Сохраняются latest/in-flight, ACK, ошибки, revision, contributors/context и повторная отправка после invalidation.
- **Extensions — `extensions/01-cache-json-accounting.patch`.** Тот же JSON serializer считает UTF-8 bytes через checked writer вместо выделения полной строки ради `.len()`. Пределы и eviction существующего cache сохранены; переполнение/ошибка не обходят лимит. Это логический размер JSON, не RSS.
- **Правила:** `desktop/03-development-rules.patch` и `extensions/02-development-rules.patch` дополняют существующие AGENTS.md: не создавать ненужные snapshots, не обходить admission при coalescing, не путать byte accounting с потреблением RAM. Общие правила Core/Modules уже находятся в PR #58.

## Базы и применение

Точные commits и исходные Git blob SHA перечислены в `SOURCES.json`. Для каждой папки используйте **соответствующий отдельный upstream checkout**; этот delivery repository не является их workspace. Патчи внутри папки применяются в числовом порядке. Сначала `git apply --check --whitespace=error-all <patch>`, затем `git apply <patch>`. Проверяйте `SHA256SUMS` перед переносом. При другой базе сначала проверьте актуальность исходников, не применяйте вслепую с принудительным разрешением конфликтов.

## Что проверено

- Исходные blob SHA, source review автором и независимым reviewer.
- Применение и whitespace каждого патча; совместное применение пакета и сочетание с PR #58 в минимальных копиях исходников.
- Добавлены regression test sources для duplicate/ambiguous bindings, ranking/Unicode/ties, permissive patch parsing, content snapshots/queue admission и encoded-byte accounting.

**Не запускались:** Rust/продуктовый код, cargo, тесты, сборки, UI, CI и benchmarks. Static apply не подтверждает компиляцию или поведение приложения. Удаление конкретных обходов/копий видно в коде; численные обещания ускорения, RSS/PSS и CPU отсутствуют. Upstream-репозитории не изменялись.

## Что намеренно не включено

- IPC encode-once: прежний кандидат ухудшал конкурентный admission; альтернативе нужен дополнительный staging budget (до 16 MiB при defaults). Она не опубликована и не включена в основу.
- Effective-theme cache key native Mermaid: простая замена ключа могла менять прежний raw-request quota и порядок ошибок. В этот пакет вошло только безопасное удаление строки для byte accounting.
- Incremental journal replay и глобальные UI invalidations требуют отдельного изменения жизненного цикла. Этот пакет не выдаётся за их решение.
