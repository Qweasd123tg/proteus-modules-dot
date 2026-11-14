import json, os, pathlib, subprocess, sys, threading, queue, time
ROOT = pathlib.Path('/workspace/shared/trace-integration-round8-evidence')
CHECKOUT = pathlib.Path('/workspace/shared/trace-integration-round8')
BINARY = pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '/workspace/shared/trace-integration-round8-target/debug/proteus')
SURFACE = 'shell'
SHELL_MODULE = pathlib.Path(os.environ.get('AUDIT_SHELL_MODULE','/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-shell-tool-module'))
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

[components.shell]
command = {json.dumps(str(SHELL_MODULE))}
[components.shell.exports.tool.shell_tools]

[tools]
enabled = ["exec_command", "write_stdin"]
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
    import shlex
    child_program = workspace/'marker.py'
    child_program.write_text("import sys,signal,pathlib,os\nsignal.alarm(12)\nlabel=sys.argv[1]\npathlib.Path(label+'.pid').write_text(str(os.getpid()))\nprint(label+':ready',flush=True)\nwith open(label+'.received','a') as out:\n for line in sys.stdin:\n  out.write(line); out.flush(); print(label+':'+line.strip(),flush=True)\n  if line.strip()=='intended-A': break\n")
    def exec_marker(label):
        return tool('exec_command',{'cmd':'python3 -u '+shlex.quote(str(child_program))+' '+label,'tty':True,'yield_time_ms':250,'with_escalated_permissions':True})
    first = exec_marker('A'); assert first['ok'],first
    old_id = first['metadata']['session_id']
    control = tool('write_stdin',{'session_id':old_id,'chars':'control-A\n','yield_time_ms':250}); assert control['ok'],control
    reload = request('reload_tools')
    missing = tool('write_stdin',{'session_id':old_id,'chars':'probe-before-B\n','yield_time_ms':250})
    second = exec_marker('B'); assert second['ok'],second
    new_id = second['metadata']['session_id']
    misdirected = tool('write_stdin',{'session_id':old_id,'chars':'intended-A\n','yield_time_ms':250})
    a_pid = int((workspace/'A.pid').read_text())
    os.kill(a_pid, 0)  # Prove old A is still a live process at the misdelivery boundary.
    a_text = (workspace/'A.received').read_text()
    b_text = (workspace/'B.received').read_text()
    result = {'first':first,'control':control,'reload':reload,'missing_before_new_session':missing,'second':second,'old_id':old_id,'new_id':new_id,'write_using_old_id':misdirected,'A_received':a_text,'B_received':b_text,'A_pid':a_pid,'A_alive_after_misdelivery':True}
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('EVIDENCE',run,flush=True)
    print('OLD_ID',old_id,'NEW_ID',new_id,'A_RECEIVED',repr(a_text),'B_RECEIVED',repr(b_text),flush=True)
    assert old_id == new_id
    assert 'intended-A' not in a_text and 'intended-A' in b_text
finally:
    try: request('shutdown')
    except Exception as e: print('shutdown:',e,flush=True)
    try: p.wait(timeout=10)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=5)
    log.close(); err.close()
