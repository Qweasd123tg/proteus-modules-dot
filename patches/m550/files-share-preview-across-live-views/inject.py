from pathlib import Path
import sys
target,witness=map(Path,sys.argv[1:])
s=target.read_bytes()
entry=b'    ) -> Result {\n        if surface == Surface::Preview {\n'
assert s.count(entry)==1
s=s.replace(entry,entry.replace(b'        if',b'        let _meter = m550_files_alloc::start(view);\n        if'))
target.write_bytes(s+witness.read_bytes())
