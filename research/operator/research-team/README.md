# Два исследователя и независимое повторное чтение

**Обязательное чтение:** [coverage timing](COVERAGE-TIMING.md) и [inspection prerequisites](INSPECTION-PREREQUISITES.md). Их ограничения включены в эту public-copy поставку; [provenance](PROVENANCE.md).
**Статус: конкретный операторский шаблон, проверенный по исходникам; не установлен и не запущен в Proteus.** В original source package четыре TOML-файла были синтаксически разобраны и29 собственных Python-контролей выполнены. **Эта adapted public layout не выполнялась; нового execution receipt нет.** Ни Core, ни module workers, ни модели, ни дочерние агенты здесь не запускались. `operator-provider.toml` намеренно отсутствует: без операторской подготовки это **не готовый к загрузке профиль**.

Продолжение [композиции AgentScope / Proteus](../EVIDENCE.md#research-composition), а не новая crate, workflow engine или каталог продуктов. Используются current Core `1fc3ef223d10322815dd9290a50d045bc95402bb` и официальные Modules `7fceaebc3bed8add9b0e3091110f59deca86ba46`. Modules закрепляет SDK `bee0e409e746e2df9db32748d4f8ea02201bd4af`; это **не** SDK `3f36a003…` опубликованных примеров. Совместимость установленного бинарного набора из этой source-проверки не следует. [Источники и точное покрытие](SOURCES.md).

## Зачем это нужно

Оператор проверяет три узких утверждения об управлении детьми в локальных исходных артефактах Proteus:

- **C1:** ребёнок запускается с собственным `--config`;
- **C2:** collaboration принимает только `parallel_safe` роли без worktree isolation;
- **C3:** истечение `wait_agent` не означает отмену ребёнка.

Исследователь A читает producer — запуск процесса. B читает admission и consumer — ожидание результатов. Отдельный verifier заново читает исходные места и может опровергнуть обоих. Координатор не считает большинство голосов доказательством. [Примеры аргументов](call-examples.json) содержат все пути и диапазоны; [идентичности двух исходных артефактов](SOURCE-ARTIFACTS.json) получены из закреплённых Git objects. Сами upstream-файлы не копируются в этот пакет.

Это **read-only tool surface**, не обещание, что весь процесс ничего не пишет: Core/модули могут вести разрешённые оператором session/event данные. Модельный provider по назначению получает выбранный контекст. Отсутствие write-tool не равно предотвращению утечки прочитанного текста.

## 1. Подготовка оператором — до любой модели

1. Выбрать уже установленный совместимый Core и доверенный `proteus-reference-module`; проверить происхождение/версии исполняемых компонентов. Здесь не приводится команда установки и не исполняется worker даже ради каталога.
2. Подготовить **отдельный source workspace только с разрешёнными материалами**, сохранив относительные пути двух файлов из `SOURCE-ARTIFACTS.json`. Самостоятельно сверить полные байты с указанными SHA-256 и ожидаемым commit; это операторская проверка артефакта, не способность LLM вычислять достоверный hash. Не помещать туда секреты, пользовательские файлы, credentials или лишнюю историю. Не выдавать доступ к основному рабочему каталогу ради удобства. Разрешённые runtime-записи должны иметь отдельно предусмотренное место/правило установки.
3. Создать три **named configs** `research-parent.config.toml`, `research-reader.config.toml`, `research-verifier.config.toml` в одном выбранном config directory, сохранив `fragments/research-runtime.toml`. Имена `research-reader` / `research-verifier` в ролях разрешаются через стандартный config directory, **не относительно родительского TOML и не относительно source workspace**. Убедиться, что родитель и дети видят именно этот directory; не полагаться на другой одноимённый профиль в обычной установке. Core учитывает `PROTEUS_CONFIG_PATH`, затем `PROTEUS_CONFIG_HOME`, `HOME`, `XDG_CONFIG_HOME` в показанном source-порядке; рецепт не меняет окружение автоматически. Не передавать весь directory вместо конкретного файла/имени: directory-loader сливает все его `.toml/.json` файлы. [S02](SOURCES.md#s02)
4. Оператор отдельно предоставляет `configs/fragments/operator-provider.toml`, содержащий **только** проверенные `active_provider`, `providers`, `module_config.model` и component/export настройки выбранного model provider. Не копировать целиком пользовательский config с tools, plugins, commands, hooks или role definitions. Это доверительная предпосылка, не ограничение TOML parser: файл способен добавлять другие поля, и merge не удаляет все лишние nested keys. Наш checker **не читает и не раскрывает** этот файл или его include.
5. Проверить **окончательные разрешённые профили и фактический каталог установленной сборки**, а не только эти snippets. Для детей ожидается единственный callable `read_file`, без MCP/plugin/provider-hosted tools, без control surface; для родителя — шесть collaboration tools, без ordinary file/shell tools. Дополнительные provider-hosted tools регистрируются отдельно от `tools.enabled`, поэтому `enabled=[]` не доказывает пустой каталог. Эта обязательная проверка установки здесь **не выполнена**. [S13–S15](SOURCES.md#s13)
6. Если нужна гарантированная изоляция процесса от остальных файлов/сети, сначала обеспечить и отдельно проверить поддерживаемую данной установкой ограничительную среду. Этот рецепт её не устанавливает и **не содержит выдуманных `read_roots`, `deny_paths` или `sandbox=true`**. Если такого ограничения нет, нельзя использовать шаблон как гарантию конфиденциальности/изоляции. `cwd` сам по себе не sandbox.

### Что именно ограничивает чтение

У выбранного официального `read_file` вызывается `workspace_path(cwd,path)`: canonicalize cwd, canonicalize target, проверка `target.starts_with(base)`. Это проверка containment **в реализации reader**, не в role prompt и не в `codex_policy.allow`. Соответствующий helper — один и тот же Git blob на SDK `bee0e409` и Core `1fc3ef2`. Она не превращает два пути из manifest в закрытую capability: другие доступные файлы внутри cwd тоже доступны reader. Нет заявления о неизменяемости дерева, OS sandbox, доверенности всего worker или предотвращении provider egress. [S19–S21](SOURCES.md#s19)

## 2. Что конфигурация выражает сегодня

| Часть | Файл / реальный механизм | Важная граница |
|---|---|---|
| Родитель | [parent](configs/research-parent.config.toml): `surface="collaboration"`; роли reader×2 и verifier×1 | Не автоматическая DAG; роли допускают повторные задачи, а не ограничивают всю сессию тремя вызовами |
| Дети | [reader](configs/research-reader.config.toml), [verifier](configs/research-verifier.config.toml): отдельные configs / System instructions | Роль verifier имеет собственный process pool key; это не доказательство статистической независимости моделей |
| Общий runtime | [runtime](configs/fragments/research-runtime.toml): `coding.codex_loop`, `codex_context`, `codex_policy`, file-tools export | Установленные бинарники доверенные; экспорт file-tools включает больше реализаций, но ordinary tools выбираются по `tools.enabled` |
| Child control | `surface="none"` **и** `roles=[]` | Одного `surface=none` недостаточно, чтобы доказать отсутствие underlying service при унаследованных roles |
| Чтение | `enabled=["read_file"]`, MCP/plugins пусты | Не произвольная регистрация и не закрытый список файлов |
| Контекст | `providers=[]`, hooks пусты; инструкции inline | Не подмешивать source `AGENTS.md`, skills, auto-search/memory как инструкции; provider include всё равно проверяется отдельно |
| Approval | У родителя `ask_before` для spawn/send/followup; normal mode | Нужен рабочий approval transport. Без разрешения не переключать на allow-all |
| Лимиты | role timeout 120 s, summary 12000 bytes, 2/1 role permits; parent pending limit 3, idle pool 3 | Это разные scopes. Role deadline начинается при leased turn, не общий deadline очереди; не токеновый/стоимостной бюджет всей иерархии |

`isolation` у collaboration-ролей **опущен**. В этом config parser строка `"none"` не допустима: распознаётся только `"worktree"`, а отсутствие даёт None. Worktree-роль не подходит collaboration. `parallel_safe=true` — декларация допуска, не статическое доказательство read-only. [S01, S03, S05](SOURCES.md#s01)

Не добавлять `spawn_agent` в `tools.enabled`: обычный tool builder ищет builtin/process implementation до того, как Core регистрирует collaboration facade. Нужны роли и `agent_control.surface`, а не ложный Tool module с тем же именем. `codex_policy.allow` тоже **не closed allowlist**: неизвестные этому списку зарегистрированные ReadOnly tools допускаются; наш узкий surface зависит от final registry. [S13–S15, S18](SOURCES.md#s13)

## 3. Ручная последовательность, а не исполняемый workflow

1. После операторских gates вызвать два `spawn_agent` с `task_name=reader_a/reader_b`, `agent_type=source_reader`. Точный ключ — `agent_type`, а не `role`, `model` или `fork_turns`. Сообщение содержит полную постановку: в traced fresh path процесс получает `request.prompt`, не автоматический fork истории родителя. Повторно используемый fresh peer очищает старую историю. [S06–S08](SOURCES.md#s06)
2. Зафиксировать реальные возвращённые `path`, `generation`, `agent_type`. `spawn` возвращает running receipt до завершения — **не результат исследования**.
3. Вызывать `wait_agent` и сверять `list_agents`. `wait_agent` — очередь completion batch, не join для заданных имён; timeout возвращает `timed_out=true, agents=[]`, не отменяя детей. Одна доставка может относиться к другому child/generation. `list_agents` сохраняет статус, но **не возвращает summary/error payload**: его нужно сохранить из доставленного completion. Не считать потерянный payload восстановленным одним list. [S05, S09–S10](SOURCES.md#s05)
4. Только после terminal-наблюдения обоих нужных поколений и проверки полноты ответов перейти к verifier. Это **операторский / application-side barrier**; prompt или TOML не обеспечивают его принудительно. Подставить в пример verifier фактические bounded claims и gaps, а не выдавать статические C1–C3 за завершённые reader results. Запустить **fresh** `source_verifier`, не followup одного из исследователей.
5. Verifier должен реально выполнить свои `read_file` и вернуть для **каждого** claim ID: `supported / contradicted / not_checked`, observed path/lines, короткую цитату и ограничение вывода. Это соглашение сообщения, не встроенный Core DTO, не криптографический receipt и не permission. Оператор проверяет фактические чтения в доступной штатной наблюдаемости, не доверяет одной фразе «прочитал». Line-numbered/ranged output не является full-file SHA-256 witness.
6. Координатор выдаёт отдельные confirmed/contradicted/unknown разделы; completion и корректный JSON сами по себе не доказывают entailment. Запись correction-memory, изменение файлов и публикация **не входят** в этот сценарий и не следуют из supported.

Существующий `coding.plan_execute_review` не заменяет отдельного verifier: review phase очищает tools и ставит `ToolChoice::None`. Здесь все три профиля используют tool-capable loop, но фазовый barrier остаётся ручным. [S22–S23](SOURCES.md#s22)

## 4. Отказы без ложного успеха

| Наблюдение | Операторское действие | Нельзя утверждать |
|---|---|---|
| Spawn approved / running | Ждать нужное поколение | «Исследование завершено» |
| `wait_agent.timed_out=true` | Продолжить ожидание или явно запросить interrupt | «Ребёнок cancelled» |
| `completed` | Проверить весь обязательный набор claims и источник | «Цель достигнута / цитата подтверждена» |
| `timed_out`, `cancelled`, `errored`, `unknown` | Сохранить наблюдаемый partial/unknown; не считать пропущенное supported | «Эффектов не было» |
| `interrupt_requested` | Дождаться terminal-наблюдения; при его отсутствии оставить unknown | «Все процессы/OS descendants уже остановлены» |
| Summary пропущен, malformed или неполон | Narrow followup при retained same-session history либо новая постановка | «Truncation всегда помечена отдельным флагом»: role summary обрезается по UTF-8 boundary без такого поля |
| Completion уже consumed, остался только list | Не выдумывать потерянный текст; новое ограниченное чтение | «list — журнал всех результатов» |
| Peer/history утрачены или parent restart | Новая задача с исходной постановкой и повторной проверкой identity | «in-memory collaboration автоматически восстановлена» |
| Approval недоступен / отказан | Остановить зависимый шаг | «Read-only role позволяет обойти spawn approval» |

`cancel_grace_ms=5000` — configured cooperative settlement interval процесса-координатора, не универсальное hard wall-clock/OS preemption или rollback. Точные cancellation/outcome ограничения ранее сохранены в [source-only матрице](../EVIDENCE.md#e07), а не воспроизведены этим рецептом. [S07–S12, S31](SOURCES.md#s07)

## 5. Чего пока не хватает — и чего не нужно писать заново

**Уже есть:** named child profiles, root-owned handles/generations, scoped host callbacks, admission/policy, process lifecycle, очередь completions, отдельные tool-capable loops и существующие journal/effect contracts. Новая универсальная team crate не нужна для ручного аудита.

**Малые, но реальные отсутствующие гарантии этого рецепта:** принудительный barrier двух результатов → независимый re-read; проверяемая привязка read observations к claim acceptance; closed per-source path capability; подтверждённая изоляция worker/provider от лишних данных; durable whole-team recovery. Они требуют конкретного host/app consumer и авторизации, не новых полей в prompt. Общее управление provider attempts/стоимостью не выводится из числа children или timeout.

R11 `evidence.verify_spans` потенциально усилит **байтовую** проверку уже разрешённого артефакта, но его 39 Rust cases всё ещё unrun; здесь он не установлен и не вызывается. Даже такой witness оставляет `origin_verified=false`, `semantic_entailment=not_evaluated` и не разрешает запись/публикацию.

## 6. Что проверено исторически — не новая public-layout execution

- В original package `python3 -B -I check_recipe.py` прочитал **только пять собственных leaf-файлов**, разобрал четыре TOML, проверил ограниченный собственный scaffold и 11 примеров аргументов.
- 29 Python-контролей: у причинных отрицательных случаев сначала валидная baseline, затем один дефект с точным diagnostic — лишний tool/export/plugin/hook, retained child roles, неверный named config или role/task binding, авторазрешение spawn, invalid isolation literal, unknown call argument, duplicate task, неверный путь, bool вместо integer, UTF-8 byte cap, отсутствие manual gate; отдельно проверены собственный partial merge и список читаемых leaf-файлов.
- Проверка **не разрешает include**, не повторяет весь Core loader/политику, не подтверждает worker exports, final provider tool catalog или permission transport. `read.recipe_path` — статическое правило нашего примера, **не runtime enforcement**. Порог spawn-message 16000 bytes здесь консервативное правило рецепта, не утверждение о таком же лимите в spawn schema.
- Core load, provider/config compatibility, три реальные child executions, read evidence, error/cancel/restart и end-to-end acceptance: **не выполнялись**. [Машинный результат и имена controls](VALIDATION.md).

Проверочный скрипт предназначен только для сохранённых fixtures. После изменения provider/config установка требует отдельной проверки; статический PASS нельзя переносить на произвольный final profile.
