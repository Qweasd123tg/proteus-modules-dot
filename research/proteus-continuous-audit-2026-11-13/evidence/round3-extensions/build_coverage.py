import json, subprocess, hashlib, csv
from pathlib import Path
repo=Path('/workspace/shared/extensions-round3')
out=Path('/workspace/shared/extensions-round3-evidence')
old=json.load(open('/workspace/shared/extensions-line-evidence/coverage.json'))
read_now='''packages/analysis/src/details.rs
packages/analysis/src/nodes.rs
packages/analysis/src/summary.rs
packages/analysis/src/tests.rs
packages/analysis/src/text.rs
packages/context/src/view.rs
packages/files/src/document.rs
packages/files/src/icons.rs
packages/files/src/menu.rs
packages/git/src/details.rs
packages/git/src/document.rs
packages/git/src/graph.rs
packages/git/src/history.rs
packages/git/src/list.rs
packages/git/src/model.rs
packages/git/src/panel.rs
packages/git/src/tests.rs
packages/json-render/src/catalog/tests.rs
packages/markdown-render/src/inlines.rs
packages/markdown-render/src/render.rs
packages/mode/src/main.rs
packages/model/src/main.rs
packages/model/src/popup.rs
packages/model/src/tests.rs
packages/plan/src/cache/tests.rs
packages/plan/src/model.rs
packages/plan/src/tests.rs
packages/quota/tests/process.rs
packages/terminal/src/main.rs
packages/usage/src/entry.rs
packages/usage/src/tests.rs
packages/usage/src/view.rs
packages/usage/src/widgets.rs
sdk/src/analytics/tests.rs
sdk/src/host/payload_tests.rs
sdk/src/host/tests.rs'''.splitlines()
extra_reread='''packages/git/src/main.rs
packages/model/src/settings.rs
packages/usage/src/main.rs
packages/json-render/src/catalog/svg_size.rs
packages/json-render/src/catalog.rs'''.splitlines()
new=set(read_now+extra_reread)
rows=[]
for f in old['files']:
 raw=subprocess.check_output(['git','show','HEAD:'+f['path']],cwd=repo)
 digest=hashlib.sha256(raw).hexdigest()
 assert digest==f['sha256_at_HEAD'],f['path']
 assert len(raw.splitlines())==f['original_lines'],f['path']
 now=f['original_lines'] if f['path'] in new else 0
 combined=max(f['reviewed_lines'],now)
 rows.append(dict(path=f['path'],original_lines=f['original_lines'],previous_reviewed_range=f['reviewed_range'] or 'not-read',round3_reviewed_range=f'1-{now}' if now else 'not-read',cumulative_reviewed_range=f'1-{combined}' if combined else 'not-read',newly_reviewed_lines=max(0,now-f['reviewed_lines']),sha256_at_HEAD=digest))
rust=[r for r in rows if r['path'].endswith('.rs')]
summary=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),rust_files_total=len(rust),rust_lines_total=sum(r['original_lines'] for r in rust),rust_newly_reviewed_lines=sum(r['newly_reviewed_lines'] for r in rust),rust_lines_cumulative=sum(int(r['cumulative_reviewed_range'].split('-')[1]) if r['cumulative_reviewed_range']!='not-read' else 0 for r in rust),rust_files_fully_reviewed=sum(r['cumulative_reviewed_range']==f"1-{r['original_lines']}" for r in rust),note='First-party Rust src/tests line-reading inventory only, including blanks/comments/tests. Does not mean behavioral/branch test coverage, absence of bugs, or review of vendor/experiments/manifests/docs. All inherited file hashes checked against this same HEAD.')
with open(out/'coverage.tsv','w') as h:
 w=csv.DictWriter(h,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
(out/'coverage.json').write_text(json.dumps(dict(summary=summary,files=rows),indent=2)+'\n')
print(json.dumps(summary,indent=2))
