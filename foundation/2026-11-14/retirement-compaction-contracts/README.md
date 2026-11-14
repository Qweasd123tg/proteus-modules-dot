# Retained-read lifecycle и compaction report cardinality

**Два узких source-only кандидата, не runtime patch.** Rust/runtime/HTTP/GUI/replay не запускались. Абстрактные модели отражают только выбранные control-flow предпосылки, не являются production evidence и не включены в пакет.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89), tree `00a3c04a70d7927d1688ea155142025f596a2874`. PR91–94 production не меняют. Позднейший upstream требует повторной проверки.

## Кандидаты

- [DS-6](DS-6.md), **P3 API lifecycle consistency**: retained SessionStore может читать cached usage/revision после завершённого owned delete, в отличие от guarded execution-state reads и документации retirement. Это не fresh HTTP lookup, не восстановление удалённой истории и не потеря данных. Initialized writer и Unix hibernated per-handle metadata являются разными ветвями с отдельными prerequisites.
- [DS-7](DS-7.md), **P3 diagnostics/replay-evidence correctness**: custom workflow принимает plural changed reports, но singular journal mutation сохраняет только последний новый report. Итоговые сообщения не объявляются потерянными. Shipped/default профиль с таким batch не установлен. Singleton control проверяет равенство report inventory, **не полный replay PASS**: direct compaction без preparation callback может отдельно оставлять unconsumed replay evidence.

## Предлагаемое упрощение

DS-6: одна active-generation проверка перед всеми writer/read-metadata fast paths либо явное documented исключение для historical snapshots. Не ослаблять writes/continuation guard, не менять cold inspection без основания.

DS-7: один accepted batch/prefix contract между checkpoint, terminal commit и durable/replay inventory. Либо сохранять весь ordered evidence, либо отвергать неподдерживаемый batch до принятия. Не скрывать потерю сравниванием только последнего report и не создавать фиктивные intermediate histories. Format change требует отдельного schema-version решения.

LOC/RSS/latency и частота production-сбоев не измерены. Регрессии предложены, но не исполнены; publication не означает исправление runtime.

## Review и дедупликация

Независимые source reviews прочитаны и учтены. DS-6 ограничен retained handles и двумя cached-read ветвями; обычный post-delete HTTP путь исключён. DS-7 review подтверждает report-loss/cardinality, требует inactive hooks для минимального inventory и сохраняет отдельный replay-consumption caveat. `modules.hooks=[]` должен быть сохранён и при recording, и при replay proposed fixture.

Дедупликация ограничена указанными в отчётах релевантными опубликованными materials и targeted поиском полного PR84 DOCX. Полный повторный просмотр всех 97 reports не заявляется. Уже известный replay ID normalization случай не добавлен как новая находка. Эти кандидаты отличаются от предыдущих cache cap, dropped-run, precommit-read и clear-snapshot цепочек.

Только три Markdown-документа, без source patches, моделей, сырых логов, приватных путей, пользовательских данных и сборок. Merge публикует исследование, а не изменяет production.
