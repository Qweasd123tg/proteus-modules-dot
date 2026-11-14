# Proteus Modules: функциональный аудит, проход 4

Дата: 2026-11-13. Репозиторий: `Proteus-harness/Proteus-modules`.
Проверенный `main`: `3270dc0f894eaf4d0360306052b806099b8f5351`.
SHA подтвержден `git ls-remote origin refs/heads/main` в начале и конце прохода. Изменений main относительно предыдущего прохода нет. Core pin: `b5fac84245b075896c24763b3aebac79b4375c2e`.

## Новый подтвержденный дефект

### MOD-R4-01: persistent LSP анализирует зависимые файлы по устаревшему открытому буферу

**Приоритет P2.** Источник: `tool/rust-lsp/src/client.rs:132-158,169-173`.

Сценарий обычного coding workflow:
1. Запросить `lsp_diagnostics(dep.rs)`. Клиент посылает `didOpen` и оставляет документ открытым.
2. Изменить `dep.rs` через edit_file/apply_patch, например поменять тип экспортируемой константы с u32 на &str.
3. Запросить `lsp_diagnostics(lib.rs)`, который использует эту константу как u32.

На третьем шаге синхронизируется только `lib.rs`. Старый `dep.rs` не получает ни `didChange`, ни `didClose`. У persistent сервера остается предыдущий открытый буфер, хотя на диске файл уже изменен. Это дает пропущенные или ложные межфайловые ошибки. Исправление не сводится к file watcher: по [контракту LSP didOpen](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didOpen.md) открытым содержимым управляет клиент, сервер не должен перечитывать его из URI.

**Воспроизведение:** тестовый LSP сервер с корректным поведением открытых overlays, изолированные временные `.rs`-файлы. Тест добавлен только в изолированную копию `tool/rust-lsp/tests/protocol.rs`; production-код не менялся.

```
AUDIT persistent=No Rust diagnostics for lib.rs.
AUDIT fresh=Rust diagnostics for lib.rs (1):
error[E0308] lib.rs:1:41-1:51: expected u32, found &str
AUDIT after refreshing dep.rs=Rust diagnostics for lib.rs (1):
error[E0308] lib.rs:1:41-1:51: expected u32, found &str
```

Два контроля: новый сервер видит текущий файл на диске; повторный запрос диагностики dep.rs синхронизирует persistent сервер и возвращает правильный результат для lib.rs. Новая регрессия падает ожидаемо; три исходных protocol-теста проходят. Дополнительно повторено 3 раза, все три воспроизведения одинаковы.

**Ограничение доказательства:** это протокольный mock, не реальный rust-analyzer. В окружении есть rustup shim, но rust-analyzer component отсутствует (`Unknown binary 'rust-analyzer'`). Классификация основана на воспроизведенном протоколе и обязанности клиента синхронизировать открытые файлы; не заявляется live RA end-to-end прогон.

**Направление исправления:** либо перед каждым анализом синхронизировать все ранее открытые файлы с диском, включая удаления, либо закрывать ненужные открытые документы сбалансированными `didClose` и перестать хранить stale overlays. Не публиковать исправление без теста на минимум два файла и оба направления изменения (новая ошибка / устраненная ошибка). Реальный RA прогон полезен как дополнительная интеграционная проверка.

Артефакты:
- `lsp-overlay-regression.patch`: только регрессионный тест и изолированный mock.
- `lsp-overlay-regression.log`: cargo-проверка, exit=1 ожидаем из-за нового падающего теста.
- `lsp-overlay-repeat-{1,2,3}.log`: воспроизводимость.

## Штатные проверки

Команда:

```
source /workspace/shared/proteus-toolchain/env.sh
CARGO_TARGET_DIR=/workspace/shared/proteus-review-20261112/modules/target \
CARGO_NET_OFFLINE=true python3 scripts/test.py \
-p code-mode -p plan-tool -p skill-pack -p tool-selection-hook -p rust-lsp -p rg-search --lib
```

Результат: **65 passed, 1 ignored, 0 failed**.
- code-mode: 16 passed
- plan-tool: 6 passed
- rg-search: 11 passed, 1 ignored
- rust-lsp: 5 passed
- skill-pack: 9 passed
- tool-selection-hook: 18 passed

Первый прямой cargo запуск без обязательного runner не имел `PROTEUS_TEST_HARNESS_ROOT`; Python-parity тест rg-search по этой причине упал. Это ошибка тестовой команды, не дефект продукта. Повтор через `scripts/test.py` корректно передал pinned harness root и прошел. Оба лога сохранены (`baseline.log`, `baseline-runner.log`).

## Проверенный новый охват и отрицательные результаты

Построчно рассмотрены CodeMode (engine/bridge/bootstrap/config и тесты), plan-tool, skill discovery, tool-selection implementation и schema-token-count tests, rg-search, rust-lsp. Точные пути, диапазоны и SHA256 оригиналов: `coverage.tsv` / `coverage.json`. В этом проходе **29 файлов, 5634 строки** включая документацию и тесты; это не весь репозиторий.

Новых подтвержденных дефектов вне MOD-R4-01 не получено. В частности:
- PlanTool принимает несколько in_progress намеренно; это зафиксировано upstream-compatibility тестом, не объявляется багом.
- CodeMode завершает запущенные host callbacks после script timeout намеренно, README это описывает; не повторяется как timeout-дефект.
- Кандидат rg max_results→SIGPIPE исключен: после раннего закрытия stdout обычный rg завершался кодом 0 в 5/5 локальных попыток.
- Тихий 100ms интервал LSP может возвращать промежуточную диагностику, но пока не классифицирован как отдельный дефект: нет реального RA подтверждения и scope формулируется как publishDiagnostics snapshot.

Не считаются прочитанными `tool-selection-hook/src/tests.rs` и три workflow-файла, вывод которых был усечен. Предыдущие file/PTY/UTF8/adapter findings не дублировались. Производственные исходники, remote refs и PR не изменялись.
