"""Only temporary synthetic sessions. Uses unchanged prebuilt pinned runtime/modules."""
import os,json,pathlib,queue,signal,subprocess,tempfile,threading,time,hashlib
E=pathlib.Path(__file__).resolve().parent
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
BIN=pathlib.Path('/workspace/shared/nested-lifetime-evidence/proteus')
WF=pathlib.Path('/workspace/shared/disabled-skill-context-target/debug/proteus-coding-workflow-module')
REF=CORE/'target/sources/modules/target/debug/proteus-reference-module'
def run(name, workflow, steer, scenario='ordinary'):
    root=pathlib.Path(tempfile.mkdtemp(prefix='proteus-private-steering-')); cwd=root/'workspace';cwd.mkdir()
    config={'active_provider':'fixture','providers':{'fixture':{'provider':'scripted','model':'fixture','stream':True}},'modules':{'workflow':workflow,'context':'simple','policy':'allow_all'},'tools':{'enabled':['probe']},'agent_control':{'surface':'none','max_depth':0},'runtime':{'workflow_timeout_ms':20000},'components':{
       'workflow':{'command':str(WF),'exports':{'workflow':{workflow:{}}}},
       'reference':{'command':str(REF),'exports':{'context':{'simple':{}},'policy':{'allow_all':{}}}},
       'model':{'command':'python3','args':['-B',str(E/'model.py'),str(root),scenario],'exports':{'model':{'scripted':{}}}},
       'probe':{'command':'python3','args':['-B',str(CORE/'crates/proteus-core/tests/fixtures/process_probe_tool.py')],'exports':{'tool':{'probe':{}}}}}}
    configpath=root/'config.json';configpath.write_text(json.dumps(config))
    env=os.environ.copy();env.update(HOME=str(root),PROTEUS_HOME=str(root/'home'),XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),PROTEUS_CONFIG_HOME=str(root/'config'),PYTHONDONTWRITEBYTECODE='1')
    p=subprocess.Popen([str(BIN),'--config',str(configpath),'--cwd',str(cwd),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
    outputs=[];errors=[];q=queue.Queue()
    def read():
        for line in p.stdout:
            try:value=json.loads(line)
            except Exception:value={'raw':line}
            outputs.append(value);q.put(value)
    threading.Thread(target=read,daemon=True).start();threading.Thread(target=lambda:errors.extend(p.stderr.readlines()),daemon=True).start()
    def send(v):p.stdin.write(json.dumps(v)+'\n');p.stdin.flush()
    def response(id):
        end=time.monotonic()+35
        while time.monotonic()<end:
            try:v=q.get(timeout=.1)
            except queue.Empty:
                if p.poll() is not None:raise RuntimeError(f'{name} exited {errors}')
                continue
            if v.get('type')=='response' and v.get('id')==id:return v
        raise RuntimeError(f'{name} no response {id}: {errors}')
    receipt=None;result=None;history=None
    try:
        send({'type':'send','id':'original','text':'Synthetic task: inspect the provided probe and reply.'})
        end=time.monotonic()+20
        while not (root/'started').exists():
            if time.monotonic()>end or p.poll() is not None:raise RuntimeError(f'{name} model did not start {errors} {outputs[-3:]}')
            time.sleep(.01)
        if steer:
            send({'type':'send','id':'steering','text':'ADDED REQUIREMENT: mention verification limits.'});receipt=response('steering')
        (root/'release').write_text('go')
        result=response('original')
        send({'type':'history_summary','id':'history'});history=response('history')
    finally:
        if p.poll() is None:send({'type':'shutdown','id':'shutdown'})
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=5)
        d=E/name;d.mkdir(exist_ok=True)
        (d/'events.json').write_text(json.dumps(outputs,indent=2));(d/'stderr.log').write_text(''.join(errors));(d/'profile.json').write_text(json.dumps(config,indent=2))
        for path in ['requests.jsonl']:
            if (root/path).exists():(d/path).write_bytes((root/path).read_bytes())
        for j in root.rglob('journal.jsonl'):(d/'journal.jsonl').write_bytes(j.read_bytes())
    journals=list(root.rglob('journal.jsonl')); assert len(journals)==1
    cold=subprocess.run([str(BIN),'--config',str(configpath),'--cwd',str(cwd),'--resume-session',str(journals[0].parent),'server','stdio'],input=json.dumps({'type':'history_summary','id':'cold_history'})+'\n'+json.dumps({'type':'shutdown','id':'shutdown'})+'\n',capture_output=True,text=True,env=env,timeout=15)
    (d/'cold-events.jsonl').write_text(cold.stdout);(d/'cold-stderr.log').write_text(cold.stderr)
    assert cold.returncode==0,(cold.returncode,cold.stderr)
    summary={'name':name,'workflow':workflow,'steer':steer,'receipt':receipt,'result':result,'history':history,'fixture_root':str(root)}
    (d/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True);return summary
allresults=[]
for name,wf,steer,scenario in [('plan_control','coding.plan_execute_review',False,'ordinary'),('single_steering','coding.single_loop',True,'ordinary'),('plan_steering','coding.plan_execute_review',True,'ordinary'),('plan_execute_tool','coding.plan_execute_review',True,'execute_tool'),('execute_steering','coding.plan_execute_review',True,'execute_first_tool')]:
    for repeat in range(3):
        allresults.append(run(name+('-repeat'+str(repeat) if repeat else ''),wf,steer,scenario))
(E/'summary.json').write_text(json.dumps(allresults,indent=2))
(E/'provenance.json').write_text(json.dumps({'core':'89997df995df7c39b713e16aba216ecb19c8f497','modules':'3270dc0f894eaf4d0360306052b806099b8f5351','binaries':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [BIN,WF,REF]}},indent=2))
