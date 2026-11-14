# Три source-only кандидата: cache availability и границы tool invocation

Статус: **исследование по исходникам, не runtime patch**. Никакие Rust tests/build, HTTP/GUI-прогоны или реальное исполнение process worker для этих кандидатов не выполнялись. Все сценарии ниже являются будущими regression contracts, а не результатами тестов.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); проверенное результирующее дерево `00a3c04a70d7927d1688ea155142025f596a2874`. Upstream после этой базы требует повторной проверки. Ссылки на код закреплены на upstream commit; перечисленные production-файлы этих цепочек не изменены указанными delivery patches. Документация runtime-and-events изменена PR89, её номера строк относятся результирующему дереву.

| Кандидат | Приоритет | Что подтверждено | Чего не доказано |
|---|---|---|---|
| [DS-1](FINDINGS.md#ds-1-disposable-cache-становится-условием-доступности-history-api) | P2 candidate | Fingerprint cap участвует в обязательных page/tool-state путях | Runtime reproduction, Desktop symptom, потеря данных |
| [Tool result identity](FINDINGS.md#tc-1-inner-call_id-не-сверяется-с-invocation) | P2, условный риск | Host не сравнивает inner result ID с исходным call ID | Реальная ошибочная запись sibling result; security escalation |
| [Zero timeout](FINDINGS.md#tc-2-zero-timeout-имеет-разную-семантику-на-двух-границах) | P3 contract clarification | Zero отключает local timer, но даёт process budget 1000 ms без override | Нарушение согласованного unlimited contract; сбой stock profile |

Общий путь упрощения: закрепить один authoritative invariant на общей границе вместо независимых защит в отдельных consumers. Для DS-1 разделить canonical read identity и disposable cache; для TC-1 валидировать результат до hooks/recorder; для TC-2 сначала выбрать и описать единую семантику бюджета. Это три разные ответственности, не повод вводить универсальный framework.

Ожидаемый выигрыш пока качественный: меньше недостижимых recovery loops и мест, где приходится помнить скрытое условие. LOC, скорость, RSS, частота сбоев и процент сокращения ошибок **не измерены**. Публикация не означает внедрение или устранение этих семейств ошибок.

## Проверка и дедупликация

Source chains перепроверены независимо; оговорки про active/cold history, sibling journal identity и export override включены. Для DS-1 дополнительно проверены 102 опубликованных reports/README/addenda и полный DOCX из PR84, закреплённый на head и сверенный с manifest SHA-256. Для tool-кандидатов проверены 97 MD/TXT материалов continuous audit, PR86–90 и полный ноябрьский DOCX. Прямого дубликата в проверенном корпусе не найдено; это не заявление абсолютной новизны. Отрицательный GitHub code search сам по себе не использовался как доказательство.

DS-1 связан с опубликованным PERSIST-2 (orphan cleanup), но фиксирует иной downstream availability consequence. PERF-2 из PR84 касается отсутствующего test oracle для новых blob files, а не описанной цепочки. History-events revision replacement, RSL-1 retained background card и PR90 live-session shutdown также не являются этой проблемой.

В пакет входят только два Markdown-документа: описание, ограничения и неисполненные тестовые контракты. Исходники, журналы, пользовательские сессии, credentials и бинарные сборки не публикуются.
