"""Real task timeout -> native Anthropic serialization -> loopback HTTP.

The root HTTP provider is synthetic. Children use either a side-effect-free
workflow or the standard delayed fake model. No live API,
credentials, user workspace, native production edits, or publication.
"""
import hashlib, http.server, json, os, pathlib, queue, signal, shutil, subprocess, tempfile, threading, time
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
MODS=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug')
MORE=CORE/'target/sources/modules/target/debug'
records=[]
active={}

class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        assert self.path=='/v1/messages'
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        records.append({'case':active['name'],'request':body})
        parts=[p for m in body['messages'] for p in m['content'] if isinstance(p,dict)]
        results=[p for p in parts if p.get('type')=='tool_result']
        if active['mode']=='collaboration_timeout' and not results:
            content=[{'type':'tool_use','id':'call_fixture','name':'spawn_agent','input':{'agent_type':'helper','task_name':'worker','message':'Finish synthetic delegated task.'}}]; stop='tool_use'
        elif active['mode']=='collaboration_timeout' and len(results)==1:
            content=[{'type':'tool_use','id':'call_wait','name':'wait_agent','input':{'timeout_ms':5000}}]; stop='tool_use'
        elif results:
            content=[{'type':'text','text':'Synthetic provider received result.'}]; stop='end_turn'
        else:
            content=[{'type':'tool_use','id':'call_fixture','name':'task','input':{'agent_type':'helper','prompt':'Finish synthetic delegated task.'}}]; stop='tool_use'
        response={'id':'msg_fixture','type':'message','role':'assistant','model':'fixture-model','content':content,'stop_reason':stop,'stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':1}}
        assert not body.get('stream'), 'fixture expects non-stream provider mode'
        data=json.dumps(response).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Provider)
threading.Thread(target=server.serve_forever,daemon=True).start()

def run_case(name,delay_ms):
    mode=name
    active.update(name=name,mode=mode)
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-task-status-'));cwd=root/'workspace';cwd.mkdir()
    child=root/'child.toml'
    child.write_text(f'''[modules]
workflow = "status_child"
[components.child]
command = "python3"
args = ["-B", {json.dumps(str(E/'child_workflow.py'))}, "{delay_ms}"]
[components.child.exports.workflow.status_child]
''')
    if mode == 'partial_timeout':
        child.write_text(f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
stream = true
[modules]
workflow = "coding.codex_loop"
context = "codex_context"
[components.workflow]
command = {json.dumps(str(MODS/'proteus-coding-workflow-module'))}
[components.workflow.exports.workflow."coding.codex_loop"]
[components.context]
command = {json.dumps(str(MODS/'proteus-context-pack-module'))}
[components.context.exports.context.codex_context]
[module_config.context.codex_context]
providers = ["environment"]
[components.model]
command = {json.dumps(str(MORE/'proteus-reference-module'))}
[components.model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
stream_delay_ms = 400
''')
    config=root/'profile.toml'
    config.write_text(f'''active_provider = "local"
[providers.local]
provider = "anthropic"
model = "fixture-model"
stream = false
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
[components.native-model.exports.model.anthropic]
[module_config.model.anthropic]
implementation = "anthropic"
api_key = "synthetic-not-a-credential"
base_url = "http://127.0.0.1:{server.server_address[1]}"
[agent_control]
binary = {json.dumps(str(BINARY))}
surface = "{'collaboration' if mode == 'collaboration_timeout' else 'task'}"
max_depth = 1
[[agent_control.roles]]
name = "helper"
description = "Synthetic local timer"
config = {json.dumps(str(child))}
parallel_safe = true
timeout_ms = 1500
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
    response=None
    try:
        send({'type':'send','id':name,'text':'Inspect the synthetic payload.'})
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:v=lines.get(timeout=.1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if v.get('type')=='response' and v.get('id')==name:response=v;break
        if response is None:raise RuntimeError(f'No response: {name}, stderr={errors}')
    finally:
        if p.poll() is None:send({'type':'shutdown','id':'shutdown'})
        try:p.wait(timeout=4)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=4)
        (E/f'{name}-events.json').write_text(json.dumps(outputs,indent=2))
        (E/f'{name}-stderr.log').write_text(''.join(errors))
        (E/f'{name}-profile.toml').write_text(config.read_text())
        (E/f'{name}-child.toml').write_text(child.read_text())
        shutil.copytree(root/'sessions', E/f'{name}-sessions'/root.name, dirs_exist_ok=True)
    requests=[r['request'] for r in records if r['case']==name]
    parts=[p for m in requests[-1]['messages'] for p in m['content'] if isinstance(p,dict)]
    results=[p for p in parts if p.get('type')=='tool_result']
    lengths=[len(r['content'].encode()) for r in results]
    summary={'case':name,'child_delay_ms':delay_ms,'provider_requests':len(requests),'provider_tool_text_bytes':lengths,'response':response,'fixture_root':str(root)}
    print(json.dumps({k:v for k,v in summary.items() if k not in ('response','fixture_root')}),flush=True)
    return summary

summaries=[]
try:
    for name,delay in [('complete',0),('timed_out',4000),('timed_out_repeat',4000),('partial_timeout',4000),('collaboration_timeout',4000)]:
        summaries.append(run_case(name,delay))
finally:
    server.shutdown()
    (E/'provider-requests.json').write_text(json.dumps(records,indent=2))
    (E/'summary.json').write_text(json.dumps(summaries,indent=2))
    binaries=[BINARY,MODS/'proteus-coding-workflow-module',MODS/'proteus-context-pack-module',MORE/'proteus-model-pack-module',MORE/'proteus-reference-module']
    (E/'provenance.json').write_text(json.dumps({'binaries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries}},indent=2))
