"""Expected-red regression on the affected source: CLI wrapper resolves module identity."""
import json,sys
from pathlib import Path
result=json.loads(Path(sys.argv[1]).read_text())
assert result['wrapper']['module_inventory_path'] is not None, 'CLI-installed module must be visible through its supported backend launcher'
assert len(result['wrapper']['replace']) == 1, 'Updating an existing bundled module must select its replacement'
