# Один владелец проверенного значения

Три небольших, связанных изменения в одном пакете вместо отдельных PR.
**Это source proposals для Modules, не применение к upstream или установленному
приложению.** Здесь публикуются только patches и проверенные результаты.

## Что убрано и что сохранено

### 1. OpenAI verbosity выбирается один раз

Единственный конструктор `OpenAiModelProfile` уже проверяет capability,
explicit verbosity и default verbosity. После успешного создания capability=false
означает оба значения None; иначе explicit имеет приоритет над default.
Внутренний профиль теперь хранит одно private значение вместо флага и двух Option.
Getter только заимствует результат, не повторяет выбор на каждом request.

Обе настройки по-прежнему валидируются eagerly, даже неиспользуемый invalid default.
Порядок и тексты ошибок, внешние config fields и request JSON не меняются.
Других constructors/readers/mutators удаляемых полей на точной базе нет.
Production −10 строк; новых test methods нет.
[Patch](openai-verbosity-owner.patch).

### 2. Plan-tool передаёт args, а не копирует их дважды

Pure `invoke_impl` владеет call Value. После копирования call_id остальные
потребители используют только args. `get_mut("args").map(Value::take)` передаёт
их private `validate_plan(Value)` и прежнему `serde_json::from_value`.
Два последовательных deep clone удалены; оставленный в call Null не читается.

`deny_unknown_fields`, статусы, default explanation и все проверки входа сохранены.
Failed tool result не превращается в invoke error или наоборот. Missing/null args,
nonobject call, malformed JSON, call_id и полный результат проверены существующими
сценариями. ToolModule/context/host/registry и status_counts не меняются.
Production +5/−5 строк; новых test methods нет.
[Patch](plan-args-owner.patch).

### 3. Одна проверка группы на каждую immutable fixture

В одном existing schema-test два borrow `capability_fields` вынесены из циклов.
Две schema instances неизменны; все 12 default comparisons сохранены.
Группа по-прежнему проверяется до первого comparison каждой fixture.
Повторные group lookup/advanced/Object checks сокращены с 12 до 2 по структуре
исходника. Это source count, не измерение времени. Production и metadata не меняются.
Test diff +4/−8; методов не добавлено и не удалено.
[Patch](schema-capability-test-hoist.patch).

Общий diff трёх файлов: +103/−57, включая расширенные assertions в существующих
сценариях. Это не массовое удаление тестов, новый runner, cache или schema framework.
Замеренного ускорения/снижения RSS нет.

## Реальные проверки

| Участок | Baseline | Candidate | Независимый повтор |
| --- | --- | --- | --- |
| OpenAI profile/request | 5 PASS | 5 PASS | 5 PASS |
| Plan-tool pure JSON | 6 PASS | 6 PASS | 6 PASS |
| Один schema-test | 1 PASS | 1 PASS | 1 PASS |

Для первых двух сначала расширены существующие behavior scenarios и выполнены
на неизменённом production. Все проверки используют прежние **12 уникальных
methods**, новых методов нет; повторные исполнения не являются новым покрытием.
У каждого кандидата отдельный independent source review: ACCEPT.

На общей candidate tree повторены те же 12 точных методов: **12 PASS, 0 FAIL**.
Каждый model-pack вызов: 1 passed / 182 filtered; plan-tool: 1 passed / 5 filtered.
Rust/Cargo 1.95.0, фактический Core dependency, locked/offline. Команда для каждого
имени из [manifest](COMPOSITION.json):

```sh
CARGO_NET_OFFLINE=true python3 scripts/test.py -p PACKAGE --lib TEST --offline -- --exact
```

`PACKAGE=model-pack` для первых шести имён, `plan-tool` для остальных шести.
Targeted rustfmt трёх файлов и diff-check PASS. Три patches применены во всех
шести порядках: одинаковые candidate bytes; reverse точно восстанавливает базу.
Это scoped qualification, не полный package/workspace gate.

## Базы и границы

- Modules: `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`.
- Неизменённый фактический Core pin: `185225a7103088c444788374ca425d230060f55a`.
- Dot при дедупликации: `23d42e2bdc463bb072a7eff22b41357c46f15e7a`, после #182.
- Source/patch hashes и имена исполненных tests: [COMPOSITION.json](COMPOSITION.json).

Public API, contracts, manifests, Cargo.lock и pins не меняются. Transport/HTTP/auth/process paths не затрагиваются.
Старые proposals не скопированы заново. Это не квалификация общей цепочки прошлых
patches; в частности #181 по-прежнему требует rebase к formatted #175/b2c285f,
и эта композиция пока не qualified.

**NOT RUN для этого пакета:** full gates, HTTP/auth/provider/process/security
fixtures, portable/GUI/install, hosted CI и benchmarks. Compaction/context-preparation
целиком исключён и остаётся STOP/HOLD; никакие его artifacts сюда не включены.
Другие HOLD не снимаются. Компиляция lib target не означает исполнение исключённых
fixtures. Raw logs и одноразовые qualification helpers не публикуются.
