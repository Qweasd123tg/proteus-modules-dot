# Каталог исследований экосистем Proteus — публикационный контекст

Эта поставка содержит **только ранее подготовленные source-pinned исследования и их обязательные уточнения**. Она не добавляет код, workflow, конфигурации, runtime-проверки или новые темы исследования. Наблюдения не являются подтверждёнными runtime-дефектами, security-аудитом либо заявлением полной совместимости.

## Что читать

- [Round 1–4: отчёты, публичные ledgers и точное покрытие](README.md): Browser Use, Google ADK, Letta/Letta Code, Strands, OpenHands и Pydantic AI.
- [Synthesis Round 1–8](synthesis-round1-8/README.md): 16 редакционных групп механизмов и 10 пунктов roadmap; добавляет сопоставление DeepAgents/LangChain, Mastra, AgentScope и LiveKit по уже выполненному чтению источников.
- [Закреплённые версии](synthesis-round1-8/PINNED-SOURCES.md) и [карта механизмов](synthesis-round1-8/MECHANISMS.md).
- [Явный allowlist этой поставки](CATALOG-ALLOWLIST.json): пути, размеры и SHA256/Git blob SHA каждого payload. Сам allowlist исключён из собственной хеш-таблицы.

**90 записей baseline, 66 записей Round 1–4 и 16 групп synthesis нельзя складывать.** Round 1–4 не дедуплицированы против baseline; synthesis группирует и повторно использует те же находки. Это не счётчик новых bugs и не глобальная оценка полноты аудита. Coverage сохраняет различия full/partial/index-only; получение и хеширование файла не означают чтение каждой строки.

## Обязательные смысловые ограничения

1. [LiveKit `completed`](synthesis-round1-8/FOLLOWUP-REPLY-STATUS.md) — классификация callback по interruption/chat items, а не подтверждение успешной, полной или акустической доставки речи.
2. [CAS wire-file](synthesis-round1-8/FOLLOWUP-CAS-WIRE-LAYER.md) — три исторически authored cases: **два own-binary + один pure framing helper**, не три binary restart tests. 58 и отдельные 69 — размеры исторических candidates, не дополнительные успешно выполненные тесты.
3. [Core cancellation grace](synthesis-round1-8/FOLLOWUP-CANCELLATION-GRACE.md) — номинальное cooperative asynchronous ожидание 500 ms, не hard wall-clock preemption, rollback или остановка всех потомков ОС.

## Исторические статусы, не обновление runtime

Synthesis фиксирует состояние **26 октября 2026, 02:18 UTC**, с последующими уже принятыми редакционными уточнениями. Слова «unrun», «source-ready», «не опубликовано» и ограничения полномочий внутри неизменённых snapshot-файлов описывают **момент их подготовки**, а не текущее состояние всех PR. Эта публикация не выполняла повторную runtime-проверку и не обновляет статусы последующих CI-пакетов. Их результат нужно проверять отдельно на exact head соответствующего PR.

Сохранены 30 файлов принятого Round 1–4 пакета (29 payload + исторический PUBLICATION.json) и 14 файлов принятого synthesis (13 payload + исторический ADAPTED-MANIFEST.json). Исходные manifests описывают подготовку своих исторических пакетов. Текущий состав публикации определяет CATALOG-ALLOWLIST.json. Hash-bound identities в INPUTS/SOURCE-ARTIFACTS не означают публичную доступность исходного внутреннего артефакта; private raw receipts здесь отсутствуют.

## Отдельные поставки и границы

- [Baseline PR #1](https://github.com/Qweasd123tg/proteus-modules-dot/pull/1), exact base `29d31fb36397008b7677cd5df4943031e24e8fdf`: его каталог и код не изменяются.
- [Operator/reliability PR #9](https://github.com/Qweasd123tg/proteus-modules-dot/pull/9), snapshot `8761a432b18e4843fcbda3ece42670406d850866`: опубликованные там 31 operator + 2 reliability файла сюда не копируются.

В эту поставку не входят raw source dumps, приватные security-гипотезы, внутренние checkpoints, исходные receipts/транскрипты, credentials или локальные workspace paths. Новых запусков upstream/Core/modules/providers/media, установок, активации, cleanup, merge или deploy эта публикация не выполняет. Исследования помогают выбрать producer/consumer проверку; сами по себе они не дают полномочий и не заменяют такую проверку.
