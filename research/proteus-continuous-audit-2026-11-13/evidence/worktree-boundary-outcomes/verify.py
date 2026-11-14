import argparse,json,pathlib
E=pathlib.Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--expected-safe',choices=['exclude','integration','cwd','index-flags']);args=p.parse_args()
count=0
for name in ['pass1','pass2']:
 d=E/name
 v={p.name.removesuffix('-summary.json'):json.loads(p.read_text()) for p in d.glob('*-summary.json')}
 assert set(v)=={'unstaged','staged','committed','cwd-subdir','cwd-shared','exclude-utf8','exclude-legacy','index-assume','index-skip','index-sparse'}
 for mode,x in v.items():
  assert x['response'] is not None,(name,mode,'missing parent completion')
  assert x['task_result']['ok'] is True,(name,mode,x['task_result'])
  assert x['task_result']['metadata']['status']=='completed',(name,mode)
  count+=1
 for mode,status in [('unstaged',' M base.py\n'),('staged','M  base.py\n')]:
  x=v[mode];r=next(r for r in x['records'] if r['name']=='child_written')
  assert r['extra']['status']==status,(mode,r)
  assert x['suggested_branch_merge']['code']==0
  assert x['suggested_branch_merge']['stdout']=='Already up to date.\n'
  assert x['branch_file']==x['root_file_after_merge']=='ROOT = "main application"\n'
  assert x['normal_worktree_remove']['code'] != 0 and x['checkout_exists_after_normal_remove'] is True
  assert x['checkout_file_after_merge']=='RESULT = "new child implementation"\n'
  assert "changes live only on that branch" in x['task_result']['output']
 x=v['committed'];assert x['suggested_branch_merge']['code']==0
 assert x['branch_file']==x['root_file_after_merge']==x['checkout_file_after_merge']=='RESULT = "new child implementation"\n'
 x=v['cwd-subdir'];assert x['files']['child_root']=='RESULT = "new child implementation"\n';assert x['files']['child_service']=='SERVICE = "subpackage"\n'
 assert x['files']['root']=='ROOT = "main application"\n';assert x['files']['service']=='SERVICE = "subpackage"\n'
 x=v['cwd-shared'];assert x['files']['root']=='ROOT = "main application"\n';assert x['files']['service']=='RESULT = "new child implementation"\n'
 x=v['exclude-legacy'];before=bytes.fromhex(x['before']['exclude_hex']);after=bytes.fromhex(x['exclude_hex_after'])
 assert b'\xe9' in before;assert b'local-settings.txt' in before;assert after==b'/.proteus/\n'
 assert x['before']['check_ignore']['code']==0 and x['check_ignore_after']['code']==1
 assert x['status_after']=='?? local-settings.txt\n'
 x=v['exclude-utf8'];assert bytes.fromhex(x['exclude_hex_after'])==bytes.fromhex(x['before']['exclude_hex'])+b'/.proteus/\n'
 assert x['before']['check_ignore']['code']==x['check_ignore_after']['code']==0;assert x['status_after']==''
 for mode,flag in [('index-assume','h base.py'),('index-skip','S base.py')]:
  x=v[mode];r=next(r for r in x['records'] if r['name']=='child_written')
  assert r['extra']['status']==r['extra']['status_all']==''
  assert flag in r['extra']['index_flags'].splitlines()
  assert x['target_exists'] is False and x['checkout_exists'] is False
  assert x['branches'].strip()=='* main'
  assert x['root_base_content']=='ROOT = "main application"\n'
  assert '[worktree: no changes, removed]' in x['task_result']['output']
 x=v['index-sparse'];r=next(r for r in x['records'] if r['name']=='child_written')
 assert r['extra']['before'] is None and 'S service/base.py' in r['extra']['initial_flags'].splitlines()
 assert r['extra']['status']==r['extra']['status_all']==' M service/base.py\n'
 assert 'H service/base.py' in r['extra']['index_flags'].splitlines()
 assert x['target_exists'] is True and x['checkout_exists'] is True
 assert '[task_id:' in x['task_result']['output']
 if args.expected_safe=='exclude':
  x=v['exclude-legacy'];assert bytes.fromhex(x['exclude_hex_after']).startswith(bytes.fromhex(x['before']['exclude_hex'])), 'desired invariant failed: adding a worktree must preserve existing Git exclude bytes/rules'
 elif args.expected_safe=='integration':
  x=v['unstaged'];assert x['root_file_after_merge']==x['checkout_file_after_merge'], 'desired invariant failed: advertised merge target does not contain the completed child result'
 elif args.expected_safe=='index-flags':
  assert v['index-assume']['target_exists'] is True, 'desired invariant failed: modified tracked source with assume-unchanged flag was deleted'
 elif args.expected_safe=='cwd':
  x=v['cwd-subdir'];assert x['files']['child_service']=='RESULT = "new child implementation"\n', 'conditional desired invariant failed: isolation should map cwd-relative paths into the same repo subdirectory'
print(f'Observed evidence verified for {count} real stdio TaskTool scenarios across two fresh-repo repetitions.')
