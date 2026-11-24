from pathlib import Path
import sys
target,witness=map(Path,sys.argv[1:])
s=target.read_bytes()
entry=b'pub fn message_text(message: &Value) -> String {\n'
assert s.count(entry)==1
s=s.replace(entry,entry+b'    let _sample = m550_message_alloc::start();\n')
target.write_bytes(s+witness.read_bytes())
