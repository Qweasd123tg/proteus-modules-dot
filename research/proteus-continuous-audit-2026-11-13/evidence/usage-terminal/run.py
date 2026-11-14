"""Local-only native Responses terminal-reconciliation fixtures.
Partial terminal output is a synthetic compatibility/robustness case, not claimed live-provider behavior.
"""
import hashlib, http.server, json, os, pathlib, queue, signal, subprocess, tempfile, threading, time
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
MODS=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug')
MORE=CORE/'target/sources/modules/target/debug'
records=[]; active={}
class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        n=sum(r['case']==active['name'] for r in records)
        records.append({'case':active['name'],'request':body})
        items=[{'id':'item_a','type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':'FIRST_MESSAGE','annotations':[]}]}, {'id':'item_b','type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':'SECOND_MESSAGE','annotations':[]}]}]
        events=[]
        for i,item in enumerate(items):
            events.append({'type':'response.output_item.added','output_index':i,'item':{**item,'content':[]}})
            events.append({'type':'response.output_text.delta','item_id':item['id'],'output_index':i,'content_index':0,'delta':item['content'][0]['text']})
            if active['kind']=='done':events.append({'type':'response.output_item.done','output_index':i,'item':item})
        output={'full':items,'empty':[],'head':items[:1],'tail':items[1:]}[active['stop']]
        events.append({'type':'response.completed','response':{'id':'resp_fixture','status':'completed','output':output,'usage':{'input_tokens':123,'output_tokens':45,'input_tokens_details':{'cached_tokens':20},'output_tokens_details':{'reasoning_tokens':5}}}})
        data=''.join(f'data: {json.dumps(value)}\n\n' for value in events).encode();ctype='text/event-stream'
        self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Provider)
threading.Thread(target=server.serve_forever,daemon=True).start()
def run_case(kind,stop,stream):
    name=f'{kind}-{stop}-stream-{stream}';active.update(name=name,kind=kind,stop=stop)
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-context-stop-'));cwd=root/'workspace';cwd.mkdir();config=root/'profile.toml'
    config.write_text(f'''active_provider = "local"
[providers.local]
provider = "openai"
model = "fixture-model"
stream = {str(stream).lower()}
[modules]
workflow = "coding.codex_loop"
context = "codex_context"
policy = "fixture_allow_all"
hooks = []
[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.workflow]
command = {json.dumps(str(MODS/'proteus-coding-workflow-module'))}
[components.workflow.exports.workflow."coding.codex_loop"]
[components.context]
command = {json.dumps(str(MODS/'proteus-context-pack-module'))}
[components.context.exports.context.codex_context]
[module_config.context.codex_context]
providers = ["environment"]
[components.native-model]
command = {json.dumps(str(MORE/'proteus-model-pack-module'))}
[components.native-model.exports.model.openai]
[module_config.model.openai]
implementation = "openai"
api_key = "synthetic-not-a-credential"
base_url = "http://127.0.0.1:{server.server_address[1]}"
[components.compactor]
command = {json.dumps(str(MORE/'proteus-codex-context-preparation-module'))}
[components.compactor.exports.hook.codex_compact]
[module_config.hook.codex_compact]
stream_max_retries = 1
[tools]
enabled = []
[agent_control]
surface = "none"
max_depth = 0
''')
    env=os.environ.copy();env.update(HOME=str(root),PROTEUS_HOME=str(root/'home'),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PROTEUS_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1',NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
    p=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    outputs=[];errors=[];lines=queue.Queue()
    def read():
        for line in p.stdout:
            try:v=json.loads(line)
            except Exception:v={'raw':line}
            outputs.append(v);lines.put(v)
    threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
    def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
    def turn(i):
        key=f'{name}-{i}';send({'type':'send','id':key,'text':f'Synthetic task {i}: inspect no files; explain the next step.'});deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            try:v=lines.get(timeout=.1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if v.get('type')=='response' and v.get('id')==key:return v
        raise RuntimeError(f'No response: {key}, stderr={errors}')
    responses=[];usage_response=None
    try:
        responses.append(turn(1))
        if False:responses.append(turn(2))
        usage_key=name+'-usage';send({'type':'usage_summary','id':usage_key});deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            try:v=lines.get(timeout=.1)
            except queue.Empty:continue
            if v.get('type')=='response' and v.get('id')==usage_key:usage_response=v;break
        assert usage_response is not None
    finally:
        if p.poll() is None:send({'type':'shutdown','id':'shutdown'})
        try:p.wait(timeout=4)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
        (E/f'{name}-events.json').write_text(json.dumps(outputs,indent=2));(E/f'{name}-stderr.log').write_text(''.join(errors));(E/f'{name}-profile.toml').write_text(config.read_text())
        journals=list(root.rglob('journal.jsonl'));assert len(journals)==1
        (E/f'{name}-journal.jsonl').write_bytes(journals[0].read_bytes())
    reqs=[r['request'] for r in records if r['case']==name]
    result={'case':name,'responses':responses,'provider_requests':len(reqs),'request_max_tokens':[r.get('max_tokens') for r in reqs],'usage_response':usage_response,'fixture_root':str(root)}
    print(json.dumps(result),flush=True);return result
summaries=[]
try:
    for stream in [True]:
        for kind in ['done','deltas']:
            for stop in ['full','empty','head','tail']:summaries.append(run_case(kind,stop,stream))
finally:
    server.shutdown();(E/'provider-requests.json').write_text(json.dumps(records,indent=2));(E/'summary.json').write_text(json.dumps(summaries,indent=2))
    binaries=[BINARY,MODS/'proteus-coding-workflow-module',MODS/'proteus-context-pack-module',MORE/'proteus-model-pack-module',MORE/'proteus-codex-context-preparation-module']
    (E/'provenance.json').write_text(json.dumps({'binaries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries}},indent=2))
