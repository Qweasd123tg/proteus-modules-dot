import json, subprocess
from pathlib import Path
p=Path('/workspace/shared/extensions-line-evidence')
binary='/workspace/scratch/3ba0fff8d310/protocol-extensions/target/debug/markdown-render'
hello={'type':'hello','protocol':4,'workspace':'/fixture','features':['surfaces.content.v1','widgets.rich_text.v1','widgets.rich_text.inlines.v1','widgets.content.v1','widgets.code_embedded.v1']}
def render(view, revision, source):
 return {'type':'render','context':'scope-audit','surface':'content','view':view,'session_dir':'/session-audit','content':{'language':'text/markdown','source':source,'source_revision':revision,'context':{'languages':['mermaid','latex']}}}
changed='```mermaid\nA-->B\n``` no longer a closing fence\n'
footnote='Read this note[^n].\n\n```rust\nlet x = 1;\n```\n\n[^n]: Important footnote text.\n'
control='Read this note[^n].\n\n[^n]: Important footnote text.\n'
messages=[hello,render('warm',1,'```mermaid\nA-->B\n```\n'),render('warm',2,changed),render('cold',2,changed),render('footnote',1,footnote),render('control',1,control)]
wire=''.join(json.dumps(m,ensure_ascii=False)+'\n' for m in messages)
p.joinpath('wire-input.ndjson').write_text(wire)
r=subprocess.run([binary],input=wire,text=True,capture_output=True,timeout=20)
p.joinpath('wire-output.ndjson').write_text(r.stdout)
p.joinpath('wire-stderr.txt').write_text(r.stderr)
assert r.returncode==0,r
out=[json.loads(line) for line in r.stdout.splitlines()]
assert len(out)==5,out
assert out[1]['root'] != out[2]['root']
assert 'Important footnote text' not in json.dumps(out[3]['root'])
assert 'Important footnote text' in json.dumps(out[4]['root'])
assert 'data-footnote-ref' in json.dumps(out[4]['root'])
print('Production process: 5 outputs; stale warm-fence defect reproduced; missing cross-fence footnote reproduced; same-segment footnote control passes.')
