"""Local deterministic CLI background question regression fixture. No network."""
import json, sys, time, uuid
from pathlib import Path
sys.path.insert(0, '/workspace/shared/core-acp-cli-chain/examples/modules')
from component_runtime import ProtocolError, run_component

def initialize(params):
    return {'protocol_version':'v3', 'component_id':params['component_id'], 'exports':[
        {key:export[key] for key in ('slot','module_id','contract_version','composition')} | {'module_features':[], 'config_schema':None}
        for export in params['exports']]}

def assistant(text):
    return {'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}

def invoke(context, method, params):
    if method != 'run': raise ProtocolError('expected run')
    task = params['task']
    def mark(kind, **data):
        with Path(task['cwd'], 'markers.jsonl').open('a') as out: out.write(json.dumps({'kind':kind,'at':time.monotonic(),**data})+'\n')
    def tool(name,args):
        return context.host_call('host.tools.execute_batch', {'task':task,'calls':[{'id':str(uuid.uuid4()),'name':name,'args':args,'surface':'function','raw_arguments':None}]})[0]
    if task['text'] == 'child':
        time.sleep(0.8)
        mark('child_about_to_ask')
        result = tool('request_user_input', {'title':'BACKGROUND_QUESTION','header':'Choice','question':'SELECT_BACKGROUND_ANSWER','options':['Alpha','Beta']})
        mark('child_input_result',result=result)
        text = 'CHILD_DONE ' + json.dumps(result)
    else:
        result = tool('spawn_agent', {'task_name':'question_child','message':'child','agent_type':'helper'})
        mark('parent_spawn_result',result=result)
        text = 'PARENT_RETURNED ' + json.dumps(result)
    return {'status':'success','result':{'output':{'text':text,'metadata':None},'new_messages':[assistant(text)],'history_replacement':None,'compactions':[]}}

run_component(initialize,invoke)
