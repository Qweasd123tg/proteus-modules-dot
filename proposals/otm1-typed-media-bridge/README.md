# OTM-1: общий typed media bridge, source-only proposal

Продолжение [PR102](https://github.com/Qweasd123tg/proteus-modules-dot/pull/102): один forward/reverse контракт для text/image/error вместо точечных заплаток. Производственный код +36 строк. Это пакет для интеграции, не установленное исправление.

**7 предложенных тестов, 0 выполнено.** Штатные зависимости отсутствуют; native/runtime/provider acceptance не проверены. См. [REPORT.md](REPORT.md), независимые reviews и patch.

Multi-text prompt representation меняется намеренно. Exact DTO round-trip не обещается. Upstream flatten/prune policy сохраняется; binary/PDF/Json, user attachments и error-image accounting вне scope. PR113 относится к другой границе и сам по себе OTM-1 не исправляет.
