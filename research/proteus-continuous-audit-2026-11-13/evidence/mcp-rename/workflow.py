"""Model-free test workflow for registration only. No turns are requested."""
import sys
sys.path.insert(0, sys.argv[1])
from component_runtime import ProtocolError, run_component

def initialize(params):
    exports = []
    for export in params['exports']:
        if (export['slot'], export['contract_version'], export['composition']) != ('workflow', 'v20', 'select_one'):
            raise ProtocolError('expected workflow/v20')
        exports.append({k: export[k] for k in ('slot','module_id','contract_version','composition')} | {'module_features': [], 'config_schema': None})
    return {'protocol_version':'v3', 'component_id':params['component_id'], 'exports':exports}

def invoke(context, method, params):
    raise ProtocolError('Deployment test must not run a workflow or a model')

run_component(initialize, invoke)
