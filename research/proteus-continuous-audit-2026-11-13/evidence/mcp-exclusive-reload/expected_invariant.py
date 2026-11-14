"""Expected regression invariant: unchanged working MCP survives a config operation.
On current HEAD, three cases FAIL; diagnostic repro.py passing is NOT a fix.
"""
from pathlib import Path
import json,sys,unittest
results=json.loads(Path(sys.argv[1]).read_text());sys.argv=sys.argv[:1]
class PreserveWorkingMcp(unittest.TestCase):
 def check(self,name):
  result=results[name]
  self.assertEqual(result['after']['mcp_servers'][0]['tools'], ['fixture__echo'])
  self.assertTrue(json.loads(result['after_call']['output']['text'])['ok'])
 def test_unrelated_save(self):self.check('exclusive_unrelated')
 def test_identical_save(self):self.check('exclusive_noop')
 def test_explicit_reload(self):self.check('exclusive_reload')
 def test_nonexclusive_control(self):self.check('shared_control')
unittest.main()
