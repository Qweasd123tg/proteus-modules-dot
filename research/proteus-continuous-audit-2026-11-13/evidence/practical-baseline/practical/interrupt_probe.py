import json,os,pathlib,signal,subprocess,time
root=pathlib.Path('/workspace/shared/proteus-review-20261112')
cfg=json.loads((root/'practical/config.json').read_text());cfg['module_config']['model']['fake'].update(stream_delay_ms=100)
conf=root/'practical/interrupt.json'; conf.write_text(json.dumps(cfg))

def tree(pid):
 records={}
 for p in pathlib.Path('/proc').glob('[0-9]*/stat'):
  try:
   s=p.read_text(); a=s[s.rfind(')')+2:].split(); records[int(p.parent.name)]=(int(a[1]),a[0],a[19])
  except (OSError,ValueError,IndexError):pass
 descendants={pid}
 while True:
  more={p for p,v in records.items() if v[0] in descendants}
  if more<=descendants:break
  descendants|=more
 return {p:records[p] for p in descendants if p in records}

def alive(p,old):
 try:
  s=pathlib.Path(f'/proc/{p}/stat').read_text();a=s[s.rfind(')')+2:].split();return a[19]==old[2] and a[0]!='Z'
 except OSError:return False

out=root/'evidence/interrupt-output.txt'
with out.open('w') as f:
 p=subprocess.Popen([str(root/'core/target/debug/proteus'),'--config',str(conf),'--cwd',str(root/'practical/workspace'),' '.join(['longword']*300)],stdout=f,stderr=f,start_new_session=True)
 time.sleep(1)
 before=tree(p.pid)
 try:
  os.killpg(p.pid,signal.SIGINT)
 except ProcessLookupError:pass
 p.wait(timeout=5)
 time.sleep(1)
 survivors={pid:v for pid,v in before.items() if alive(pid,v)}
 result={'cli_exit':p.returncode,'before':before,'survivors_after_1s':survivors}
 print(json.dumps(result,indent=2));(root/'evidence/interrupt-result.json').write_text(json.dumps(result,indent=2))
 for pid,v in survivors.items():
  if alive(pid,v):
   try:os.kill(pid,signal.SIGKILL)
   except ProcessLookupError:pass
