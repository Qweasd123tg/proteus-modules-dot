# ET-1: предложение пересмотреть fail-fast policy diagnostic log

## Статус

**Policy/robustness improvement, не установленный defect и не новый bug count.** Одно malformed UTF-8 место в diagnostic event log прерывает весь context snapshot, несмотря на доступную корректную canonical history. Но `context_map/tests.rs:239–240` явно проверяет `[0xff, newline] → is_err()`: fail-fast поведение закреплено существующим тестом. Изменение требует решения о желаемой policy, а не выдачи existing behavior за пропущенную ошибку. Это не проблема безопасности, не terminal-permission finding и не потеря canonical journal.

**Correction record:** первоначальная версия этого отчёта и первый source reviewer ошибочно утверждали, что тесты покрывают только ASCII malformed lines. Дополнительный независимый review указал на `:239–240`; автор перепроверил исходник и снял формулировки missed-test/defect/P3. Причинный путь сохранён как основание обсудить robustness tradeoff.

Core база: `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. PR91–93 прочитаны и не меняют эту production-базу. Код проекта, Rust, HTTP, filesystem fault/crash harness не запускались. Production не менялся.

## Причинный путь

1. `app_server/context_map/telemetry.rs:76–103`, `parse`, вызывает `reader.read_line(&mut String)?` до serde parser и до session filter. `BufRead::read_line` возвращает ошибку на invalid UTF-8, согласно [Rust std documentation](https://doc.rust-lang.org/std/io/trait.BufRead.html#method.read_line). Следовательно, байты вроде оборванного scalar `0xD0` не попадают в ветку `Err(_) => skipped += 1` для malformed JSON.
2. `telemetry::read:61–64` передаёт ошибку наверх; частично собранная telemetry не возвращается. `context_map.rs:34–39` использует `?` **до** формирования canonical history summary и fallback. Отсутствующий log обрабатывается как history-only (`telemetry.rs:46–53`), malformed ASCII JSON пропускается, но одна invalid UTF-8 строка блокирует весь response.
3. `AppServerHandle::context_map_snapshot`, `app_server.rs:337–372`, перед вызовом уже может успешно получить current history/summary. Cold `http/sessions.rs:148–193` тоже получает canonical read model, затем вызывает тот же context builder. В обоих случаях ошибка diagnostic log отменяет полезный ответ. HTTP `/context` в `http/reads.rs:69` лишь передаёт error. Точный HTTP status и экран клиента не проверялись.
4. `matches_session` вызывается только после успешного decode (`telemetry.rs:86–90,105–122`). Поэтому invalid bytes из события одной session блокируют запрос другой session, **если они читают тот же resolved log path**.
5. Default path `.proteus/events.jsonl` (`core/config.rs:539–541`) не включает session ID. `core/runtime/paths.rs:3–11` разрешает relative path от config root, а без config path от cwd. Несколько sessions соответствующего root/workspace штатно делят log. Это не глобальное утверждение обо всех sessions: разные resolved log paths изолированы; explicit absolute path может расширить shared scope.

## Откуда может возникнуть такая запись

`JsonlEventStore::append`, `core/event_store.rs:32–51`, сериализует UTF-8 JSON с newline и делает `write_all`/`flush`. На этом пути нет tail repair, rollback или byte quarantine. Partial failed/interrupted write Unicode-события может оставить неполный scalar; это **допустимая fault предпосылка**, не воспроизведённый crash outcome на конкретной filesystem. Обычный successful append сам invalid UTF-8 не производит.

Позднейший append просто дописывает данные к тому же файлу. Он не устраняет старый invalid byte. Если новый event приклеился к оборванной строке, оба могут образовать одну malformed строку; данный отчёт не обещает восстановить её содержимое. Но следующие самостоятельные валидные строки тоже остаются недоступны текущему parser, потому что он каждый раз прекращает чтение на прежней UTF-8 ошибке.

Telemetry cache не лечит проблему: `telemetry/cache.rs:102–110` отвергает прежнюю запись при изменении source stamp, а ошибка parse не сохраняет новую telemetry. Пока invalid bytes остаются в выбранном log, повторный запрос возвращается к тому же error. Исправление/rotation log может восстановить функцию; «необратимый» или «вечный» отказ не заявляется.

## Существующая policy и проверки

`app_server/context_map/tests.rs:104–137` добавляет malformed **ASCII** tail и ждёт diagnostic `skipped 1 malformed event log lines`. `:217–229` проверяет ASCII malformed lines и отсутствующий log. **`:239–240` отдельно записывает invalid UTF-8 `[0xff, newline]` и ожидает `is_err()`**. Таким образом, разделение JSON syntax damage и encoding damage уже закреплено, и предлагаемое продолжение чтения меняет существующий контракт. Тесты прочитаны, не запускались.

## Предложенные policy-change проверки, НЕ ЗАПУЩЕНЫ

1. Расширить существующий context-map fixture: два валидных canonical sessions A/B, один общий temporary event log, valid usage/context events для B.
2. Добавить synthetic malformed byte line, например JSON prefix, заканчивающийся `0xD0`, и newline; после неё добавить ещё один полный valid event для B. Это synthetic corruption fixture, **не crash reproduction**.
3. Сначала принять policy decision. Если выбран tolerant diagnostic mode, проверить `telemetry::read` и context builder для B: новый желаемый result сохраняет B history/summary и доступные valid telemetry events, содержит явную diagnostic о пропущенной invalid строке. Текущий error до session filtering соответствует existing test; его нельзя называть failed regression без изменения policy.
4. Вариант настоящего unterminated tail плюс следующий append проверяет, что объединённая malformed строка пропускается, но parser продолжает с последующей независимой строкой. Не ожидать восстановления утраченных bytes.
5. Контроли: intact Unicode; malformed ASCII; empty/missing log; valid log другой session; invalid bytes в другом resolved log path; source/cache invalidation после исправления log. Отдельный I/O-error policy не смешивать с malformed-record policy.

Отдельная минимальная parser-модель (не включена в пакет) только иллюстрирует различие UTF-8 decode-before-filter и byte-framed malformed-record handling. Это не реализация Rust `BufRead`, не запуск Proteus/HTTP и не эксперимент с дисковой записью.

## Локальное упрощение

Если продукт выбирает доступность canonical context при повреждённой auxiliary telemetry, diagnostic reader можно перевести на одну границу malformed **record**, а не глобальную UTF-8 корректность всего файла. Читать byte-framed строки (`read_until`), парсить `serde_json::from_slice`, учитывать decode/JSON errors в существующем `skipped` diagnostic и продолжать. Это сохраняет raw evidence и не требует «чинить» log при чтении. Не использовать lossy decode для тихой подмены payload. Tradeoff: часть telemetry будет отсутствовать, поэтому diagnostic обязателен; fail-fast policy тоже допустима, если это осознанное требование продукта.

Отдельно определить fallback при настоящих filesystem I/O errors: можно вернуть canonical history с явным diagnostic, но это другая policy, а не причина скрывать любые ошибки. Не ослаблять strict canonical journal reader: здесь речь только о вспомогательной telemetry.

Такой разрез устраняет неявную зависимость whole context response от корректности чужих diagnostic bytes и объединяет existing ASCII/UTF-8 malformed cases. Runtime/LOC/RSS эффект не измерен.

## Дедупликация и review

Не повторяет DS-1–4, SL-1 и CT-1 из PR91–93: речь о diagnostic log parser, его session filtering и history-only fallback, не о cache cap, journal commit, async lineage или context timeout.

Targeted поиск в полном PR84 extracted text по telemetry/context_map/UTF-8/malformed не выявил совпадения. Самостоятельно прочитаны опубликованные `context-memory`, `hook-usage`, `history-events`, `memory-reload`, `profile-runtime`: точного policy discussion не найдено. Memory-reload относится к canonical memory provider и требует другого failure policy; это не разрешение терпимо читать canonical storage. Полный поиск 97 reports не завершён и не заявляется.

Независимые source reviews подтверждают causal path; дополнительный reviewer установил существующий fail-fast test и тем самым изменил классификацию. Этот материал предлагается только как policy discussion. Материал не включается в число установленных новых defects.

## Закреплённые source anchors

Пути `core/...` и `app_server/...` относительны `crates/proteus-core/src/`. Ключевые production-файлы не менялись delivery PR87–89.

- [app_server/context_map/telemetry.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/context_map/telemetry.rs#L76-L103)
- [app_server/context_map/tests.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/context_map/tests.rs#L239-L240)
