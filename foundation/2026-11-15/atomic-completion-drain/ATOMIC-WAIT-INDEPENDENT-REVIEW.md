# Независимый exact review: atomic completion drain

## Verdict

Source-level blocker не найден. Candidate — оправданное небольшое invariant simplification: результат существующего atomic drain одновременно определяет наличие и владение updates. Он удаляет check-then-act окно без нового lock/helper/framework. Это не новый high-severity incident, не подтверждённый обычный serial workflow failure и не исправление PR118 completion-budget delivery.

## Reachability и semantics

Старые has_completions и drain_completions каждый отдельно берут mutex. Между ними нет await, поэтому две futures на одном executor thread не обязаны и обычно не могут переключиться в этом месте. Для witness нужен действительно конкурентный thread consumer: A получил true, B удалил queue item, A получил empty drain и преждевременно вернул timed_out=true. Shared synchronized CollaborationControl и существующий комментарий competing waiters согласуются с этим contract, но source slice не доказывает частоту/штатный путь такого concurrency в production.

Новый initial path делает drain и смотрит owned Vec. Непустой batch возвращается; zero timeout возвращает empty сразу; nonzero timeout при empty переходит к собственному wait deadline. Loop аналогично возвращает только реально полученный непустой Vec. Drain implementation, mutex, лимит batch=8, snapshots/history handling и queue consumption не меняются. Lock errors продолжают распространяться через `?`; отсутствующая session по-прежнему даёт empty drain.

Lost-wake protection сохранена: notified создаётся/pin/enable до loop drain. Completion между initial drain и loop registration остаётся в queue и находится повторным drain. Completion после enable либо находится drain, либо будит notified. Если конкурент потребил broadcast update, loop снова регистрируется и ждёт до своего deadline; новый код не превращает одно уведомление в фиктивно принадлежащий waiter batch. Timeout и zero-poll semantics остаются прежними; true race на границе deadline не превращается в гарантию справедливости между waiters.

Consumption по-прежнему происходит до serialization/Core caps/AfterTool. Никакого delivery ACK/replay/recovery удалённых reports не добавлено. PR118 HOLD остаётся открытым. Независимого measured runtime/performance claim нет.

## Compile-shape и proposed test

Explicit `Ok::<_, anyhow::Error>(completed)` согласует async block error type с drain `?` и timeout unwrap_or_else. Shadow completed переносит owned Vec без borrow state через await. Удалённый helper использовался в двух изменённых branches рассматриваемого source; новых API/dependencies нет.

Child tests/wait.rs имеет доступ через super::* к TestHost/context/call/output и private collaboration types. futures-util и tokio macros/runtime/sync/time уже в Cargo.toml. TestHost::session_id, reserve/attach/complete fixture согласованы; ожидаемые paths /root/first и /root/second соответствуют существующему reserve naming. Borrowed call/context lifetimes охватывают вручную pinned futures; временный zero-timeout call живёт до завершения await statement.

Предложенный test вручную poll-ит две futures, отдаёт broadcast update первому и требует Pending у второго до следующего update. Он проверяет полезный competing-notification contract, **но не заставляет старую реализацию переключиться между двумя CPU lock operations и может пройти baseline**. Это не детерминированный regression witness исходного race. Test не выполнялся; Rust/compiler/runtime не запускались. No test PASS claim.

## Evidence

Baseline Core bcbda4435534a296c707a1daa250813d692f68e1. Coordinator catalog 10 sources/text verification. Reviewer прочитал exact diff, existing atomic drain/notify/spec/test helpers и пересчитал:

- patch: 512d41de07d99ed11d6579f5fefcb751a7b5f61a013c5273f60745d6b257df86
- collaboration/mod.rs: 1867bc56e822f16a00853f90676182685c237c633c00edfd9e324f17a704c048
- control.rs: 76a63947c9d44a75db0d61742279fb50950a7a9c436de8278ee021527f4232f9
- tests.rs: 3953207521630e5d3999486fb9e8dab6ed50f729ccc1d2d421107f49c0ddacc8
- tests/wait.rs: d59697e53a6a7ab19a0c5c1c17201c95b1bfa28bf494c2d9653a3d87ca92c365

Production, refs и публикации не менялись. Project scripts/tests/compiler/runtime/install не запускались. Принятие как небольшой correctness cleanup не требует выдавать source interleaving за observed production incident.
