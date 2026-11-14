"""Safe synthetic tool/v6 fixture: no external effects, deterministic text."""
import json, sys
sys.path.insert(0, '/workspace/shared/proteus-review-20261112/core/examples/modules')
from component_runtime import ProtocolError, run_component

def initialize(params):
    exports=[]
    for export in params['exports']:
        assert (export['slot'],export['contract_version']) == ('tool','v6')
        exports.append({**{k:export[k] for k in ('slot','module_id','contract_version','composition')},'module_features':[],'config_schema':None})
    return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}

def invoke(context,method,params):
    if method == 'list':
        return {'result':[{'spec':{'name':'content_probe','description':'Return a bounded synthetic test payload.','input_schema':{'type':'object','properties':{'mode':{'type':'string'},'size':{'type':'integer'}},'required':['mode','size'],'additionalProperties':False},'surface':{'kind':'function','strict':False,'output_schema':None},'safety':'ReadOnly','supports_parallel_tool_calls':False,'timeout_ms':3000,'metadata':{}},'model_visible':True,'user_command':None}]}
    if method != 'invoke': raise ProtocolError('unexpected method')
    call=params['call']; mode=call['args']['mode']; size=call['args']['size']
    assert 0 <= size <= 350000
    text='A'*size
    result={'call_id':call['id'],'ok':True,'output':'','content':[],'error':None,'metadata':{'fixture_mode':mode,'fixture_bytes':size}}
    if mode == 'output': result['output']=text
    elif mode == 'text': result['content']=[{'type':'text','text':text}]
    elif mode == 'json': result['content']=[{'type':'json','value':{'body':text}}]
    elif mode == 'error': result.update(ok=False,error=text)
    elif mode == 'preferred_output': result.update(output='short visible output',content=[{'type':'text','text':text}])
    else: raise ProtocolError('unknown mode')
    return {'result':result}

run_component(initialize,invoke)
