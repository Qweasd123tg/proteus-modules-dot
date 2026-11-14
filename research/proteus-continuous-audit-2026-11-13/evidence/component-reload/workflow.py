"""Synthetic model-free workflow: execute one authorized tool via normal host path."""
import json, sys, uuid
sys.path.insert(0, '/workspace/shared/trace-integration-round8/examples/modules')
from component_runtime import ProtocolError, run_component

def uid(): return str(uuid.uuid4())
def initialize(params):
    exports = []
    for export in params['exports']:
        if (export['slot'], export['contract_version'], export['composition']) != ('workflow', 'v20', 'select_one'):
            raise ProtocolError('expected workflow/v20')
        exports.append({k: export[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features': [], 'config_schema': None})
    return {'protocol_version':'v3', 'component_id':params['component_id'], 'exports':exports}

def message(role, payload, provenance, call_id=None):
    return {'id':uid(), 'role':role, 'phase':None, 'parts':[{'part_id':uid(), 'provenance':provenance, 'scope':'conversation', 'payload':payload}], 'name':None, 'tool_call_id':call_id, 'metadata':None}

def invoke(context, method, params):
    if method != 'run': raise ProtocolError('expected run')
    requested = json.loads(params['task']['text'])
    call = {'id':uid(), 'name':requested['tool'], 'args':requested['args'], 'surface':'function', 'raw_arguments':None}
    call_message = message('Assistant', {'ToolCall':{'call':call}}, 'model')
    binding = {'call_id':call['id'], 'execution_call':call, 'message_id':uid(), 'part_id':uid()}
    proposal = {'new_messages':[call_message], 'history_replacement':None, 'compactions':[]}
    acknowledgement = context.host_call('host.history.checkpoint', {'history':proposal, 'tool_results':[binding], 'preparation_target':None})
    result = context.host_call('host.tools.execute_batch', {'task':params['task'], 'calls':[call]})[0]
    tool_message = message('Tool', {'ToolResult':{'result':result}}, 'tool', call['id'])
    tool_message['id'] = binding['message_id']
    tool_message['parts'][0]['part_id'] = binding['part_id']
    text = json.dumps(result, sort_keys=True)
    final = message('Assistant', {'Text':{'text':text}}, 'model')
    new_messages = acknowledgement['history']['new_messages'] + [tool_message, final]
    return {'status':'success', 'result':{'output':{'text':text, 'metadata':None}, 'new_messages':new_messages, 'history_replacement':None, 'compactions':[]}}

run_component(initialize, invoke)
