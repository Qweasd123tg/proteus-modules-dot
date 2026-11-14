# P2: добавление корректных skills молча убирает весь каталог из context

Дата: 2026-11-13. Повторно сверены remote HEAD: Core `89997df995df7c39b713e16aba216ecb19c8f497`, Modules `3270dc0f894eaf4d0360306052b806099b8f5351`. Production checkouts чистые. Новых production-правок, commit/push/PR нет.

## Наблюдение

Проверена реальная цепочка `Core → coding.codex_loop → codex_context → skills → canonical model request`. Использованы штатный набор providers `["project_instructions", "skills", "environment"]` из Codex profile и штатный `max_context_bytes = 60000`. Модель синтетическая: только сохраняет фактические requests, возвращает контрольный ответ и по отдельному запросу вызывает настоящий skill tool. Внешнего API нет.

В одной живой сессии:

| Состояние workspace | Каталог, переданный модели | Итог turn |
|---|---:|---|
| 40 enabled skills, description каждого 900 символов | 40 | Success |
| Добавлены ещё 20 таких же корректных skills | **0** | Success |
| При тех же 60 запрошен `skill("procedure-000")` | **0**, но tool возвращает правильное тело | Success |
| Дополнительные 20 файлов убраны из discovery обратимым переименованием | 40 | Success |
| К тем же 40 добавлен `AGENTS.md` размером 20000 байт | **0**, инструкции проекта сохранены | Success |

Настоящий `context_provider/v4 catalog` отдельно подтверждает 40/60 enabled skills без warnings. `provide` возвращает один chunk размером **43158/64718 байт** соответственно. Description в 900 символов меньше разрешённых 1024; 60 skills меньше ограничения 128. Все файлы синтетические, корректные YAML, без disabled skills и без plugin packages.

Таким образом, это не ошибка parsing/discovery и не прежний disabled-malformed-skill дефект. При расширении набора рабочих workflows или увеличении нормального AGENTS-файла **вся** их автоматическая обнаруживаемость пропадает. Сам `skill` остаётся доступным, но его описание требует точное имя из `<available_skills>`, которого больше нет. Ручное указание имени пользователем либо чтение файлов напрямую остаётся обходным путём. Это не потеря исходников и не доказательство того, что любая живая модель непременно ошибётся.

## Причина

1. [`skill-pack/src/lib.rs:43–50`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/skill-pack/src/lib.rs#L43-L50) собирает **все** доступные skills в один `ContextChunk`.
2. [`available_skills_chunk:204–223`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/skill-pack/src/lib.rs#L204-L223) не ограничивает совокупный размер и не делит каталог на независимо отбираемые entries.
3. [`budget.rs:14–43`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context/context-pack/src/budget.rs#L14-L43) сначала резервирует проектные инструкции, затем пропускает целиком каждый scored chunk, не вместившийся в остаток. Сообщение о пропущенном каталоге не создаётся.
4. При 60 skills их chunk уже больше штатных 60000 байт. При 40 skills он помещается отдельно, но после AGENTS-wrapper на 20108 байт сумма становится 63266. В обоих случаях весь skills chunk исчезает.

Разумное направление исправления: согласовать гранулярность каталога и budget. Например, отбирать целые bounded skill entries, оставлять короткую диагностику неполного списка и способ загрузить/просмотреть остальные. Альтернативой может быть явная ошибка конфигурации при невозможности разместить необходимый каталог. Не нужно убирать общий budget, автоматически читать тела skills или вытеснять обязательные project instructions. Конкретный UX при переполнении требует выбора владельца; подтверждённый дефект здесь именно молчаливое all-or-nothing исчезновение.

## Проверки и артефакты

- `run.py`, `capture_model.py`: 5 turns, 6 фактических model requests, настоящие Core/workflow/context/skill processes.
- `catalog.py`: read-only прямые process-v3 вызовы настоящего `catalog` и `provide`; это проверка provider API, **не GUI**.
- `model-requests.jsonl`, `catalogs.json`, `results.json`, `outputs.json`: полные синтетические evidence.
- `verify.py`: PASS для диагностических assertions. `--expect-discoverable`: ожидаемый FAIL (exit 1), поскольку добавление корректных skills обнуляет список в request. Green диагностического runner не означает, что продукт исправлен.
- `baseline-tests.log`: повторно пройдены **23 context-pack + 9 skill-pack** tests. Полный workspace gate не запускался; production не менялся.
- `provenance.json`, `source-provenance.json`: SHA, clean status, SHA256 используемых binaries. Взяты проверенные неизменённые Core binary и отдельно ранее чисто собранные components из предыдущего аудита. Сам этот проход заново production binaries не собирал. `coverage.json` перечисляет прочитанные реализации и hashes.

Повтор в этой среде: `python3 run.py && python3 verify.py`. Скрипты используют явные пути к pinned binaries и Core Python helper; для переноса нужно указать эквивалентные зависимости. HOME/cwd/configs и все данные создаются заново во временной папке. Запуски повторены после окончательной правки только test fixtures; финальные evidence относятся к последнему успешному прогону.

## Границы

Проверены local project skills, стандартный Codex provider order и default aggregate budget. Native GUI, live LLM, user/plugin-skill sources и другие context builders динамически не проверялись. Указанные 40/60 не универсальный порог: он зависит от длины описаний, абсолютных путей и другого обязательного context. Воспроизведение не утверждает, что любой допустимый каталог обязан целиком умещаться в любое окно модели. Модельный лимит fixture специально 200000 tokens, чтобы отделить byte-budget loss до запроса от модели/compaction.

Дополнительно прочитаны discovery precedence, body loading, wrapper shaping, directory traversal, bounded file reads, search/memory provider wiring. Независимой второй подтверждённой проблемы в этом проходе нет. Ранее найденный malformed disabled skill не пересчитывался.
