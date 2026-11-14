"""Test-only workflow invokes real skill tool; no model or custom skill parser."""
import json,sys,uuid
sys.path.insert(0,'/workspace/shared/proteus-review-20261112/core/examples/modules')
from component_runtime import ProtocolError,run_component

def initialize(params):
 exports=[]
 for e in params['exports']:
  if (e['slot'],e['module_id'],e['contract_version'])!=('workflow','skill_isolation_probe','v20'):raise ProtocolError('unexpected binding')
  exports.append({k:e[k] for k in ('slot','module_id','contract_version','composition')}|{'module_features':[],'config_schema':None})
 return {'protocol_version':'v3','component_id':params['component_id'],'exports':exports}

def invoke(context,method,params):
 if method!='run':raise ProtocolError('unexpected method')
 task=params['task'];results={}
 for name in ['testing','review']:
  call={'id':str(uuid.uuid4()),'name':'skill','args':{'name':name},'surface':'function','raw_arguments':None}
  results[name]=context.host_call('host.tools.execute_batch',{'task':task,'calls':[call]})[0]
 text=json.dumps(results);out={'text':text,'metadata':None}
 msg={'id':str(uuid.uuid4()),'role':'Assistant','phase':None,'parts':[{'part_id':str(uuid.uuid4()),'provenance':'model','scope':'conversation','payload':{'Text':{'text':text}}}],'name':None,'tool_call_id':None,'metadata':None}
 context.host_call('host.events.emit',{'event':{'TurnFinished':{'output':out}}})
 return {'status':'success','result':{'output':out,'new_messages':[msg],'history_replacement':None,'compactions':[]}}
run_component(initialize,invoke)
