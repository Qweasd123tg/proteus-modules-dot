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
