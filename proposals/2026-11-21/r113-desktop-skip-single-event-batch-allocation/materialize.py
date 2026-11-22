"""Copy exact transport/router/types/projection and lift only the native pump body."""
from pathlib import Path
import hashlib
import shutil
import sys

source, dest, packet = map(Path, sys.argv[1:])
src = dest / "src"
src.mkdir(parents=True)
for name in ("router.rs", "types.rs", "projection.rs"):
    shutil.copyfile(source / "src/agents/codex" / name, src / name)
for a, b in (("harness.toml", "Cargo.toml"), ("harness.lock", "Cargo.lock"),
             ("probe.rs", "src/lib.rs"), ("cases.rs", "src/cases.rs"), ("counter.rs", "src/counter.rs")):
    shutil.copyfile(packet / a, dest / b)
shutil.copytree(source / "crates/codex-client", dest / "crates/codex-client", symlinks=True)
shutil.copyfile(source / "LICENSE-APACHE", dest / "LICENSE-APACHE")

p = source / "src/ui/chat/codex/mod.rs"
original = p.read_text()
start = "        chat._pump = Some(cx.spawn(async move |this, cx| {\n"
end = "        }));\n        chat\n"
assert original.count(start) == original.count(end) == 1
body = original.split(start, 1)[1].split(end, 1)[0]
assert body.count("while let Ok(first)") == body.count("yield_after_batch().await") == 1
assert body.endswith("            .ok();\n")
carrier = ("use super::{Context, Observed, Recorder, Event};\n"
           "pub(super) async fn run(this: &Recorder, cx: &Context, events: &Observed<'_>) {\n"
           + body + "}\n")
(src / "pump.rs").write_text(carrier)
# Keep complete exact sources used to prove the lifted bytes, as build inputs, too.
shutil.copyfile(p, src / "product_pump.rs")
ysrc = source / "src/ui/chat/stream_batch.rs"
shutil.copyfile(ysrc, src / "product_stream_batch.rs")
raw = ysrc.read_text()
start = "pub(in crate::ui) async fn yield_after_batch() {\n"
end = "\n}\n"
assert raw.count(start) == 1
body = raw.split(start, 1)[1].split(end, 1)[0]
assert "std::future::poll_fn" in body and "cx.waker().wake_by_ref()" in body
(src / "scheduler.rs").write_text("pub(super) async fn yield_after_batch() {\n" + body + "\n}\n")
