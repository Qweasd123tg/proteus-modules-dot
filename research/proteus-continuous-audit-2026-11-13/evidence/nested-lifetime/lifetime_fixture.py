"""Synthetic workflow proving real worktree/active peer lifetime boundaries."""
import json, os, sys, time, uuid
from pathlib import Path
sys.path.insert(0, '/workspace/shared/background-agent-chain-audit/examples/modules')
from component_runtime import ProtocolError, run_component
MARKERS=Path(sys.argv[1]); RELEASE=Path(sys.argv[2]); READY=Path(sys.argv[3])
def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['module_id'],e['contract_version']) != ('workflow','lifetime_probe','v20'):
            raise ProtocolError('unexpected workflow')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}
def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
def invoke(context,method,params):
    if method!='run':raise ProtocolError('unexpected method')
    task=params['task'];prompt=task['text'];cwd=Path(task['cwd'])
    def log(name,extra=None):
        with MARKERS.open('a') as f:
            f.write(json.dumps({'name':name,'prompt':prompt,'cwd':str(cwd),'pid':os.getppid(),'worker_pid':os.getpid(),'session':params['runtime']['conversation']['session_id'],'time':time.time(),'extra':extra})+'\n')
    def tool(name,args):
        call={'id':str(uuid.uuid4()),'name':name,'args':args,'surface':'function','raw_arguments':None}
        result=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
        log(name,result);return result
    def await_file(path):
        deadline=time.monotonic()+15
        while not path.exists():
            if time.monotonic()>deadline:raise RuntimeError('fixture barrier timed out: '+str(path))
            time.sleep(.01)
    log('start')
    if prompt.startswith('root-'):
        result=tool('task',{'agent_type':'parent','prompt':prompt.replace('root-','parent-',1)})
        text=result['output']
    elif prompt.startswith('parent-'):
        result=tool('spawn_agent',{'task_name':'reader','agent_type':'reader','message':'leaf'})
        if not result['ok']:raise RuntimeError(str(result))
        await_file(READY)
        if 'dirty' in prompt:(cwd/'parent-note.txt').write_text('keep parent checkout\n')
        if 'wait' in prompt:tool('wait_agent',{'timeout_ms':10000})
        log('before_parent_finish',{'reader_started':True})
        text='parent finished after spawning read-only reader'
    else:
        READY.write_text(str(cwd))
        log('reader_ready',{'base_exists':(cwd/'base.txt').exists()})
        await_file(RELEASE)
        try:
            content=(cwd/'base.txt').read_text();read={'ok':True,'content':content}
        except OSError as e:read={'ok':False,'errno':e.errno,'error':str(e)}
        log('reader_result',{'cwd_exists':cwd.exists(),**read})
        text=json.dumps(read)
    log('finish')
    output={'text':text,'metadata':None}
    context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':output}}})
    return {'status':'success','result':{'output':output,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
