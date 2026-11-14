"""Real Core collaboration completion -> output hook -> native provider.
All children and provider responses are synthetic; only loopback HTTP is used.
"""
import hashlib, http.server, json, os, pathlib, queue, signal, shutil, subprocess, tempfile, threading, time
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
MODS=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug')
MORE=CORE/'target/sources/modules/target/debug'
records=[];active={}

def terminal_count():
    return sum('SubagentFinished' in v.get('event',{}).get('envelope',{}).get('event',{}) for v in active['outputs'])

class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        records.append({'case':active['name'],'request':body})
        step=active['step'];active['step']+=1
        def call(name,args):
            return {'type':'tool_use','id':f'call_step_{step}','name':name,'input':args}
        if step < active['count']:
            content=[call('spawn_agent',{'agent_type':'helper','task_name':f'worker_{step}','message':json.dumps({'worker':step,'size':active['size'],'escaped':active['escaped']})})]
        elif step==active['count']:
            deadline=time.monotonic()+20
            while terminal_count()<active['count'] and time.monotonic()<deadline:time.sleep(.02)
            assert terminal_count()==active['count'], (terminal_count(), active['count'])
            # SubagentFinished precedes final monitor enqueue by a few instructions.
            time.sleep(.2)
            content=[call('wait_agent',{'timeout_ms':0})]
        elif step==active['count']+1:
            content=[call('wait_agent',{'timeout_ms':0})]
        elif step==active['count']+2:
            content=[call('list_agents',{})]
        else:
            content=[{'type':'text','text':'Synthetic provider captured both waits and retained status.'}]
        response={'id':f'msg_{step}','type':'message','role':'assistant','model':'fixture-model','content':content,'stop_reason':'tool_use' if content[0]['type']=='tool_use' else 'end_turn','stop_sequence':None,'usage':{'input_tokens':1,'output_tokens':1}}
        assert not body.get('stream')
        data=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Provider)
threading.Thread(target=server.serve_forever,daemon=True).start()

def run_case(name,count,size,hook=False,escaped=False):
    outputs=[]
    active.update(name=name,step=0,count=count,size=size,hook=hook,escaped=escaped,outputs=outputs)
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-completion-budget-'));cwd=root/'workspace';cwd.mkdir()
    child=root/'child.toml'
    child.write_text(f'''[modules]
workflow = "status_child"
[components.child]
command = "python3"
args = ["-B", {json.dumps(str(E/'child_workflow.py'))}]
[components.child.exports.workflow.status_child]
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
hooks = {json.dumps(['hook.output_budget'] if hook else [])}
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
[components.output-budget]
command = {json.dumps(str(MORE/'proteus-hook-pack-module'))}
[components.output-budget.exports.hook."hook.output_budget"]
[module_config.hook."hook.output_budget"]
max_bytes = 16000
head_bytes = 12000
[agent_control]
binary = {json.dumps(str(BINARY))}
surface = "collaboration"
max_depth = 1
max_parallel = 8
max_idle_processes = 8
[[agent_control.roles]]
name = "helper"
description = "Synthetic completion reporter"
config = {json.dumps(str(child))}
parallel_safe = true
max_processes = 8
timeout_ms = 15000
''')
    env=os.environ.copy();env.update(HOME=str(root),PROTEUS_HOME=str(root/'home'),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PROTEUS_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1',NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost')
    p=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    errors=[];lines=queue.Queue()
    def read():
        for line in p.stdout:
            try:v=json.loads(line)
            except Exception:v={'raw':line}
            outputs.append(v);lines.put(v)
    threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
    def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
    response=None
    try:
        send({'type':'send','id':name,'text':'Run synthetic collaboration completion check.'})
        deadline=time.monotonic()+80
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
        if (root/'sessions').exists():shutil.copytree(root/'sessions', E/f'{name}-sessions'/root.name, dirs_exist_ok=True)
    requests=[r['request'] for r in records if r['case']==name]
    parts=[p for m in requests[-1]['messages'] for p in m['content'] if isinstance(p,dict)]
    results={r['tool_use_id']:r for r in parts if r.get('type')=='tool_result'}
    first=results[f'call_step_{count}']['content'];second=json.loads(results[f'call_step_{count+1}']['content']);listed=json.loads(results[f'call_step_{count+2}']['content'])
    try:parsed=json.loads(first);first_agents=len(parsed.get('agents',[]))
    except json.JSONDecodeError:first_agents=None
    summary={'case':name,'count':count,'size':size,'hook':hook,'escaped':escaped,'provider_requests':len(requests),'terminal_count':terminal_count(),'first_wait_bytes':len(first.encode()),'first_wait_agents':first_agents,'markers_visible':[i for i in range(count) if f'UNIQUE_WORKER_{i}_REPORT' in first],'first_wait_error':results[f'call_step_{count}'].get('is_error'),'second_wait':second,'listed_agents':len(listed['agents']),'list_has_payload':any(a.get('summary') or a.get('error') for a in listed['agents']),'response':response,'fixture_root':str(root)}
    print(json.dumps({k:v for k,v in summary.items() if k not in ('response','fixture_root')}),flush=True)
    return summary

summaries=[]
try:
    for args in [('six-no-hook',6,8000,False,False),('six-hook',6,8000,True,False),('six-hook-repeat',6,8000,True,False),('short-hook-control',6,1000,True,False),('escaped-core-cap',8,16000,False,True)]:
        summaries.append(run_case(*args))
finally:
    server.shutdown();(E/'provider-requests.json').write_text(json.dumps(records,indent=2));(E/'summary.json').write_text(json.dumps(summaries,indent=2))
    binaries=[BINARY,MODS/'proteus-coding-workflow-module',MODS/'proteus-context-pack-module',MORE/'proteus-model-pack-module',MORE/'proteus-hook-pack-module']
    (E/'provenance.json').write_text(json.dumps({'binaries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries}},indent=2))
