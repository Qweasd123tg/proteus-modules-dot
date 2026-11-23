# R159 — OpenCode: переиспользовать найденную строку локального каталога

Нужен #465. Единственный патч `composed.patch` для точной основы
#452 → #462 → #465 → #466 → #467 → #468 → #469. Он меняет только
`info` в `model/opencode-provider/runtime.mjs`; для stock без seed
отдельного патча нет.

При `describe` и `resolve` один `.find` проверяет ID, provider и поддержку
canonical chat и сразу оставляет найденную строку. Раньше первый `.some`
проверял её наличие, затем `.find` заново проходил тот же список по ID.
Перед выдачей seed уже валидированы уникальные непустые ID. Модель и
snapshot остаются связанными, provider settings merge и полный модельный
DTO не меняются. Если совпадения нет, сохраняются live lookup и прежние
ошибки отсутствия/provider и неподдерживаемого chat. Нет индекса,
промежуточного tuple/объекта, нового ожидания для no-seed или кеша.

Ветка чтения env (включая свой прежний `.some`) остаётся прежней.
Не меняются seed acquisition/limits, live refresh/retry/fallback, отмена,
явные file/URL overrides, injected loaders, selector/model effort,
quota/stream routing и lazy resolver. Это убирает только повторный
проход внутри `info`, не все проходы целого stream.

Проверены exact apply/reverse 0 fuzz, полный byte readback и Node syntax.
В 7 из 7 VM тестов с точными исходниками runtime и настоящими pinned
raw seed-файлами проверены полные describe/info/resolve DTO, ошибки,
live/failure/override и отмена. SDK normalizer/transport/resolver были
инертными. В тестовой проекции под счётчиками callback для последнего
точного ID: Go 66→33, Zen 228→114 **посещений элемента на один** info-based
lookup после загрузки seed. Это структурные счётчики выбранных фикстур,
не измерение времени или размера полного native SDK. Реальные
OpenCode SDK, network, пользовательские данные и benchmark не запускались.
