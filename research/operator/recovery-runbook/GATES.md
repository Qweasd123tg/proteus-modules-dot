# Десять необходимых проверок — не выполнены

Все сценарии ниже — проект проверки будущего host/app consumer на собственных разрешённых fixtures. Это не результаты Core, HTTP, CLI или provider запуска; этот пакет не содержит нового runtime. Перед выполнением нужны отдельные authority, source identity, ресурсные bounds и supervision. Production sessions не используются.

| ID | Изолированная причинная пара | Что должна сохранить проверка |
|---|---|---|
| G01 | Started принят, ACK получен / ACK потерян после admission | Потеря ответа не превращается в rejection; exact active ID сопоставляется без повторной отправки. |
| G02 | Queued ACK сохранён / потерян, затем queue item потреблён | `request_id` и `message_id` различны; отсутствие request ID в pending и текстовое сходство не дают ложный dedup receipt. |
| G03 | Известный ID active / terminal last / last вытеснен следующим run | Первые два — наблюдаемые live facts; третье — unknown, не безопасный retry. Отдельно ID reuse и новый server incarnation. |
| G04 | Cancel запрошен до settlement / settlement уже записан | ACK запроса отмены не равен terminal canceled; disappearance of active не доказывает OS/external-effect stop. |
| G05 | Исторический turn открыт без settlement / закрыт Error / неверный T | `unsettled` не считается live-running; Error относится только к T; unknown turn/read failure не выдаёт пустой успешный отчёт. |
| G06 | Только effect record / effect + final после AfterTool | Existing analysis теряет эту разницу. Будущий inspector обязан показывать различимые variants/sequence/owner; ни один результат не объявляет physical-effect receipt. |
| G07 | Catalog cache fresh / stale placeholder / malformed canonical source | Catalog visibility не является strict validation; анализ имеет отдельный validation outcome. Cache refresh/первый SSE start отмечаются как side effects. |
| G08 | Eval failed при незавершённом turn / lifecycle success с tool failure | Exit/доставленный human report не превращаются в task success; objective остаётся отдельным unknown. |
| G09 | Replay report matched Success / matched Error / divergence / invalid shape | Существующий R39 классифицирует только reported state; matching Error не objective success. Actual Core replay и compatibility проверки остаются отдельно не выполнены. |
| G10 | Проверка проекта доставила failed report / passed без подтверждённого ожидаемого набора тестов | Delivery, command status, coverage и objective oracle не сливаются. Никакие чужие scripts/tests не запускаются автоматически. |

Каждый eventual runtime gate должен хранить точные входы, producer identity, наблюдаемые ответы/ошибки и ожидаемый независимый oracle; одних `exit 0`, UI prose или совпавшего текста недостаточно. Эти требования не доказывают, что gate уже реализован.
