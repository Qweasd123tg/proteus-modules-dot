import argparse,json,pathlib
E=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--expected-safe',choices=['env','hook']);args=p.parse_args()
tasks=children=0
for passname in ['pass1','pass2']:
 D={f.name[:-len('-summary.json')]:json.loads(f.read_text()) for f in (E/passname).glob('*-summary.json')}
 assert len(D)==11
 for mode,d in D.items():
  records=d['snapshots'][-1]['records'];results=[r for r in records if r['name']=='task_result'];tasks+=len(results)
  children+=len([r for r in records if r['name'] in ['child_written','mcp_result','child_noop']])
  assert all(s['response']['ok'] for s in d['snapshots'])
  if mode.startswith('env-'):
   s=d['snapshots'][-1];w=next(r for r in records if r['name']=='child_written');result=results[0]['extra'];requested=mode.startswith('env-clear') or mode=='env-same'
   assert w['extra']['before']==('SOURCE = "requested repository"\n' if requested else 'SOURCE = "other repository"\n')
   assert s['requested_file']=='SOURCE = "requested repository"\n';assert s['other_file']=='SOURCE = "other repository"\n'
   assert result['ok'];assert all(x['exists'] for x in s['child_paths'].values())
   assert s['requested_branch_tip']['code']==(0 if requested else 128)
   assert s['other_branch_tip']['code']==(128 if requested else 0)
   assert ('cleanup failed' in result['output'])==(mode in ['env-same','env-other'])
   assert ('[task_id:' in result['output'])==(mode not in ['env-same','env-other'])
   if mode.endswith('-commit'):
    owner='requested' if requested else 'other'
    assert s[owner+'_head']['stdout']!=s[owner+'_branch_tip']['stdout']
    assert s[owner+'_branch_file']['stdout']=='RESULT = "synthetic child edit"\n'
   if args.expected_safe=='env':
    assert w['extra']['before']=='SOURCE = "requested repository"\n',mode+' read source from unrelated repository'
    assert s['requested_branch_tip']['code']==0 and s['other_branch_tip']['code']==128,mode+' created branch in unrelated repository'
  elif mode=='hook':
   assert [x['extra']['ok'] for x in results]==[False,False,True]
   assert 'failed to add git worktree' in results[0]['extra']['error']
   assert 'worktree path already exists' in results[1]['extra']['error']
   assert len([r for r in records if r['name']=='child_noop'])==1
   assert results[0]['session']!=results[1]['session']
   assert all('refs/heads/proteus/coder-call_0' in s['requested_worktrees']['stdout'] for s in d['snapshots'])
   assert all(s['requested_branch_tip']['code']==0 for s in d['snapshots'])
   assert all(s['requested_status']['stdout']=='' for s in d['snapshots'])
   if args.expected_safe=='hook':assert 'refs/heads/proteus/coder-call_0' not in d['snapshots'][0]['requested_worktrees']['stdout'],'failed preparation left a live checkout'
  else:
   mcp=[r for r in records if r['name']=='mcp_result'];assert len(mcp)==2
   assert all(r['extra']['ok'] for r in mcp)
   assert all(r['extra']['metadata']['structured_content']['content']=='SOURCE = "requested repository"\n' for r in mcp)
   pids=[r['extra']['metadata']['structured_content']['pid'] for r in mcp]
   assert pids[0]!=pids[1], 'fresh-task session rotation should restart MCP'
   if mode in ['reuse-same','reuse-shared']:assert mcp[0]['peer_pid']==mcp[1]['peer_pid']
   if mode=='reuse-same':assert mcp[0]['cwd']==mcp[1]['cwd']
   if mode=='reuse-noidle':assert mcp[0]['peer_pid']!=mcp[1]['peer_pid']
   if mode=='reuse-unique':assert mcp[0]['cwd']!=mcp[1]['cwd']
 print(passname+': 11 scenarios verified')
print(f'{tasks} real task facade calls; {children} child workflow invocations; all baseline assertions passed.')
