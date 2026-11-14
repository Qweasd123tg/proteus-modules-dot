#!/usr/bin/env python3
"""Real unchanged Git+SDK -> loopback fault injector -> real Core -> disposable Git repo."""
from pathlib import Path
import argparse,hashlib,http.server,json,os,queue,signal,subprocess,threading,time,urllib.request,urllib.error,urllib.parse
from repro import walk
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'))
p.add_argument('--core-binary',type=Path,default=Path('/workspace/shared/nested-lifetime-evidence/proteus'))
p.add_argument('--git-binary',type=Path,default=R/'target/debug/git');a=p.parse_args()
CORE=a.core.resolve();BINARY=a.core_binary.resolve();GIT=a.git_binary.resolve()
F=R/f'core-run-{time.time_ns()}';F.mkdir()
ALPHA='Alpha change\n\nImportant Alpha explanation.\n\nRefs: ALPHA-123'
BETA='Beta change\n\nImportant Beta explanation.\n\nRefs: BETA-456'
TOKEN='synthetic-loopback-only'
results={}
for scenario in ['healthy-control','failed-details','checkout-after-amend','same-branch-head-change']:
 d=F/scenario;d.mkdir();home=d/'home';home.mkdir();repo=d/'repository';repo.mkdir();(d/'no-hooks').mkdir()
 env={'PATH':os.environ['PATH'],'HOME':str(home),'PROTEUS_HOME':str(home/'.proteus'),'PROTEUS_CONFIG_HOME':str(d/'config'),
      'XDG_DATA_HOME':str(d/'data'),'XDG_CONFIG_HOME':str(d/'config'),'PYTHONDONTWRITEBYTECODE':'1',
      'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost',
      'GIT_AUTHOR_DATE':'2026-11-13T12:00:00Z','GIT_COMMITTER_DATE':'2026-11-13T12:00:00Z'}
 def git(*args):
  r=subprocess.run(['git','-C',str(repo),*args],env=env,capture_output=True,text=True,timeout=15)
  assert r.returncode==0,(args,r.stderr)
  return r.stdout.rstrip('\n')
 git('init','-qb','main');git('config','user.name','Synthetic Fixture');git('config','user.email','fixture@example.invalid')
 git('config','commit.gpgsign','false');git('config','core.hooksPath',str(d/'no-hooks'))
 (repo/'base.txt').write_text('base\n');git('add','.');git('commit','-qm','Base fixture')
 git('switch','-qc','beta');(repo/'beta.txt').write_text('beta\n');git('add','.');git('commit','-qm',BETA);beta=git('rev-parse','HEAD')
 git('switch','-q','main');(repo/'alpha.txt').write_text('alpha\n');git('add','.');git('commit','-qm',ALPHA);alpha=git('rev-parse','HEAD')
 cfg=d/'profile.toml';cfg.write_text(f'''[modules]\nworkflow="audit_tool_driver"\npolicy="fixture_allow_all"\n[components.workflow]\ncommand="python3"\nargs=["-B",{json.dumps(str(R/'workflow.py'))},{json.dumps(str(CORE/'examples/modules'))}]\n[components.workflow.exports.workflow.audit_tool_driver]\n[components.policy]\ncommand="python3"\nargs=["-B",{json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]\n[components.policy.exports.policy.fixture_allow_all]\n''')
 err=(d/'core.stderr').open('w')
 proc=subprocess.Popen([str(BINARY),'--config',str(cfg),'--cwd',str(repo),'--new-session','server','http','--host','127.0.0.1','--port','0','--token',TOKEN,'--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True)
 q=queue.Queue()
 def reader(proc=proc,q=q,d=d):
  for line in proc.stdout:
   with (d/'core.stdout').open('a') as out:out.write(line)
   try:q.put(json.loads(line))
   except ValueError:pass
  q.put(None)
 th=threading.Thread(target=reader,daemon=True);th.start()
 try:
  ready=q.get(timeout=30);assert ready and ready['type']=='http_ready',ready
  def api(path,data=None):
   req=urllib.request.Request(ready['origin']+path,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
   try:
    with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  status,new=api('/new-session',{'id':'fixture','workspace':str(repo)});assert status==200 and new.get('ok'),new
  session=new['output']['session_dir'];requests=[]
  class Proxy(http.server.BaseHTTPRequestHandler):
   def forward(self):
    url=urllib.parse.urlparse(self.path);raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
    body=json.loads(raw) if raw else None
    record={'method':self.command,'path':url.path,'query':urllib.parse.parse_qs(url.query),'body':body}
    if self.command=='GET' and url.path=='/workspace/changes':
     self.server.changes_reads += 1
     if scenario=='same-branch-head-change' and self.server.changes_reads==2:
      (repo/'external-change.txt').write_text('synthetic new commit\n');git('add','external-change.txt');git('commit','-qm',BETA);self.server.external_head=git('rev-parse','HEAD')
    allowed={'GET':{'/workspace/changes','/workspace/branches','/workspace/log','/workspace/commit'},'POST':{'/workspace/commit','/workspace/checkout'}}
    assert url.path in allowed[self.command],record
    if self.command=='GET' and url.path=='/workspace/commit' and self.server.fail_details:
     self.server.fail_details=False;status,answer=503,{'error':'synthetic one-time details failure'};record['injected']=True
    else:status,answer=api(self.path,body)
    record.update({'status':status,'response':answer});requests.append(record)
    b=json.dumps(answer).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
   do_GET=forward;do_POST=forward
   def log_message(self,*args):pass
  with http.server.ThreadingHTTPServer(('127.0.0.1',0),Proxy) as proxy:
   proxy.fail_details=scenario=='failed-details';proxy.changes_reads=0;proxy.external_head=None;threading.Thread(target=proxy.serve_forever,daemon=True).start()
   acts=[('amend',None)]
   if scenario in ['failed-details','same-branch-head-change']:acts+=[('refresh',None)]
   if scenario=='checkout-after-amend':acts+=[('checkout','beta')]
   acts+=[('commit',None)]
   messages=[{'type':'hello','protocol':4,'features':[],'server':{'origin':f'http://127.0.0.1:{proxy.server_port}','token':TOKEN}},
             {'type':'context','context':'window','session_dir':session,'workspace':str(repo)},
             {'type':'render','context':'window','session_dir':session,'surface':'panel','view':'panel'}]
   messages += [{'type':'action','view':'panel','sequence':i,'action':action,'value':value} for i,(action,value) in enumerate(acts,1)]
   run=subprocess.run([str(GIT)],input=''.join(json.dumps(m)+'\n' for m in messages),env=env,capture_output=True,text=True,timeout=30)
   proxy.shutdown()
   assert run.returncode==0 and not run.stderr,(run.returncode,run.stderr)
  output=[json.loads(l) for l in run.stdout.splitlines()]
  trace=[]
  for out in output:
   if out.get('type')=='view' and out.get('view')=='panel':
    nodes=list(walk(out['root']));inp=next(n for n in nodes if n.get('type')=='input' and n.get('id')=='message')
    amend=next(n for n in nodes if n.get('action')=='amend')
    commit=next(n for n in nodes if n.get('action')=='commit' and n.get('type')!='input')
    trace.append({'sequence':out.get('sequence'),'draft':inp['value'],'amend':amend['checked'],'commit_disabled':commit.get('disabled'),
                  'danger':[n for n in nodes if n.get('tone')=='danger']})
  assert not trace[-2]['danger'] and not trace[-2]['commit_disabled'],trace
  commits=[r for r in requests if r['method']=='POST' and r['path']=='/workspace/commit'];assert len(commits)==1 and commits[0]['status']==200,commits
  after=git('log','-1','--format=%B');expected=ALPHA.split('\n')[0] if scenario=='failed-details' else ALPHA
  assert after==expected,(after,expected)
  assert trace[-1]['draft']=='' and not trace[-1]['amend']
  if scenario=='checkout-after-amend':assert git('branch','--show-current')=='beta' and git('show',beta+':beta.txt')=='beta'
  original_sha=proxy.external_head or (beta if scenario=='checkout-after-amend' else alpha)
  original=git('show','-s','--format=%B',original_sha)
  assert original==(BETA if scenario in ['checkout-after-amend','same-branch-head-change'] else ALPHA)
  summary={'final_branch':git('branch','--show-current'),'old_target':original_sha,'old_message':original,'final_head':git('rev-parse','HEAD'),
           'final_message':after,'request':commits[0]['body'],'commit_http_status':commits[0]['status'],
           'warnings_before_commit':trace[-2]['danger'],'old_object_still_readable':True,
           'worktree_clean':git('status','--porcelain')=='','native_gui_run':False,'model_calls':0}
  record={'scenario':scenario,'input':messages,'output':output,'trace':trace,'http':requests,'result':summary}
  (d/'trace.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');results[scenario]=summary
 finally:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=8)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
  th.join(timeout=2);err.close()
results['core_binary_sha256']=hashlib.sha256(BINARY.read_bytes()).hexdigest();results['git_binary_sha256']=hashlib.sha256(GIT.read_bytes()).hexdigest()
(F/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'evidence':str(F),**results},ensure_ascii=False,indent=2))
