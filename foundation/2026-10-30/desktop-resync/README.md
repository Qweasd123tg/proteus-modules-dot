# Desktop: согласование состояния после SSE reconnect / lag

**Source-only кандидат, не проверенная runtime-поставка.** Основа:
`Proteus-harness/Proteus-desktop@a28cc7f507424a570e86dc44230ee323156fdf6c`.
Поведение сервера проверено по исходникам
`Proteus-harness/Proteus-core@befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Обе вершины `main` повторно проверены 2026-10-30 в 16:28 UTC.

## Две подтверждённые по исходникам проблемы

1. После пропущенного terminal ExecutionUpdated snapshot восстанавливает
   execution/transcript, но прежний клиент не выдаёт RunSettled. Этот сигнал
   обновляет список сессий и передаётся подписанному расширению активного чата.
2. Snapshot не содержит config/reload state. Если успешный reload пропущен
   при disconnect/lag, чат может сохранить старый config.

`desktop-resync.patch` содержит обе узкие правки. Для независимого переноса
есть `run-settled-resync.patch` и `config-resync.patch`; применяйте **либо**
общий патч, **либо** два отдельных, не все три.

- RunSettled восстанавливается только для ранее наблюдавшегося active run:
  совпадают session + stream generation и run_id с terminal last, нового
  active нет. Решение принимается после cursor acceptance, сигнал выдаётся
  после применения snapshot. Начальная история, чужая generation, иной id,
  nonterminal last, повторный snapshot и уже доставленный terminal не создают
  ложного завершения. Root может смениться/очиститься при settlement; равенство
  root не требуется и не заменяет идентичность run/session/stream.
- После реального reconnect и EventStreamLagged вызывается существующий
  load_config: local read, затем discovery с прежними generation guards.
  Начальная загрузка и offline-поведение сохранены; каждый обычный snapshot
  settlement не запускает discovery. Новых watcher/cache/settings/timer нет.

## Совместимость и применение

Все три патча отдельно проходят строгую проверку применимости к указанной
основе. Общий патч побайтово совпадает с результатом двух отдельных.
Проверена композиция в обоих порядках с
[PR69 — bounded ready batch + yield](https://github.com/Qweasd123tg/proteus-modules-dot/pull/69),
head `06b3b2bc231b15ae81296071ecb215f64257a6f0`, patch SHA256
`ada1f395c3ecaaf16723a16d2cd8d60a6fa6cb65cca9537e637ae90558ba3f9b`.
Результаты обоих порядков идентичны; обратное применение восстанавливает все
исходные файлы побайтово и удаляет добавленный PR69 test source. Форматирование
совместного результата проверено rustfmt. Это **source composition**, не
доказательство поведения собранного приложения.

## Почему здесь нет bounded producer queue

Текущая очередь Desktop остаётся unbounded. Блокировка producer на её лимите
останавливает чтение SSE, затем Core body/subscription; bounded broadcast Core
может потерять события и заменить их snapshot. Snapshot — проекция состояния,
а не replay всех событий. Error/reload-failure notices и все промежуточные
terminal/control notifications он не восстанавливает. Локально lossless send
не означает end-to-end lossless stream. Эти две правки не снимают этот HOLD.

## Проверки и обязательные следующие gates

Выполнены: точные preimage hashes, независимое source review, строгие apply /
reverse / byte restoration, взаимная композиция с PR69, rustfmt.
Пять новых source regression tests проверяют решение о settlement; они
**не запускались**. Не запускались также Cargo, project scripts, сборка, CI,
нативное приложение или transport fixture. Замеров latency/RSS/CPU нет.

| Gate | Состояние / требуемое evidence |
| --- | --- |
| Settlement unit regressions | Исходники добавлены; выполнить с существующим Desktop runner при разрешённом запуске |
| GPUI subscriber delivery | Не проверено: подтверждённый terminal snapshot должен один раз обновить summaries и HostEvent; повтор не должен дублировать |
| Config HTTP/GPUI | Не проверено: initial/offline load, reconnect, lag с пропущенным reload, отсутствие fetch на обычном settlement snapshot |
| Overlapping config requests | Не проверено runtime: задержанные local/discovery ответы не должны переписать новый config/settings result |
| Composed live stream | Не проверено runtime: поток с PR69, reconnect/lag, root clear/change, cancel, terminal, rehost/close |
| Canonical settlement/history | Существующие Core gates остаются нужны; этот патч не меняет journal и не заменяет cold-history/replay evidence |

Фиктивный тест loader не добавлен: модельный snapshot test не проверяет
реальный load_config и callbacks GPUI/HTTP. Подробности границ и независимого
ревью — в REVIEW.md; точные источники и статические результаты — в JSON.
