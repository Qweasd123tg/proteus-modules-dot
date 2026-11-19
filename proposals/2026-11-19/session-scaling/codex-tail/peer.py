"""Synthetic JSONL producer; never reads any user data or credentials."""
import json, sys
for line in sys.stdin:
    request=json.loads(line)
    method=request.get("method")
    if method=="initialize":
        print(json.dumps({"id":request["id"],"result":{}}),flush=True)
    elif method=="replay":
        p=request["params"]
        payload=json.dumps({"method":"item/agentMessage/delta","params":{"threadId":"chat","turnId":"turn","itemId":"answer","delta":"x"*p["width"]}},separators=(",",":"))+"\n"
        sys.stdout.write(payload*p["batch"]);sys.stdout.flush()
