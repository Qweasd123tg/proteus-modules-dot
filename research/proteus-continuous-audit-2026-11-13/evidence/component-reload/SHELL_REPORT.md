# После ReloadTools старый exec session_id начинает адресовать другой живой процесс

## Статус

Подтверждено 2/2 end-to-end прогонами с **двумя отдельными чистыми сборками**:
- Core `89997df995df7c39b713e16aba216ecb19c8f497`;
- Modules `3270dc0f894eaf4d0360306052b806099b8f5351` (его штатный Cargo.lock с Core dependency `b5fac842...`).
Обе source working tree чистые. Ничего не опубликовано, production не изменён.
Приоритет предлагаю P1: это успешная доставка stdin не тому процессу, а не просто отказ устаревшего handle.

## Реальный путь

Root `proteus server stdio` -> model-free workflow/v20 fixture -> обычный
`host.tools.execute_batch` -> policy -> настоящий поставляемый `proteus-shell-tool-module`.
Локальная test policy явно разрешает harmless marker commands; `tty=true`,
`with_escalated_permissions=true` в synthetic вызовах. Изменений системной sandbox/security конфигурации нет.
Никаких секретов, сетевых моделей или чужих процессов. Marker children имеют 12-секундный alarm,
закрываются после проверки; после shutdown их процессов не осталось.

1. `exec_command` запускает marker A. Возвращает `session_id=1001` и terminal UUID A.
2. Положительный контроль: `write_stdin(1001, "control-A\n")` пишет именно A, ответ содержит `A:control-A`.
3. `ReloadTools` при неизменном config: успешно epoch `0 -> 1`, tools те же.
4. До нового exec `write_stdin(1001, ...)` возвращает `unknown exec session 1001`.
5. `exec_command` запускает marker B. **Снова возвращает `session_id=1001`**, terminal UUID уже другой.
6. `write_stdin` с сохранённым ID A и текстом `intended-A\n` возвращает **успех**, output содержит `B:intended-A`.
7. Marker files: `A.received == "control-A\n"`, `B.received == "intended-A\n"`.
   Старый A в момент проверки всё ещё жив (`os.kill(A_pid, 0)` успешен).

Следовательно, одновременно существуют старый живой A и новый B, а model-facing numeric handle
перестаёт однозначно определять адресата. Успешная запись не сообщает, что адресат изменился.

## Причина

- Core `app_server/profile.rs:92-94` целиком пересобирает assembly при ReloadTools.
- Новый process-backed shell export имеет новый worker и пустой session map.
- Modules `tool/shell-tool/src/unified_exec/session.rs:302`: каждый процесс стартует
  `NEXT_SESSION_ID` с фиксированного `1001`.
- Там же `:343-346`: ID выдаётся через process-local `fetch_add`, generation не включена.
- `unified_exec.rs:201-212`: write_stdin принимает лишь i64 ID и делает lookup в текущем worker.
- `session.rs:238-247,269-278`: owner check проверяет root session/thread/workspace,
  которые здесь правильные и одинаковые; это не защита от stale generation в той же session.
- Core `process_adapters/tool/host.rs:29-54,120-143` отдельно удерживает старый export client в
  TerminalController и использует generation-pinned terminal API. Поэтому старый A жив,
  хотя model-facing write_stdin маршрутизируется через новый registry.

Это функциональная проблема межпоколенческой адресации, не доказательство обхода policy,
доступа к чужой пользовательской session или атакующего модуля.

## Последствия и исправление

После обычного обновления tools/profile модель может записать ввод в не тот shell job,
перепутать его output либо адресовать отмену не тому процессу. В тесте проверена именно
ошибочная доставка обычной строки; отправка команд с реальными последствиями не выполнялась.
Terminal GUI UUID path не объявляем сломанным: по коду он generation-pinned, отдельно GUI не запускался.

Нужен generation-safe model-facing handle (или гарантированно непереиспользуемый ID), чтобы старый
ID после смены module generation всегда либо продолжал адресовать прежнюю сессию, либо явно отклонялся.
Сохранение неизменного process-backed component при reload устранит текущий триггер, но само по себе
не закрывает alias после настоящего restart worker. Не следует лишь делать ошибку unknown_session мягче.
Regression: в одной conversation/workspace два поколения worker; старый handle не может управлять новым процессом.

## Артефакты и повтор

- `repro_shell_reload.py`, общий `workflow.py`.
- Чистые прогоны `clean-both-shell-1.log`, `clean-both-shell-2.log`.
- `shell-run-1794563211820275024/`, `shell-run-1794563213432156038/`:
  raw wire, result.json, неизменный parent config, marker source/PIDs/files, canonical journal.
- Предварительный прогон `clean-head-shell.log` использовал ранее собранный, чистый Modules package.
- Modules build log `/workspace/shared/trace-integration-round8-shell-build.log`.
- Команда сборки: `CARGO_TARGET_DIR=/workspace/shared/trace-integration-round8-module-target CARGO_PROFILE_DEV_DEBUG=0 cargo build --locked --offline -p proteus-shell-tool-module`.
- Modules binary SHA256 `810acf3e4f33ebfc7a530e9db16687173927f3ca770d3c641d5b82a985464dd0`.
- Запуск:
  `AUDIT_SHELL_MODULE=/workspace/shared/trace-integration-round8-module-target/debug/proteus-shell-tool-module python3 /workspace/shared/trace-integration-round8-evidence/repro_shell_reload.py`
- Core binary и его clean build описаны в соседнем REPORT.md.
- GUI, реальные LLM, root restart, автозапуск watcher, workflow replay не проверялись.
