from pathlib import Path
import subprocess,hashlib,json
repo=Path('/workspace/shared/extensions-line-audit'); out=Path('/workspace/shared/extensions-line-evidence')
def git(*a): return subprocess.check_output(['git',*a],cwd=repo)
full='''sdk/src/lib.rs sdk/src/host.rs sdk/src/host/documents.rs sdk/src/host/instances.rs sdk/src/host/scopes.rs sdk/src/host/inbox.rs sdk/src/preferences.rs sdk/src/conversation.rs sdk/src/analytics.rs sdk/src/clock.rs sdk/src/format.rs sdk/src/value.rs sdk/src/ui.rs
packages/files/src/main.rs packages/files/src/operations.rs packages/files/src/paths.rs packages/files/src/tree.rs packages/files/src/git.rs packages/files/src/tree_tests.rs
packages/git/src/main.rs packages/git/src/cache.rs
packages/json-render/src/catalog.rs packages/json-render/src/catalog/svg_size.rs packages/json-render/src/main.rs
packages/markdown-render/src/main.rs packages/markdown-render/src/fences.rs packages/markdown-render/src/references.rs packages/markdown-render/tests/process.rs
packages/mermaid-render/src/main.rs packages/mermaid-render/src/worker.rs packages/mermaid-render/src/cache.rs packages/mermaid-render/tests/wire.rs
packages/plan/src/main.rs packages/plan/src/cache.rs packages/plan/src/settings.rs packages/model/src/settings.rs
packages/quota/src/main.rs packages/quota/src/describe.rs packages/usage/src/main.rs packages/usage/src/report.rs
packages/context/src/main.rs packages/context/src/window.rs packages/analysis/src/main.rs packages/analysis/src/facts.rs
package.py packages/mermaid-render/worker.mjs packages/mermaid-render/svg-theme.mjs packages/mermaid-render/update-vendor.py'''.split()
# Conservative ranges. Some tests beyond these ranges were read, but not counted.
partial={'packages/files/src/document.rs':112,'packages/git/src/document.rs':112,'packages/markdown-render/src/render.rs':225,'packages/markdown-render/src/inlines.rs':270}
paths=git('ls-files').decode().splitlines()
rows=[]
for path in paths:
 if not (path.endswith('.rs') and (path.startswith('sdk/src/') or path.startswith('packages/'))) and path not in full: continue
 data=git('show','HEAD:'+path); lines=len(data.splitlines()); read=lines if path in full else min(lines,partial.get(path,0))
 rows.append({'path':path,'original_lines':lines,'reviewed_range':f'1-{read}' if read else None,'reviewed_lines':read,'sha256_at_HEAD':hashlib.sha256(data).hexdigest()})
rs=[r for r in rows if r['path'].endswith('.rs')]
summary={'commit':git('rev-parse','HEAD').decode().strip(),'rust_source_and_test_files_total':len(rs),'rust_lines_total':sum(r['original_lines'] for r in rs),'rust_files_at_least_partially_read':sum(r['reviewed_lines']>0 for r in rs),'rust_lines_reviewed_conservative':sum(r['reviewed_lines'] for r in rs),'note':'Counted source lines include blanks/comments/tests. This is reading coverage, not an assurance that every behavior was tested. Untallied docs and partially read test ranges are excluded. Vendored Pele and experiments were not line-by-line audited.'}
out.joinpath('coverage.json').write_text(json.dumps({'summary':summary,'files':rows},indent=2))
out.joinpath('coverage.tsv').write_text('path\toriginal_lines\treviewed_range\tsha256_at_HEAD\n'+''.join(f"{r['path']}\t{r['original_lines']}\t{r['reviewed_range'] or 'not-read'}\t{r['sha256_at_HEAD']}\n" for r in rows))
print(json.dumps(summary,indent=2))
