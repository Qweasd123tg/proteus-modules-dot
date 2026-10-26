# Агентные экосистемы: четыре source-grounded раунда

Этот инкремент расширяет исследование за пределы coding loops: browser/computer agency, orchestration, memory, durable tool execution и recovery. Это **статическое исследование закреплённых исходников**, не запуск upstream-приложений и не измерение скорости.

| Раунд | Основные системы | Наблюдения | Полученные source-файлы | Отчёт / ledger / coverage |
|---|---|---:|---:|---|
| 1 | BrowserUse, Google ADK | 17 | 35 | [Отчёт](round1/REPORT.md) · [ledger](round1/public-ledger.json) · [coverage](round1/coverage.json) |
| 2 | Letta V1/current MemFS, Strands | 19 | 46 | [Отчёт](round2/REPORT.md) · [ledger](round2/public-ledger.json) · [coverage](round2/coverage.json) |
| 3 | OpenHands software-agent-sdk | 16 | 31 | [Отчёт](round3/REPORT.md) · [ledger](round3/public-ledger.json) · [coverage](round3/coverage.json) |
| 4 | Pydantic AI / harness / Temporal adapter | 14 | 22 | [Отчёт](round4/REPORT.md) · [ledger](round4/public-ledger.json) · [coverage](round4/coverage.json) |

**66 записей в четырёх раундах — не глобальный deduplicated count.** Ранее опубликованный каталог из 90 наблюдений остаётся историческим baseline и здесь не переписывается. Сумма полученных файлов — 134, 3 531 400 байт; получение файла не равно прочтению каждой строки. Точные full/partial/index-only ranges, исключения и pins сохранены отдельно в каждом coverage/source manifest.

## Что практически полезно

- Progressive disclosure и attachment membership не должны становиться источником полномочий.
- Tool call, внешний effect, normalized result и checkpoint — разные факты; conversation history не заменяет effect ledger.
- Recovery inspection не означает разрешения replay; cancel не доказывает физическую остановку или отсутствие effect.
- Изолированный verifier читает разрешённый artifact и проверяет exact bytes, но не истинность цитаты, происхождение файла или право изменять память. [Конкретный research-сценарий](round3/EVIDENCE-SPANS-RESEARCH-USECASE.md).
- Перед новым модулем сопоставлены существующие Core/contracts/Modules. Новые authority, admission, persistence или CAS semantics не предполагаются по умолчанию.

## Границы evidence

Каждый раунд фиксирует собственные source pins и состояние на момент исследования. Исторические фразы «не реализовано / не запускалось» относятся к соответствующему раунду, а не к последующим module CI increments. Runtime status модуля требует отдельного exact-head CI receipt; этот пакет его не заменяет.

`source-manifest.json` и `hash-verification.txt` описывают проверку закреплённых текстов источников. `validation.json` — историческая проверка согласованности исходного исследовательского пакета, а не runtime validation и не свежая проверка изменённого upstream HEAD. Git blob/hash — идентичность байтов, не доказательство поведения или безопасности. Полные source snapshots, внутренние рабочие заметки, гипотезы о безопасности, пользовательские сообщения и credentials не включены.

[PUBLICATION.json](PUBLICATION.json) — явный allowlist: исходный и подготовленный SHA256 каждого включённого документа, адаптации публичных путей и scope. Ссылки на upstream закреплены на commit. Сам manifest исключён из собственной хеш-таблицы; его digest передаётся отдельно при приёмке.
