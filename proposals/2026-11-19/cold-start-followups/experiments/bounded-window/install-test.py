"""Copy the experiment into a disposable Core checkout with the R13 history-only renderer."""
from pathlib import Path
import sys
import shutil

src = Path(__file__).resolve().parent
root = Path(sys.argv[1])
tr = root / "crates/proteus-core/src/app_server/transcript"
assert "let mut history_only" in (tr / "journal/source.rs").read_text(), "apply R13 history-only-render.patch for baseline parity first"
for path in [tr/"plain_pages.rs", tr/"journal/tests/round14.rs"]:
    assert not path.exists(), f"refusing to overwrite {path}"
for file, mod in [(tr.with_suffix(".rs"),"plain_pages"), (tr/"journal/tests.rs","round14")]:
    assert f"mod {mod};" not in file.read_text(), file
shutil.copy2(src/"plain_pages.rs",tr/"plain_pages.rs")
shutil.copy2(src/"round14.rs",tr/"journal/tests/round14.rs")
for file, mod in [(tr.with_suffix(".rs"),"plain_pages"), (tr/"journal/tests.rs","round14")]:
    with file.open("a") as f:
        f.write(f"\n#[cfg(test)]\nmod {mod};\n")
