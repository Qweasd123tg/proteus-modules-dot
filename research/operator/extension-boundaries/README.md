# Какую границу расширения выбрать — и чего она не обещает

**Обязательное дополнение:** [OBSERVED-GUARD-LIMITS.md](OBSERVED-GUARD-LIMITS.md) — narrow R57 runtime, accepted limitations, без повышения broad cells до ENFORCED. [Provenance](PROVENANCE.md).
**Операторская памятка, 2026-10-26.** Это синтез уже принятых источников, не новый framework audit, sandbox conformance или готовая конфигурация. Core baseline: `1fc3ef223d10322815dd9290a50d045bc95402bb`; runtime supplements имеют собственные pins и не подменяют current-Core acceptance. [Матрица 4 × 7](MATRIX.md) дополняет [adoption guide](../EVIDENCE.md#e05), а не повторяет roadmap.

## Сначала определить владельца, затем выбирать технологию

1. **Код доверенный, нужны host model/tools/approvals:** обычный локальный workflow/tool с существующими bound APIs. Прямой OS/network код расширения остаётся отдельной доверенной поверхностью; упаковка в tool не переносит его эффекты под Core автоматически.
2. **Нужно уменьшить OS-доступ процесса:** отдельно рассмотреть существующий Linux Restricted launch и точные grants. Это не замена API policy, numerical fidelity, resource accounting или task oracle. Unsupported platform не исправляют тихим downgrade в Trusted.
3. **Нужна только обработка выбранных байтов:** первый guest proposal — process `context_provider/v4` wrapper, без Proteus/effect callbacks и WASI; явные bounded ABI primitives для Extism. Пока это **design-only**, не поставленная sandbox-функция. Не давать guest файловый поиск «заодно».
4. **Нужен чужой автономный агент:** признать делегирование и выбрать endpoint/principal, egress scope, remote task identity, unknown-outcome и artifact policy. Remote-agent connector proposal не наследует Core authority/durability на удалённой стороне. Native ACP server — другое направление, не готовый outbound A2A connector.

Эти варианты **не взаимоисключающие слои**: guest wrapper может быть Restricted process, а connector может работать внутри локального workflow. При композиции нельзя просто сложить обещания: результат зависит от каждого фактического route/import/grant и владельца эффекта. Cwd, роль, hash pin и declaration `allowed-tools` не создают OS sandbox.

## Пять вопросов перед подключением

- Кто выполняет эффект: Core bound API, прямой код модуля, guest import или remote service?
- Какие точные данные пересекают границу — включая args, context, error, metadata и tracing?
- Где проверяются effective arguments **после** преобразования, и сохраняет ли выбранный язык нужные значения?
- Где фиксируются admission/settlement; что остаётся unknown при потере ACK/timeout?
- Какие реальные evidence относятся к этому binary/config/platform/producer→consumer, а какие только к исходникам или проекту?

Если ответа нет, соответствующая ячейка остаётся **unknown**. Не заменять её словом «sandbox».

## Конкретные анти-примеры завышенных обещаний

1. **«Инициализация — безопасный inspect».** SDK factory/JS setup уже исполняются при initialize; stdio MCP process запускается до tool discovery. [SDK §01](../EVIDENCE.md#e02), [adoption §4](../EVIDENCE.md#e05).
2. **«Restricted/network=false ⇒ никакого внешнего канала».** Inspected Linux policy ограничивает IP network; Unix sockets в granted paths остаются отдельной поверхностью. Host-mediated callbacks и разрешённый output тоже не становятся автоматически секретными. Это границы source-модели, не выполненный escape test. [W01](../EVIDENCE.md#e01), [portability](../EVIDENCE.md#e03).
3. **«JSON/schema/OS isolation ⇒ точные аргументы».** R45 реально наблюдал в pinned JS hook worker `9007199254740993 → 9007199254740992` и отрицательную пару. String control сохранился. Core/policy не запускались, обход approval не заявлен; известная схема/string policy должна существовать до JS ingestion. [Отдельный runtime result](../EVIDENCE.md#e06).
4. **«Cancel ACK/timeout ⇒ можно повторить эффект».** Ни local cancellation, ни A2A cancel attempt не являются rollback receipt; effect/final запись и UI presentation различаются. [R20](../EVIDENCE.md#e07), [R56 runbook](../recovery-runbook/RUNBOOK.md).
5. **«Fuel/page cap/queue cap ⇒ ограничены wall time и RSS».** Fuel не прерывает блокирующий host callback; guest memory не включает все host allocations; tracing queue8192 — items, не bytes/RSS. [W02–W03](../EVIDENCE.md#e01), [обязательное queue уточнение](../EVIDENCE.md#e11).
6. **«Успешный run/replay ⇒ задача доказана».** Matching Error — valid reproduction, не objective success; lifecycle success не требует нуля tool failures. [R36](../EVIDENCE.md#e10).
7. **«Redaction flag/нет сети у guest ⇒ privacy».** Выход guest может попасть в host context/log/export; truncation не sanitization, SDK sensitive-data flag не очищает arbitrary metadata/custom spans. Сетевая доставка запроса и telemetry — отдельные recipients. [R49](../EVIDENCE.md#e11).

Все примеры выше публично безопасные accepted findings либо ограниченные design inferences, не private vulnerability chains. Здесь **не выполнены** команды Core/SDK, тесты, настройки, sandbox/remote calls, builds или публикация. Проверены только связи локальных evidence artifacts и структура самой памятки. [Покрытие и происхождение](../EVIDENCE.md).
