"""Model-free workflow; all memory operations go through the real tool host."""
import json, os, sys, time, uuid
from pathlib import Path
sys.path.insert(0, '/workspace/shared/proteus-review-20261112/core/examples/modules')
from component_runtime import ProtocolError, run_component
MARKERS = Path(sys.argv[1])
def initialize(params):
    exports=[]
    for e in params['exports']:
        if (e['slot'],e['module_id'],e['contract_version']) != ('workflow','memory_lifetime_probe','v20'):
            raise ProtocolError('unexpected workflow binding')
        exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}
def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
def invoke(context, method, params):
    if method!='run': raise ProtocolError('unexpected method')
    task=params['task']; request=json.loads(task['text']); cwd=Path(task['cwd'])
    def log(name, value):
        with MARKERS.open('a') as f:
            f.write(json.dumps({'name':name, 'cwd':str(cwd), 'session':params['runtime']['conversation']['session_id'], 'value':value})+'\n')
    def tool(name,args):
        call={'id':str(uuid.uuid4()),'name':name,'args':args,'surface':'function','raw_arguments':None}
        r=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
        log(name,r);return r
    if request['phase']=='root':
        child=dict(request,phase='child')
        result=tool('task',{'agent_type':'rememberer','prompt':json.dumps(child)})
        recalled=tool('recall_memory',{'query':request['fact'],'limit':20})
        text=json.dumps({'task':result,'root_recall':recalled})
    else:
        saved=tool('remember_fact',{'kind':'fact','content':request['fact'],'metadata':{'source':'synthetic-audit'}})
        recalled=tool('recall_memory',{'query':request['fact'],'limit':20})
        if request['dirty']:(cwd/'keep-checkout.txt').write_text('retain synthetic worktree\n')
        path=Path(request['absolute_path']) if request['absolute_path'] else cwd/'.proteus'/request['filename']
        log('before_return',{'memory_path':str(path),'exists':path.exists(),'bytes':path.stat().st_size if path.exists() else 0,'saved_ok':saved['ok'],'recall_ok':recalled['ok'],'items':recalled.get('metadata',{}).get('items')})
        text=json.dumps({'saved':saved,'recall':recalled,'memory_path':str(path)})
    out={'text':text,'metadata':None}
    context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':out}}})
    return {'status':'success','result':{'output':out,'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
