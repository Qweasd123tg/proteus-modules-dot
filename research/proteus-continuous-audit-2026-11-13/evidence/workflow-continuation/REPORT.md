# Workflow completion review: причина продолжения теряется до модели

## Итог

**Подтверждён один новый дефект, рекомендуемый приоритет P2.** `coding.single_loop` и `coding.plan_execute_review` не передают модели `runtime.instructions`. Из-за этого теряются и настройки `[[instructions]]`, и причина, по которой `BeforeStop` reviewer потребовал доработать ответ. Runtime корректно повторяет workflow, но повторная модель не получает замечание reviewer. В детерминированном process-тесте это расходует весь лимит продолжений и заканчивается ошибкой вместо исправленного ответа.

Это не повтор cancel→unmatched tool, steering/private-draft, compaction или provider-ошибок. В сценарии нет tools, отмены, steering, compaction или повреждения данных.

## Версии и границы

- Core локальный HEAD и `origin/main`, проверенные в этом проходе: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Modules локальный HEAD и `origin/main`: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Использованы уже собранные неизменённые Core, coding-workflow и native Anthropic adapter. Точные SHA-256 бинарников в `provenance.json`; верификатор повторно проверил hashes.
- Только изолированные временные профили/сессии, собственные синтетические данные и localhost HTTP. Нет живого LLM, реальных ключей, пользовательских данных или внешней передачи.
- Production-код, исходные checkout и git refs не изменялись. Ничего не опубликовано. Полный workspace gate не запускался: production-патча нет.

## Цепочка причины

1. Core `crates/proteus-core/src/core/reviewed_workflow.rs:67–75` добавляет `continuation.reason` как `InstructionKind::Developer` в `invocation.instructions`; структура continuation также передаётся workflow.
2. Modules `workflow/coding-workflow/src/host.rs:44–73` строит инструкции `request_from_state` только из фиксированной System-инструкции. `input.runtime.instructions` туда не входят. Следующий helper добавляет planning intent, phase instruction и dynamic-tool instruction, но не runtime list.
3. `single_loop.rs` и все три фазы `plan_execute_review.rs` используют именно этот helper. Наличие `runtime.continuation` учитывается scaffold для user anchor и накопленной истории, но его reason отдельно не читается.
4. Core снова вызывает `BeforeStop` с очередным кандидатом. При девятом не принятом кандидате `reviewed_workflow.rs:158–159` выдаёт `before_stop continuation limit exceeded (8)`.
5. Контроль: codex first sampling использует `input.runtime.instructions.clone()` в `host.rs:137`; дальнейшие итерации делают то же в `codex_loop.rs`. Он получает замечание и корректно завершает второй attempt.

Документация обещает эту границу: Core `docs/architecture/process-module-architecture.md:1112–1127` и `docs/architecture/modules.md:233–239` описывают bounded continuation и передачу причины developer instruction. `docs/guides/configuration.md`, раздел Instructions, описывает превращение config entries в ordered canonical InstructionBlock list.

## Воспроизведение через реальные процессы и HTTP

Рецензент просит добавить `REVIEW_ACK`, если его нет в финальном ответе. Локальный native Anthropic endpoint отвечает `FINAL REVIEW_ACK` только если требование реально присутствует в полученных model instructions; иначе `BASELINE CANDIDATE`. Это не проверка способности LLM догадаться: HTTP-захват прямо показывает отсутствие причины.

Основная матрица: reviewer × 3 workflow × 3 независимые сессии, в каждой fresh/warm/cold turn; плюс accept-reviewer и передача той же инструкции штатным `hook.instructions`.

| Workflow | Reviewer требует коррекцию | Вызовов модели на turn | Результат |
|---|---|---:|---|
| `coding.single_loop` | да | **9** | limit error, reason отсутствует во всех HTTP requests |
| `coding.plan_execute_review` | да | **27** | limit error, reason отсутствует во всех plan/execute/review requests |
| `coding.codex_loop` | да | **2** | success, второй request содержит reason |
| `coding.single_loop` | принимает сразу | 1 | success |
| `coding.plan_execute_review` | принимает сразу | 3 | success |
| `coding.codex_loop` | принимает сразу | 1 | success |
| Любой из трёх | reason передан через штатный `hook.instructions` | 1 / 3 / 1 | success |

