# Дополнение: третий подтверждённый сквозной дефект

## 3. P2: откат Agent Plugin через History ломает последующее обновление из каталога

**Подтверждено, высокая уверенность.** Проверены те же Core `89997df…` и Desktop `75bf201…`.

### Цепочка

1. Catalog устанавливает plugin v1, затем v2 в новый immutable path.
2. `Preferences::remember` оставляет только receipt v2 для source/entry/profile.
3. History восстанавливает профиль v1. Файлы v1 предусмотрительно сохранены, поэтому откат работоспособен. Каталожный receipt при этом остаётся v2.
4. Пользователь устанавливает v3 через тот же каталог. `install::connect` ищет previous binding по пути receipt v2, но draft уже ссылается на v1. Поиск не находит previous, поэтому новый binding добавляется рядом с v1 вместо замены.
5. Core закономерно отклоняет сохранение: `duplicate Agent Plugin name: demo`.

Это supported flow без внешнего редактирования файлов/профилей. Пользователь не может штатно продолжить каталоговые обновления после отката, пока не разберёт старое подключение вручную. Новая immutable папка уже подготовлена до отказа сохранения; повторная попытка может оставлять ещё неподключённые версии. Потеря пользовательских данных или разрушение активного профиля **не** заявляются.

### Реальные результаты

```text
после catalog v1 → v2, History → v1, catalog → v3:
bindings=2, names=["demo", "demo"], stable keys=[None, None]
Core set_profile_config:
invalid Agent Plugin ...: duplicate Agent Plugin name: demo
```

Desktop probe исполняет существующие `prepare`, `connect`, `plugin::binding`, `plugin::connect`, `Preferences::remember`, `Draft::from_revision`, folder install и реальные contract types. Для компиляции изолированного headless harness неиспользуемые ветви extension/source-build/process-component заменены fail-fast заглушками; ветвь AgentPlugin не переписывалась. `catalog_types.rs` скопирован как точный блок type declarations из исходника. Это не интерактивный GPUI прогон.

Выход `AppAddonsUpdate` этого самого Desktop probe передан настоящему Core `AgentAppServer::set_profile_config` через JSON. Core не подменён: он читает подготовленные plugin manifests и отклоняет payload в штатной addon validation.

### Почему прежний тест это не замечает

`catalog_updates_and_rollback_keep_the_original_state_address` в `src/catalog/tests/plugin_identity.rs` делает rollback через `install::connect(v1, previous=v3)`, а затем проверяет повторное подключение **того же** v1. Но реальная History меняет только draft/profile и не обновляет latest receipt. Сценарий **нового** каталожного обновления после настоящего history restore там отсутствует.

### Источники

- [latest-only receipt](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/mod.rs#L109-L115).
- [History меняет только draft](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/settings/revisions.rs#L81-L105).
- [Поиск previous binding только по last receipt или new path](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/install.rs#L173-L200).
- [Core duplicate name validation](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_plugins/mod.rs#L92-L96).
- [Существующий тест со специальным connect rollback](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/catalog/tests/plugin_identity.rs#L41-L99).

### Направление исправления

Согласовать immutable installation lineage/receipts с History restore и искать точное текущее подключение по доказанному происхождению. Не заменять чужой пакет только по совпавшему manifest name: существующая защита от такого присвоения должна сохраниться. Можно сохранять историю подтверждённых путей source/entry/profile и восстанавливать receipt при откате или явно разрешать replacement для доказанно того же lineage.

### Доказательства

- `desktop-probe/src/bin/plugin_history.rs`.
- `desktop-probe/src/install_plugin_probe.rs`, `catalog_types.rs`: исходные тексты с описанными compile-only substitutions.
- `plugin-history-repro.log`, `plugin-history-repeat-{1,2,3}.log`.
- `core-config-builder-tests-final.log`: **10/10**, из них 4 новых tests и 6 существующих.
- `plugin-core-repeat-{1,2,3}.log`.
- `core-repros.patch`: теперь четыре теста. Последний требует `AUDIT_PLUGIN_ADDONS_JSON`, указывающий на `post-connect-addons.json` из Desktop fixture.

Production-файлы репозиториев не менялись. Публикаций нет.
