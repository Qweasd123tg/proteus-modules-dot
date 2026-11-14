"""Local benign completion reviewer, no tools or external requests."""
import json,sys,pathlib
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
sys.path.insert(0,str(CORE/'examples/modules'))
from component_runtime import run_component
log=pathlib.Path(sys.argv[1]); mode=sys.argv[2]
REASON='The candidate lacks the required completion acknowledgement. Append exactly REVIEW_ACK to your next final answer.'
def initialize(params):
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':[{**{k:e[k] for k in ('slot','module_id','contract_version','composition')},'module_features':[],'config_schema':None} for e in params['exports']]}
def invoke(ctx,method,params):
    e=params['event']; response={'action':'continue'}
    if e['event']=='before_stop' and mode!='accept' and 'REVIEW_ACK' not in e['output']['text']:
        response={'action':'continue_turn','reason':REASON}
    with log.open('a') as f:f.write(json.dumps({'event':e,'response':response,'attribution':params['attribution']})+'\n')
    return {'result':response}
run_component(initialize,invoke)
