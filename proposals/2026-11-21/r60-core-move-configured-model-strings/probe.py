"""Compile both exact option functions against prebuilt real Core/Contracts rlibs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = Path("crates/proteus-core/src/app_server/config_summary.rs")
ALLOC = Path("crates/proteus-contracts/src/test_alloc.rs")

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("checkout", type=Path)
p.add_argument("--core-rlib", type=Path, required=True)
p.add_argument("--contracts-rlib", type=Path, required=True)
p.add_argument("--serde-json-rlib", type=Path, required=True)
p.add_argument("--native-dir", type=Path, required=True)
a = p.parse_args()

def extract(source):
    s = source.read_text()
    start = s.index("fn configured_model_options(")
    end = s.index("pub(super) fn configured_reasoning_effort_options(", start)
    return s[start:end].strip()

with tempfile.TemporaryDirectory(prefix="proteus-r60-isolated-") as d:
    root = Path(d)
    tree = root / "source"
    shutil.copytree(a.checkout, tree, ignore=shutil.ignore_patterns(".git","target"))
    source = tree / SOURCE
    old = extract(source).replace("fn configured_model_options(", "fn stock_configured_model_options(", 1)
    subprocess.run(["git","apply","--check",HERE/"source.patch"], cwd=tree, check=True)
    subprocess.run(["git","apply",HERE/"source.patch"], cwd=tree, check=True)
    new = extract(source)
    shutil.copyfile(HERE/"measure.rs",root/"measure.rs")
    shutil.copyfile(tree/ALLOC,root/"r60_alloc.rs")
    main = root/"main.rs"
    main.write_text("""
use proteus_core::core;
use proteus_contracts::domain;
mod r60_alloc;

mod tested_options {
    use crate::core::AppConfig;
""" + old + "\n" + new + '''
    #[path = "../measure.rs"]
    mod cases;
}
''')
    (root/"tested_options").mkdir()
    output = root/"proof"
    deps = a.core_rlib.parent.resolve(strict=True)
    cmd = ["rustc","--edition=2024","--test","-C","debuginfo=0","-C","codegen-units=1",
           "-C","link-arg=-fuse-ld=lld","-L",f"dependency={deps}",
           "-L",f"native={a.native_dir.resolve(strict=True)}","-o",str(output),str(main)]
    for name,path in (("proteus_core",a.core_rlib),("proteus_contracts",a.contracts_rlib),
                      ("serde_json",a.serde_json_rlib)):
        path = path.resolve(strict=True)
        assert path.parent == deps, "all artifacts must come from the same locked Core target"
        cmd.extend(["--extern",f"{name}={path}"])
    subprocess.run(cmd,cwd=root,check=True)
    snap=root/"options.json"
    subprocess.run([output,"--nocapture","--test-threads=1"],cwd=root,check=True,
                   env={**os.environ,"R60_OPTION_SNAPSHOT":str(snap)})
    data=snap.read_bytes()
    assert len(json.loads(data))==154
    print(f"154 byte-identical model-option outputs ({len(data)} serialized bytes), SHA256 {hashlib.sha256(data).hexdigest()}")