Все результаты одинаковы в fresh, warm и cold. Основная матрица: **45 turns**.

### Достижимость с поставляемым reviewer

Дополнительно вместо synthetic Python reviewer подключён **настоящий `claude-command-hooks`**, его pinned SDK проверка, штатный Core `hook-process/worker.mjs` и opt-in `Stop` command. Собственная безопасная команда читает только JSON stdin и возвращает exit 2 с тем же замечанием, если marker отсутствует.

Ещё **9 turns**, fresh/warm/cold по каждому workflow: single_loop снова 9 вызовов и error; plan_execute_review 27 и error; codex_loop 2 и success. Сохранены реальные Stop payloads, включая `stop_hook_active`, model HTTP bodies и journals.

**Всего 54 turns: 24 воспроизведённых error outcomes и 30 успешных контролей.** В плохих сценариях журнал подтверждает 9 проверенных кандидатов на turn и `turn_settled: error`; после трёх turns в принятой истории 27 assistant candidates и 3 user messages. Перезапуск сессии не устраняет причину.

### Общий симптом с profile instructions

В каждый профиль добавлен обычный Developer block `PROFILE_ONLY_MARKER`. Он есть во всех HTTP requests codex_loop и отсутствует во всех requests single_loop/plan_execute_review, включая обычный turn без запроса коррекции. Это то же место потери информации, не отдельная finding. `hook.instructions` работает, поскольку добавляет инструкции позже через BeforeModel.

## Применимость без преувеличения

- Ошибка относится к поставляемым workflows, используемым в `examples/configs/proteus.example.toml`, `proteus.coding.example.toml`, `proteus.external-tools.example.toml` и `config.example.json`.
- Текущие packaged codex/default фрагменты выбирают `coding.codex_loop`; для него этот дефект **не воспроизвёлся**. Не заявляем, что обычный codex профиль зацикливается.
- Для сбоя BeforeStop требуется подключённый reviewer, например opt-in `claude-command-hooks` Stop. Без него проблема проявляется как потеря profile instructions, а не как автоматические 9 повторов.
- Реальная LLM может случайно удовлетворить условие и закончить раньше. Доказан пропуск reason на wire, а не гарантированное число запросов для любой реальной модели.

## Направление исправления

В legacy workflow request builder сохранять runtime instruction blocks вместе с workflow-specific System/phase блоками, с явным порядком и без второго добавления continuation reason. Не прятать исправление только в Core или в конкретном reviewer: кодексный контроль показывает, что Core доставляет информацию.

Регрессионные проверки: profile instructions на первом request; BeforeStop reason на повторном request; точное число attempts при исправимом reviewer; single_loop и все фазы plan_execute_review; codex без дублирования; fresh/warm/cold. Изменение production-кода в этом проходе не делалось.

## Проверки и материалы

- `python3 -B run.py`: 45 process/native HTTP turns.
- `python3 -B official.py`: 9 turns через поставляемый Claude Stop adapter.
- `python3 -B verify.py`: матрица, HTTP instruction presence, attempts, journal settlements/history и binary SHA-256; **PASS**.
- `PROTEUS_HOOK_SDK_ROOT=... node --test .../hook/claude-command-hooks/tests/*.test.mjs`: **33 passed, 0 skipped**, включая настоящий worker.
- `run.py`, `official.py`, `runtime.py`, `review_hook.py`, `stop_command.py`: локальные воспроизводители. Для другой машины поправить только корни/пути к pinned checkout и трём собранным бинарникам в `runtime.py`; тесты не компилируют production и не требуют provider credentials.
- Каждая папка случая содержит profile, wire, events, journal, summary, hook/Stop payloads. `verified-matrix.json` даёт компактную сводку.

## Не повышено до finding

Cross-turn повтор provider call ID имеет явный запрет в Core progress contract и документации; без наблюдаемого штатного provider-повтора не трактовался как баг. Гипотеза о сохранении private execute draft после compaction не подтверждена для штатного codex compactor, который удаляет durable assistant history; в результат не включена.
