#!/usr/bin/env python3
# Synthetic local peer only: no model, account, existing sessions or shell tools.
import http.server,json,os,sys,threading,time,urllib.parse
from pathlib import Path
cwd=Path.cwd(); token=sys.argv[sys.argv.index('--token')+1]
counter=cwd/'launches'; generation=int(counter.read_text())+1 if counter.exists() else 1;counter.write_text(str(generation))
def record(method,path,session_dir=None):
 with (cwd/'requests.jsonl').open('a') as f: f.write(json.dumps({'generation':generation,'method':method,'path':path,'session_dir':session_dir})+'\n')
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  record('GET',self.path); path=urllib.parse.urlsplit(self.path).path
  if path=='/events':
   self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
   try:
    while True:self.wfile.write(b': heartbeat\n\n');self.wfile.flush();time.sleep(.05)
   except (BrokenPipeError,ConnectionResetError):pass
  elif path=='/sessions':self.reply([])
  else:self.send_error(404)
 def reply(self,obj):
  data=json.dumps(obj).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
  record('POST',self.path,body.get('session_dir'))
  if self.path=='/fixture/exit': os._exit(17)
  if self.path=='/resume':output={'session_dir':body['session_dir'],'workspace_path':str(cwd),'activity':{'status':'idle','running_runs':0,'running_run_ids':[],'pending_approvals':0,'pending_user_inputs':0}}
  elif self.path=='/send-async':output={'accepted':True}
  else: self.send_error(404);return
  self.reply({'type':'response','id':body.get('id'),'ok':True,'output':output,'error':None})
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
print(json.dumps({'type':'http_ready','origin':'http://127.0.0.1:'+str(server.server_port)}),flush=True)
server.serve_forever()
