# Совместимость новых source-пакетов — 30 октября 2026

**Все девять patches совместимы по строгому применению исходников на указанных
базах. Это не результат compilation, behavioral tests или upstream integration.**
Проверены 49 случаев применения с точным обратным восстановлением; конфликтов
не обнаружено. Исторические PR60–62 и mode08 в эту композицию не входят.

## Что и куда применять

Patches применяются к соответствующим upstream исходникам, **не** к этому
delivery-репозиторию. Точные SHA-256 и immutable ссылки каждого patch находятся
в [COMPOSITION.json](COMPOSITION.json).

| Исходники | Точная база | Независимые patches в удобном порядке |
|---|---|---|
| Core | `befd30516aefa6f0a0ad5db9924ad4957160b8dc` | `terminal` (PR63) → `worktree` (PR65) → `journal` (PR66) → `cli` (PR68) |
| Modules | `200d1ec54f1217f61a31823db939df3799c638dc` | `client` (PR65) → `capture` (PR66) |

Это удобный, а не обязательный порядок: перечисленные независимые изменения
не требуют друг друга. `worktree` — финальный patch `38eb7954…`, не старый
`90d9dc23…`; старую версию перед ним не применять.

**Отдельно, только при выборе coordinated API proposals PR67:** после Core
списка можно добавить `runtime` → `typed_core`, после Modules списка —
`typed_modules`. Проверен именно этот полный порядок и полностью обратный
порядок внутри каждого репозитория; конечные bytes совпадают. Ни `runtime`,
ни typed workflow не требуют принятия другого предложения.

Применять `typed_modules` к текущей зависимости Modules и объявлять рабочую
интеграцию нельзя: новый Rust helper требует согласованного Core API.
Сначала нужен настоящий проверенный Core commit с выбранными изменениями,
затем согласованные consumer pins и штатная регенерация lockfiles, затем
исполняемые gates. Публикация delivery PR не создаёт такой Core commit.

## Что именно установлено

- Все 57 существующих preimages совпали с Git blob identities зафиксированных
  upstream trees. Десять новых путей отсутствуют на этих базах. Всего затронуто
  67 уникальных путей; существующие локальные точные копии использованы повторно.
- `git apply --whitespace=error-all`: 9 самостоятельных случаев,
  36 упорядоченных пар и 4 полных порядка. После каждого успешного применения
  reverse с тем же whitespace gate восстановил точные baseline bytes.
- Каждая пара проверена в обоих порядках и даёт одинаковые bytes. У Core только
  два пересечения файлов: `cli` + `typed_core` в process-module architecture
  guide, `cli` + `runtime` в testing guide. Оба набора объяснений сохраняются:
  typed helper и feature-enabled CLI; полный runner и отдельный DTO-only gate.
- Изменённые production-файлы разных packets не пересекаются. В смежных callers
  terminal claim остаётся получением результата в process-agent wait, а
  worktree owner — владельцем подготовки/dispatch/finalization. Новый receipt
  не подменяет cancellation token и не доказывает прекращение внешних writers.
- Core и SDK явно включают `runtime`; typed process helper остаётся вне этой
  feature-границы. В Modules typed export/workflow callers не изменяют transport
  constructor одного client и capture writer. Проверка этих границ — чтение
  исходников, не доказательство корректности всего runtime.

## Незакрытая интеграционная граница

Modules всё ещё закрепляет пять Core dependencies на
`1f533a13f20a93bf164f7c8a169553b0b219bb51`; обновлять их нужно согласованно на
реальный Core commit. Desktop root и client-common используют contracts на
`925de0fc5ee5995409b11e42b216a15ca12f76d0`; DTO-only adoption требует согласованного
нового pin и `default-features = false` в обоих consumers. Pins/locks здесь
не менялись. Feature unification требует проверки реального dependency graph.

Не выполнены Core/Modules full gates, module_swap, conformance и real-worker
invocation, lifecycle/cancel/failure boundaries, focused regression targets,
CLI runner-selection/feature gates и DTO-only/client gates. Project code,
tests, scripts, Cargo, builds, CI и benchmarks не запускались. Нет заявлений
об измеренном ускорении, снижении RAM или готовности к merge. На новой upstream
ревизии нужны новые preimages и review, а не только чистое применение patch.
