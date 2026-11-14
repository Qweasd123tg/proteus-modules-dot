"""Synthetic model records real prepared requests and exercises one requested skill."""
import json,sys,uuid
from pathlib import Path
sys.path.insert(0, '/workspace/shared/proteus-review-20261112/core/examples/modules')
from component_runtime import ProtocolError,run_component
settings={}
def initialize(params):
 export=params['exports'][0]
 assert (export['slot'],export['contract_version'])==('model','v13')
 settings.update(export['module_config'])
 return {'protocol_version':'v3','component_id':params['component_id'],'exports':[{**{k:export[k] for k in ('slot','module_id','contract_version','composition')},'module_features':[],'config_schema':None}]}
def invoke(context,method,params):
 if method=='describe':
  cap={k:False for k in ['supports_tools','supports_parallel_tool_calls','supports_freeform_tools','supports_streaming','supports_json_schema','supports_system_role','supports_developer_role','supports_cache_hints','supports_reasoning_config','supports_image_input','supports_file_input']}
  cap.update(supports_tools=True,supports_system_role=True,supports_developer_role=True,provider_hosted_tools=[],max_input_tokens=200000,max_output_tokens=2048)
  return {'adapter_id':'skills-budget-capture','capabilities':cap,'hosted_tools':[]}
 if method in ('catalog','quota'):return None
 if method!='stream':raise ProtocolError('unexpected method')
 request=params['request']
 with open(settings['capture_path'],'a') as f:f.write(json.dumps(request)+'\n')
 # Locate the actual latest user query, ignoring context-shaped user messages.
 last_user=next((m for m in reversed(request['messages']) if m['role']=='User'),None)
 last_parts=[p['payload'] for p in request['messages'][-1]['parts']]
 current_load=last_user is not None and any(p['payload'].get('Text',{}).get('text')=='LOAD procedure-000' for p in last_user['parts'])
 result=next((p['ToolResult']['result'] for p in last_parts if 'ToolResult' in p),None)
 call=None
 if current_load and result is None:
  call={'id':str(uuid.uuid4()),'name':'skill','args':{'name':'procedure-000'},'surface':'function','raw_arguments':None}
  payload={'ToolCall':{'call':call}}
 else:payload={'Text':{'text':json.dumps(result) if result else 'Synthetic inspection complete.'}}
 msg={'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'name':None,'tool_call_id':None,'metadata':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':payload}]}
 return {'event_count':0,'terminal':{'kind':'response','response':{'messages':[msg],'tool_calls':[call] if call else [],'finish_reason':'ToolCalls' if call else 'Stop','usage':None,'end_turn':None,'provider_metadata':None}}}
run_component(initialize,invoke)
