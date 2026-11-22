"""Keep exact upstream transcript and projection source, with a tiny carrier."""
from pathlib import Path
import shutil
import sys

source, dest, packet = map(Path, sys.argv[1:])
src = dest / "src"
agent = src / "agents/codex"
agent.mkdir(parents=True)
shutil.copytree(source / "src/transcript", src / "transcript")
for name in ("types.rs", "projection.rs"):
    shutil.copyfile(source / "src/agents/codex" / name, agent / name)
(agent / "mod.rs").write_text("mod types;\npub mod projection;\npub use types::*;\n")
for a, b in (("harness.toml", "Cargo.toml"), ("harness.lock", "Cargo.lock"),
             ("probe.rs", "src/lib.rs"), ("cases.rs", "src/cases.rs"), ("counter.rs", "src/counter.rs")):
    shutil.copyfile(packet / a, dest / b)

ui = source / "src/ui/chat/codex/mod.rs"
shutil.copyfile(ui, src / "product_ui.rs")
raw = ui.read_text()
def exact(start, end):
    assert raw.count(start) == 1
    return start + raw.split(start, 1)[1].split(end, 1)[0]

append = exact("        let append_bound = match &event {\n", "        let change = match event")
arms = exact("            Event::TextDelta { id, turn_id, delta } => {\n", "            Event::TurnStarted")
trim = exact('            let headroom = &mut self.codex.as_mut().expect("Codex binding").live_headroom;\n',
             "            if self\n")
assert arms.count("external_delta(") == 3
assert "external_trim_after_change(" in trim and "8 * 1024 * 1024" in trim
assert raw.count("        self.pause_codex_before_eviction(&event, cx);") == 1
(src / "lifted.rs").write_text(
    "impl Carrier {\n    fn fold(&mut self, event: Event) -> Outcome {\n"
    "        let state = &mut self.state;\n"
    + append + "        let change = match event {\n" + arms
    + "            _ => unreachable!(\"delta-only fixture\"),\n        };\n"
    + "        let trimmed = if !matches!(change, Change::None) {\n"
    + trim + "            trimmed\n        } else { Change::None };\n"
    + "        Outcome { change, trimmed, append_bound, output: state.output }\n"
    + "    }\n}\n")
