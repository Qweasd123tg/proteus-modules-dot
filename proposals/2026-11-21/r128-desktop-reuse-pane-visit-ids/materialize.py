"""Copy exact tabs source as the real test dependency; no product lifts/stubs."""
from pathlib import Path
import shutil
import sys

source,dst,packet = map(Path,sys.argv[1:])
(dst/"src").mkdir(parents=True)
shutil.copytree(source/"crates/tabs",dst/"crates/tabs",symlinks=True)
shutil.copyfile(source/"LICENSE-GPL",dst/"LICENSE-GPL")
for old,new in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),
                ("probe.rs","src/lib.rs"),("counter.rs","src/counter.rs")):
    shutil.copyfile(packet/old,dst/new)
