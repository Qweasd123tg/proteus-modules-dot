import json,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
bundle=Path(sys.argv[sys.argv.index('--bundle')+1]);(bundle/'bin').mkdir()
release=(root/'release.txt').read_text().strip()
worker=bundle/'bin/proteus-model-pack-module'
worker.write_text('#!/usr/bin/env python3\nimport json,sys\nRELEASE='+repr(release)+'\nfor line in sys.stdin:\n message=json.loads(line)\n if "id" in message: print(json.dumps({"jsonrpc":"2.0","id":message["id"],"result":RELEASE}),flush=True)\n')
worker.chmod(0o755)
