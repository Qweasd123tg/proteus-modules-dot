# DS-8: warm/canonical model-context order

[Отчёт и план проверки](REPORT.md). Узкий **P3 source-only consistency candidate / contract clarification** для concurrent custom workflow, пока turn resident. Canonical commit order и outer recorder application order могут различаться; total usage не объявляется потерянным, normal release возвращает canonical authority.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); tree `00a3c04a70d7927d1688ea155142025f596a2874`.

Независимый source review учтён. Не выбрано значение физически «последнего» concurrent response, не установлен default-profile incidence, не измерены LOC/RSS/latency. Предлагаемый regression требует post-inner-append/pre-ack gate, а не timing sleep или before-write pause.

Только два Markdown-документа. Нет production changes, сырых логов, приватных путей, пользовательских данных, моделей или сборок. Rust/runtime/HTTP/tests не запускались. Абстрактная модель не является runtime evidence; merge означает публикацию исследования, не исправление.
