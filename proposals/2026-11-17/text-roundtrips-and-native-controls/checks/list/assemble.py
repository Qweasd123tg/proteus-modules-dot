"""Generate a standalone display-only rustc input from pinned list.rs; no tool is called."""
from pathlib import Path
import sys
p=Path(__file__).parent
s=(Path(sys.argv[1])/'tool/file-tools/src/list.rs').read_text()
a=s.index("            let name = entry.file_name()")
tail='        let output = lines.join("\\n");'
b=s.index(tail,a)+len(tail)
slice=s[a:b]
assert slice.count("entry.file_name()")==1 and slice.count("entry.file_type()")==1
assert not any(v in slice for v in ['std::fs','read_dir','canonicalize','open(','?;'])
Path(sys.argv[2]).write_text((p/'harness-head.rs').read_text()+slice+'\n'+(p/'harness-tail.rs').read_text())
