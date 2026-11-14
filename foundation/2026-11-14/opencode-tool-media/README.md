# OTM-1: PNG tool-result останавливает OpenCode continuation

[Source-only отчёт](REPORT.md). **P2 interoperability candidate**, независимо проверенный по исходникам: успешный `opencode_tools/read` сохраняет PNG в canonical result, но обязательный `nativeContext` на следующей итерации `opencode_loop` отвергает non-text content до второго sampling. Отключение compaction hook не убирает эту projection.

Базы: Modules `c035142558f0fca43e9772fc0e50ca293abf1531`, Core `bcbda4435534a296c707a1daa250813d692f68e1`, upstream OpenCode `527f0b931d1f9b3ebd34e106c51b31ce5db5b075` (`@opencode/core@2.0.22`). Modules Cargo pin Core отличается от Core main; runtime-композиция не проверена.

Направление упрощения: единый canonical-to-native media bridge для estimate и compaction вместо дополнительных text-only обходов. Следующий regression gate: successful PNG tool-result → checkpoint → второй sampling с сохранением payload и call identity. Это план, не написанный или выполненный тест.

Scope ограничен PNG workflow continuation, не JSON и не произвольными binary result. Старый A1 касался silent loss в provider serializer; OTM-1 останавливается раньше, на другой границе. Дедупликация ограничена проверенными опубликованными материалами.

Только два Markdown-документа. Production patch отсутствует; project scripts/tests, модели, provider, GUI и runtime не запускались. Нет сырых логов, внутренних путей, пользовательских данных или сборок. Merge публикует исследование, не исправляет runtime. LOC/RSS/latency выигрыш не измерялся.
