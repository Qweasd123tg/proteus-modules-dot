#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,os,queue,signal,subprocess,threading,time,tomllib,urllib.request,urllib.error,urllib.parse
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--binary',type=Path,default=Path('/workspace/shared/trace-component-deployment-evidence/run-1794580123588475346/home/.proteus/releases/fixture/proteus'));a=p.parse_args();CORE=a.core.resolve();BINARY=a.binary.resolve();PROBE=R/'target/debug/mcp-text-roundtrip-probe'
F=R/f'run-{time.time_ns()}';F.mkdir();results={}
cases={'api_control':['--empty',''],'ordinary_control':['--value','normal'],'empty':['--empty',''],'whitespace':['--value','  alpha  '],'newline':['--value','first\nsecond'],'env_append':['--value','normal']}
for mode,extra in cases.items():
 d=F/mode;d.mkdir();(d/'home').mkdir();(d/'workspace').mkdir();cfg=d/'profile.toml';events=d/'mcp-events.jsonl'
 argv=['-B',str(R/'mcp.py'),'empty' if mode=='api_control' else mode,str(events),*extra]
 txt=f'''[modules]\nworkflow="audit_tool_driver"\npolicy="fixture_allow_all"\n[components.workflow]\ncommand="python3"\nargs=["-B",{json.dumps(str(R/'workflow.py'))},{json.dumps(str(CORE/'examples/modules'))}]\n[components.workflow.exports.workflow.audit_tool_driver]\n[components.policy]\ncommand="python3"\nargs=["-B",{json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]\n[components.policy.exports.policy.fixture_allow_all]\n[[tools.mcp_servers]]\nname="fixture"\nenabled=true\ncommand="python3"\nargs={json.dumps(argv)}\ntimeout_ms=2000\n[tools.mcp_servers.env]\nPREFIX="  synthetic-prefix  "\n'''
 cfg.write_text(txt);(d/'profile-before.toml').write_text(txt)
 env={**os.environ,'HOME':str(d/'home'),'PROTEUS_HOME':str(d/'home/.proteus'),'PROTEUS_CONFIG_HOME':str(d/'config-home')}
 err=(d/'stderr').open('w');proc=subprocess.Popen([str(BINARY),'--config',str(cfg),'--cwd',str(d/'workspace'),'--new-session','server','http','--host','127.0.0.1','--port','0','--token','fixture-only','--ready-stdout'],env=env,text=True,stdout=subprocess.PIPE,stderr=err,start_new_session=True);q=queue.Queue()
 def reader(proc=proc,q=q,d=d):
  for line in proc.stdout:
   with (d/'stdout').open('a') as f:f.write(line)
   try:q.put(json.loads(line))
   except ValueError:pass
  q.put(None)
 reader_thread=threading.Thread(target=reader,daemon=True);reader_thread.start()
 try:
  ready=q.get(timeout=30);assert ready and ready['type']=='http_ready',(ready,proc.wait(timeout=2),(d/'stderr').read_text())
  def api(path,data=None):
   req=urllib.request.Request(ready['origin']+path,headers={'Authorization':'Bearer fixture-only','Content-Type':'application/json'},data=json.dumps(data).encode() if data is not None else None)
   try:
    with urllib.request.urlopen(req,timeout=30) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  status,new=api('/new-session',{'id':'fixture','workspace':str(d/'workspace')});assert status==200 and new.get('ok'),new
  query='?'+urllib.parse.urlencode({'session_dir':new['output']['session_dir']})
  status,snapshot=api('/config/builder'+query);assert status==200;(d/'snapshot.json').write_text(json.dumps(snapshot,indent=2))
  status,before=api('/addons'+query);assert status==200
  assert before['mcp_servers'][0]['tools']==['fixture__echo'] and before['mcp_servers'][0]['error'] is None,before
  starts_before=[json.loads(x) for x in events.read_text().splitlines()];assert starts_before[-1]['argv']==extra
  assert starts_before[-1]['PREFIX']=='  synthetic-prefix  '
  projected=json.loads(subprocess.check_output([str(PROBE),mode,str(d)],text=True));(d/'projection.json').write_text(json.dumps(projected,ensure_ascii=False,indent=2))
  status,saved=api('/config/builder'+query,projected['request']);assert status==200,(status,saved)
  status,addons=api('/addons'+query);assert status==200
  starts_after=[json.loads(x) for x in events.read_text().splitlines()];launched=starts_after[len(starts_before):];assert launched
  runtime=addons['mcp_servers'][0];persisted=tomllib.loads(cfg.read_text())['tools']['mcp_servers'][0]
  assert persisted['args']==projected['after']['args']
  assert persisted['env']==projected['after']['env']
  if mode=='api_control':
   assert launched[-1]['argv']==['--empty','','--tag','new'] and launched[-1]['valid'] and runtime['tools']==['fixture__echo']
  elif mode=='empty':
   assert launched[-1]['argv']==['--empty','--tag','new'] and not launched[-1]['valid']
   assert runtime['tools']==[] and runtime['error'],runtime
  elif mode=='whitespace':assert launched[-1]['argv']==['--value','alpha','--tag','new']
  elif mode=='newline':assert launched[-1]['argv']==['--value','first','second','--tag','new']
  elif mode=='env_append':assert launched[-1]['PREFIX']=='synthetic-prefix'
  else:assert launched[-1]['argv']==['--value','normal','--tag','new'] and runtime['tools']==['fixture__echo']
  assert projected['same_text_is_dirty']==(mode!='ordinary_control')
  results[mode]={'save_http_status':200,'final_validation_errors':projected['final_validation_errors'],'same_text_is_dirty':projected['same_text_is_dirty'],'before_launch':starts_before[-1],'after_launch':launched[-1],'registered_before':before['mcp_servers'][0],'registered_after':runtime,'persisted_matches_sent':True,'unrelated_field_control_preserved':projected['unrelated_edit_preserves_inputs']}
  (d/'addons-after.json').write_text(json.dumps(addons,ensure_ascii=False,indent=2));(d/'saved.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2))
 finally:
  if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=8)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
  reader_thread.join(timeout=2);err.close()
results['binary_sha256']=hashlib.sha256(BINARY.read_bytes()).hexdigest();results['probe_sha256']=hashlib.sha256(PROBE.read_bytes()).hexdigest();(F/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'evidence':str(F),**results},ensure_ascii=False,indent=2))
