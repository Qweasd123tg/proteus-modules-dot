# Один Responses Client На Constructor

## Результат

Source-only candidate для `Proteus-harness/Proteus-modules`
`200d1ec54f1217f61a31823db939df3799c638dc`:
`single-client.patch`, SHA-256
`4ac68a86d0171280443d37dcc2eec7c88c8fc928fc0a9fa2f3f96b8a39ba36ec`.
Это отдельная работа после уже перенесённых catalog/retry/capture исправлений;
PR62 не требуется повторно. Других patch prerequisites нет.

В `model/model-pack/src/adapters/openai/transport.rs:62–67` прежний Codex
constructor создаёт обычный API client через `from_provider_config`, затем
немедленно заменяет его новым client с запретом redirects. Первый pool никогда
не отправляет запрос. `module.rs:44–49` строит stream/complete adapters отдельно,
поэтому при Codex registration повторная работа происходит дважды.

Private helper принимает настроенный `reqwest::ClientBuilder` **до**
единственного Responses `Client::build`. Публичный API constructor передаёт
стандартный builder с `Policy::default()`, Codex — builder с `Policy::none()`.
`http1_only` применяется
в прежнем общем месте. Auth client остаётся отдельным; stream/complete pools,
TTL caches, runtime, secret/header ownership, auth refresh и retries не меняются.
Нет global cache, новых config keys или объединения разных bindings.

## Error / Policy Boundary

Codex-specific validation, base URL, auth constructor, quota URL и client version
проверяются в прежней последовательности. Общие model profile/retry/idle/http1
checks остаются в прежнем порядке перед Responses client build. Единственное
исчезнувшее fallible действие — построение немедленно выбрасываемого client;
TLS/resolver failure у остающегося client по-прежнему возвращается как ошибка,
не fallback. Создание infallible builder переносится перед общими checks;
его fallible `build()` остаётся после них. Не обещается идентичный результат при внешнем изменении system
TLS/proxy/resolver configuration между двумя прежними build calls.

Закреплённый reqwest 0.12.28: `ClientBuilder::redirect` только устанавливает
policy; `ClientBuilder::new` использует `Policy::default()`, равную limit 10;
`none()` возвращает исходный redirect response без follow. Политика не создаёт
новый fallible validation stage. Первичные источники и hashes — в SOURCES.json:
[client.rs](https://github.com/seanmonstar/reqwest/blob/d97859910c357827ad5993d37ce750ad595f4fff/src/async_impl/client.rs),
[redirect.rs](https://github.com/seanmonstar/reqwest/blob/d97859910c357827ad5993d37ce750ad595f4fff/src/redirect.rs).

## Regression Sources И Статические Проверки

Новый `transport_tests.rs` содержит:
- один bounded loopback сценарий на четыре combinations общего private helper:
  default/none redirect policy × `http1_only=false/true`; default следует
  302 → 200, none возвращает исходный 302. Request идёт напрямую через client,
  построенный общим helper с test-only `ClientBuilder::no_proxy()`, без OAuth
  access/provider endpoint. Весь exchange ограничен 10 s; server и request —
  owned futures внутри join, без detached tasks. Это не ALPN/HTTP2 negotiation test;
  применение `http1_only` подтверждается также неизменённой production веткой.
  Выбор default/none в двух actual constructor call sites проверен по исходникам,
  а не выдаётся за network coverage этих call sites;
- config regression: retry setting error остаётся раньше http1 setting error,
  Codex auth-file validation раньше общих settings. Missing temporary auth path
  не читается и не создаётся constructor-ом.

Эти sources охраняют поведение; число client builds установлено прямым source
comparison, а не тестом на текст/расположение исходников. Runtime выигрыш,
latency/RAM/build-time цифры и successful executable gates не заявлены.

Loopback fixture явно исключает ambient proxy через свой builder, не меняя
production system proxy behavior или shared environment других tests.
Это заменяет прежний недостаточный runner precondition из superseded patch
`f48480b3…`; старый вариант не следует публиковать. Проверены `CodexAuth::from_config`,
`OAuthClient::new` и `expand_user_path`: constructor только разбирает path/URL
и строит auth transport; credential file I/O находится в отдельном `access`.
Все новые error-path configs не задают `base_url_file`/`base_url_env`.

Проверены все три preimage Git blobs и отсутствие нового test file в fresh
полном дереве. Strict `git apply --check --whitespace=error-all`, reverse check,
реальный forward/reverse на отдельной копии с byte equality и прямой rustfmt
1.95.0 (`--check --edition 2024 --config skip_children=true`) прошли.
Tests/build/CI/product/provider/fixture requests не запускались. Перед переносом
остаются model-pack constructor/Codex auth/transport regression gates.

Actual Core dependency Modules остаётся
`1f533a13f20a93bf164f7c8a169553b0b219bb51`, не observed Core main
`befd30516aefa6f0a0ad5db9924ad4957160b8dc`. Cargo/pins/lock не меняются.
