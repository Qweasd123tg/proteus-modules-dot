# P2: отключённый локальный skill блокирует context и исправные skills

Дата проверки: 2026-11-13. Core remote HEAD `89997df995df7c39b713e16aba216ecb19c8f497`; Modules remote HEAD `3270dc0f894eaf4d0360306052b806099b8f5351`, оба повторно сверены через `git ls-remote origin HEAD`.

## Наблюдаемый результат

`addons.disabled_skills = ["review"]` действительно запрещает вызов `skill(name="review")`, пока его файл исправен. Но отключение не изолирует ошибки этого файла:

1. В рабочей папке лежат два синтетических локальных skill: отключённый `review` и включённый `testing`.
2. Обычный turn через реальные `coding.codex_loop → codex_context → skills` успешно доходит до fake model.
3. Только у **отключённого** review меняется YAML frontmatter на некорректный. Профиль, включённый testing, процесс и cwd не меняются.
4. Следующий обычный turn, не просивший загружать skills, завершается Error на `host.context.build`. `ModelRequestPrepared` отсутствует.
5. Независимая проверка через настоящий `host.tools.execute_batch` показывает: `skill(name="testing")` тоже возвращает ошибку YAML из **review/SKILL.md**, а не тело исправного testing.
6. Возврат review к исправному содержимому восстанавливает оба пути в тех же живых сессиях, без reload.

| Состояние отключённого review | Обычный coding turn | Загрузка включённого testing | Вызов review |
|---|---|---|---|
| Исправный | Success, model request есть | Success | `not available` |
| Некорректный YAML | **Error до model request** | **Error из review/SKILL.md** | Error |
| Восстановленный | Success | Success | `not available` |

Это одна причина с двумя подтверждёнными проявлениями, не два отдельных дефекта. Потери данных, обхода отключения или выполнения отключённого skill не показано. Значимость: переключатель не позволяет изолировать ошибочный неиспользуемый skill; обычная незавершённая правка такого файла делает профиль неработоспособным, пока файл не исправлен/убран или provider не исключён.

`skills` присутствует в штатных Codex contexts: [codex-profile.toml:18–23](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/configs/fragments/codex-profile.toml#L18-L23). Probe намеренно сокращает providers до `["skills"]` для выделения причины, а не меняет semantics.

## Причина по коду

- [discovery.rs:62–118](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/skill-pack/src/discovery.rs#L62-L118): local/user discovery выполняется с `?` до применения `settings.disabled`; отключение лишь меняет `enabled` уже разобранных документов.
- [discovery.rs:136–150,192–226](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/skill-pack/src/discovery.rs#L136-L226): ошибка одного локального файла из `parse_skill_file` обрывает весь каталог. Для plugin skills рядом уже предусмотрены per-entry warnings, но для local/user нет.
- [lib.rs:43–48](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/skill-pack/src/lib.rs#L43-L48): automatic context фильтрует enabled только после успешного discovery.
- [lib.rs:156–170](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/skill-pack/src/lib.rs#L156-L170): вызов конкретного skill сначала разбирает **все** skills с телами, затем ищет имя. Ошибка постороннего отключённого документа мешает загрузке выбранного.
- [codex.rs:11–22](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context/context-pack/src/codex.rs#L11-L22), [retrieval.rs:90–99](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context/context-pack/src/retrieval.rs#L90-L99): provider error пробрасывается наружу и становится ошибкой turn.

Направление исправления: сохранить диагностику невалидных файлов в каталоге, но отделить её от доступности исправных skills и model context; учитывать отключение до общей fatal-валидации или обрабатывать ошибки отдельных документов как предупреждения с исключением именно этого документа. Нельзя просто скрыть все ошибки instructions/context: независимая проверка активных источников должна сохраниться.

## Воспроизведение и артефакты

- `run.py`: реальные неизменённые Core/coding/context/skills processes, три turn в одной сессии.
- `run_tool.py`, `workflow.py`: test-only workflow, три turn, шесть вызовов настоящего skill tool через Core host; fake model не участвует в выборе tool.
- `results.json`, `outputs.json`, `tool-probe/*`: полные ответы и события; `run.log`, `tool.log`: компактные результаты.
- `verify.py`: диагностические утверждения; `verify.py --assert-isolated` ожидаемо падает на safety invariant (exit 1), см. `expected-failure.log`.
- `build.log`: отдельная чистая сборка трёх production components из изолированного checkout, собственный target. `provenance.json` и `tool-probe/provenance.json`: SHA256 используемых binaries.
- `first-pass/`: та же цепочка на ранее собранных baseline components. После независимой чистой пересборки результат повторился. Итого 12 синтетических turn в четырёх процессных сессиях: шесть обычных coding turn и шесть tool-probe turn.
- `baseline-tests.log`: штатные targeted Rust tests выбранных packages; все прошли (coding-workflow: 92, context-pack: 23, skill-pack: 9), это не полный workspace gate.

Запуск в текущей audit-среде: `python3 run.py && python3 run_tool.py && python3 verify.py`. Скрипты содержат явные пути к проверенным binaries и Core Python fixture helper; для другого checkout их нужно заменить. Все HOME/cwd/configs и skill files создаются в новых временных папках. Нет live API keys, сети к модельным провайдерам, пользовательских репозиториев или файлов.

## Границы и отрицательные результаты

Это функциональная failure-isolation проблема, не security finding и не новая ошибка memory backend. Проверка покрыла malformed YAML у отключённого **project** skill, а не все ошибки I/O, все источники или GUI-click flow. Отключение было уже записано в профиль до старта и сохранено на всех стадиях. Успешные ответы модели синтетические; падение произошло до sampling и не зависит от интеллекта модели.

Дополнительно построчно просмотрены обе memory implementations, context-pack, scaffold/history/context accounting, context-provider wiring и compaction lifetime. Нового независимого дефекта в JSONL/SQLite в этом проходе не установлено. Ранее известные JSONL partial append, FTS punctuation, worktree memory cleanup и compaction orphan tool result здесь не пересчитываются. Production sources не менялись; commit/push/PR не выполнялись.
