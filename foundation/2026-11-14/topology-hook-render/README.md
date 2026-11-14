# THR-1: ordered hook chain в full Mermaid topology

[Source-only отчёт и proposed regression](REPORT.md). **P3 diagnostics-only**: full Mermaid использует singular active_module для Hook и показывает `hook<br/>missing` при непустой выбранной цепочке. Snapshot сохраняет hooks/order/active entries; runtime Mermaid трактует ordered chain отдельно.

**Runtime hook execution не затронут этим выводом.** Не заявляются потеря configuration, malformed Mermaid syntax, rendered SVG/GUI defect или наблюдённый CLI/HTTP incident. Source path обычного configured profile установлен, но runtime не запускался.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); tree `00a3c04a70d7927d1688ea155142025f596a2874`. Позднейший upstream требует перепроверки.

Независимый review подтвердил producer/renderer mismatch, ordinary nonempty chain и controls. До публикации повторно прочитаны полные опубликованные round3-core, round4-core, round3-framing, hooks-replay; PR91–100 не содержат этого projection finding. Targeted extracted PR84 search также не выявил совпадения. Это ограниченная дедупликация, не абсолютная новизна.

Упрощение: один небольшой ordered-selection display helper для full/runtime renderer, без фиктивного singular Hook active_module и без потери порядка. Proposed regression: normal topology builder с двумя hooks; one/reversed/empty и required singular-slot controls. Если выбран graph-edge вариант, сначала создать соответствующие nodes. Тесты не реализованы/не запускались; LOC/RSS/latency не измерены.

Только два Markdown-документа, без production patch, моделей, сырых логов, приватных путей, пользовательских данных или сборок. Rust/project tests/CLI/HTTP/Mermaid renderer/GUI не запускались. Abstract label model не runtime evidence. Merge публикует исследование, не меняет runtime.
