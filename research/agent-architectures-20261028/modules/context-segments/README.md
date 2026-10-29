# Безопасные сегменты контекста — Rust-прототип политики

**Статус: только исходники; не собран, не запущен и не интегрирован в Proteus.** Сборки, тесты, бенчмарки и CI в этой работе не выполнялись. Проверку пользователь проводит самостоятельно. Здесь нет экспорта runtime-модуля, provider adapter, hook registration или изменений upstream.

## Что добавлено и зачем

`analyze(History, Limits)` вычисляет **структурно допустимые границы** в неизменённой последовательности сообщений. На входе только нормализованные host-owned метаданные: числовые идентификаторы, виды частей, принадлежность группам и полнота нормализации. Тексты, аргументы инструментов, результаты, reasoning, подписи и непрозрачные provider bytes библиотека не принимает и не копирует.

Результат — `SegmentPlan` с границами, непрерывными неделимыми сегментами и причинами защищённых интервалов. Это **не compactor**: библиотека не выбирает бюджет, не создаёт summary, не удаляет, не дедуплицирует и не переставляет события. При неоднозначности возвращается `Rejection`, без частично пригодного плана.

Основные гарантии при корректной нормализации host:

- вызов инструмента и единственный окончательный результат не разделяются;
- все вызовы одного параллельного assistant batch остаются атомарными вместе с их результатами, даже когда результаты приходят в другом порядке;
- provider-owned opaque/reasoning-группа, в том числе полный связанный tool loop, не разрезается;
- пересекающиеся ограничения замыкаются транзитивно;
- неизвестная семантика, незавершённая группа, непарный вызов или конфликтующие результаты блокируют **весь** план;
- никаких «первый результат всегда истинный» и молчаливого удаления поздних observations.

Сегментация гарантирует только отсутствие разреза известных структурных связей. Она не доказывает качество summary, сохранность пользовательских требований, корректность произвольного нового provider request или безопасность удаления целого сегмента.

## Что уже есть в Proteus

Исследование опирается на ранее прочитанные snapshots Core `125a9eb4088991513e9f61d899469be2076e266c` и Modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a`, а не на утверждение о сегодняшнем HEAD:

- `codex-context-preparation` уже выполняет threshold-based compaction с модельной summary;
- существующий путь сохраняет user anchors и отдельно обрабатывает request-scoped/ephemeral context;
- Core проверяет неизменность существующих message/part identities и происхождение replacements;
- в исследованном compactor вся compactable history заменяется summary и anchors; selective retention tool tail там не реализован.

**Текущая compaction не объявляется сломанной.** Этот прототип — дополнительный алгоритм для будущих keep-tail/selective compaction или принятия prepared summary со свежим suffix, а не исправление доказанной регрессии и не замена существующей identity validation.

Основание: локальный отчёт `proteus-agent-research-20261028/reports/openhands-deepagents.md`, раздел «Структурно безопасное сокращение истории». Закреплённые первичные источники:

- [Proteus compactor](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/hook/codex-context-preparation/src/compaction.rs).
- [Core identity validation](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/contracts/compaction_validation.rs).
- [Canonical content parts](https://github.com/Proteus-harness/Proteus-core/blob/125a9eb4088991513e9f61d899469be2076e266c/crates/proteus-contracts/src/model_standard/content_part.rs).
- [OpenHands tool matching](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/tool_call_matching.py), [batch atomicity](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/batch_atomicity.py), [provider tool-loop atomicity](https://github.com/OpenHands/software-agent-sdk/blob/7486c1d16ef67e00a57d6eec8baf48c8efdd7be2/openhands-sdk/openhands/sdk/context/view/properties/tool_loop_atomicity.py).

Перенесена идея явных ограничений границ, не Python event hierarchy и не исходный код upstream. В рамках этой реализации внешние страницы повторно не исследовались: ссылки и сведения взяты из указанного локального отчёта. Заявлений об измеренном ускорении нет.

## Контракт нормализации

### Сообщение — минимальная единица

Один `Event` означает **целое canonical message**, а не отдельный токен, chunk или произвольно выделенную часть. `parts` — полный список дескрипторов его частей; `Plain` не содержит текст и допустим только для известной обычной части без дополнительных preservation obligations. Разрез внутри сообщения невозможен по конструкции. Если host уже разбил один provider response на несколько canonical messages, он обязан сохранить общую `AssistantBatch` identity.

`EventId`, `CallId`, `GroupId` — маленькие host-issued handles. Они должны однозначно соответствовать исходным identities в данном snapshot, включая нужный session/provider scope. Нельзя без проверки свести внешние строковые IDs к обрезанному хешу или повторно использовать call ID. `SnapshotId` лишь возвращается в результате: это **не** проверка digest, не источник полномочий и не механизм защиты от stale plan.

### Полнота — явное свидетельство host, не эвристика

Для получения плана необходимы:

1. `History.normalization == Complete`: перечислены все части и все зависимости этой закрытой model-view projection; произвольное окно с неизвестными связями за краями недопустимо.
2. `provider_coverage == HostVerified`: host определил все provider constraints для конкретной модели и representation. Отсутствие обнаруженного reasoning само по себе не позволяет поставить этот флаг.
3. Каждая `Group` имеет известный kind, `completeness == Complete`, ненулевое `expected_members` и ровно столько уникальных event memberships. Число означает **сообщения**, не calls/parts. Даже `Complete + совпавший count` не доказывает полноту без доверенного источника этих данных.
4. Каждый `ToolCall` ссылается на объявленную `AssistantBatch`, в которую входит его event.
5. Каждый `Reasoning` и `Opaque` ссылается на объявленную `ProviderAtomic`, в которую входит его event. Нужна вся область сохранения provider, а не только сообщение с подписью. Даже неподписанный reasoning в этом консервативном прототипе требует явной provider-группы; host может подтвердить singleton-группу, если это действительно вся область.
6. Каждому call соответствует ровно один окончательный `ToolResult` в более позднем сообщении. Ошибка/отмена может быть окончательным результатом, если canonical model view так её представляет. Само предположение «вызов, наверное, отменён» не заменяет наблюдение.

Неизвестные kind/part/coverage и `Incomplete` не означают «пока пропустить»: они означают отказ. Если batch identity потеряна, не следует восстанавливать её по соседству, timestamp или похожему тексту. Нужны host-owned метаданные, либо отказ от этой selective-segmentation операции. Другой уже существующий compaction path должен оставаться под собственной проверенной политикой host; библиотека не выбирает fallback.

Streaming chunks нельзя подавать как несколько окончательных `ToolResult`. Если одновременно существуют recovery error и поздний реальный result, нужен явный host reconciliation для model view. Прототип не решает, какое наблюдение истинно, и не разрешает стирать journal/settlement records. Незавершённый live call приводит к `MissingResult`, даже если где-то раньше мог бы существовать независимый префикс: это сознательное fail-closed ограничение первой версии.

## Как строятся границы

Для каждого call/result создаётся защищённый полуинтервал `[call_event, result_event + 1)`. Для каждой атомарной группы — `[first_member, last_member + 1)`. Промежуточные сообщения между несмежными членами тоже защищены: это консервативный способ не переупорядочивать историю.

Интервал `[s, e)` запрещает границы `s < b < e`. Sweep по разностному массиву пересекает все разрешения, включая перекрытия tool pairs, batches и provider loops. Поэтому не нужно многократно склеивать группы.

Пример с целыми сообщениями:

```text
event 0: пользователь
event 1: call A + call B          [AssistantBatch X, один event-member]
event 2: result B
event 3: result A
event 4: ответ

