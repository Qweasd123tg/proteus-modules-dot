from pathlib import Path
import sys
f, witness = map(Path,sys.argv[1:])
s=f.read_bytes()
header=b'    fn render(&mut self, host: &mut Host, view: &str, surface: Surface, _: Option<&str>) -> Result {\n'
show=b'        host.show(view, root);\n'
assert s.count(header)==1 and s.count(show)==1
s=s.replace(header,header+b'        let _native_witness = m550_wire_alloc::start();\n')
s=s.replace(show,b'        m550_wire_alloc::before_write();\n'+show)
f.write_bytes(s+witness.read_bytes())
