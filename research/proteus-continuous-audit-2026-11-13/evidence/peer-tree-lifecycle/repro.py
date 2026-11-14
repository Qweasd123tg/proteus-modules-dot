import argparse,hashlib,json,os,queue,signal,subprocess,threading,time
from pathlib import Path
R=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));p.add_argument('--binary',type=Path,default=Path('/workspace/shared/trace-component-deployment-evidence/run-1794580123588475346/home/.proteus/releases/fixture/proteus'));p.add_argument('--shell',type=Path,default=Path('/workspace/shared/trace-integration-round8-module-target/debug/proteus-shell-tool-module'));a=p.parse_args();CORE=a.core.resolve();BINARY=a.binary.resolve()
F=R/f'run-{time.time_ns()}'; F.mkdir(); results=[]
def proc(pid):
    try:
        data=Path(f'/proc/{pid}/stat').read_text(); tail=data[data.rindex(')')+2:].split(); return {'pid':pid,'state':tail[0],'ppid':int(tail[1]),'pgid':int(tail[2])}
    except FileNotFoundError:return None
SHELL=a.shell.resolve()
for mode in ['role_timeout','component_timeout','shell_timeout','shell_cancel']:
    D=F/mode; D.mkdir(); home=D/'home';home.mkdir();work=D/'workspace';work.mkdir();cfg=D/'root.toml';childcfg=D/'child.toml'
    common=f'''[modules]\nworkflow="lifecycle_probe"\npolicy="fixture_allow_all"\n[components.workflow]\ncommand="python3"\nargs=["-B",{json.dumps(str(R/'workflow.py'))},{json.dumps(str(CORE/'examples/modules'))}]\n[components.workflow.exports.workflow.lifecycle_probe]\nTIMEOUT\n[components.policy]\ncommand="python3"\nargs=["-B",{json.dumps(str(CORE/'crates/proteus-core/tests/fixtures/process_allow_all_policy.py'))}]\n[components.policy.exports.policy.fixture_allow_all]\n'''
    childcfg.write_text(common.replace('TIMEOUT','timeout_ms = '+str(1800 if mode=='component_timeout' else 30000)))
    if mode.startswith('shell_'):
        childcfg.write_text(childcfg.read_text()+f'\n[components.shell]\ncommand={json.dumps(str(SHELL))}\n[components.shell.exports.tool.shell_tools]\n[tools]\nenabled=["exec_command","write_stdin"]\n')
    cfg.write_text(common.replace('TIMEOUT','timeout_ms = 25000')+f'''\n[agent_control]\nsurface="collaboration"\nmax_depth=2\n[[agent_control.roles]]\nname="helper"\nparallel_safe=true\ndescription="Local lifecycle diagnostic"\nconfig={json.dumps(str(childcfg))}\ntimeout_ms={2500 if mode in ('role_timeout','shell_timeout') else 15000}\n''')
    env=os.environ.copy();env.update(HOME=str(home),XDG_CONFIG_HOME=str(home/'config'),XDG_DATA_HOME=str(home/'data'),PYTHONDONTWRITEBYTECODE='1')
    stderr=(D/'stderr.log').open('w');p=subprocess.Popen([str(BINARY),'--config',str(cfg),'--cwd',str(work),'--new-session','server','stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,text=True,env=env,start_new_session=True)
    outputs=[]; q=queue.Queue();known=set();markers=[];response=None
    def reader():
        for line in p.stdout:
            try:v=json.loads(line)
            except Exception:v={'raw':line}
            outputs.append(v);q.put(v)
    threading.Thread(target=reader,daemon=True).start()
    try:
        p.stdin.write(json.dumps({'type':'send','id':'main','text':'root-'+mode})+'\n');p.stdin.flush()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:v=q.get(timeout=.1)
            except queue.Empty:
                if p.poll() is not None:break
                continue
            if v.get('type')=='response' and v.get('id')=='main':response=v;break
        assert response is not None,outputs[-5:]
        response_time=time.time()
        time.sleep(4.5)
        markers=[json.loads(x) for x in (work/'markers.jsonl').read_text().splitlines()]
        h=next(m for m in markers if m['name']=='helper-started');known.update([h['pid'],h['ppid'],h['helper_pid']])
        record={'mode':mode,'response':response,'response_time':response_time,'helper':proc(h['helper_pid']),'child_core':proc(h['ppid']),'child_workflow':proc(h['pid']),'helper_parent':proc(h.get('helper_ppid',h['pid'])),'marker':json.loads((work/'after-timeout-marker.json').read_text()) if (work/'after-timeout-marker.json').exists() else None}
        results.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
    finally:
        # All recorded PIDs belong to this freshly created, exclusively owned fixture.
        try:
            for x in (work/'markers.jsonl').read_text().splitlines():
                m=json.loads(x);known.add(m['pid']);known.add(m['ppid']);
                if m.get('helper_pid'):known.add(m['helper_pid'])
                if m.get('helper_ppid'):known.add(m['helper_ppid'])
        except FileNotFoundError:pass
        try:
            p.stdin.write('{"type":"shutdown","id":"shutdown"}\n');p.stdin.flush();p.wait(timeout=3)
        except (BrokenPipeError,subprocess.TimeoutExpired):
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
        for pid in known:
            s=proc(pid)
            if s and s['state']!='Z':
                try:os.kill(pid,signal.SIGKILL)
                except ProcessLookupError:pass
        (D/'outputs.json').write_text(json.dumps(outputs,ensure_ascii=False,indent=2));stderr.close()
        time.sleep(.2)
        cleanup={str(pid):proc(pid) for pid in known}
        (D/'cleanup.json').write_text(json.dumps(cleanup,indent=2))
        assert all(x is None or x['state']=='Z' for x in cleanup.values()),cleanup
(F/'results.json').write_text(json.dumps({'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'shell_binary_sha256':hashlib.sha256(SHELL.read_bytes()).hexdigest(),'core_head':subprocess.check_output(['git','-C',str(CORE),'rev-parse','HEAD'],text=True).strip(),'cases':results},ensure_ascii=False,indent=2))
print('EVIDENCE',F)
