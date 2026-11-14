"""Read-only catalog invocation against the genuine skill-pack process."""
import json,os,subprocess,uuid

def catalog(binary,cwd,home):
 env=os.environ.copy();env.update(HOME=str(home),PROTEUS_HOME=str(home/'proteus-home'))
 p=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
 def call(i,method,params):
  p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush()
  line=p.stdout.readline()
  if not line:raise RuntimeError(p.stderr.read())
  out=json.loads(line);assert 'error' not in out,out
  return out
 try:
  init=call('h:1:0','initialize',{'protocol_version':'v3','component_id':'catalog-probe','exports':[{'slot':'context_provider','module_id':'skills','contract_version':'v4','composition':'ordered_many','module_config':{},'host_features':[]}]})
  out=call('h:1:1','catalog',{'export':{'slot':'context_provider','module_id':'skills'},'lineage':{'root_invocation_id':'h:1:1','parent_invocation_id':None,'depth':0},'params':{'cwd':str(cwd),'skills':{'disabled':[],'packages':[]}}})
  catalog=out['result']['result']
  chunks=call('h:1:2','provide',{'export':{'slot':'context_provider','module_id':'skills'},'lineage':{'root_invocation_id':'h:1:2','parent_invocation_id':None,'depth':0},'params':{'input':{'provider_id':'skills','task':{'text':'Inspect skills','cwd':str(cwd)},'metadata':None},'attribution':{'execution_id':str(uuid.uuid4()),'agent':None},'skills':{'disabled':[],'packages':[]}}})
  return {'catalog':catalog,'chunks':chunks['result']['result']}
 finally:
  p.stdin.close()
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=3)
