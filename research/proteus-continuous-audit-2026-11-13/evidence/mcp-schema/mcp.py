"""Benign MCP fixture with controlled schemas; no tools/call side effects."""
import json,sys
mode=sys.argv[1]
for line in sys.stdin:
 req=json.loads(line);rid=req.get('id');method=req.get('method')
 if rid is None:continue
 if method=='initialize':
  value={'protocolVersion':req['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'schema-fixture','version':'1'}}
  if mode=='bad_initialize':value={'protocolVersion':42}
 elif method=='tools/list':
  schema={'type':'object','properties':{'message':{'type':'string'}}}
  if mode=='bad_schema':schema['properties']['message']['type']='invalid-type'
  if mode=='bad_wire':schema=[]
  value={'tools':[{'name':'echo','description':'Fixture only','inputSchema':schema}]}
 elif method=='tools/call':value={'content':[{'type':'text','text':'fixture-ok'}]}
 else:continue
 print(json.dumps({'jsonrpc':'2.0','id':rid,'result':value}),flush=True)
