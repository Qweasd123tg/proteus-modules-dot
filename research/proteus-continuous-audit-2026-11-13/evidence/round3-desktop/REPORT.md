# Proteus Desktop: аудит 3, новые участки

Проверенная версия: `75bf201764278eac4b50d156650edcf1429101ff` (`main`). Локальный HEAD и remote main совпали при начале и завершении прохода 2026-11-12.

Production-файлы не менялись, публикаций не было. Все артефакты этого прохода находятся в `audit-round3/`.

## Результат

Найдены три воспроизводимых сценария в **прямом Codex-драйвере Desktop**, не в model-profile Codex через Proteus Core. Два относятся к смешиванию snapshot и live events, третий к состоянию незавершённого элемента истории. Не заявляется потеря сохранённой истории на сервере: это неверное состояние отображаемого transcript. Последующий полный `item/completed` способен исправить строку.

### 1. P2: resume дважды применяет output delta, уже включённую в историю

- [Регистрация подписки до чтения истории](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/mod.rs#L232-L266)
- [UI сначала загружает snapshot, затем читает очередь событий](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/codex/mod.rs#L77-L150)
- `src/transcript/external.rs:88-140` добавляет tool output delta к уже существующему running item без позиции/версии.

В процессе `thread/items/list` сервер может прислать output delta работающего commandExecution. Возвращаемый snapshot уже содержит эту delta. После создания чата очередь применяется к более новому snapshot повторно.

Тест `resume_overlap_must_not_replay_tool_delta_already_in_history`: history содержит `Hello world`, ожидающее событие содержит ` world`; итог `Hello world world`, ожидалось `Hello world`.

Подтверждено на настоящих `CodexService`, wire client и `Transcript`, с синтетическим JSONL server peer. GUI и установленный Codex не запускались. Fixture использует `commandExecution.status=inProgress`, поэтому не зависит от спорного определения завершённости agentMessage.

### 2. P2: resync после отказа удаления выбрасывает восстановленный префикс из-за единственной delta

- [Общий filter по item ID](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/router.rs#L169-L198)
- [Delta считается полноценной заменой item](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/router.rs#L311-L331)
- `src/agents/codex/recovery.rs:1-50` выполняет resume и читает хвост истории для восстановления.

UI до unsubscribe содержит `Hello`. За время отписки появляются ` missed`, затем во время resync приходит live delta ` world`. Серверный snapshot содержит `Hello missed world`. Router удаляет весь snapshot item из `history`, поскольку его ID встречался в delta. UI остаётся с `Hello world`: пропущенный текст не восстановлен.

Тест `resync_delta_must_not_discard_authoritative_prefix` моделирует definitive remote rejection удаления. Явный файловый barrier не даёт peer вернуть snapshot, пока тест не получил live delta через настоящий router. Это не случайная гонка планировщика. Исходная streaming-строка устанавливается тестом как состояние уже открытого работающего чата.

Нельзя исправлять простым подавлением всех delta или безусловной заменой snapshot: первый сценарий показывает другую сторону той же границы. Нужна согласованная точка среза/порядок snapshot и последующих событий; при отсутствии версии протокола требуется отдельная стратегия сверки.

### 3. Кандидат P2: незавершённый agentMessage из history помечается завершённым

- [История всегда вызывает projection с completed=true](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/mod.rs#L404-L425)
- [Если у item нет status, используется completed](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/projection.rs#L100-L123)
- [Завершённый transcript item больше не принимает delta](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/transcript/external.rs#L116-L128)

Тест `active_history_snapshot_ignores_following_delta`: resume возвращает active thread, current turn `t`, agentMessage `Hello` без status. Следующая delta ` world` проигнорирована: transcript остаётся `Hello`.

Отсутствие `status` у agentMessage соответствует проверенной текущей upstream-схеме OpenAI Codex; там также есть nullable `completedAtMs` у history entry. Desktop не использует его. Но **в этом проходе не подтверждалось на живом установленном Codex, что его конкретная версия возвращает незавершённый agentMessage с частичным текстом через items/list**. Поэтому это кандидат с подтверждённой ошибкой обработки такого payload, а не объявление воспроизведённого live-дефекта. Сохранённые выдержки схемы: `upstream-schema-evidence.txt`.

## Тесты

Стенд `probe/` компилирует production-модули по относительным путям, не копии реализации. Python peer не запускает модель, не использует аккаунты и не обращается к сети.

```sh
cargo test --manifest-path audit-round3/probe/Cargo.toml -- --skip audit::
cargo test --manifest-path audit-round3/probe/Cargo.toml audit:: -- --nocapture
```

- Штатные unit-тесты включённых модулей: **64 passed, 0 failed, 1 ignored**. Ignored: реальный installed-app-server smoke.
- Новые проверки ожидаемого корректного поведения: **3 failed**. Это ожидаемый результат на неисправленном production SHA, не успешное прохождение.
- Повторение всего нового набора: **10/10 одинаковых отказов**, 30 воспроизведений суммарно.
- Логи: `baseline.log`, `probe.log`, `repeat-1.log` ... `repeat-10.log`.
- Это не полный GUI test suite, не запуск пользовательского harness по профилям и не полный аудит репозитория.

## Охват

`coverage.tsv` фиксирует SHA, точные прочитанные диапазоны и SHA-256 исходных файлов: **35 файлов, 8876 строк, 29 файлов прочитаны полностью**. Список не пересекается с `audit-round2/coverage.tsv`; общие с первым проходом файлы могли перечитываться для новых взаимодействий, старые находки не выдаются за новые.

Новые области: preferences/recent, запись настроек, workspace/windows/spaces/documents, API transport/proxy/connection, attachments, прямой Codex resume/recovery/router/projection, внешний transcript и navigation. В просмотренных settings/workspace/attachment областях отдельные дефекты достаточной доказанности не заявляются. Частичные чтения отдельно обозначены; выводы по всему непрочитанному файлу не делаются.
