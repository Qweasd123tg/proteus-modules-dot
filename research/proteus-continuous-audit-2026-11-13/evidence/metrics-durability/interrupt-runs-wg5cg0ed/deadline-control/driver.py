
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, '/workspace/shared/proteus-review-20261112/core/examples/performance/coding-harness')
import runner, adapters
root=Path('/workspace/shared/metrics-durability-evidence/interrupt-runs-wg5cg0ed/deadline-control')
def prepare(args,runtime):
    (runtime/'home').mkdir()
    (runtime/'native').mkdir()
    (runtime/'native/registry.json').write_text('{}')
    return ['/usr/bin/python3','/workspace/worker.py'], [(Path('/workspace/shared/proteus-review-20261112/core/examples/performance/coding-harness')/'open_code_native.py','/runtime/open_code_native.py')]
sys.argv=['runner.py','--agent','opencode','--case-dir',str(root/'case'),'--output',str(root/'output'),'--binary','/usr/bin/python3','--model','openai/fixture-model','--reasoning','high','--timeout','10']
with patch.object(adapters,'prepare',side_effect=prepare):
    raise SystemExit(runner.main())
