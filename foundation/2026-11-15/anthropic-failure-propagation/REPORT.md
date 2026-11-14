# Native Anthropic: source-only candidate для известного M4

## Итог и статус

**Подготовлено узкое исправление propagation для уже опубликованного M4, не новая finding.** Один provider-local decoder сохраняет причину ошибки через native Anthropic HTTP и SSE boundaries. Существующие compactor и Codex sampling loop уже умеют действовать по typed ModelFailure; копировать recovery logic в provider или заставлять workflow разбирать provider text не требуется.

Это source-reviewed candidate, не compile/test/runtime PASS. Production и upstream refs не изменялись. Исторические тесты исходной finding не выполнялись повторно и не доказывают работоспособность этого patch.

## Версии и происхождение

- Modules: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Actual Core dependency pin: `41bdfffa6e70228278b4abc758b7f81a12672f35`; Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Delivery main на начале прохода: `3c78eedf559d66094e769a303f10d6d6f691d035`, включает PR109.
- [Исторический M4 report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/3c78eedf559d66094e769a303f10d6d6f691d035/research/proteus-continuous-audit-2026-11-13/evidence/model-context/REPORT.md) описывает потерю actionable kind: oversized summary повторялся без удаления старой истории; premature SSE EOF/overload обходили configured reconnects. Этот проход проверяет source fix direction, а не воспроизводит старую матрицу.
- PR109 чинит другой boundary, legacy runtime instructions. PR108 меняет ownership Anthropic SSE state и текстово пересекается с этим candidate. PR99/default Model::complete остаётся отдельным ограничением ниже.

## Точная allowlist классификации

| Вход | Предлагаемый kind |
|---|---|
| HTTP400 + `error.type=invalid_request_error` + message точно `prompt is too long` или начинается с `prompt is too long:` | ContextWindowExceeded |
| HTTP529 + `error.type=overloaded_error` + строковое message | Retryable, без синтетического delay |
| HTTP200 SSE error с `error.type=overloaded_error` и строковым message | Retryable, без синтетического delay |
| HTTP200 SSE чисто заканчивается без terminal event | StreamDisconnected |
| Любой другой status/type/message, malformed error payload | Прежний Other |

Provider docs подтверждают отдельный HTTP400 input-overflow diagnosis, отличающийся от успешного generation stop при заполнении окна. Последний остаётся прежним FinishReason::Length; эта ветка не меняется. [Context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows)

