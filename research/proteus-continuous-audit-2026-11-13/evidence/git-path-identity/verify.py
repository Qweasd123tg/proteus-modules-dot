import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--expected-safe',action='store_true');args=p.parse_args();E=pathlib.Path(__file__).resolve().parent
calls=children=0
for passname in ['pass1','pass2']:
 for file in sorted((E/passname).glob('*-summary.json')):
  d=json.loads(file.read_text());s=d['snapshots'][0];mode=d['mode'];records=s['records'];calls+=1
  r=next(x for x in records if x['name']=='task_result');w=[x for x in records if x['name']=='child_written'];children+=len(w)
  assert d['git_environment']=={},(mode,d['git_environment'])
  assert r['cwd']==d['requested'],mode
  assert s['requested_head']['code']==s['other_head']['code']==0,mode
  assert s['requested_file']=='SOURCE = "requested repository"\n'
  assert s['other_file']=='SOURCE = "other repository"\n'
  assert s['requested_status']['stdout']==s['other_status']['stdout']=='',mode
  if mode=='env-space-alone-commit':
   assert not r['extra']['ok'] and not w
   assert 'No such file or directory' in r['extra']['error']
   assert s['requested_branch_tip']['code']==s['other_branch_tip']['code']==128
   if args.expected_safe:assert r['extra']['ok'], 'valid whitespace-path repo was rejected'
   continue
  assert r['extra']['ok'] and r['extra']['metadata']['status']=='completed'
  assert len(w)==1 and '[task_id:' in r['extra']['output']
  correct=mode=='env-clear-commit';owner='requested' if correct else 'other';other='other' if correct else 'requested'
  assert w[0]['extra']['before']=='SOURCE = "'+('requested' if correct else 'other')+' repository"\n',mode
  assert s[owner+'_branch_tip']['code']==0 and s[other+'_branch_tip']['code']==128,mode
  assert s[owner+'_branch_file']['stdout']=='RESULT = "synthetic child edit"\n',mode
  assert s[owner+'_branch_tip']['stdout']!=s[owner+'_head']['stdout'],mode
  assert pathlib.Path(w[0]['cwd']).is_relative_to(pathlib.Path(d[owner])),mode
  if args.expected_safe:
   assert pathlib.Path(w[0]['cwd']).is_relative_to(pathlib.Path(d['requested'])),mode+' redirected the checkout to a sibling'
   assert w[0]['extra']['before']=='SOURCE = "requested repository"\n',mode
 print(passname+': six scenarios verified')
print(f'{calls} real TaskTool invocations; {children} child workflows; observed assertions passed')
