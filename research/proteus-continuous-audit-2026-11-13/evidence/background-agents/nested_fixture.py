"""Model-free repository-compatible workflow exercising nested background peers."""
import json, os, sys, time, uuid
from pathlib import Path
sys.path.insert(0, '/workspace/shared/background-agent-chain-audit/examples/modules')
from component_runtime import ProtocolError, run_component

def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['module_id'],e['contract_version']) != ('workflow','nested_probe','v20'):
            raise ProtocolError('unexpected workflow')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}

def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}

def invoke(context, method, params):
    if method != 'run': raise ProtocolError('unexpected method')
    task=params['task']; prompt=task['text']; cwd=Path(task['cwd'])
    def log(name, extra=None):
        with (cwd/'fixture-markers.jsonl').open('a') as f:
            f.write(json.dumps({'name':name,'prompt':prompt,'pid':os.getppid(),'session':params['runtime']['conversation']['session_id'],'time':time.time(),'extra':extra})+'\n')
    def tool(name,args):
        call={'id':str(uuid.uuid4()),'name':name,'args':args,'surface':'function','raw_arguments':None}
        result=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
        log(name,result)
        return result
    log('start')
    if prompt == 'root-resume':
        tool('followup_task',{'target':'parent','message':'inspect-leaf'})
        result=tool('wait_agent',{'timeout_ms':10000})
        text=result['output']
    elif 'inspect-leaf' in prompt:
        result=tool('wait_agent',{'timeout_ms':100})
        text=result['output']
    elif prompt.startswith('root-'):
        tool('spawn_agent',{'task_name':'parent','agent_type':'next','message':prompt.replace('root-','parent-')})
        result=tool('wait_agent',{'timeout_ms':10000})
        text=result['output']
    elif prompt.startswith('parent-'):
        tool('spawn_agent',{'task_name':'leaf','agent_type':'next','message':('leaf-ask' if 'ask' in prompt else 'leaf')})
        if prompt.endswith('-wait'):
            tool('wait_agent',{'timeout_ms':10000})
        text='parent finished'
    else:
        time.sleep(1.5)
        tool('list_agents',{})
        if prompt == 'leaf-ask':
            log('before_user_input')
            tool('request_user_input',{'header':'Probe','question':'Choose fixture option','options':['A','B']})
            log('after_user_input')
        text='leaf finished'
    log('finish')
    output={'text':text,'metadata':None}
    context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':output}}})
    return {'status':'success','result':{'output':output,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
