"""Side-effect-free synthetic workflow, stable distinctive completion payload."""
import json, sys, time, uuid
sys.path.insert(0, '/workspace/shared/proteus-review-20261112/core/examples/modules')
from component_runtime import ProtocolError, run_component

def initialize(params):
    exports = []
    for export in params['exports']:
        if (export['slot'], export['contract_version'], export['composition']) != ('workflow', 'v20', 'select_one'):
            raise ProtocolError('expected workflow/v20')
        exports.append({k: export[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features': [], 'config_schema': None})
    return {'protocol_version':'v3', 'component_id':params['component_id'], 'exports':exports}

def invoke(context, method, params):
    if method != 'run': raise ProtocolError('expected run')
    spec=json.loads(params['task']['text'])
    index=spec['worker']
    marker=f'UNIQUE_WORKER_{index}_REPORT'
    fill='"' if spec.get('escaped') else chr(ord('A')+index)
    text=marker+'\n'+fill*(spec['size']-2*len(marker)-2)+'\n'+marker
    msg={'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
    return {'status':'success', 'result':{'output':{'text':text,'metadata':None},'new_messages':[msg],'history_replacement':None,'compactions':[]}}

run_component(initialize, invoke)
