# Операторское восстановление: не повторять неизвестный эффект

Source-only runbook для **Core 1fc3ef223d10322815dd9290a50d045bc95402bb**. Сначала отличить потерянный ACK, live activity, recorded settlement, tool outcome, replay и objective verification — затем принимать решение о повторе.

- [RUNBOOK.md](RUNBOOK.md): шесть развилок и компактная запись расследования.
- [READ-SURFACES.md](READ-SURFACES.md): реальные HTTP/CLI формы, cache/инициализация/исполнение; никаких выдуманных inspector commands.
- [SURFACES.json](SURFACES.json): 14 строк и точные source anchors.
- [COVERAGE.md](COVERAGE.md): 40 source objects / 52 selected ranges, слои и ограничения.
- [GATES.md](GATES.md): десять end-to-end проверок, **все не выполнены**.
- [SOURCE-MANIFEST.json](SOURCE-MANIFEST.json) и [evidence identities](../EVIDENCE.md): exact source и reused accepted-evidence bindings.
- [PROVENANCE.md](PROVENANCE.md): historical source-check identities и граница новой public-copy адаптации; не Core runtime.

Полезная граница: `/analysis` умеет читать cold journal без resume, но объединяет `ToolEffectRecorded` и `ToolResultRecorded` в одно поле. Existing strict library projection сохраняет записи раздельно; готовой CLI-инспекции этих фактов здесь не установлено. `GET /events` и session catalog тоже нельзя безоговорочно называть write-free: первый может инициировать event sink, второй обновлять disposable cache.

Ничего не запускалось на пользовательских данных, не отправлялось серверу и не публиковалось. Этот текст сам по себе не предоставляет доступ к сессии или authority на retry/cancel/resume/replay.
