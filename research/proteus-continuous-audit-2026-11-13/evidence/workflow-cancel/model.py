"""Synthetic model/v13 fixture: deterministic phase responses, no HTTP."""
import json, sys, time, uuid
from pathlib import Path
sys.path.insert(0, '/workspace/shared/proteus-review-20261112/core/examples/modules')
from component_runtime import run_component, ProtocolError
root=Path(sys.argv[1]); ordinal=0

def initialize(params):
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':[
        {**{k:e[k] for k in ('slot','module_id','contract_version','composition')},'module_features':[],'config_schema':None} for e in params['exports']]}

def invoke(ctx, method, params):
    global ordinal
    if method=='describe':
        caps={f'supports_{k}':False for k in ['tools','parallel_tool_calls','freeform_tools','streaming','json_schema','system_role','developer_role','cache_hints','reasoning_config','image_input','file_input']}
        caps.update(supports_tools=True,supports_streaming=True,supports_system_role=True,supports_developer_role=True,provider_hosted_tools=[],max_input_tokens=16000,max_output_tokens=2048)
        return {'adapter_id':'workflow-steering-fixture','capabilities':caps,'hosted_tools':[]}
    if method!='stream':raise ProtocolError('unsupported '+method)
    n=root/'counter'
    ordinal=int(n.read_text())+1 if n.exists() else 1
    n.write_text(str(ordinal))
    req=params['request'];phase=(req['metadata'] or {}).get('workflow_phase')
    with (root/'requests.jsonl').open('a') as f:f.write(json.dumps({'ordinal':ordinal,'phase':phase,'request':req})+'\n')
    tool_round=ordinal==1
    call={'id':f'probe-{ordinal}','name':'probe','args':{},'surface':'function'}
    payload={'ToolCall':{'call':call}} if tool_round else {'Text':{'text':f'ANSWER-{ordinal}-{phase}'}}
    msg={'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':payload}], 'name':None,'tool_call_id':None,'metadata':{}}
    response={'messages':[msg],'tool_calls':[call] if tool_round else [],'finish_reason':'ToolCalls' if tool_round else 'Stop','usage':None,'end_turn':None,'provider_metadata':{}}
    return {'event_count':0,'terminal':{'kind':'response','response':response}}
run_component(initialize,invoke)
