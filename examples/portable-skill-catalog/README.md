# Portable skill catalog — реальный read-only importer для Proteus

Независимый Rust executable с **context_provider/v4** и **tool/v6**, SDK pin
`3f36a003b4f3fde2242fc80f7aedac00dd127d1d`. Не требует изменений Core и не
предоставляет собственный workflow/permission runtime.

## Для чего нужен

Владелец явно подключает существующие `.agents/skills`, `.claude/skills`,
`.pi/skills` либо другую локальную папку — без копирования и без запуска чужих
scripts/hooks. Provider показывает каталог; `portable_skill_load` читает
выбранную инструкцию. `portable_skill_catalog` обновляет каталог после изменения
файла, поэтому ошибка stale digest имеет рабочий путь восстановления в том же
turn, а не требует перезапуска всего приложения.

Native `skill-pack` уже умеет читать skills, показывать каталог и body-on-demand.
Этот пример **не изобретает это заново**. Его проверяемый delta:

- Только explicit absolute roots, без скрытого HOME/git-root/ancestor поиска.
- `root-id:directory-name`: два `review` из разных roots не затеняют друг друга.
  Повтор root id либо канонический alias того же root — ошибка конфигурации.
- Ранние общие лимиты entries/read bytes; disabled exact ID проверяется до
  stat/open/parse его SKILL.md. Общий overflow не возвращает частичный каталог.
- Ошибка одного файла — diagnostic при `strict=false`, ошибка операции при
  `strict=true`. Общие budgets/cancellation всегда fail-closed.
- `compatibility`, `license`, `metadata`, `allowed-tools` сохраняются как **данные**.
  Они не подтверждают совместимость окружения и не выдают права.
- Загрузка требует **id + sha256 + catalog_path**. Path сравнивается с вычисленным
  путём из конфигурации, а не используется как произвольный адрес чтения.
  Это ловит и изменение body, и случай разных provider/tool roots с одинаковыми
  SKILL.md, но разной базой относительных references.

## Использование

```sh
cargo build --locked
cargo test --locked
```

`host.example.toml` — полный offline template c fake provider. Замените **оба**
`/ABSOLUTE/PATH/TO/...` на одну реальную директорию `fixtures/skills` и добавьте
собранный executable и `proteus-reference-module` в PATH. Для реальных skills
укажите их абсолютные roots самостоятельно; входящий запрос не может их менять.

Вызов `portable_skill_catalog` с `{}` возвращает JSON text в `ToolResult.output`:
`catalog.skills[]` содержит `id`, `sha256`, `path`, `skill_directory`, `fields`.
Затем вызовите:

```json
{
  "id": "project-agents:review-note",
  "sha256": "<64 lowercase hex characters from the catalog>",
  "catalog_path": "<exact path field from the same catalog>"
}
```

Это аргументы `portable_skill_load`. Результат содержит body, исходные metadata,
точный skill_directory и явное предупреждение о недоверенном содержимом.
Не добавляйте выдуманный digest из примера: берите фактическое значение каталога.
После changed-file/source error обновите каталог и повторите осознанный выбор.

`addons.disabled_skills` применяется по точным namespaced IDs; дополнительный
`module_config.*.disabled` позволяет владельцу отключить skill на уровне export.
Provider/tool конфигурации независимы. Для одинаковой доступности держите roots
и disabled настройки согласованными; при несовпадении source load не проходит.
Native addon catalog доступен для отображения, но его текущий `SkillDescriptor`
не содержит параметры digest-bound activation. Поддерживаемый путь активации —
наши два tools, а не несуществующий автоматический native `/skill` routing.

## Границы формата и переносимости

| Поддерживается | Не заявляется |
|---|---|
| UTF-8 YAML frontmatter + Markdown body; LF/CRLF, closing fence на отдельной строке, включая EOF | BOM, repair malformed YAML, полная Claude/Pi/Codex skill runtime parity |
| Стандартные `name`, `description`, `license`, `compatibility`, строковая `metadata`, строковый `allowed-tools` | Исполнение hooks, scripts, shell substitutions, resource fetching, package installation |
| `disable-model-invocation: true` скрывает и блокирует загрузку; `user-invocable` сохраняется | User-explicit bypass `disable-model-invocation`, slash commands, user-invocable semantics native UI |
| Имена в ASCII subset native Proteus: lowercase/digits/hyphens, 1–64 | Unicode skill names, неизвестные top-level поля, списки вместо allowed-tools строки |

