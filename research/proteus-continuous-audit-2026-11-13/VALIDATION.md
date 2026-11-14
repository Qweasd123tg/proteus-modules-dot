# Проверка публикации

Проверка от 13 ноября 2026 относится к **поставке evidence**, не к повторному запуску продукта.

## Выполнено

- Удалённые `main` Core, Modules, Desktop и Desktop Extensions прочитаны заново. Полные SHA в `SOURCES.json`; они совпали с поздними отчётами.
- Delivery base соответствует merge PR #84; новых наборов от 12–13 ноября в нём не было.
- Выбраны 95 завершённых наборов. Незавершённые исследования не включены. Повторные архивы и PDF/DOCX предыдущего аудита не добавлялись.
- 3973 исходных evidence-файла сверены по SHA-256, исходному размеру и UTF-8. 1386 JSON/JSONL файлов объединены в 33 deterministic tar/gzip; всего 2620 хранимых файлов evidence. Original bytes: 108116131; stored evidence bytes: 17214438.
- `restore_evidence.py --verify-only` проверил все оригинальные и упакованные checksum. Отдельные materialization 68 файлов `reconnect-state` и 179 файлов `workflow-continuation` совпали с исходными SHA-256; overwrite existing output, неизвестная группа и unsafe relative paths отвергнуты.
- Все локальные ссылки в новом главном индексе, RELATED, REPRODUCING и license notes проверены на существование. Проверено наличие 95 entry reports. Доступность каждой внешней line-link отдельно не проверялась.
- Scan известных форматов ключей, Bearer/credential literals, NUL и бинарных сигнатур не нашёл настоящих credentials. Credential-подобные значения оказались явными synthetic fixture literals; ложные `sk-` совпадения были частью `task-*` имён. Это целевой scan, не гарантия отсутствия любой возможной формы секрета.
- Нет executable-бинарников, Cargo targets, git directories или symlinks. 43 исключения явно перечислены в MANIFEST: производные SQLite/icon caches и исходный AGENTS.md. Source license notices сохранены.
- Новые wrapper/docs/helper проверены отдельно. Whitespace и намеренно malformed fixtures внутри исторических evidence не «исправлялись», чтобы не менять результаты.

## Не выполнялось при публикации

- Повторные 95 наборов probes, большие Cargo/GUI/portable builds и live-model вызовы.
- Перепроверка частоты гонок в реальной UI нагрузке или доказательство совместимости четырёх компонентов в одной поставке.
- Установка candidate fixes в upstream или заявление о закрытии findings.

Результаты исходных запусков остаются в каждом REPORT и соседних logs, вместе с ожидаемо красными regression и положительными controls. Merge этой поставки означает доступность документов в delivery-репозитории, а не исправление Proteus.
