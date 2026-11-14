# Здоровый single-instance MCP теряется после несвязанного Save или ReloadTools

2026-11-13. Новая подтверждённая **P2-находка** в lifecycle/config publication. Production-исходники не менялись, публикаций не было.

## Результат

В одной HTTP bootstrap-сессии здоровый MCP работает и исполняет `fixture__echo`. Затем любое из трёх действий:

1. `POST /addons` меняет только `addons.disabled_skills`, не MCP;
2. `POST /addons` отправляет **идентичные** настройки;
3. `POST /request` с `type=reload_tools`;

возвращает HTTP 200, но следующий runtime уже не содержит этот tool. Вызов через настоящий workflow → `host.tools.execute_batch` даёт `unknown tool: fixture__echo`.

Условие: MCP владеет эксклюзивным локальным ресурсом, поэтому не допускает двух одновременных процессов с одной конфигурацией. Fixture использует обычный неблокирующий `flock` на собственном временном файле внутри evidence. Это имитирует допустимый single-instance backend с lock-файлом; ни порты, ни чужие данные, ни внешние сервисы не затронуты.

Старый MCP ещё держит lock, когда Core запускает кандидата. Кандидат получает `exclusive resource busy` и завершает handshake. Core трактует это как изолированную discovery-ошибку и **публикует epoch без старого работающего tool**. Только после замены освобождается старый процесс и его lock. Через 1,2 секунды lock уже свободен, но tool по-прежнему отсутствует. Второй одинаковый Save восстанавливает его без изменений конфигурации.

`GET /addons` честно содержит server-local error. Это не утверждение о полностью скрытой ошибке: проблема в потере исправного tool и успешном завершении Save/Reload, а не в отсутствии всей диагностики. `reload_error` остаётся `null`.

## Проверенная матрица

Три независимых финальных прогона, по четыре случая, **12 случаев**. В каждом реальный Core executable, HTTP endpoints, синтетический workflow/v20, штатный policy fixture, MCP stdio и инструмент через обычный host path. Модель не используется.

| Случай | До операции | После операции | Ресурс после операции | Повторный Save |
|---|---|---|---|---|
| exclusive + изменение только disabled_skills | tool работает | HTTP 200, tool отсутствует | lock свободен | tool восстановлен |
| exclusive + no-op Save | tool работает | HTTP 200, tool отсутствует | lock свободен | tool восстановлен |
| exclusive + ReloadTools | tool работает | HTTP 200/ok, tool отсутствует | lock свободен | tool восстановлен |
| non-exclusive + изменение disabled_skills | tool работает | HTTP 200, tool работает | нет конфликта | tool работает |

В assertions проверяется равенство MCP-конфигурации до/после, реальная успешность вызовов, конфликт кандидата в process log, освобождение lock и восстановление при повторе. `repro.py` является диагностическим тестом текущего дефекта, а не зелёным regression gate. `expected_invariant.py` проверяет желаемый инвариант и на HEAD даёт **3 FAIL + 1 PASS**.

## Причинная связь в коде

Core HEAD `89997df995df7c39b713e16aba216ecb19c8f497`, подтверждён через `git ls-remote origin HEAD` в этом проходе.

- [config_builder.rs:220–235](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_builder.rs#L220-L235): Save готовит новую assembly **до** publication. Проверка равенства состояния применяется только к Config History, не предотвращает no-op rebuild.
- [module_catalog/tools.rs:70–83](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/module_catalog/tools.rs#L70-L83): новый tool surface снова запускает MCP discovery для всех включённых servers.
- [tools/mcp.rs:119–130](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/tools/mcp.rs#L119-L130): создаётся новый host; ошибка кандидата преобразуется в diagnostic state с пустыми tools, не в отказ от publication.
- [runtime/reload.rs:47–77](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/reload.rs#L47-L77): старый runtime существует во время candidate preparation и commit, затем заменяется подготовленным registry.
- [profile.rs:82–95](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile.rs#L82-L95): явный ReloadTools проходит ту же prepare-before-publish цепочку.
- [profile_watch.rs:126–142](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile_watch.rs#L126-L142): неизменённый/уже опубликованный profile не вызывает новый discovery. Само освобождение lock не порождает повторную попытку.

Документированная изоляция start/handshake failures полезна для **изначально** неисправных серверов; здесь конфигурация и здоровый ресурс не изменены, а отказ создаёт сама процедура замены.

## Направление исправления

Для несвязанных/no-op настроек сохранять существующую MCP generation, привязанную к полной effective launch/discovery identity, вместо безусловного второго запуска. Не смешивать это с произвольным переиспользованием при изменённой authority/config.

Для настоящего explicit reload нужно определить контролируемый handoff эксклюзивного ресурса или сохранять last-good surface при отказе кандидата. Простое раннее убийство всех старых процессов сломает in-flight snapshots и rollback; это не предлагается как готовый patch. Одно short-circuit для no-op устраняет лишь часть сценариев.

Production patch не делался: задача этого прохода была локально подтвердить новый cross-component дефект.

## Воспроизведение и ограничения

```bash
python3 repro.py --core /path/to/Proteus-core --binary /path/to/proteus
python3 expected_invariant.py run-.../results.json
```

Нужны Linux/POSIX flock, Python 3 и настоящий Core binary данного HEAD. Использован ранее собранный Core без новой сборки: SHA-256 `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`. Fixture workflow использует repo-owned `examples/modules/component_runtime.py`; allow-all policy берётся из test fixtures. Все profiles, sessions, журналы и lock-файлы изолированы в собственном `run-*` каталоге.

Первый exploration (`run-1.log`, `repro-multisession-exploration.py`) дополнительно создавал вторую session. Её watcher мог перехватить освобождённый lock и влиять на retry; это **не использовано** для основной матрицы. Финальные `run-3.log`–`run-5.log` адресуют только исходную `/bootstrap` session, не создают новых сессий. `run-2.log` был предварительной проверкой той же single-session цепочки без ReloadTools-case.

Не проверялись native Desktop, реальные MCP продукты, live provider, Windows, полный workspace gate, in-flight tool во время Save. Перенос на lock-owning реальный MCP является выводом из воспроизведённого общего lifecycle, не отдельным натурным тестом конкретного продукта. Данных fixture не теряли, утверждений о потере пользовательских данных нет.
