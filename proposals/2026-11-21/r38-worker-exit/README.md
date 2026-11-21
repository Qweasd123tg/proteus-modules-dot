# Не выдавать ошибку наблюдения за подтверждённый выход процесса

База: [Proteus-core, 32e56ecb](https://github.com/Proteus-harness/Proteus-core/commit/32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f). SHA-256 `source.patch`: `6e44b396daa05becebfe704f23f3947512e88e960e0f102f263e147ac63ce9d9`.

При сбое чтения broker ждал до 50 мс, пока монитор получит статус выхода дочернего процесса. Ветвь ошибки самого монитора возвращала то же `ComponentLost(ProcessExit)`, что и полученный статус. Теперь только положительное наблюдение текущего поколения даёт `ProcessExit`. Ошибка наблюдения даёт `ComponentLost(Resource)`; диагностика сохраняет ошибку монитора и причину остановки reader в прежнем ограниченном поле. Таймер, обычные ветки невышедшего процесса, приоритет ожидающей отмены, wire и перезапуск брокера не менялись.

**Воспроизводимый случай на Linux:** изолированная копия тестового процесса запускается с явно игнорируемым SIGCHLD. После v3 handshake и команды на штатном Python fixture ядро убирает завершившийся дочерний процесс без статуса, доступного монитору. Сигналы остальных тестов не затрагиваются. На базе новое ожидание падает: терминал `ComponentLost(ProcessExit)`. После патча: `ComponentLost(Resource)` с диагностикой ошибки наблюдения, включая 20/20 дополнительных прогонов. Это тест доступности доказательства, а не утверждение, что дочерний процесс в этом тесте выжил.

**Проверено:** Rust 1.95.0, Linux. Из источников собраны contracts, process-host, module-protocol, все его тестовые targets и conformance CLI, с использованием уже собранных внешних Rust-зависимостей. 53 библиотечных теста, 22 broker integration, 1 startup deadline и 3 теста conformance CLI прошли (79, изолированный повтор внутри одного теста не прибавляется к сумме). Среди контролей: наблюдаемый выход, malformed frame, ограничения, cancel grace, отмена и restart. Conformance CLI через новый broker выполнил по одному строгому List с реальным Rust storage worker для JSONL и SQLite. Оба вернули успешный пустой каталог на отдельных синтетических корнях. Это вспомогательный бинарник Modules 9469e3b с ранее предложенным патчем ETag; SHA-256 `91d99f69c56d5207af0385ba5e21d88bfb124811102b3d8d72d581aaefdba4c2`. Полный workspace, module_swap, HTTP и Desktop не проверялись. Форматирование, чистое наложение патча и git diff --check прошли.

**Границы:** это самостоятельная корректировка классификации, не исправление задержки каталога. В частности, если неправильный кадр и реальный выход совпали, один статус выхода ничего не говорит о корректности данных. Успех reset, исчезновение HTTP-клиента и истечение таймера не подтверждают завершение конкретного List. Здесь нет новых критериев повтора, coalescing, кэша, изменений авторизации, Desktop или API.

Из чистой базы:

```sh
git apply /path/to/proposal/source.patch
cargo fmt --all --check && git diff --check
python3 scripts/test.py -p proteus-module-protocol --features conformance-cli
```

При наличии собранного storage worker дополнительный контроль:

```sh
cargo build --locked -p proteus-module-protocol --features conformance-cli --bin proteus-component-conformance
python3 /path/to/proposal/conformance.py target/debug/proteus-component-conformance /path/to/proteus-session-storage-module
```

`baseline-red.log` и `final-suite.log` содержат исходную ошибку и результаты кандидата; `conformance.log` содержит ответы List. Реальные данные пользователя не использовались.
