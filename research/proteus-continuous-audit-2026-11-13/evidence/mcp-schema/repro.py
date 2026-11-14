#!/usr/bin/env python3
"""Real Core HTTP and cold launch; all state lives beneath this evidence folder."""
from pathlib import Path
import argparse,json,os,subprocess,time,urllib.request,urllib.error,urllib.parse,queue,threading,signal,hashlib
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--binary',type=Path,default=Path('/workspace/shared/trace-component-deployment-evidence/run-1794580123588475346/home/.proteus/releases/fixture/proteus'));a=p.parse_args();CORE=a.core.resolve();BINARY=a.binary.resolve()
F=R/f'run-{time.time_ns()}';F.mkdir()
def server_config(name,mode,enabled=True):return {'name':name,'enabled':enabled,'command':'python3','args':['-B',str(R/'mcp.py'),mode],'timeout_ms':2000}
def launch(label,mode=None,enabled=True):
 d=F/label;d.mkdir();(d/'home').mkdir();(d/'workspace').mkdir();cfg=d/'profile.toml'
 txt=f'''[modules]\nworkflow = "audit_tool_driver"\npolicy = "fixture_allow_all"\n[components.workflow]\ncommand = "python3"\nargs = ["-B", {json.dumps(str(R/'workflow.py'))}, {json.dumps(str(CORE/'examples/modules'))}]\n[components.workflow.exports.workflow.audit_tool_driver]\n[components.policy]\ncommand = "python3"\nargs = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]\n[components.policy.exports.policy.fixture_allow_all]\n'''
 for name,m,en in [('good','ok',True)]+([('bad',mode,enabled)] if mode else []):
  txt+='\n[[tools.mcp_servers]]\n'+f'name={json.dumps(name)}\nenabled={str(en).lower()}\ncommand="python3"\nargs=["-B",{json.dumps(str(R/"mcp.py"))},{json.dumps(m)}]\ntimeout_ms=2000\n'
 cfg.write_text(txt);env={**os.environ,'HOME':str(d/'home'),'PROTEUS_HOME':str(d/'home/.proteus'),'PROTEUS_CONFIG_HOME':str(d/'config-home')}
 err=(d/'stderr').open('w');proc=subprocess.Popen([str(BINARY),'--config',str(cfg),'--cwd',str(d/'workspace'),'--new-session','server','http','--host','127.0.0.1','--port','0','--token','fixture-only','--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True)
 q=queue.Queue()
 def reader():
  for line in proc.stdout:
   with (d/'stdout').open('a') as f:f.write(line)
   try:q.put(json.loads(line))
   except ValueError:pass
  q.put(None)
 threading.Thread(target=reader,daemon=True).start();ready=q.get(timeout=30)
 if ready is None:proc.wait(timeout=5);err.close();return None,{'ready':False,'exit_code':proc.returncode,'stderr':(d/'stderr').read_text()}
 assert ready['type']=='http_ready',ready
 def api(path,data=None):
  req=urllib.request.Request(ready['origin']+path,headers={'Authorization':'Bearer fixture-only','Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
  try:
   with urllib.request.urlopen(req,timeout=30) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 status,new=api('/new-session',{'id':'fixture','workspace':str(d/'workspace')});assert status==200 and new.get('ok'),new
 query='?'+urllib.parse.urlencode({'session_dir':new['output']['session_dir']})
 status,snapshot=api('/addons'+query);assert status==200
 def stop():
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=8)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
  err.close()
 return (api,query,cfg,stop),{'ready':True,'snapshot':snapshot}
results={}
for mode in ['ok','bad_initialize','bad_wire','bad_schema']:
 handle,result=launch(mode,mode);results[mode]=result
 if handle:handle[-1]()
# A disabled malformed-schema server still must not launch/discover.
handle,result=launch('disabled_schema','bad_schema',False);results['disabled_schema']=result;assert handle;handle[-1]()
handle,result=launch('save');assert handle;api,q,cfg,stop=handle
try:
 before=cfg.read_bytes();base=result['snapshot']['settings']
 for mode in ['bad_wire','bad_schema']:
  payload=json.loads(json.dumps(base));payload['mcp_servers'].append(server_config('bad',mode));status,body=api('/addons'+q,payload)
  results['save_'+mode]={'status':status,'body':body,'profile_unchanged':cfg.read_bytes()==before}
  if status==200:
   status,body=api('/addons'+q,base);assert status==200;before=cfg.read_bytes()
finally:stop()
# Diagnostic assertions describe CURRENT observed bug, not fixed behavior.
for mode in ['ok','bad_initialize','bad_wire','disabled_schema']:
 assert results[mode]['ready'],(mode,results[mode])
 good=next(x for x in results[mode]['snapshot']['mcp_servers'] if x['name']=='good');assert good['tools']==['good__echo'] and good['error'] is None
for mode in ['bad_initialize','bad_wire']:
 bad=next(x for x in results[mode]['snapshot']['mcp_servers'] if x['name']=='bad');assert bad['error'] and bad['tools']==[]
assert not results['bad_schema']['ready'] and results['bad_schema']['exit_code']!=0
assert 'invalid JSON Schema' in results['bad_schema']['stderr'] or 'invalid-type' in results['bad_schema']['stderr']
assert results['save_bad_wire']['status']==200
assert results['save_bad_schema']['status']==400 and results['save_bad_schema']['profile_unchanged']
results['binary_sha256']=hashlib.sha256(BINARY.read_bytes()).hexdigest();results['core_head']=subprocess.check_output(['git','-C',str(CORE),'rev-parse','HEAD'],text=True).strip();(F/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'evidence':str(F),'core_head':results['core_head'],'binary_sha256':results['binary_sha256'],'launches':{k:{'ready':v['ready'],'error':v.get('stderr')} for k,v in results.items() if isinstance(v,dict) and 'ready' in v},'saves':{k:v['status'] for k,v in results.items() if k.startswith('save_')}},ensure_ascii=False,indent=2))
