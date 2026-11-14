from pathlib import Path
import subprocess, csv, json, hashlib
repo=Path('/workspace/shared/modules-round4'); out=Path(__file__).parent
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
full='''AGENTS.md
Cargo.toml
scripts/test.py
tool/code-mode/README.md
tool/code-mode/Cargo.toml
tool/code-mode/src/engine.rs
tool/code-mode/src/bridge.rs
tool/code-mode/src/bootstrap.js
tool/code-mode/src/config.rs
tool/code-mode/src/lib.rs
tool/code-mode/src/tests.rs
tool/plan-tool/src/lib.rs
hook/tool-selection-hook/src/config.rs
hook/tool-selection-hook/src/config_schema.rs
hook/tool-selection-hook/src/lib.rs
hook/tool-selection-hook/src/tests/schema_token_count.rs
tool/skill-pack/src/lib.rs
tool/skill-pack/src/discovery.rs
tool/rust-lsp/src/lib.rs
tool/rust-lsp/src/client.rs
tool/rust-lsp/src/diagnostics.rs
tool/rust-lsp/src/path.rs
tool/rust-lsp/tests/protocol.rs
tool/rust-lsp/Cargo.toml
context_provider/rg-search/src/lib.rs
context_provider/rg-search/src/tests.rs
context_provider/rg-search/src/tool.rs
context_provider/rg-search/src/provider.rs'''.splitlines()
read={x:None for x in full}; read['README.md']=100
unread=['hook/tool-selection-hook/src/tests.rs','workflow/coding-workflow/src/project_check.rs','workflow/coding-workflow/src/plan_execute_review.rs','workflow/coding-workflow/src/single_loop.rs']
rows=[]
for path in list(read)+unread:
    b=subprocess.check_output(['git','show',f'{sha}:{path}'],cwd=repo); n=len(b.splitlines()); k=n if read.get(path,0) is None else read.get(path,0)
    rows.append(dict(repository='Proteus-modules',revision=sha,path=path,lines=n,reviewed_ranges=f'1-{k}' if k else '',reviewed_lines=k,status='full' if k==n else 'partial' if k else 'not_counted',sha256=hashlib.sha256(b).hexdigest()))
with (out/'coverage.tsv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=rows[0],delimiter='\t');w.writeheader();w.writerows(rows)
(out/'coverage.json').write_text(json.dumps({'sha':sha,'note':'Only this pass; original HEAD lines. The changed protocol test contains audit-only additions excluded from these counts. Truncated workflow output not counted. Not a whole-repository audit.','reviewed_files':len(read),'reviewed_lines':sum(r['reviewed_lines'] for r in rows),'files':rows},ensure_ascii=False,indent=2)+'\n')
print(len(read),sum(r['reviewed_lines'] for r in rows))
