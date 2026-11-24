from pathlib import Path
import sys
target,witness=map(Path,sys.argv[1:])
s=target.read_bytes()
entry=b'pub(super) fn render(id: &str, source: &str, languages: &[String]) -> Result<Value> {\n'
expand=b'\n    let html = root["html"].as_str().unwrap();\n'
assert s.count(entry)==1 and s.count(expand)==1
s=s.replace(entry,entry+b'    let _sample = m550_inline_alloc::start();\n')
s=s.replace(expand,expand+b'    m550_inline_alloc::expand();\n')
target.write_bytes(s+witness.read_bytes())
