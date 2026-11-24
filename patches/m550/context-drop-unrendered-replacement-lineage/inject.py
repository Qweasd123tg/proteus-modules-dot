from pathlib import Path
import sys
target,witness=map(Path,sys.argv[1:])
s=target.read_bytes()
entry=b'    fn popup(&mut self, host: &mut Host, view: &str) -> Result<Value> {\n'
assert s.count(entry)==1
s=s.replace(entry,entry+b'        let _meter = m550_context_alloc::start();\n')
target.write_bytes(s+witness.read_bytes())
