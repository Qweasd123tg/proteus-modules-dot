import hashlib,json,os,pathlib,queue,subprocess,tempfile,threading,time
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/background-agent-chain-audit')
BINARY=pathlib.Path('/workspace/shared/proteus-runtime-audit-target/debug/proteus')
REFERENCE=pathlib.Path('/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module')
for mode in ['wait','background']:
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-nested-'+mode+'-'))
    cwd=root/'workspace'; cwd.mkdir(); configs=root/'configs'; configs.mkdir(); config=configs/'test.toml'
    config.write_text(f'''active_provider = "fake"
[providers.fake]
provider = "fake"
model = "fake-tool-model"
[modules]
workflow = "nested_probe"
policy = "fixture_allow_all"
[components.workflow]
command = "python3"
args = [{json.dumps(str(E/'nested_fixture.py'))}]
[components.workflow.exports.workflow.nested_probe]
[components.policy]
command = "python3"
args = [{json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]
[components.policy.exports.policy.fixture_allow_all]
[components.test-model]
command = {json.dumps(str(REFERENCE))}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
[agent_control]
surface = "collaboration"
max_depth = 3
max_idle_processes = 4
[[agent_control.roles]]
name = "next"
description = "nested fixture"
config = {json.dumps(str(config))}
parallel_safe = true
timeout_ms = 15000
''')
    env=os.environ.copy(); env['HOME']=str(root); env['XDG_DATA_HOME']=str(root/'data'); env['XDG_CONFIG_HOME']=str(root/'config'); env['PYTHONDONTWRITEBYTECODE']='1'
    p=subprocess.Popen([str(BINARY),'--config',str(config),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    outputs=[]; errors=[]; lines=queue.Queue()
    def read():
        for line in p.stdout:
            try: v=json.loads(line)
            except Exception: v={'raw':line}
            outputs.append(v); lines.put(v)
    threading.Thread(target=read,daemon=True).start()
    threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
    def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
    send({'type':'send','id':'main','text':'root-'+mode})
    deadline=time.monotonic()+25; response=None
    while time.monotonic()<deadline:
        try:v=lines.get(timeout=.1)
        except queue.Empty:
            if p.poll() is not None:break
            continue
        if v.get('type')=='response' and v.get('id')=='main':response=v;break
    time.sleep(3)
    before_followup=list(outputs)
    send({'type':'shutdown','id':'shutdown'})
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:
        import signal
        os.killpg(p.pid,signal.SIGTERM); p.wait(timeout=3)
    markers=(cwd/'fixture-markers.jsonl').read_text() if (cwd/'fixture-markers.jsonl').exists() else ''
    (E/(mode+'-outputs.json')).write_text(json.dumps(before_followup,indent=2))
    (E/(mode+'-markers.jsonl')).write_text(markers)
    (E/(mode+'-stderr.log')).write_text(''.join(errors))
    print(json.dumps({'mode':mode,'root':str(root),'response':response,'outputs':len(before_followup),'markers':markers},ensure_ascii=False))
