"""Benign local MCP fixture: initialize, empty tools/list, no filesystem or network effects."""
import json,sys
for line in sys.stdin:
 request=json.loads(line);method=request.get('method');rid=request.get('id')
 if rid is None:continue
 if method=='initialize': result={'protocolVersion':'2025-06-18','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'toggle-fixture','version':'1'}}
 elif method=='tools/list':result={'tools':[]}
 else:
  print(json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'unsupported'}}),flush=True);continue
 print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
