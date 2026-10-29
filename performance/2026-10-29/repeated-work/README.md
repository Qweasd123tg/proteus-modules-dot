# Меньше повторной работы в runtime

Пять независимых исходниковых patches: три изменения runtime и два изменения правил разработки. Они предназначены для отдельных checkout Core/Modules; этот каталог не применяет их автоматически.

## Базы и состав

**Core:** [60f667d53dd2b1e6f2e271f2e1af1e94cc63f316](https://github.com/Proteus-harness/Proteus-core/commit/60f667d53dd2b1e6f2e271f2e1af1e94cc63f316).

- [01-compiled-schema-reuse.patch](core/01-compiled-schema-reuse.patch): один текущий скомпилированный JSON Schema validator на зарегистрированную tool identity; reuse при clone/повторном выборе registry. Динамический `Tool::spec()` не заморожен. Смена схемы компилирует новую, ошибка не подменяется старым validator. Сравнение учитывает вложенный порядок объектов и представление чисел, чтобы не менять first-error diagnostics. Аргументы, raw JSON, hooks, policy и approvals проверяются как прежде.
- [02-development-rules.patch](core/02-development-rules.patch): короткие правила в `AGENTS.md` и существующем `docs/development/testing.md`.

**Modules:** [ecbf04a68079d9f493c141d63d09ff4014c7823e](https://github.com/Proteus-harness/Proteus-modules/commit/ecbf04a68079d9f493c141d63d09ff4014c7823e).

- [01-request-lifetime.patch](modules/01-request-lifetime.patch): OpenAI освобождает исходный запрос после построения provider body, **до сетевого ожидания**, если fallback выключен. Включённый fallback сохранён; Anthropic fallback не меняется.
- [02-owned-json-arrays.patch](modules/02-owned-json-arrays.patch): готовые массивы истории/контента перемещаются в JSON OpenAI/Anthropic вместо повторного преобразования через `json!`. Существующие позиции ключей и порядок элементов сохраняются.
- [03-development-rules.patch](modules/03-development-rules.patch): те же принципы в `AGENTS.md` и `docs/reference.md`, без отдельного большого отчёта.

## Что закреплено в правилах

Move/borrow вместо необоснованной глубокой копии; подготовка неизменяемых схем на нужное время жизни; отсутствие JSON-string кругов внутри процесса; обновление производных данных по изменившейся части; ограниченные caches с точной invalidation; admission/coalescing до дорогой подготовки.

Это не запрет `clone`, JSON или snapshots. Копии для независимого состояния, rollback и replay остаются допустимыми. Cancellation intent не освобождает reservation ещё живой работы. Существующие contract-owned grants/remembered approvals не запрещаются: их scope и lifetime проверяет владелец authority, а не случайный derived cache.

## Владение и компромиссы

Schema cache не глобален и не хранит историю вариантов. Он сохраняет одну schema и один validator на identity; in-flight проверки могут временно удерживать старый `Arc`. Hit всё ещё требует O(schema) сравнения, numeric leaves форматируются отдельно. Mutex локален одному tool и не удерживается на проверке аргументов, hooks или await. Часто меняющиеся схемы могут перекомпилироваться. Это не фиксированный общий RAM budget и не cache разрешений. Standalone validation APIs остаются uncached.

## IPC отдельно

Encode-once IPC-кандидат **не включён**: при incremental byte reservation два конкурентных encoder могут оба получить отказ, хотя прежнее atomic full-frame admission пропускало один. Лимиты не превышались, но это новое поведение под нагрузкой. Устранение повторной сериализации не должно ухудшать progress/backpressure. Для этого направления нужен отдельный вариант, сохраняющий admission semantics; текущий эксперимент не следует переносить как готовую оптимизацию.

## Применение и проверка

Применяйте patches из `core/` только к Core, из `modules/` только к Modules на указанных базах. Сначала `git apply --check /absolute/path/to/PATCH`, затем `git apply /absolute/path/to/PATCH`. Файлы внутри каждого набора не конфликтуют; совместное последовательное применение проверено на точных исходниковых подмножествах. Не применять вслепую к другому HEAD.

Выполнены сверка исходных Git blob identities, независимое чтение кода, whitespace и проверки применения отдельно/вместе. Добавлены regression test sources для schema reuse/динамических схем/ошибок/порядка и provider JSON; **компиляция, tests, benchmarks и CI не запускались**. `rustfmt` недоступен; format gate не заявлен. Сценарии проверки выбираются по существующей матрице каждого проекта; новый обязательный harness не добавляется.

Убрана конкретная повторная работа, но величина изменения latency/RSS не измерена. Runtime tests выполняются владельцем перед переносом. Сырой состав и pins — [SOURCES.json](SOURCES.json), контрольные суммы patches — [SHA256SUMS](SHA256SUMS). Никаких изменений upstream, main, workflows или автоматического включения модулей этот пакет не выполняет.
