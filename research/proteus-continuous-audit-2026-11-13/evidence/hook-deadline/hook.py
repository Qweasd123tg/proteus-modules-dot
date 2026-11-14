"""Local test-only hook, uses production example protocol helper."""
import json, pathlib, sys, time
CORE=pathlib.Path('/workspace/shared/proteus-review-20261112/core')
sys.path.insert(0,str(CORE/'examples/modules'))
from component_runtime import run_component
phase,delay,auxcount,log = sys.argv[1:5]
delay=float(delay); auxcount=int(auxcount)
def write(value):
    with open(log,'a') as f:f.write(json.dumps({'time':time.monotonic(),**value})+'\n')
def initialize(params):
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':[{**{k:v for k,v in e.items() if k in ('slot','module_id','contract_version','composition')},'module_features':[],'config_schema':None} for e in params['exports']]}
def invoke(context,method,params):
    event=params['event']; kind=event['event']
    write({'phase':kind,'point':'start'})
    if kind==phase:
        context.on_cancel(lambda:write({'phase':kind,'point':'cancel'}))
        until=time.monotonic()+delay
        while time.monotonic()<until:
            context.ensure_active();time.sleep(min(.01,until-time.monotonic()))
        context.ensure_active()
        for i in range(auxcount):
            request=event['request'].copy();request['instructions']=[];request['tools']=[]
            write({'phase':kind,'point':'aux_start','i':i})
            result=context.host_call('host.model.complete',{'request':request})
            write({'phase':kind,'point':'aux_done','i':i})
    write({'phase':kind,'point':'end'})
    return {'result':{'action':'continue'}}
run_component(initialize,invoke)
