"""Inject observation immediately before each production Markdown parser API call. Timing builds do not use this."""
import sys
from pathlib import Path
root=Path(sys.argv[1])/'packages/markdown-render/src'
edits={
  'fences.rs':[('    let Ok(root) = markdown::to_mdast(text, &options)', '    eprintln!("MDPASS route {}", text.len());\n    let Ok(root) = markdown::to_mdast(text, &options)')],
  'inlines.rs':[
    ('            let root =\n                markdown::to_mdast(&guarded,', '            eprintln!("MDPASS inline {}", guarded.len());\n            let root =\n                markdown::to_mdast(&guarded,'),
    ('    let root = markdown::to_mdast(source, &markdown::ParseOptions::gfm())', '    eprintln!("MDPASS guard {}", source.len());\n    let root = markdown::to_mdast(source, &markdown::ParseOptions::gfm())'),
    ('    let html = markdown::to_html_with_options(source,', '    eprintln!("MDPASS html {}", source.len());\n    let html = markdown::to_html_with_options(source,')],
}
for p, pairs in edits.items():
 f=root/p;s=f.read_text()
 for old,new in pairs:
  assert s.count(old)==1,(p,old)
  s=s.replace(old,new)
 f.write_text(s)
# Plain-text and cfg(test) calls are not reachable in these Markdown workloads.
p=root/'main.rs';s=p.read_text();line='        if content.language == "text/plain" {'
assert s.count(line)==1
p.write_text(s.replace(line,'        eprintln!("MDFRAME {} {}",content.source_revision.unwrap_or(0),content.source.len());\n'+line))