pair A: [1,4)     pair B: [1,3)     batch X: [1,2)
legal boundaries: 0, 1, 4, 5
segments: [0,1), [1,4), [4,5)
```

Если provider-группа связывает reasoning в event 0 со всем loop до event 4, её `[0,5)` оставляет только границы `0` и `5`. Если batch X разбит на несколько assistant messages, группа должна перечислять все эти event members; её интервал вместе с парами удержит результаты **всех** calls. Порядок результатов A/B значения не имеет, но result до собственного call или в одном сообщении с ним отклоняется.

Границы `0` и `N` означают отсутствие структурного разреза на краях, **не** разрешение удалить весь контекст. Для пустой закрытой истории результат содержит границу `[0]` и пустые segments; все условия полноты сохраняются.

Для selective retention разрешено рассматривать только объединения **целых** сегментов и сохранять исходный порядок. Но даже удаление целого сегмента требует независимых правил anchors, summary и provider validity. Здесь намеренно нет API `drop`, `retain`, `summarize` или `apply`.

## Ограничения ресурсов и диагностика

У библиотеки нет внешних зависимостей, I/O, потоков, async tasks, JSON parser и сетевых запросов. Все slices заимствованы, результаты содержат только IDs, индексы, диапазоны и типизированные причины.

| Предел | По умолчанию | Жёсткий максимум |
|---|---:|---:|
| Сообщения | 4 096 | 16 384 |
| Все parts | 32 768 | 131 072 |
| Parts в сообщении | 512 | 1 024 |
| Объявленные groups | 8 192 | 32 768 |
| Все event memberships | 32 768 | 131 072 |
| Memberships в сообщении | 128 | 256 |
| Сохранённые diagnostics | 64 | 128 |

Caller может понижать пределы; превышение жёсткого максимума — `InvalidLimit`, а не дополнительное разрешение на память. Нулевые caps разрешают только отсутствие соответствующих данных; diagnostics должен быть от 1 до 128. Preflight проверяет lengths **до** создания индексов и до обхода вложенного чрезмерного slice. Уже выделенная host память и сериализованный вход этими ограничениями не защищены: adapter обязан ограничить их раньше.

Используются `BTreeMap`/`BTreeSet`, чтобы получить детерминированное поведение без ожиданий о качестве входных hashes. Для `N` сообщений, `P` частей, `G` групп и `M` memberships время ограничено `O((N + P + G + M) log(N + P + G + M + 1))`, дополнительная память — `O(N + P + G + M)` в рамках caps; sweep линейный по числу сообщений и constraints. Это оценка конструкции, не результат измерений. Обычная ошибка выделения памяти среды Rust не преобразована в `Rejection`: жёсткие caps не гарантируют наличие свободной памяти и не равны отсутствию OOM.

`Rejection.diagnostics` содержит типизированные причины и, где применимо, event/part index и ID. Причины включают:

- `InvalidLimit` / `LimitExceeded`;
- `NormalizationNotComplete` / `ProviderCoverageUnknown`;
- дубликаты identities, declarations и memberships;
- несуществующую группу, отсутствие membership, неправильный group kind;
- `GroupNotComplete`, `EmptyGroup`, `InvalidMemberCount`, `MemberCountMismatch`;
- `UnknownPart`, `MissingCall`, `MissingResult`, `DuplicateCall`, `DuplicateResult`, `ResultNotAfterCall`;
- защитный `InternalEmptyCallIndex` на случай нарушения внутреннего инварианта при последующем изменении реализации.

Число скрытых из-за cap сообщений доступно в `suppressed_diagnostics`; насыщение счётчика не превращает отказ в успех. Не копируются названия инструментов, сообщения об ошибках внешних процессов или какие-либо пользовательские данные. При cap/preflight/coverage-ошибке обработка завершается рано; полный перечень всех проблем входа не обещается.

## Чего не хватает до Core adapter

Потребуются отдельная реализация и проверка на стороне существующего context-preparation path:

1. **Нормализатор Core contracts.** Перевод реальных canonical messages/parts и identities без потерь, строгие caps до материализации metadata, поддержка конкретных provider representations. Любой новый/неизвестный part должен приводить к `Unknown`, не к `Plain`.
2. **Надёжный источник групп.** Assistant response/batch identity и полные provider preservation groups, включая closed/open состояние, signatures/opaque blocks и зависимые tool loops. Отсутствующие identities нельзя выдумать; контракт может потребовать расширения host metadata.
3. **Закрытый snapshot.** Host должен доказать, что нет скрытых связей за краями выбранного view, а live/incomplete operations обозначены. Сводка предыдущей compaction — не автоматическое доказательство такой замкнутости.
4. **Reconciliation model view.** Разрешение late/duplicate observations отдельно от неизменяемого journal и settlement. Библиотека ничего не «чинит» удалением.
5. **Интеграция бюджетной политики.** Выбирать кандидат лишь среди допустимых границ, сохранять user anchors и request-scoped контекст, проверять provider-valid replacement и полезность summary. Известная batch-атомарность не решает смысловую зависимость двух обычных сообщений.
6. **Применение на host.** Привязка плана к реальным session/view identities и актуальному epoch/digest, повторная проверка при изменении snapshot, compare-and-replace, существующая identity validation и правила сохранения suffix. Сам `SnapshotId` CAS не выполняет.
7. **Проверка результата.** Компиляция, тесты и provider compatibility остаются впереди. Ни manifest, ни наличие исходника не означают, что это готовый plug-in.

Нельзя подключать эту библиотеку напрямую как новый process slot, ослаблять existing validation или выдавать её за Core-compatible runtime export. Cargo manifest `publish = false`, зависимостей и регистрационных файлов нет.

## Сценарии для самостоятельной проверки

Это перечень ожидаемых свойств, **не отчёт о выполненных тестах**:

- пустая история; обычные сообщения; единичный целый call/result;
- два параллельных calls в одном assistant message и в разных messages одного batch; обратный порядок результатов;
- перекрывающиеся пары, вложенные provider-группы, раздельные и касающиеся только краями интервалы;
- signed/opaque loop со связанными calls/results: ни одной внутренней границы;
- incomplete/unknown group, потерянная batch identity, неописанный provider constraint: `Err`, без legal boundaries;
- отсутствующий, ранний или повторный result; recovery error + поздний observation; повторный call ID;
- duplicate event/group/membership; member count mismatch; неизвестный part; ссылка на группу неправильного kind;
- каждый cap на пределе и за пределом; oversized nested slice не обходится; diagnostics cap не маскирует отказ;
- stale snapshot не применяется Core adapter; после изменения live suffix требуется новая host-проверка;
- все успешные segments покрывают исходные event indices ровно один раз и в исходном порядке; ни один protected span не содержит legal boundary строго внутри.

**Проверено в этой работе:** прочитан локальный исследовательский отчёт и вручную рассмотрены исходники нового прототипа. **Не выполнено:** компиляция, rustfmt, тесты, запуск кода, CI, измерения, изменение upstream и публикация этим модулем. Ожидаемые свойства выше должны быть независимо проверены, а не считаться уже подтверждёнными.
