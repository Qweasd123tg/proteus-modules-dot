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

def run(workflow,cancel,repeat):
    name=workflow.split('.')[1]+('-cancel' if cancel else '-control')+f'-{repeat}'
    d=E/('native-'+name);d.mkdir(exist_ok=True)
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-workflow-cancel-'));cwd=root/'workspace';cwd.mkdir()
    records=[]
    class HTTP(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls=[];results=[]
            for m in body['messages']:
                for block in m['content']:
                    if block['type']=='tool_use':calls.append(block['id'])
                    if block['type']=='tool_result':results.append(block['tool_use_id'])
            missing=[x for x in calls if x not in results]
            ordinal=len(records)+1
            records.append({'ordinal':ordinal,'body':body,'missing_results':missing})
            if missing:
                status=400;response={'type':'error','error':{'type':'invalid_request_error','message':'LOCAL FIXTURE: tool_use lacks matching tool_result: '+','.join(missing)}}
            else:
                status=200;tool=ordinal==1
                response={'id':f'fixture-{ordinal}','type':'message','role':'assistant','model':'claude-sonnet-4-20250514','content':[{'type':'tool_use','id':'probe-1','name':'probe','input':{}}] if tool else [{'type':'text','text':f'ANSWER-{ordinal}'}],'stop_reason':'tool_use' if tool else 'end_turn','usage':{'input_tokens':50,'output_tokens':5}}
            raw=json.dumps(response).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    http=ThreadingHTTPServer(('127.0.0.1',0),HTTP);threading.Thread(target=http.serve_forever,daemon=True).start()
    config={'active_provider':'fixture','providers':{'fixture':{'provider':'anthropic','model':'claude-sonnet-4-20250514','stream':False}},'module_config':{'model':{'anthropic':{'implementation':'anthropic','base_url':f'http://127.0.0.1:{http.server_address[1]}','api_key':'fixture-not-a-secret','stream':False}}},'modules':{'workflow':workflow,'context':'simple','policy':'allow_all'},'tools':{'enabled':['probe']},'agent_control':{'surface':'none','max_depth':0},'runtime':{'workflow_timeout_ms':30000},'components':{
      'workflow':{'command':str(WF),'exports':{'workflow':{workflow:{}}}},
      'reference':{'command':str(REF),'exports':{'context':{'simple':{}},'policy':{'allow_all':{}},'model':{'anthropic':{}}}},
      'probe':{'command':'python3','args':['-B',str(E/'probe.py'),str(root)],'exports':{'tool':{'probe':{}}}}}}
    configpath=root/'profile.json';configpath.write_text(json.dumps(config));(d/'profile.json').write_text(json.dumps(config,indent=2))
    app=App(root,configpath,cwd);summary={'name':name,'workflow':workflow,'cancel':cancel,'fixture_root':str(root)}
    try:
        app.send({'type':'send','id':'first','text':'Synthetic read-only test: call probe and answer.'})
        end=time.monotonic()+20
        while not (root/'tool-started').exists():
            if time.monotonic()>end or app.p.poll() is not None:raise RuntimeError(f'tool not started {app.errors} {app.outputs[-4:]}')
            time.sleep(.01)
        if cancel:summary['cancel_reply']=app.call({'type':'cancel','id':'cancel','target_id':'first'})
        else:(root/'tool-release').write_text('go')
        summary['first']=app.response('first')
        for i in range(2):summary['warm'+str(i)]=app.call({'type':'send','id':'warm'+str(i),'text':'Continue answering.'})
    finally:
        app.close();app.save(d,'warm-')
    journal=list(root.rglob('journal.jsonl'));assert len(journal)==1
    (d/'warm-journal.jsonl').write_bytes(journal[0].read_bytes())
    app=App(root,configpath,cwd,journal[0].parent)
    try:
        summary['cold']=app.call({'type':'send','id':'cold','text':'Continue after reopening.'})
        summary['clear']=app.call({'type':'clear_history','id':'clear'})
        summary['cleared']=app.call({'type':'send','id':'cleared','text':'Fresh conversational response.'})
    finally:
        app.close();app.save(d,'cold-');http.shutdown();http.server_close()
        (d/'wire.json').write_text(json.dumps(records,indent=2));(d/'journal.jsonl').write_bytes(journal[0].read_bytes())
        (d/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='fixture_root'}),flush=True)
    return summary

if __name__=='__main__':
    allresults=[]
    for workflow in ['coding.single_loop','coding.plan_execute_review','coding.codex_loop']:
        for cancel in [False,True]:
            for repeat in range(3):allresults.append(run(workflow,cancel,repeat))
    (E/'native-summary.json').write_text(json.dumps(allresults,indent=2))
    (E/'provenance.json').write_text(json.dumps({'core':'89997df995df7c39b713e16aba216ecb19c8f497','modules':'3270dc0f894eaf4d0360306052b806099b8f5351','binaries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [BIN,WF,REF]}},indent=2))
