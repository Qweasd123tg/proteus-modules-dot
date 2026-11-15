# Anthropic start blocks: source-only candidate A2/A3

Известные A2/A3 из [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85), не новые findings. [REPORT.md](REPORT.md) содержит семантику, источники и ограничения; [независимый review](START-BLOCK-INDEPENDENT-REVIEW.md) относится только к исходникам.

Патч применяется к Proteus-harness/Proteus-modules c035142558f0fca43e9772fc0e50ca293abf1531. Сохраняет начальный text/tool input; start и delta используют общий text accumulator. Production prefix +29 строк. Это исправление потерь, не оптимизация производительности.

6 proposed tests NOT RUN. Rust/compiler/runtime/CI не запускались. Проверены Git blob SHA всех 15 источников, SHA256 патча, strict text apply и byte equality с reviewed after. Публикация этого пакета не меняет upstream production.

## Композиция
С [PR108](https://github.com/Qweasd123tg/proteus-modules-dot/pull/108) и [PR110](https://github.com/Qweasd123tg/proteus-modules-dot/pull/110) проверено семь текстовых порядков, не runtime integration. Для сочетания PR108+PR110 обязательно использовать rebased [anthropic-failure-on-PR108.patch](../anthropic-failure-propagation/anthropic-failure-on-PR108.patch): оригинальные патчи конфликтуют. Интеграция с [PR111](https://github.com/Qweasd123tg/proteus-modules-dot/pull/111) не проверена.

До внедрения upstream нужны штатные project gates и реальные regression tests. Здесь только source proposal и документация, без logs, binaries и source snapshots.
