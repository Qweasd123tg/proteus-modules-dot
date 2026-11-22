from pathlib import Path
import shutil, sys

source, dest, packet = map(Path, sys.argv[1:])
src = dest / "src"
src.mkdir(parents=True)
for name in ("router.rs", "types.rs", "projection.rs"):
    shutil.copyfile(source/"src/agents/codex"/name, src/name)
for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),("probe.rs","src/lib.rs"),
            ("cases.rs","src/cases.rs"),("counter.rs","src/counter.rs")):
    shutil.copyfile(packet/a, dest/b)
shutil.copytree(source/"crates/codex-client", dest/"crates/codex-client",symlinks=True)
shutil.copyfile(source/"LICENSE-APACHE", dest/"LICENSE-APACHE")