HTTP529 означает временную перегрузку; error envelope содержит type/message. Это не основание считать transient любой HTTP400/429/500 или новый неизвестный type. Candidate намеренно не расширяет классификацию на эти статусы. [API errors](https://platform.claude.com/docs/en/api/errors)

Overload также может прийти отдельным SSE error после HTTP200. Stream terminal и error являются разными исходами; partial text не превращается в завершённое сообщение. [Streaming messages](https://platform.claude.com/docs/en/build-with-claude/streaming)

Узкая message allowlist может не распознать будущую новую формулировку overflow. Тогда останется Other, а не необоснованный trim. Это сознательный предел, не обещание полного покрытия всех Anthropic ошибок или прокси.

## Изменения по границам

1. **Non-stream HTTP:** прежние status + raw body diagnostics сохранены, но известная причина обёрнута в ModelFailure. Unknown statuses/types остаются Other с прежним текстом.
2. **Streaming HTTP startup:** body читается только для400/529, чтобы классифицировать точную пару status/type и сохранить диагноз. Остальные статусы проходят прежний `error_for_status()`.
3. **SSE error event:** используется тот же provider-local decoder. `stream_failure_kind` разрешает actionable SSE kinds только на HTTP200, поэтому1xx/3xx/прочие2xx не приобретают recovery из-за прежнего разрешающего HTTP gate.
4. **EOF:** только HTTP200 без terminal становится StreamDisconnected. Явные eventsource parser/transport errors, malformed SSE JSON и недопустимые tool args сохраняют Other. Не заявляется, что все виды сетевого обрыва теперь умеют reconnect.

Независимый reviewer выявил важную ошибку первой версии: сохранение `error_for_status()` само по себе не сохраняет semantics1xx/3xx, если их последующий EOF/overload становится retryable. Candidate исправлен явным HTTP200 eligibility gate, затем перечитан. Это закрытый scope blocker proposal, не дополнительная finding в продукте.

## Что не меняется

- Публичные contracts и DTO, provider configuration, transport retry count/backoff, workflow retry budgets и timing ownership.
- Successful response parsing, terminal stop reasons, tool execution и completed-message ownership. EOF/error не дополняются partial deltas.
- Native OpenAI, Pi и прочие providers. Не заявляется исправление текущего default Pi profile.
- HTTP429, unknown5xx и произвольные validation failures не получают новые retries или context trimming.

Чтение полного error body теперь добавляется в streaming startup400/529. Non-stream и раньше читал body целиком. Candidate не вводит новый body budget, не сохраняет отдельные payload artifacts и не заявляет снижение RAM/CPU/latency. Read/parse failure остаётся обычной ошибкой; необходимость ограничения крупных diagnostics отдельно не решалась.

## Propagation и важный предел PR99

`ProviderModule::stream` преобразует outer typed error через ModelFailure::from_error в ProcessModelTerminal::RequestError, а canonical Error в ProcessModelTerminal::StreamError. На этом пути kind не теряется. `codex-context-preparation/recovery.rs` использует ContextWindowExceeded для удаления старого материала; `coding-workflow/codex_sampling.rs` принимает StreamDisconnected/Retryable в свой уже bounded reconnect loop. Они не изменены.

Но inherited raw Rust `Model::complete` на actual Core pin всё ещё игнорирует canonical Ok(Error), как описано в PR99. Поэтому candidate **не** обещает сохранность typed SSE failures через любой direct Rust `.complete()` call. Это отдельный известный boundary, не исправленный здесь. HTTP error, возвращённый до создания stream, не проходит через этот ошибочный event fold.

## Предложенные тесты, все NOT RUN

Четыре pure/source-level unit test functions в новом `anthropic/errors.rs`:

- Матрица HTTP status/type/message с exact allowed pairs, сохранением diagnostics и empty completed_messages; downcast через anyhow context и serde round trip.
- Матрица SSE eligibility: только HTTP200 сохраняет recovery kind; в том числе101/201/204/302 остаются Other.
- Unknown types, unrelated validation messages, нестроковые/отсутствующие поля, malformed JSON и похожие неподходящие overflow strings не получают recovery.
- Реальный AnthropicStreamState по source API: partial text → error не выдаёт завершённого сообщения; overload и unknown/malformed controls.

Pure tests не проверяют actual HTTP requests, EOF polling, provider errors после разных progress checkpoints, retry delays или успешную compaction/reconnect. Новое EOF место и startup wiring сейчас проверены чтением, не исполнением. Нужны focused compile/tests и затем loopback integration matrix exact patched binary; старый M4 test-only reproducer может быть основой, но не был запущен этим проходом.

## Проверки artifacts и PR108

- 14 source blobs совпали с repository Git SHA; `READ-VERIFICATION.json` содержит SHA256/размеры.
- Standalone `anthropic-failure-classification.patch` проходит `git apply --check --whitespace=error` и текстовое применение к сохранённому baseline.
- **Исходные PR108 и M4 patches не auto-compose:** оба порядка дают context conflict в соседнем SSE-loop hunk. Это сохранено в `PATCH-VERIFICATION.json`, а не выдано за успешный merge.
- Подготовлен отдельный `anthropic-failure-on-PR108.patch`: тот же M4 diff поверх прямого ownership из PR108. В combined source ровно три прежние ownership substitutions; errors.rs и stream.rs совпадают с standalone candidate. Rebased patch проходит text apply/check и совпадает с `combined-with-PR108/`. Это ручное разрешение текстовой коллизии, не совместный build.
- `M4-INDEPENDENT-REVIEW.md` фиксирует независимый exact source verdict и пределы.

Не запускались Rust/cargo/compiler/rustfmt/clippy, project scripts, tests, fixtures, live providers или приложение. Toolchain/dependencies не устанавливались. Публикаций и production changes нет. Только source/text/hash операции и чтение первичных docs.

## Артефакты

- Standalone patch SHA256: `09c17c0b5ba48e7e715453c3c90a24875e8d288f740eefe4fc1e62e631303ce4`.
- Rebased-on-PR108 patch SHA256: `264ede250e103dc353d9fb630e30217d6ceae34b821ce68cdac894a802a43acf`.
- `before/`, `after/`, `combined-with-PR108/`, `core-pin/`, `SOURCES.json`, `READ-VERIFICATION.json`, `PATCH-VERIFICATION.json`, итоговый independent review.
- `PRIOR-M4-REPORT.md`: историческое обоснование, не результат текущих tests.

До toolchain и интеграционных проверок публиковать только как непроверенный source candidate для известного дефекта, не как готовый production fix.
