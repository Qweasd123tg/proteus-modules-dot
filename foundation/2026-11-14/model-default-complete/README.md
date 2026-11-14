# MDC-1: typed failure в default Model::complete

[Source-only отчёт и proposed regression](REPORT.md). **P3 direct public Rust API consistency candidate**, не product incident. Default trait helper игнорирует valid canonical `Ok(Error { failure })`, затем возвращает generic EOF; typed kind/message/retry advice/completed messages недоступны этому caller.

**ModelService и BoundModel корректно обрабатывают terminal Error и не затронуты.** Обычные recorded workflow calls используют BoundModel. Потеря typed failure в raw helper не означает потерю persisted history, отказ automatic retry или сбой stock HTTP/ACP/GUI. RequestError/outer Err уже проходит через `event?`; scope только canonical Ok(Error).

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); tree `00a3c04a70d7927d1688ea155142025f596a2874`. Позднейший upstream требует перепроверки.

Независимый source review подтвердил inherited raw ProcessModel и public catalog builder route, wrapper controls и узкую границу. Дедупликация тематическая по extracted PR84 и полным опубликованным round3-framing, round3-models, model-context: прежний native-provider Other mapping отличается от утраты уже корректного DTO здесь. Полная проверка всех отчётов и абсолютная новизна не заявляются.

Proposed regression: stream-only in-memory Model, одна canonical Error с typed retry/progress, проверка полного failure; controls Response, true EOF, outer typed Err и ModelService. Тесты не созданы/не запускались. Минимальный DRY путь: общий terminal drain с Response/Error без изменения wrapper preparation, validation или recording ownership. EOF classification нужно сохранить намеренно.

Только два Markdown-документа. Rust/build/project tests/fixtures/providers/runtime не запускались; abstract Python fold не production evidence и не включён. Нет source patch, логов, приватных путей, пользовательских данных или сборок. LOC/RSS/latency не измерены; merge публикует исследование, не исправляет runtime.
