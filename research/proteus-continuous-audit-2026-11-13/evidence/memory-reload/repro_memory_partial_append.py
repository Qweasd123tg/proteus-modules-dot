"""Real module + model-free workflow; isolated partial-write fault, no production edits."""
import json, os, pathlib, subprocess, sys, threading, queue, time

ROOT = pathlib.Path(__file__).resolve().parent
CORE = pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BINARY = pathlib.Path('/workspace/shared/trace-integration-round8-target/debug/proteus')
MEMORY = pathlib.Path('/workspace/shared/trace-integration-round8-module-target/debug/proteus-memory-pack-module')
run = ROOT / ('memory-run-' + str(time.time_ns()))
run.mkdir()
workspace = run/'workspace'; workspace.mkdir()
control_mode = '--control' in sys.argv
limit_file = run/'worker-limit.txt'; limit_file.write_text('1048576' if control_mode else '512')
profile = run/'profile.toml'
profile.write_text(f'''
[modules]
workflow = "audit_tool_driver"
policy = "fixture_allow_all"

[components.workflow]
command = "python3"
args = ["-B", {json.dumps(str(ROOT/'workflow.py'))}]
[components.workflow.exports.workflow.audit_tool_driver]

[components.policy]
command = "python3"
args = ["-B", {json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]

[components.memory]
command = "python3"
args = ["-B", {json.dumps(str(ROOT/'limited_worker.py'))}, {json.dumps(str(limit_file))}, {json.dumps(str(MEMORY))}]
[components.memory.exports.tool.jsonl_memory]

[module_config.tool.jsonl_memory]
path = {json.dumps(str(workspace/'memory.jsonl'))}

[tools]
enabled = ["remember_fact", "recall_memory"]
''')
log = (run/'wire.jsonl').open('w')
err = (run/'stderr.log').open('w')
env = os.environ.copy(); env['PROTEUS_CONFIG_HOME'] = str(run)
p = subprocess.Popen([str(BINARY),'--config',str(profile),'--cwd',str(workspace),'--new-session','server','stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True, env=env)
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
def recall(query='', limit=20):
    return tool('recall_memory', {'query':query,'limit':limit})
try:
    baseline = tool('remember_fact', {'kind':'fact','content':'known-good durable fact'})
    assert baseline['ok'], baseline
    before = recall(); assert before['ok'], before
    if control_mode:
        large = tool('remember_fact', {'kind':'fact','content':'X'*1024})
        assert large['ok'], large
        reload = request('reload_tools')
        final = recall(); assert final['ok'], final
        assert len(final['metadata']['items']) == 2
        (run/'result.json').write_text(json.dumps(dict(mode='healthy-control', baseline=baseline, large=large, reload=reload, final=final),indent=2))
        print('CONTROL_EVIDENCE',run,flush=True)
        raise SystemExit(0)
    failed = tool('remember_fact', {'kind':'fact','content':'X'*1024})
    assert not failed['ok'], failed
    data = (workspace/'memory.jsonl').read_bytes()
    (run/'after-failed-write.bin').write_bytes(data)
    assert len(data) == 512, len(data)
    assert not data.endswith(b'\n'), data[-60:]
    after_failure = recall(); assert not after_failure['ok'], after_failure
    # Lift the fault for the next worker. Host configuration and source remain unchanged.
    limit_file.write_text('1048576')
    reload = request('reload_tools')
    after_reload = recall(); assert not after_reload['ok'], after_reload
    subsequent = tool('remember_fact', {'kind':'fact','content':'successful-after-reload'})
    assert subsequent['ok'], subsequent
    final = recall('successful-after-reload'); assert not final['ok'], final
    prior_prefix = recall('',1); assert prior_prefix['ok'], prior_prefix
    assert 'known-good durable fact' in prior_prefix['output']
    result = dict(baseline=baseline, before=before, failed_write=failed, bytes_after_failed_write=len(data), ends_with_newline_after_failed_write=data.endswith(b'\n'), after_failure=after_failure, reload=reload, after_reload=after_reload, subsequent_success=subsequent, recall_successful_fact=final, prior_prefix=prior_prefix)
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('EVIDENCE',run,flush=True)
finally:
    try: request('shutdown')
    except Exception as e: print('shutdown:',e,flush=True)
    try: p.wait(timeout=10)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=5)
    log.close(); err.close()