Неизвестные поля и duplicate YAML/metadata keys отклоняются явно, а не молча
отбрасываются. Синтаксис description с двоеточием подчиняется YAML: модуль не
угадывает, как переписать чужой документ. `serde_yaml 0.9.34+deprecated` закреплён
ради parser совместимости с исследованным Proteus skill-pack; его maintenance
status — ограничение примера, не рекомендация для нового универсального YAML SDK.

## Лимиты и надёжность

- 1–8 roots; до 512 total entries и 128 успешных skills (настраиваемые меньшие лимиты).
- 128 KiB на SKILL.md; 16 KiB YAML, включая expanded serialized metadata; 64 metadata keys.
- До 2 MiB суммарно прочитанных bytes. Для определения overflow читается максимум
  один дополнительный byte. Это не measured speedup и не абсолютный RSS bound YAML parser.
- Context до 64 KiB с pinned SourceAnnotated envelope; provider/serialized tool result до
  256 KiB; сам tool output text до **128 KiB**, ниже pinned Core default
  `max_output_bytes=200000`. Overflow внутри модуля — явная ошибка, не обрезанная
  инструкция/JSON. **Host с меньшим max_output_bytes всё ещё может обрезать ответ**:
  потребитель обязан учитывать `output_truncated`/`max_output_bytes` metadata.
  Модуль не может отменить общую host output policy.
- Каталог читает bounded **весь SKILL.md**, чтобы посчитать SHA256, затем
  отбрасывает body. Это model-context progressive disclosure, **не** обещание
  filesystem metadata-only I/O. References/assets/scripts не читаются.
- Cancellation проверяется между entries и блоками чтения. Блокирующий filesystem
  syscall не прерывается самим callback; hard timeout/termination остаётся у host.
- Symlink roots/entries/files отвергаются. Unix final open дополнительно использует
  O_NOFOLLOW/O_NONBLOCK и проверку regular file. Проверки ancestors не создают
  race-free filesystem capability: доверенные roots должны не перемещаться
  враждебно во время чтения. Это **не sandbox**, не защита от hostile concurrent
  rename, не authentication подпись и не атомарный directory snapshot.
- Digest относится только к прочитанным bytes SKILL.md. Изменения references,
  assets, scripts, окружения или внешних эффектов он не проверяет.

## Процессы и authority

SDK позволяет один process с двумя exports (проверяется wire fixture). В sample
config намеренно два запуска одного executable, каждый с **одним export**:
так они не требуют общего failure domain и совместимы по cardinality с opt-in
restricted launch. Сам sample остаётся trusted default и не утверждает, что
sandbox включён. Для restricted нужно отдельно настроить действующую host launch
policy с read grants; автоматического sandbox fallback нет. Export не вызывает
соседний export и не делает host tool/model callbacks. Core сохраняет admission,
ToolSafety, call identity, cancellation, settlement и canonical history.

## Проверки

`tests/behavior.rs` — authored filesystem/policy fixtures; `tests/wire.rs` —
реальный executable + SDK wire-v3 со **синтетическим host**. Последнее не равно
Core end-to-end. Сводка фактических запусков и ограничения: `VALIDATION.md`.
Точные исходники и hashes: `SOURCES.json`. Расширенный MCP/skills анализ и raw
regression vectors передаются отдельным research increment.

## Ограничение поддержки YAML зависимости

В этом исследовательском варианте закреплены `serde_yaml 0.9.34+deprecated` и транзитивный `unsafe-libyaml 0.2.11`. Их исходные проекты больше не поддерживаются: [заявление автора serde_yaml](https://github.com/dtolnay/serde-yaml/releases/tag/0.9.34), [RustSec INFO Unmaintained](https://rustsec.org/advisories/RUSTSEC-2024-0449.html). Это замечание о сопровождении, а не доказательство эксплуатации в данном модуле. Перед применением с недоверенными данными в production необходим выбор поддерживаемого parser и повторная проверка именно typed Frontmatter, alias/depth/expansion limits, duplicate keys и всей совместимости. В этом PR parser молча не заменяется; ограниченные функциональные тесты не объявляются полным аудитом parser.
