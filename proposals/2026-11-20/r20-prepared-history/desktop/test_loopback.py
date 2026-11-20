"""Positive and negative controls for pinned, unmodified Rust HTTP API, not a backend benchmark."""
import http.server, json, os, subprocess, threading, time, urllib.parse
from pathlib import Path
here=Path(__file__).resolve().parent
reqs=[]; lock=threading.Lock()
page={"revision":"r20","start":0,"total":0,"messages":[],"base":None}
raw=json.dumps(page).encode()
class Test(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  u=urllib.parse.urlsplit(self.path); q=urllib.parse.parse_qs(u.query)
  with lock: reqs.append(dict(route=u.path,query=q,bearer_ok=self.headers.get('Authorization')=='Bearer synthetic-r20'))
  d=q['session_dir'][0]
  if d=='/delay':
   time.sleep(34)
   return
  slow=d=='/slow-drip'
  body=b' '*100+raw if slow else raw
  self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers()
  try:
   if slow:
    for b in body:
     self.wfile.write(bytes([b]));self.wfile.flush();time.sleep(.46)
   else:self.wfile.write(body)
  except (BrokenPipeError, ConnectionResetError):pass
 def log_message(self,*a):pass
def main():
 s=http.server.ThreadingHTTPServer(('127.0.0.1',0),Test)
 with s:
  thread=threading.Thread(target=s.serve_forever,daemon=True);thread.start()
  proc=subprocess.Popen([here/'client',f'http://127.0.0.1:{s.server_port}','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=dict(os.environ,PROTEUS_BENCH_TOKEN='synthetic-r20'),text=True)
  try:
   assert json.loads(proc.stdout.readline())=={'ready':True}
   payload=[dict(id='tail',dir='/stored/session + #1'),dict(id='older',dir='/stored/session + #1',before=50,revision='r20/prev?'),dict(id='stalled_headers',dir='/delay'),dict(id='slow_drip_body',dir='/slow-drip')]
   results,_=proc.communicate(''.join(json.dumps(q)+'\n' for q in payload),timeout=45)
   assert proc.returncode==0
   r={v['id']:v for l in results.splitlines() if (v:=json.loads(l))}
   assert set(r)=={q['id'] for q in payload}
   assert all(i['route']=='/history/page' and i['bearer_ok'] for i in reqs)
   assert sorted(json.dumps(i['query'],sort_keys=True) for i in reqs)==sorted(json.dumps({k:[str(v)] for k,v in {'session_dir':q['dir'],**{k:q[k] for k in ('before','revision') if k in q}}.items()},sort_keys=True) for q in payload)
   for id in ('tail','older'): assert r[id]['ok'] and r[id]['page']==page
   for id in ('stalled_headers','slow_drip_body'):
    assert not r[id]['ok'] and 'timeout' in r[id]['error'].lower() and 29500<=r[id]['api_ms']<33500, r[id]
   report=dict(control='loopback mocked HTTP /history/page, not Core or GUI',passed=True,source=json.loads((here/'build-identity.json').read_text())['desktop'],results=r,requests=reqs)
   (here/'loopback.json').write_text(json.dumps(report,indent=2)+'\n')
   print({k:(v['ok'],round(v['api_ms'],1),v.get('error')) for k,v in r.items()})
  finally:
   if proc.poll() is None: proc.kill(); proc.wait()
   s.shutdown()
if __name__=='__main__': main()
