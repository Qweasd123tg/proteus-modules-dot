# Async lifetime и durability: три source-only кандидата

Это исследовательская документация, **не runtime patch и не подтверждение тестовых прогонов**. Rust/build/tests/worker/HTTP/GUI/fault-injection не выполнялись. Иллюстративные модели не являются экспериментальным evidence и не включены в пакет.

Точная база: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89), результирующее дерево `00a3c04a70d7927d1688ea155142025f596a2874`. [PR90](https://github.com/Qweasd123tg/proteus-modules-dot/pull/90) и [PR91](https://github.com/Qweasd123tg/proteus-modules-dot/pull/91) содержат документацию и не меняют эту production-базу. Более поздний upstream требует повторной проверки.

| Отчёт | Условие | Подтверждённая source-граница | Не установлено |
|---|---|---|---|
| [SL-1](SL-1.md), P2 conditional | Workflow/model в одном exact broker; для admission symptom нужны занятые root slots и barrier | Stream pump теряет task-local process parent через spawn | Вечный deadlock, обязательный timeout всех calls, runtime reproduction |
| [DS-2](DS-2.md), P2 только при обещании OS/power-crash durability | Durable existing session и новый referenced blob | ACK не устанавливает file + namespace dependency barrier | Потеря данных на конкретной FS, вероятность power-loss outcome |
| [DS-3](DS-3.md), P2 conditional | Internal direct Rust API; drop/abort run future после admission append; runtime жив | Durable append переживает caller, warm reconciliation не переживает | Достижимость через обычный HTTP disconnect/GUI, permanent corruption |

## Системный вывод и выигрыш

Три случая объединяет необходимость явно назначить владельца обязательства через async/storage boundary, но обязанности различны:

- process parent/admission должны переживать перенос model stream в task;
- canonical ACK должен покрывать durability referenced dependencies, если продукт обещает именно power-crash guarantee;
- accepted append, warm invalidation/publish и release run admission должны иметь согласованное lifetime.

Предлагаются локальные границы ответственности в существующих подсистемах, не общий task/storage framework. Направления исправления и ещё не выполненные regression contracts приведены в отчётах. Меньше разрозненных условий и обходных recovery-веток ожидается качественно; LOC, скорость, RSS и доля предотвращённых ошибок не измерены.

## Проверка и дедупликация

Независимые source reviews учитывают exact-broker/barrier и timeout/cancel controls для SL-1; retry directory barriers и условность power-crash guarantee для DS-2; internal API scope, drop future, active-hooks control и surviving runtime для DS-3. Source-only review не заменяет runtime validation.

SL-1 сверялся с 97 continuous audit reports/README/addenda, полным ноябрьским DOCX и PR91. DS-2/DS-3 сверялись с релевантными persistence/runtime/history/resume отчётами и тематическими фрагментами полного extracted PR84. Это не повторное построчное чтение всех 91 страниц и не доказательство абсолютной новизны. PERSIST-1 частично пересекается с initial identity подслучаем DS-2; он не считается второй новой находкой. PERSIST-2 относится к ошибочному write/cleanup, а основной DS-2 к success ACK. PR90 completion fence не является fsync ordering; PR91 рассматривает другие цепочки.

Публикуются только четыре Markdown-документа. Production-код, модели, сырые логи, пользовательские сессии, credentials и сборки не включены. Публикация и merge исследовательских документов не означают внедрение исправлений.
