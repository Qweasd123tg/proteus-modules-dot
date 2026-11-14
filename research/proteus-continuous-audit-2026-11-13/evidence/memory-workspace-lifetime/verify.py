"""Diagnostic assertions, not fixed-behavior regression assertions."""
import json,pathlib,sys
E=pathlib.Path(__file__).resolve().parent
for backend in ('jsonl_memory','sqlite_memory'):
 for mode in ('worktree-default','worktree-absolute','worktree-dirty','shared-default'):
  s=json.loads((E/f'{backend}-{mode}-summary.json').read_text())
  assert s['response']['ok'],s
  p=json.loads(s['response']['output']['text'])
  assert p['task']['ok'],p
  b=s['before_return']['value']
  assert b['exists'] and b['bytes']>0 and b['saved_ok'] and b['recall_ok'],b
  assert len(b['items'])==1,b
  assert p['root_recall']['ok'],p
  if mode=='worktree-default':
   assert not s['after_memory_exists'] and not s['after_child_cwd_exists'],s
   assert '[worktree: no changes, removed]' in p['task']['output'],p
   assert not p['root_recall']['metadata']['items'],p
   if '--expect-fixed' in sys.argv:assert s['after_memory_exists'], 'successful durable memory was deleted by normal task cleanup'
  elif mode=='worktree-absolute':
   assert s['after_memory_exists'] and not s['after_child_cwd_exists'],s
   assert len(p['root_recall']['metadata']['items'])==1,p
  elif mode=='worktree-dirty':
   assert s['after_memory_exists'] and s['after_child_cwd_exists'],s
   assert '!! .proteus/' in s['git_status'],s
   assert not p['root_recall']['metadata']['items'],p
  else:
   assert s['after_memory_exists'] and s['after_child_cwd_exists'],s
   assert len(p['root_recall']['metadata']['items'])==1,p
  print(backend, mode, 'PASS')
print('PASS: 8 real process runs; 2 durable-store deletion reproductions, 6 controls')
