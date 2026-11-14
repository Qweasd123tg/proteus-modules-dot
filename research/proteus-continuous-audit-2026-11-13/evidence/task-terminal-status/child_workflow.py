"""Side-effect-free synthetic workflow, delays completion for role deadline tests."""
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
    time.sleep(int(sys.argv[1])/1000)
    text='Synthetic child completed its assignment.'
    msg={'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
    return {'status':'success', 'result':{'output':{'text':text,'metadata':None},'new_messages':[msg],'history_replacement':None,'compactions':[]}}

run_component(initialize, invoke)
