"""Assert observations; --expect-fixed checks the desired preservation invariant."""
import json,pathlib,sys
E=pathlib.Path(__file__).resolve().parent
cases={m:json.loads((E/(m+'-summary.json')).read_text()) for m in ('clean-parent-uncommitted','dirty-parent-uncommitted','clean-parent-committed')}
for mode,s in cases.items():
 assert s['response']['ok'],(mode,s['response'])
 markers=[json.loads(l) for l in (E/(mode+'-markers.jsonl')).read_text().splitlines()]
 nested=[r['extra'] for r in markers if r['name']=='task' and r['prompt'].startswith('parent-')]
 assert len(nested)==1 and nested[0]['ok'] and '[task_id:' in nested[0]['output'],(mode,nested)
 assert len([r for r in markers if r['name']=='finish'])==3,mode
assert cases['dirty-parent-uncommitted']['leaf_exists']
assert not any(r['returncode']==0 for r in cases['dirty-parent-uncommitted']['leaf_branch_contents'])
if '--expect-fixed' in sys.argv:
 assert cases['clean-parent-uncommitted']['leaf_exists'], 'parent cleanup deleted nested uncommitted leaf result'
 assert cases['clean-parent-committed']['leaf_exists'], 'parent cleanup deleted retained nested checkout'
else:
 assert not cases['clean-parent-uncommitted']['leaf_exists']
 assert not any(r['returncode']==0 for r in cases['clean-parent-uncommitted']['leaf_branch_contents'])
 assert 'prunable' in cases['clean-parent-uncommitted']['worktrees']
 assert '[worktree: no changes, removed]' in cases['clean-parent-uncommitted']['response']['output']['text']
 assert not cases['clean-parent-committed']['leaf_exists']
 assert any(r['returncode']==0 and 'unique uncommitted leaf result' in r['stdout'] for r in cases['clean-parent-committed']['leaf_branch_contents'])
print('PASS: all three real-peer runs and preservation/control observations verified')
