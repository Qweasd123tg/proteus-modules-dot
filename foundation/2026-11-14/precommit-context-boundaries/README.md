# Context deadline и precommit history publication

**Исследовательская документация, не runtime patch.** Rust/build/tests/CLI/HTTP/fault-injection не запускались. Абстрактная Python-модель не является независимым экспериментом над Proteus и не включена в пакет.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery [PR87](https://github.com/Qweasd123tg/proteus-modules-dot/pull/87) → [PR88](https://github.com/Qweasd123tg/proteus-modules-dot/pull/88) → [PR89](https://github.com/Qweasd123tg/proteus-modules-dot/pull/89); результирующее дерево `00a3c04a70d7927d1688ea155142025f596a2874`. PR90–92 production не меняют. Более поздний upstream требует повторной проверки.

- [CT-1](CT-1.md): **P3 diagnostic/runtime mismatch**. Doctor называет context timeout zero отключённым, runtime создаёт zero-duration timeout. Ready future может успеть завершиться. Продуктовая семантика ещё не выбрана: исправление может относиться к runtime, диагностике или validation. Unlimited process execution не предполагается.
- [DS-4](DS-4.md): **P2 candidate при committed-only contract history revision**. Полностью записанный, но ещё не committed JSONL prefix может попасть в named cached display до последующего sync failure и успешного rollback. Нужны управляемое interleaving, успешные cache save/rollback и запрос с matching revision до замены cache. Это не canonical corruption, потеря committed history или power-loss finding.

## Что упрощать

CT-1 требует согласованного определения sentinel semantics для runtime и doctor, а не распространения одного helper на поля с разными контрактами. DS-4 требует одной publication boundary, связывающей named history revision с committed prefix, а не вывода commit из EOF/fingerprint. Намеренная поддержка старых действительно committed revisions должна сохраниться. Универсальный framework не предлагается.

Ожидаемый выигрыш качественный: меньше неявных противоречий между слоями. LOC/RSS/latency и процент предотвращённых ошибок не измерены. Regression plans в отчётах предложены, но не реализованы и не исполнены.

## Review и дедупликация

Независимый source review CT-1 подтвердил прямую передачу zero, unconditional timeout и doctor mismatch; ready-future exception и независимый protocol budget сохранены. Независимый DS-4 review подтвердил complete-vs-committed boundary, отсутствие writer gate в read path и намеренное stale matching-revision чтение. DS-4 остаётся условным контрактным кандидатом; source review не доказывает наблюдённый HTTP incident.

CT-1 сверялся с 97 continuous-audit материалами, полным ноябрьским DOCX и PR91/92. Для DS-4 выполнена тематическая сверка 97 ранее выгруженных reports и полного extracted PR84, не повторное построчное чтение 91 страницы. Дубликат в проверенном корпусе не найден; абсолютная новизна не гарантируется. TC-2 из PR91 связан с другим timeout-полем и process budget: общее sentinel семейство не выдаётся за две независимые архитектурные причины. DS-1/2/3 относятся соответственно к cache cap, power-crash dependencies и dropped direct-run lifetime, а не к precommit publication с failed append/rollback.

В пакет входят только три Markdown-файла. Нет исходников, моделей, сырых логов, пользовательских данных или сборок. Merge означает публикацию исследования, а не внедрение исправлений.
