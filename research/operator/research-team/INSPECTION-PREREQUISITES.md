# Как проверять установленную конфигурацию, не подменяя scope

Дополнение к R41, без изменения исходного recipe receipt `797dc336…`. Используется уже отдельно source-reviewed [checklist эффективной конфигурации](../EVIDENCE.md#e12), а не повторный аудит или запуск CLI.

- `modules list` и `inspect plan --format json` в выбранных Core1fc ветках читают config/includes/instructions и строят каталог/план без module connect или намеренной записи. Это не filesystem sandbox и не permission читать произвольные include.
- `tools list`, `inspect topology`, `doctor` **не считать статической проверкой**: они могут инициализировать configured module/MCP processes; resolver может создавать plugin data directories; doctor для literal `rg` выполняет `rg --version`. Ни одна из этих команд в рецепте не запускалась.
- `inspect plan` — диагностическая проекция, **не полный импортируемый resolved-config export**. Не выдумывать `config export`: в pinned dispatcher неизвестное верхнеуровневое слово может стать task input. `/config/local` также не lossless export и предполагает уже выбранную активную session.
- Поэтому prerequisite R41 остаётся: отдельно сверить операторские входы и итоговую реально установленную surface/policy с явно разрешёнными operational checks. PASS нашего Python scaffold checker не разрешает запуск discovery и не подтверждает каталог.

Источник-документ: `CHECKLIST.md` SHA-256 `cffc91d034d8e414d0e75258995bbe14d080f1ffb4ad4a47c1a0459e11919a60`; source snapshot `d87baf51273b18e22f0d9bc16a6f7d6631bd1a7d4e32d394ef9791bd0652f891`; независимый source review `638204f1b589a1e8147680dd08d00c3d49ce06b674073dbe1876e844e21a6cd1`. Это перенос границ уже принятого source-study, не новая runtime валидация или авторизация.
