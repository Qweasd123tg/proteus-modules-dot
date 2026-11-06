# Proteus: каталог, состояние плагинов и терминалы

Срез исходников: **6 ноября 2026 года**. Это точечный статический аудит трёх закреплённых ревизий, а не полный аудит проекта. Отчёт описывает оставшиеся ограничения и следующие проверки; исправлений исходников в этом PR нет.

## Источники и статус проверки

| Репозиторий | Проверенная ревизия |
|---|---|
| Core | [6b918bb7293e258f32b69d4fb705ba76a2133a86](https://github.com/Proteus-harness/Proteus-core/commit/6b918bb7293e258f32b69d4fb705ba76a2133a86) |
| Desktop | [306be31b77e935e1bc2696f49deee9cdfa3fb2e9](https://github.com/Proteus-harness/Proteus-desktop/commit/306be31b77e935e1bc2696f49deee9cdfa3fb2e9) |
| Modules | [4e22f9e746a1c8756a7b1df8cd543e4fe352d5c3](https://github.com/Proteus-harness/Proteus-modules/commit/4e22f9e746a1c8756a7b1df8cd543e4fe352d5c3) |

**Исходники, сборки, upstream-тесты и приложение не запускались. Динамически воспроизведённых новых дефектов в этом проходе нет.** Проверены причинные цепочки в исходниках и документация. Все сценарии ниже являются предложениями регрессионных проверок, а не выполненными тестами. Совместная сборка этих трёх ревизий также не проверялась.

[SOURCES.json](SOURCES.json) содержит точные пути, Git blob SHA и границы цитируемых строк. Ссылки закреплены на commits; статус будущего upstream `main` из них не следует.

### Связь с предыдущими результатами

- [Ориентир 4 ноября](../proteus-direction-2026-11-04/README.md) сохраняет прежний статус проектных предложений. Ниже уточняются конкретные текущие пути, а не переписывается продуктовая спецификация.
- Смена `PLUGIN_DATA` развивает **EXT-10B** из [исторического каталога](https://github.com/Qweasd123tg/proteus-modules-dot/blob/587d96d4ca009082320f00c984d98f65de444fe2/research/catalog.json). Тогда рассматривался перенос корня пакета; теперь показано, что корень меняется при штатном обновлении версии из каталога. Это одна причинная проблема, не две независимые находки.
- [PR #82](https://github.com/Qweasd123tg/proteus-modules-dot/pull/82) доставил отдельный [installation patch](../../patches/proteus-desktop/2026-11-05-installation/README.md). В проверенном Desktop уже видны сохранение `enabled` при catalog update и проверка staged extension до публикации. Они не объявляются заново открытыми дефектами.
- Старые результаты тестов PR #82 относятся к его собственной базе и указанному там scope. Они не переносятся на новые ревизии или на перечисленные здесь сценарии.

## Краткая карта

| ID | Вывод по исходникам | Что ещё не установлено |
|---|---|---|
| CAT-SAVE | Успешный catalog save безусловно заменяет draft, включая правки, сделанные после отправки запроса | Воспроизведение в нативном UI и частота проявления |
| EXT-10B / update | Новая папка версии меняет вычисляемый `PLUGIN_DATA` | Реальная потеря файлов или состояние конкретного стороннего MCP |
| ZIP-IDENTITY | Повторный ZIP добавляет новый путь того же Agent Plugin в draft | Итоговый UX сохранения; одновременный запуск двух копий не заявляется |
| TERMINAL-NESTED | Вложенные tool/hook callbacks не передают terminal host по проверенному пути | Поведение всех workflow и нативного UI |
| TERMINAL-COST | Terminal record и запись вывода создаются независимо от поддержки публикации терминала | Величина накладных расходов и необходимость оптимизации |
| CATALOG-SCOPE | Backend process modules не входят в четыре типа текущего каталога | Это документированная граница, а не дефект распаковки |

## CAT-SAVE: catalog save может сбросить более новые правки

**Условие.** Открыт writable профиль, Settings чистые в момент начала профильной операции каталога. После отправки в backend запроса сохранения профиля для установки, обновления или удаления Agent Plugin/MCP пользователь меняет поле на другой странице до успешного ответа.

**Цепочка.**

1. [profile_blocked](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/catalog/apply.rs#L48-L60) запрещает начать запись с уже изменённым draft; повторная проверка выполняется непосредственно перед запросом в [write_catalog_profile](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/catalog/apply.rs#L204-L228).
2. После async save обработчик успеха вызывает [accept(snapshot)](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/catalog/apply.rs#L228-L246) без сохранённого `edit_revision`.
3. [accept](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/mod.rs#L263-L268) заменяет baseline и draft, затем очищает редакторы. `catalogs.busy` блокирует кнопку Save, но в проверенных [переходе между страницами](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/mod.rs#L347-L360) и [контролах полей](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/fields.rs#L89-L115) нет такого запрета.
4. Обычная кнопка Save уже использует [accept_save и submitted_revision](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/save.rs#L3-L36), сохраняющие более новые редакторские правки. Путь каталога этот механизм обходит.

**Граница вывода.** Речь о несохранённых локальных правках, появившихся во время запроса. Успешная запись в backend не доказывает, что последующие правки были отправлены. Не заявляется произвольная потеря сохранённого профиля.

**Практическое исправление.** Общий revision-aware путь подтверждения профильной записи с объединением несвязанных правок. Простая замена `accept` на `accept_save` недостаточна без проверки композиции: catalog writer меняет клон baseline, а локальный draft ещё не содержит установленный пакет. При сохранении старого draft следующий Save может отменить только что записанное подключение. Нужно совместить catalog delta и более новый draft либо явно показать конфликт.

**Следующая проверка, NOT RUN.** Задержать ответ save, изменить другое поле, затем завершить запрос. Проверить сохранность нового поля, подключение/удаление пакета в draft и baseline, следующий Save, ошибки ответа и повторные операции. До исправления безопаснее дождаться завершения операции каталога перед редактированием других настроек.

## EXT-10B: обновление версии меняет расположение данных Agent Plugin

**Условие.** Stateful Agent Plugin содержит поддерживаемый stdio MCP, использующий `PLUGIN_DATA`; каталог обновляет запись на другую версию, сохраняя рабочий каталог Core.

- Desktop повторно использует папку только при совпадающей версии и подходящей прежней установке. Иначе создаётся [новый immutable путь с UUID](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/catalog/install.rs#L93-L116); [connect](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/catalog/install.rs#L155-L175) заменяет profile reference, сохраняя `enabled`.
- Core получает canonical root и вычисляет [путь данных из хеша корня](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/agent_plugins/mod.rs#L128-L142). Этот путь передаётся stdio MCP как [PLUGIN_DATA](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/agent_plugins/mcp.rs#L107-L121).
- Следовательно, успешное обновление на новый корень меняет адрес состояния. В рассмотренном пути нет переноса данных между старым и новым адресами.

**Граница вывода.** Это смена адреса состояния, не доказанное удаление данных. Файлы старых версий специально [сохраняются](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/examples/catalog/README.md#L117-L122). In-place обновление того же canonical root не даёт этого эффекта. Плагин без состояния в `PLUGIN_DATA` может его не заметить.

**Практическое исправление.** Отделить стабильную identity установки от immutable каталога версии. Для существующих установок нужен явный миграционный план, учитывающий рабочий каталог, происхождение пакета, rollback и несколько профилей. Один лишь `plugin.name` не является достаточным доказательством общей identity для независимых источников.

**Следующая проверка, NOT RUN.** Временный stdio fixture хранит безвредный маркер через `PLUGIN_DATA`. Проверить установку v1, обновление v2, rollback, повторную установку той же версии, выключенный пакет и два профиля. Сверять адреса и содержимое без удаления прежнего состояния.

## ZIP-IDENTITY: повторный импорт не является обновлением по identity

[import_zip](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/catalog/install.rs#L286-L294) проверяет manifest и каждый раз распаковывает пакет в новую `zip-UUID` папку. [UI callback](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/ui/settings/catalog/zip.rs#L35-L46) добавляет полученный путь в draft. [Draft::add_package](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/settings/addons.rs#L98-L108) устраняет совпадение только по пути, не по manifest name.

Поэтому повторный импорт того же ZIP при сохранённой прежней записи создаёт вторую запись draft. При разрешении конфигурации Core [проверяет уникальность manifest.name](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/agent_plugins/mod.rs#L83-L98) и помечает повторное имя ошибкой. Нельзя из этого заключать, что обе копии успешно запускаются.

**Практическое исправление.** Перед подключением показывать существующую identity и явный выбор обновления или отказа. При согласованной замене сохранять `enabled` и состояние; не перезаписывать другой источник только из-за совпавшего имени. Файловую подготовку и серверную валидацию сохранить.

**Следующая проверка, NOT RUN.** Два импорта одинакового ZIP, новая версия того же пакета, совпадающее имя из другого источника, выключенный пакет и отмена draft. Проверить количество profile references, диагностику Core и сохранность прежних файлов. До исправления повторный ZIP нельзя считать автоматическим обновлением: перед Save следует проверить список Packages.

## TERMINAL-NESTED: terminal host не наследуется вложенными вызовами

Проверенный путь ограничен вызовами инструментов через `HookHost::execute_tool` и `DelegatingToolHost::execute_tool`.

- [HookHost callback](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/extension_operations.rs#L56-L84) и [delegating tool callback](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/extension_operations.rs#L157-L164) приходят в `BoundTools::execute`.
- [execute](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/bound_tools.rs#L244-L246) передаёт пустую функцию обогащения контекста.
- [ToolContext](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/core/bound_tools/invocation.rs#L34-L64) начинается с `terminal_host: None`; установка обычного `host` после этого не устанавливает terminal host.
- Process adapter [передаёт это поле dispatcher](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/process_adapters/tool.rs#L108-L140). Если terminal host отсутствует, обработчик публикации [возвращает null без terminal binding](https://github.com/Proteus-harness/Proteus-core/blob/6b918bb7293e258f32b69d4fb705ba76a2133a86/crates/proteus-core/src/process_adapters/tool/host.rs#L28-L59).

**Вывод.** По этой цепочке вложенный инструмент не получает опубликованную через данный callback ссылку на живой терминал. Обычный результат инструмента при этом может успешно вернуться. Не утверждается, что все терминалы, direct tool calls или shell output сломаны. Это ограничение доступности интерфейса; обхода прав этот анализ не устанавливает.

**Практическое исправление.** Передавать разрешённый terminal host через execution binding и nested callback с сохранением владельца, scope, cancellation и lifecycle. Не заменять отсутствие контекста глобальным host.

**Следующая проверка, NOT RUN.** Сопоставить прямой tool call, tool→tool и hook→tool в одном допустимом execution. Проверить terminal reference, UI publication, обычный output, отмену и отсутствие поддержки terminal у host. Нужен отдельный native UI smoke.

## TERMINAL-COST: ring создаётся раньше проверки поддержки публикации

[execute_command](https://github.com/Proteus-harness/Proteus-modules/blob/4e22f9e746a1c8756a7b1df8cd543e4fe352d5c3/tool/shell-tool/src/unified_exec.rs#L121-L142) сначала вызывает `spawn_session` и лишь затем проверяет `supports_terminal_publish()`. [spawn_session](https://github.com/Proteus-harness/Proteus-modules/blob/4e22f9e746a1c8756a7b1df8cd543e4fe352d5c3/tool/shell-tool/src/unified_exec/process.rs#L41-L58) всегда готовит terminal admission и record; [push_output](https://github.com/Proteus-harness/Proteus-modules/blob/4e22f9e746a1c8756a7b1df8cd543e4fe352d5c3/tool/shell-tool/src/unified_exec/session.rs#L178-L192) пишет каждый chunk и в terminal ring, и в буфер обычного результата.

**Вывод.** Даже когда публикация терминала не поддерживается, этот путь ведёт дополнительный журнал вывода. [Ring ограничен](https://github.com/Proteus-harness/Proteus-modules/blob/4e22f9e746a1c8756a7b1df8cd543e4fe352d5c3/tool/shell-tool/src/unified_exec/terminal.rs#L74-L88); это не утверждение о неограниченной утечке памяти. Накладные расходы чтением кода не измерены.

**Практическое решение.** Сначала подтвердить, нужен ли ring для позднего подключения или иного consumer в headless-режиме. Если такой гарантии нет, рассмотреть optional/lazy record, не меняя обычный output, capture, ограничения ресурсов и cleanup.

**Следующая проверка, NOT RUN.** На одном workload сравнить hosts с поддержкой публикации и без неё: allocations, peak RSS, CPU, совпадение stdout/stderr и поведение отмены. Отдельно проверить late attachment, если оно должно поддерживаться. Численных обещаний ускорения нет.

## CATALOG-SCOPE: process module ZIP пока не поддерживается каталогом

Это документированный предел текущего формата. [Kind](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/catalog/schema.rs#L16-L23) содержит только `client_extension`, `agent_plugin`, `skill` и `mcp_server`. [README каталога](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/examples/catalog/README.md#L124-L126) прямо исключает `components.*`. ZIP importer ожидает Agent Plugins 1.0 `plugin.json`, а не backend process module.

Agent Plugin, Desktop extension и backend process module имеют разные загрузчики и контракты. Нельзя обещать установку process module через Packages → ZIP только потому, что файл является ZIP.

Следующий продуктовый шаг: единая точка подключения с честным определением поддерживаемого типа. Поддержка process modules требует отдельного плана совместимости, доставки, активации, выбора профиля и rollback. Это предложение, не уже реализованный installer.

## Что уже исправлено и что делать дальше

В текущем Desktop сохранение `enabled` видно в [catalog connect](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/catalog/install.rs#L155-L175); extension preflight вызывается в [catalog install](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/catalog/install.rs#L124-L132) и выполняется [до publish staged files](https://github.com/Proteus-harness/Proteus-desktop/blob/306be31b77e935e1bc2696f49deee9cdfa3fb2e9/src/packages.rs#L142-L168). Эти исправления не закрывают CAT-SAVE, стабильную identity данных или повторный ZIP.

Рекомендуемый порядок:

1. Регрессия и исправление CAT-SAVE, включая последующий Save после успешного catalog update.
2. Общее решение identity для catalog update и ZIP; фикстуры миграции и rollback.
3. Передача terminal host в разрешённых nested callbacks и проверка нативного UI.
4. Измерение terminal ring без публикации; менять поведение только при подтверждённой пользе.
5. Отдельная спецификация доставки process modules, без объявления текущего ZIP универсальным.

## Граница публичного отчёта

Материал ограничен поведением настроек, адресацией состояния, совместимостью и потенциальными накладными расходами. В него не включены приватные журналы, пользовательские данные, credentials, exploit payloads или способы обхода разрешений. Отсутствие таких материалов не означает завершённый security audit. Публикация отчёта и его слияние не исправляют upstream и не являются production gate.
