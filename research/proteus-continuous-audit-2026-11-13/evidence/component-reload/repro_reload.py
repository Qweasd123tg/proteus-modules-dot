import json, os, pathlib, subprocess, sys, threading, queue, time
ROOT = pathlib.Path('/workspace/shared/trace-integration-round8-evidence')
CHECKOUT = pathlib.Path('/workspace/shared/trace-integration-round8')
BINARY = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '/workspace/shared/trace-integration-round8-target/debug/proteus')
SURFACE = os.environ.get('AUDIT_SURFACE', 'collaboration')
run = ROOT / (SURFACE + '-run-' + str(time.time_ns()))
run.mkdir()
workspace = run/'workspace'; workspace.mkdir()
config = run/'configs'; config.mkdir()
child = config/'child.toml'; child.write_text('# Deliberately model-free child. No network.\n')
parent = config/'parent.toml'
parent.write_text(f'''
[modules]
workflow = "audit_tool_driver"
policy = "fixture_allow_all"

[components.workflow]
command = "python3"
args = ["-B", {json.dumps(str(ROOT/'workflow.py'))}]
[components.workflow.exports.workflow.audit_tool_driver]

[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CHECKOUT/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]

[agent_control]
binary = {json.dumps(str(BINARY))}
surface = "{SURFACE}"
max_idle_processes = 8

[[agent_control.roles]]
name = "helper"
description = "Local model-free child"
config = {json.dumps(str(child))}
parallel_safe = true
max_processes = 4
timeout_ms = 30000
''')
log = (run/'wire.jsonl').open('w')
err = (run/'stderr.log').open('w')
env = os.environ.copy(); env['PROTEUS_CONFIG_HOME'] = str(run)
p = subprocess.Popen([str(BINARY),'--config',str(parent),'--cwd',str(workspace),'--new-session','server','stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, env=env)
q = queue.Queue()
def reader():
    for line in p.stdout:
        log.write(line); log.flush()
        try: q.put(json.loads(line))
        except json.JSONDecodeError: pass
    q.put(None)
threading.Thread(target=reader,daemon=True).start()
responses = {}
def request(kind, **args):
    ident = str(len(responses)+1)
    req = dict(type=kind,id=ident,**args)
    p.stdin.write(json.dumps(req)+'\n'); p.stdin.flush()
    end = time.monotonic()+45
    while time.monotonic()<end:
        row = q.get(timeout=max(.1,end-time.monotonic()))
        if row is None: raise RuntimeError('process exited: '+(run/'stderr.log').read_text())
        if row.get('type')=='response' and row.get('id')==ident:
            responses[ident] = {'request':req,'response':row}
            print(kind, json.dumps(row,ensure_ascii=False), flush=True)
            assert row['ok'], row
            return row['output']
    raise TimeoutError(req)
def tool(name,args):
    output = request('send',text=json.dumps({'tool':name,'args':args}))
    return json.loads(output['text'])
try:
    if SURFACE == 'task':
        first = tool('task',{'agent_type':'helper','prompt':'first task'}); assert first['ok'],first
        task_id = first['metadata']['child_thread_id']
        first_wait = None
        control = tool('task',{'agent_type':'helper','prompt':'control: continue before reload','task_id':task_id}); assert control['ok'],control
        control_wait = None
        before = {'task_id':task_id, 'resumable':control['metadata'].get('resumable')}
        reload = request('reload_tools')
        after = None
        followup = tool('task',{'agent_type':'helper','prompt':'continue after tools reload','task_id':task_id})
    else:
        first = tool('spawn_agent',{'task_name':'worker','message':'first task','agent_type':'helper'}); assert first['ok'], first
        first_wait = tool('wait_agent',{'timeout_ms':30000}); assert first_wait['ok'],first_wait
        control = tool('followup_task',{'target':'worker','message':'control: continue before reload'}); assert control['ok'],control
        control_wait = tool('wait_agent',{'timeout_ms':30000}); assert control_wait['ok'],control_wait
        before = tool('list_agents',{})
        reload = request('reload_tools')
        after = tool('list_agents',{})
        followup = tool('followup_task',{'target':'worker','message':'continue after tools reload'})
    result = {'first':first,'first_wait':first_wait,'control_before_reload':control,'control_wait':control_wait,'before_reload':before,'reload':reload,'after_reload':after,'followup_after_reload':followup}
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('EVIDENCE',run,flush=True)
    print('FOLLOWUP_AFTER_RELOAD_OK',followup['ok'],flush=True)
    assert not followup['ok'], 'Bug not reproduced: followup succeeded'
finally:
    try: request('shutdown')
    except Exception as e: print('shutdown:',e,flush=True)
    try: p.wait(timeout=10)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=5)
    log.close(); err.close()
