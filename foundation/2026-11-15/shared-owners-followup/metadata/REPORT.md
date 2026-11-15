# Codex metadata: один владелец HTTP/401-перехода

## Результат

Один небольшой source-only кандидат: `catalog` и `quota` вызывают общий
`send_metadata_request` в **существующем** `openai/transport.rs`. Вместо двух
копий политики GET → HTTP 401 → refresh → один повторный GET остаётся одна.
Не вводятся общий provider framework, transport trait, второй cache,
dependency, DTO, новая настройка или поведение Core.

Это не новый bug и не performance-результат. **Compiler, Rust tests, rustfmt,
HTTP fixtures, provider/API, application runtime, CI и benchmarks НЕ
ЗАПУСКАЛИСЬ.** Готовность к production-интеграции не установлена.

Patch `metadata-transport.patch`, SHA-256:
`8983c8b8ec0c6acdb65f5495dc0509f68ee63ad57ae7d1c3adb352128e95eac7`.

## База и дедупликация

- Modules current main:
  [`42ae75355256190d01b569c85633b333d573f052`](https://github.com/Proteus-harness/Proteus-modules/tree/42ae75355256190d01b569c85633b333d573f052).
- Реальный Core dependency pin из Modules Cargo.toml:
  `185225a7103088c444788374ca425d230060f55a`; он не меняется.
- Dot delivery main после #165:
  [`cbd9ec315f88f85708d26d47cc2193970a7c904b`](https://github.com/Qweasd123tg/proteus-modules-dot/commit/cbd9ec315f88f85708d26d47cc2193970a7c904b).
- Проверены titles/bodies PR1–165, связанные прежние model reports и
  ограниченный поиск по `send_metadata_request`, `codex_catalog codex_quota`.
  Прежнего такого cut в проверенном материале не найдено. Это bounded dedup,
  не полный ручной аудит всех исторических raw artifacts.

#62 уже исправлял включение cache-lock wait в общий catalog deadline и
повторное JSON encoding inference requests. #65 убирал выбрасываемый
промежуточный HTTP client. Они сохраняются, а не предлагаются повторно.
#108/#158 касались SSE ownership/provider semantics. #165 уже публикует
удаление dead terminal reader и ложной test matrix: здесь они не повторяются.
Ранее упомянутый instruction-prefix helper также не включён.

С fresh recursive tree сопоставлены Git blob SHA и SHA-256 для 64 файлов,
включая все 61 Rust source file model-pack. Это полнота поиска caller в этом
Rust-пакете, **не полный ручной аудит каждого файла**. Все три изменяемых
production preimage и existing test file дополнительно получены напрямую
через connector. `SOURCES.json` содержит точные identities.

## Почему граница именно здесь

Общая ответственность принадлежит provider transport: получить OAuth access,
прикрепить те же headers, выполнить запрос, при первом HTTP 401 передать
отвергнутый token в существующий `CodexAuth::access`, повторить ровно один раз
и сохранить существующую диагностику status/transport error.

Endpoint-specific owners остаются отдельными:

| Инвариант | Catalog | Quota |
| --- | --- | --- |
| Адрес | `base_url/models`, query `client_version` | Явный `quota_url` |
| Cache TTL | 300 секунд | 30 секунд |
| Lock/coalescing | Свой существующий mutex | Свой существующий mutex |
| Общий deadline | 30 секунд, включая lock/auth/decode | 30 секунд, включая lock/auth/decode |
| DTO | ModelsResponse, sort priority, catalog validation | QuotaResponse, snapshot validation |
| Parse error | Прежний anyhow context/error chain | Прежняя обобщённая ошибка без body |
| Publication | Только после decode + validate | Только после decode + validate |

API-key client по-прежнему возвращает `None` без OAuth. Cache hit не запускает
HTTP/auth. Нет stale fallback. Другие статусы, включая 429 и 5xx, не получают
повторов. Второй 401 завершается прежней HTTP-ошибкой. Тексты ошибок не меняются;
общий `metadata_request_error` сохраняет `without_url` и становится private,
поскольку единственный caller теперь в том же файле.

Request-builder closure не вводит boxed future/dynamic transport и вызывается
в тех же request attempts. У catalog lookup `client_version` теперь выполняется
при каждом build; поле читается из неизменяемого `secret_config`, поэтому query
остаётся тем же. Временный `Access` с token/headers теперь завершает свой scope
при возврате HTTP response, до endpoint JSON decoding. Раньше он оставался в
scope endpoint loop; после HTTP он нигде не использовался. Это изменение
локального lifetime, не обещание уменьшения памяти. Отдельная bounded refresh
transaction, переживающая отмену caller, остаётся в `CodexAuth` без изменений.

## Что сознательно не объединяется

- Responses inference transport использует свою request retry policy,
  canonical per-request affinity headers и `ensure_success` с typed failures.
  Перенос metadata на этот путь добавил бы нежелательные 5xx/network retries.
- Anthropic transport имеет другую retry/error/status политику; его sharing
  лишь по похожей форме цикла было бы изменением поведения.
- Catalog и quota не получают общего cache/DTO/deadline wrapper: TTL, endpoint,
  parsing diagnostics, validation и publication должны остаться видимыми.
- OpenAI и Anthropic serializers, usage counters, stop-reason mapping,
  cache-control и legacy System-message rules не нормализуются насильно.

## Масштаб и фактическая проверка

Три production файла: 490 → 488 строк, **net −2 LOC**. Один shared helper стоит
29 строк; catalog снимает 16, quota 15. Ценность здесь в одном владельце
bounded auth transition, не в обещании большого сокращения или ускорения.
С одним новым тестом общий diff составляет +153/−74 строки; существенная часть
diff — снятие вложенности существующего endpoint decoding.

Проверены strict whitespace apply-check, применение с `--fuzz=0` без offset,
точное совпадение результата с after/, reverse и точное восстановление before/.
Python выполнял только hash/diff/file bookkeeping, не модель Rust behavior.
Результаты в `CHECKS.json`. Ни один Rust test не считается прошедшим.

## Regression coverage и оставшийся gate

Сохранены без изменения существующие tests для:

- cache coalescing, cache hit, TTL expiry и отсутствия stale fallback обоих endpoints;
- catalog lock-wait deadline, waiter cancellation и leader cache acceptance;
- успешного HTTP401 refresh и rotated authorization headers;
- catalog query/version, projection/validation, quota buckets/validation;
- неподдерживаемости metadata у API-key adapter.

Добавлен **один Rust test method, шесть сценариев**: оба публичных endpoint
метода × второй 401 / 429 / 500. Он проверяет неизменные exact status diagnostics,
число запросов, catalog query, rotated headers, отсутствие cache publication.
Два joined fixture futures ограничены общим timeout; лишний request не может
получить ожидаемую terminal HTTP-ошибку после закрытия listener. Это proposed
loopback fixture, **не executed network-isolation доказательство**: `.no_proxy()`
устанавливается только для metadata client; OAuth имеет отдельный HTTP client.
Штатный test runner задаёт localhost NO_PROXY и должен использоваться.

Перед интеграцией в полном checkout нужны `cargo fmt --all -- --check` и
`python3 scripts/test.py -p model-pack --lib` с настоящим закреплённым Core.
Это проверит в том числе компиляцию generic async helper/Send requirements.
Отдельные transport-failure redaction, refresh failure/cancellation и второй
401 controls стоит сохранить в scope gate; новый тест не объявляется полной
матрицей ошибок. Live-account проверки для самого refactor не требуются.

Ничего не опубликовано. Upstream, delivery Git refs, workflows, установленные
приложения, credentials и dependency pins не изменены. Snapshot directories,
raw connector evidence и локальные check copies не являются delivery artifacts.
