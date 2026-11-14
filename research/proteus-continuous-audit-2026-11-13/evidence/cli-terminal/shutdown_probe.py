import json, os, pathlib, pty, select, signal, subprocess, tempfile, time, sys
ROOT = pathlib.Path(__file__).resolve().parent
binary = '/workspace/shared/proteus-runtime-audit-target/debug/proteus'
reference = '/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module'
policy = '/workspace/shared/core-acp-cli-chain/crates/proteus-core/tests/fixtures/process_allow_all_policy.py'
mode = 'shutdown'
root = pathlib.Path(tempfile.mkdtemp(prefix='proteus-cli-idle-'))
(root/'home').mkdir()
def cfg(timeout):
    return f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[components.test-model]
command = {json.dumps(reference)}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
[modules]
workflow = "idle_probe"
policy = "fixture_allow_all"
[components.workflow]
command = "/usr/bin/python3"
args = [{json.dumps(str(ROOT/'idle_workflow.py'))}]
[components.workflow.exports.workflow.idle_probe]
[components.policy]
command = "/usr/bin/python3"
args = [{json.dumps(policy)}]
[components.policy.exports.policy.fixture_allow_all]
[tools]
enabled = ["request_user_input"]
[app_server]
approval_timeout_ms = {timeout}
[event_log]
path = {json.dumps(str(root/'events.jsonl'))}
'''
(root/'child.toml').write_text(cfg(0))
(root/'parent.toml').write_text(cfg(1200 if mode == 'timeout' else 0)+f'''
[agent_control]
surface = "collaboration"
binary = {json.dumps(binary)}
max_depth = 1
max_idle_processes = 0
[[agent_control.roles]]
name = "helper"
description = "Local deterministic question fixture"
config = {json.dumps(str(root/'child.toml'))}
parallel_safe = true
max_processes = 1
timeout_ms = 20000
''')
master, slave = pty.openpty()
env = dict(os.environ, PROTEUS_HOME=str(root/'home'))
p = subprocess.Popen([binary,'--config',str(root/'parent.toml'),'--cwd',str(root),'--interactive'],stdin=slave,stdout=slave,stderr=slave,start_new_session=True,env=env)
os.close(slave)
transcript=bytearray()
def drain(duration):
    deadline=time.monotonic()+duration
    while time.monotonic()<deadline:
        ready,_,_=select.select([master],[],[],max(0,deadline-time.monotonic()))
        if ready:
            try: chunk=os.read(master,65536)
            except OSError:return
            if not chunk:return
            transcript.extend(chunk)
def until(needle,timeout=10):
    start=len(transcript); deadline=time.monotonic()+timeout
    while needle.encode() not in transcript[start:]:
        if time.monotonic()>=deadline:raise RuntimeError('waiting for '+needle+'\n'+transcript.decode(errors='replace'))
        drain(.04)
    return transcript[start:].decode(errors='replace')
try:
    until('Context waiting')
    os.write(master,b'start\n')
    until('PARENT_RETURNED')
    drain(3)
    before=transcript.decode(errors='replace')
    markers=[json.loads(x) for x in (root/'markers.jsonl').read_text().splitlines()]
    print('MODE',mode,'TEMP',root)
    print('=== MARKERS BEFORE NEXT COMMAND ===\n'+json.dumps(markers,indent=2))
    print('=== TERMINAL BEFORE NEXT COMMAND ===\n'+before)
    assert any(x['kind']=='child_about_to_ask' for x in markers), markers
    assert 'BACKGROUND_QUESTION' not in before, 'question unexpectedly displayed while idle'
    if mode == 'timeout':
        result=next(x for x in markers if x['kind']=='child_input_result')['result']
        assert not result['metadata']['answers'], result
    else:
        assert not any(x['kind']=='child_input_result' for x in markers), markers
    os.write(master,b'/exit\n')
    appeared=until('SELECT_BACKGROUND_ANSWER')
    print('=== /exit OPENED CHILD QUESTION ===\n'+appeared)
    drain(4)
    print('alive_after_4_seconds=',p.poll() is None)
    assert p.poll() is None, 'CLI exited normally'
    print('=== MARKERS AFTER SHUTDOWN ===\n'+(root/'markers.jsonl').read_text())
    os.write(master,b'1\n')
    drain(.5)
    try:p.wait(timeout=4)
    except subprocess.TimeoutExpired:pass

finally:
    (ROOT/(mode+'-transcript.txt')).write_text(transcript.decode(errors='replace'))
    (ROOT/(mode+'-workspace.txt')).write_text(str(root))
    if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
    os.close(master)
