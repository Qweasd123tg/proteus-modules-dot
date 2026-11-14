#!/usr/bin/env python3
"""Regression oracle. Intentionally exits nonzero against today's defect evidence."""
from pathlib import Path
import json,sys
results=json.loads(Path(sys.argv[1]).read_text())
assert results['bad_schema']['ready'], 'Malformed schema from one MCP server must not prevent unrelated good MCP/Core startup'
assert results['save_bad_schema']['status']==200, 'Malformed-schema server should be represented as a server-local /addons error'
