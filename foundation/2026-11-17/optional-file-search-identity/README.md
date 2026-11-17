# Optional file identity: paired Core + Modules proposal

**COORDINATED ROLLOUT / MIXED-VERSION HOLD.** Это связанный source proposal с focused native evidence, не upstream integration и не release-ready поставка. Module patch нельзя применять отдельно к старому Core. Публикация или merge этого пакета в delivery repo не снимает HOLD и не обновляет исходники, pins или binaries upstream.

## Подтверждённая проблема

Официальный OpenAI SDK допускает отсутствие `file_id` у отдельного file-search result. Текущий Modules parser требует строку; Core `FileSearchResult` тоже требует `String`. Pure Rust diagnostics независимо подтвердили: такой result отвергает весь completed response, даже с корректными соседними answer и usage. Это schema-level воспроизведение, не наблюдённый live-инцидент и не оценка частоты. [Закреплённая схема SDK](https://github.com/openai/openai-node/blob/4517ca801b79a93ccc17826b0b63ba2313355307/src/resources/responses/responses.ts#L3640).

## Один владелец и честное представление

- Core DTO: `FileSearchResult.file_id: Option<String>`, constructor явно принимает `Option<String>`.
- Modules: существующий `optional_string` принимает omission без выдуманного ID и удаления result. Metadata, порядок, answer, usage и raw provider metadata сохраняются.
- Provider `null` и нестроковые значения по-прежнему отклоняются: optional string не расширяется до nullable provider field.
- Canonical serde пишет `None` как `null`, читает missing/null как `None`; строка остаётся `Some` без нормализации.
- Обязательные hosted activity ID и citation file ID не меняются.

## Совместимость и consumers

Старые строковые ID читаются новым DTO и сохраняют прежнее значение. Новые null-ID не читаются старым mandatory-String consumer. Rust constructor и field type являются breaking source change. Для этой формы старую историю со строковыми ID переписывать не нужно, но downgrade reader после записи новых null-ID несовместим.

Core transcript projection считает результаты и сериализует activity в metadata, не разыменовывая file ID. Его единственный direct constructor fixture обновлён. В Modules обновлены direct parser и существующий pattern assertion. Просмотренные независимым reviewer Desktop/Extensions display paths используют JSON Value/AppTranscriptTool, а не direct FileSearchResult decode; это не exhaustive client compile proof. Desktop остаётся на старом Core dependency pin.

Это соответствует экспериментальной alpha-политике Core: менять tracked producers/consumers вместе, не добавлять migration shims, aliases или dual-read/dual-write. Пустой ID, silent filtering и адаптерный workaround не предлагаются.

## Состав

- [Core patch](core-optional-file-id.patch), base `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`: DTO, serde tests, constructor fixture, документация.
- [Modules patch](modules-optional-file-id.patch), base `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`: parser, tests, assertion migration, документация.
- [Проверки](VALIDATION.md), [источники и consumers](SOURCES.md), [независимый review](REVIEW.md), [checksums](SHA256SUMS).

Локальный Cargo overlay, Cargo.lock, абсолютные пути и полные metadata dumps намеренно не включены. Ни один patch не меняет pins, workflows, process/security код или deployment.

## Что удерживает integration на HOLD

Нужно согласованно обновить Core contract, Modules producer и typed consumers/pins, проверить boundary/versioning и выполнить применимые DTO/client/integration gates. Смешанная поставка старого host и нового adapter небезопасна по данному полю. Эти gates не заменяются успешными serde/parser tests; в рамках этой работы они не запускались. Решение о coordinated rollout остаётся отдельным от публикации proposal.
