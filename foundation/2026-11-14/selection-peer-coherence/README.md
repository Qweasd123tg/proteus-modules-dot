# DS-9 / DS-10: два source-only P3 кандидата coherence

Только исследовательская документация, не production patch. Rust/runtime/HTTP/ACP/GUI/tests не запускались; abstract Python models не являются runtime evidence и не включены в пакет.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); tree `00a3c04a70d7927d1688ea155142025f596a2874`. Позднейший upstream требует перепроверки.

- [DS-9](DS-9.md): presentation race собирает current model и catalog options из разных publications. Это не wrong-provider invocation или повреждение durable configuration: setters повторно валидируют актуальный snapshot. Допустим coherent old response; смешанная tuple является предметом кандидата. Existing catalog_wait seam слишком поздний для нужной фазы.
- [DS-10](DS-10.md): Unix same-process independent SessionStore opens делят writer, но не metadata cache. Peer hibernation может заставить retained active handle вернуться от уже прочитанного S2 к старому S1. Это не обычный fresh HTTP lookup, не canonical data loss или billing error. Clone shares metadata и является negative control. Usage/history revisions различны: history append сам по себе не доказывает изменение usage.

Независимые source reviews включены. Для DS-9 proposed regression нужен gate до registry capture, не просто slow catalog. Для DS-10 проверка последовательная, с independent opens, валидными committed facts и peer hibernation. Ни один regression не реализован/исполнен.

## Упрощение и пределы выигрыша

DS-9: переиспользовать уже существующий coherent configuration_view → assembly config → same registry catalog путь, не держать write lock через remote discovery. DS-10: shared committed summary или shared mutation epoch с provenance для handle-local cache; active/retired enum сам по себе не исправляет disagreement активных peers. Full per-request usage растёт с количеством requests, постоянный memory bound не заявлен.

LOC/RSS/latency и frequency не измерены; default-profile incidence не установлен. Дедупликация тематическая по указанным в отчётах опубликованным материалам и extracted PR84, не полный повторный аудит всех отчётов.

Три Markdown-документа без моделей, сырых логов, приватных путей, пользовательских данных и сборок. Merge означает публикацию исследования, не исправление runtime.
