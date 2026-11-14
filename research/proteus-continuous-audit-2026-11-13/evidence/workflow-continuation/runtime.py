"""Local-only native Anthropic transport fixture. No live provider or user data."""
import os,json,pathlib,queue,signal,subprocess,tempfile,threading,time,hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BIN=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
WF=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug/proteus-coding-workflow-module')
REF=CORE/'target/sources/modules/target/debug/proteus-reference-module'

class App:
    def __init__(self,root,config,cwd,session=None):
        self.outputs=[];self.errors=[];self.q=queue.Queue()
        env=os.environ.copy();env.update(HOME=str(root),PROTEUS_HOME=str(root/'home'),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PROTEUS_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
        self.p=subprocess.Popen([str(BIN),'--config',str(config),'--cwd',str(cwd)]+(['--resume-session',str(session)] if session else ['--new-session'])+['server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
        def read():
            for line in self.p.stdout:
                try:value=json.loads(line)
                except Exception:value={'raw':line}
                self.outputs.append(value);self.q.put(value)
        threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:self.errors.extend(self.p.stderr.readlines()),daemon=True).start()
    def send(self,v):self.p.stdin.write(json.dumps(v)+'\n');self.p.stdin.flush()
    def response(self,id):
        end=time.monotonic()+35
        while time.monotonic()<end:
            try:v=self.q.get(timeout=.1)
            except queue.Empty:
                if self.p.poll() is not None:raise RuntimeError(f'exited {self.errors}')
                continue
            if v.get('type')=='response' and v.get('id')==id:return v
        raise RuntimeError(f'no response {id}: {self.errors}')
    def call(self,v):self.send(v);return self.response(v['id'])
    def close(self):
        if self.p.poll() is None:self.send({'type':'shutdown','id':'shutdown'})
        try:self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(self.p.pid,signal.SIGTERM);self.p.wait(timeout=5)
    def save(self,d,prefix):
        (d/(prefix+'events.json')).write_text(json.dumps(self.outputs,indent=2))
        (d/(prefix+'stderr.log')).write_text(''.join(self.errors))

