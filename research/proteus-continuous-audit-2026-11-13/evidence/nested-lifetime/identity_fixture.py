"""Synthetic workflow; real task facade, peers, and worktree lifecycle. No models/network."""
import json, os, sys, time, uuid, subprocess
from pathlib import Path
sys.path.insert(0, '/workspace/shared/background-agent-chain-audit/examples/modules')
from component_runtime import ProtocolError, run_component

def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['module_id'],e['contract_version']) != ('workflow','worktree_probe','v20'):
            raise ProtocolError('unexpected workflow')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}

def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}

def invoke(context,method,params):
    if method!='run': raise ProtocolError('unexpected method')
    task=params['task']; prompt=task['text']; cwd=Path(task['cwd'])
    def log(name,extra=None):
        with open(sys.argv[1],'a') as f:
            f.write(json.dumps({'name':name,'prompt':prompt,'cwd':str(cwd),'pid':os.getppid(),'session':params['runtime']['conversation']['session_id'],'time':time.time(),'extra':extra})+'\n')
    def tool(name,args):
        call={'id':('call_0' if 'collision' in prompt else ('root_call_0' if prompt.startswith('root-') else 'parent_call_0')),'name':name,'args':args,'surface':'function','raw_arguments':None}
        result=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
        log(name,result); return result
    log('start')
    if prompt.startswith('root-'):
        result=tool('task',{'agent_type':'next','prompt':prompt.replace('root-','parent-',1)})
        text=result['output']
    elif prompt.startswith('parent-'):
        result=tool('task',{'agent_type':'next','prompt':prompt.replace('parent-','leaf-',1)})
        if 'dirty-parent' in prompt:
            (cwd/'parent-note.txt').write_text('synthetic parent-owned edit\n')
        log('before_parent_finish',{'nested_result':result})
        text='Nested task result: '+json.dumps(result)
    else:
        log('leaf_reached',{'base_exists':(cwd/'base.txt').exists()})
        text='leaf reached successfully'
    log('finish')
    output={'text':text,'metadata':None}
    context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':output}}})
    return {'status':'success','result':{'output':output,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
