# Offline smoke трёх examples через настоящий Proteus Core

Эта самостоятельная проверка дополняет wire/pure-policy tests: она линкует
**неизменённый Core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`** и запускает
настоящие executables `pi-ready-steps`, `hermes-verify-evidence` и
`letta-evidence-blocks` через его process adapters. Rust 1.95.0; зависимости
зафиксированы `Cargo.lock`.

## Что проверяется

21 явная проверка перечислена в `scenarios.json`:

- Все три исходных TOML проходят `AppConfig::load`, `ModuleCatalog` и
  **статический** `AssemblyPlan`. На этом шаге reference executable не запускается.
- Pi: discovery не включает tool; отсутствие policy оставляет `deny_all`;
  положительный вызов идёт через **`BoundTools → process policy → process tool`**;
  проверены schema rejection, pre-cancel и независимый следующий execution.
- Hermes: настоящий `RuntimeRegistry::execution_context().hooks` вызывает hook
  process и проверяет missing/stale receipt, continuation, exhaustion и binding
  execution attribution. **История и receipt синтетические; verifier здесь нет.**
- Letta: настоящий Core вызывает context process, принимает его
  `host.context.provide`, маршрутизирует в настоящий provider process и возвращает
  canonical chunks. Проверены выбор/tombstone, empty/oversized query, следующий
  успешный вызов после ошибки и отсутствие fallback при missing provider.
- Изменение одного config поля `max_results=0` приводит к отказу инициализации
  после успешного контроля с тем же executable. **Core скрывает внутренний текст
  ошибки за `child stdout closed`; host-проверка не доказывает точную причину.**
  Отдельный direct-factory adversarial test проверяет именно max_results diagnostic.
- Временные workspace и HOME остаются пустыми.

`smoke.read_only` и `smoke.provider_relay` — **авторские test-only exports** внутри
того же executable, не новые production modules. Первый разрешает исключительно
`planning.ready_steps` с `ReadOnly`; второй только передаёт один явный запрос к
`letta.evidence_blocks` через разрешённый callback. Они не читают/пишут файлы,
не выполняют shell и не используют модель/сеть.

## Запуск

Соберите три examples из того же проверяемого checkout. Пример для структуры
репозитория, где этот пакет находится в `integration/core-smoke`:

```sh
export CARGO_TARGET_DIR="$PWD/target"
for name in pi-ready-steps hermes-verify-evidence letta-evidence-blocks; do
  cargo build --locked -j2 --manifest-path "examples/$name/Cargo.toml"
done
cargo build --locked -j2 --manifest-path integration/core-smoke/Cargo.toml
python3 integration/core-smoke/run_smoke.py \
  --binary "$CARGO_TARGET_DIR/debug/proteus-examples-host-smoke" \
  --example-bin-dir "$CARGO_TARGET_DIR/debug" \
  --examples-dir "$PWD/examples" \
  --output "$PWD/smoke-result-new"
```

После первого получения dependencies добавьте `--offline` к Cargo commands.
Не запускайте всё workspace/reference test suite ради этой проверки. Программа
не вызывает Cargo сама. `--output` обязан быть новым; сохранены stdout/stderr,
результат, длительность и SHA-256 всех входных source/binary файлов. Runner задаёт
пустой HOME, отдельный cwd, очищенное окружение и 60-секундный timeout с максимум 5 секунд на drain.
При timeout он завершает process group контроллера; Core создаёт собственные
groups для components, поэтому полный descendant cleanup не заявляется.
Результат timeout всегда failure, включая незавершённую очистку. До запуска
требуется ≥1 GiB свободного места; ничего не удаляется автоматически.

В этом batch использованы уже собранные examples с Rust source bytes/config/Cargo.lock, совпадающими
с опубликованным baseline; **rebuild original examples не выдаётся за новую
проверку их tests**. Точные пути/хэши находятся в evidence `inputs.json`.

## Pins и границы утверждений

| Источник | Pin / статус |
|---|---|
| Core и SDK для фактической сборки | `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` |
| Опубликованный baseline examples | PR1 head `29d31fb36397008b7677cd5df4943031e24e8fdf` |
| Modules snapshot, упомянутый старым Pi profile | `04114bbe85f179895e2b8553b6169a284caaeae3` |
| SDK pin в manifest этого Modules snapshot | `bee0e409e746e2df9db32748d4f8ea02201bd4af` |
| Modules pin в `repositories.json` Core `3f36a003` | `7fceaebc3bed8add9b0e3091110f59deca86ba46` |

Эти pins не смешаны в runtime-сборке: reference module **не был собран или
запущен**. Исходные full profiles проверены загрузкой/планом; фактические
invocations используют отдельную минимальную model-free assembly из
`src/scenarios.rs`. Отличающиеся Modules pins сами по себе не доказывают
несовместимость; compatibility полной reference assembly остаётся непроверенной.

Это не полный agent turn, не fake/live-model eval, не journal/replay/settlement
проверка, не in-flight cancellation/restart gate и не OS sandbox. Trusted process
launch сохраняет OS-права запускающего пользователя. Никаких новых прав модулю
или обходов registry/policy не добавлено. Latest Core отдельно не проверялся.
