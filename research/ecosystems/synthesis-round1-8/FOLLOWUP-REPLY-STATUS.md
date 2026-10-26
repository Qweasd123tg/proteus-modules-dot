# Уточнение Round8: ToolReplyUpdated.completed не подтверждает полную озвучку

26 октября2026, после независимой проверки выбранной цепочки. Исходные REPORT.md, INTEGRATION-LIMITS.md и receipt `d05d2e0535f5fa29ea93e97218dd43549d2220b3df7070a9254aa83f2f807caa` остаются неизменными. Это обязательное дополнение к **R8-R08** и таблице сигналов, не новое runtime воспроизведение.

## Точный смысл source label

В закреплённом LiveKit `4c24224f0ef4f511fa3395dcd87b294a87ae241e` callback `_on_speech_done` выбирает:

- `interrupted`, если установлен `speech.interrupted`;
- иначе `skipped`, если нет `speech.chat_items`;
- иначе `completed`.

Эта ветка **не читает `speech.exception()`**, не проверяет успешное окончание аудиосинтеза/вывода и не подтверждает акустическую доставку. Поэтому «уведомление completed» в R8-R08 означает **только классификацию указанного callback**, а не доказанное успешное или полное озвучивание. Источник: [tool_executor.py695–718](https://github.com/livekit/agents/blob/4c24224f0ef4f511fa3395dcd87b294a87ae241e/livekit-agents/livekit/agents/voice/tool_executor.py#L695-L718).

## Дополнение к таблице сигналов

| Наблюдение | Разрешённый вывод | Чего нельзя заключать |
|---|---|---|
| `ToolReplyUpdated.completed` | Done callback увидел непустые chat items и отсутствие speech.interrupted | Нет generation/TTS error; весь текст был озвучен; слушатель получил звук |
| `ToolReplyUpdated.interrupted` | В callback установлен speech.interrupted | Tool effect отсутствует или должен быть повторён |

ToolCallEnded, generation error, sink playback accounting и ToolReplyUpdated остаются отдельными producers. UI должен показывать исходный label либо свою явно определённую осторожную формулировку, а не повышать его до «успешно доставлено». Уже имеющийся caveat о partial без aligned transcript и локальной RTC queue position сохраняется.

Новых upstream/Core/media/provider запусков нет. Это source-label limitation, **не подтверждённый runtime дефект**. При дальнейшем переносе отчёта или synthesis необходимо сохранить это уточнение вместе с исходными hash-bound материалами.

