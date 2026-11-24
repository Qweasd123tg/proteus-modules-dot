from pathlib import Path
import sys
target,witness=map(Path,sys.argv[1:])
source=target.read_bytes()
entry=b'fn aggregate_patch(patch: String) -> Value {\n'
assert source.count(entry)==1
target.write_bytes(source.replace(entry,entry+b'    let _sample = m550_git_alloc::start(&patch);\n')+witness.read_bytes())
