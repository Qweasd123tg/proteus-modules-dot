import json,pathlib,sys,unittest
E=pathlib.Path(__file__).resolve().parent
class Reproduction(unittest.TestCase):
 def test_real_process_outcomes(self):
  for directory in [E,E/'repeat1']:
   for mode in ['branch-original','branch-switched','branch-renamed']:
    with self.subTest(run=str(directory),mode=mode):
     x=json.loads((directory/(mode+'-summary.json')).read_text())
     first=x['task_result'];resume=next(r['extra'] for r in x['records'] if r['name']=='resume_result')
     self.assertTrue(first['ok']);self.assertEqual(first['metadata']['status'],'completed');self.assertTrue(x['target_exists']);self.assertTrue(x['checkout_exists'])
     if mode=='branch-original':
      self.assertTrue(resume['ok']);self.assertIn('unique child result',x['suggested_branch_merge']['root_base_after'])
     elif mode=='branch-switched':
      self.assertTrue(resume['ok']);self.assertIn('| branch: proteus/coder-call_0]',first['output'])
      self.assertEqual(x['child_written']['extra']['current_branch'],'feature/implementation')
      self.assertEqual(x['suggested_branch_merge']['stdout'],'Already up to date.\n')
      self.assertEqual(x['suggested_branch_merge']['root_base_after'],'BASE = True\n')
      self.assertIn('unique child result',x['branch_contents']['feature/implementation'])
      self.assertEqual(x['branch_contents']['proteus/coder-call_0'],'BASE = True\n')
     else:
      self.assertTrue(first['metadata']['resumable']);self.assertNotIn('[task_id:',first['output']);self.assertIn('worktree cleanup failed',first['output'])
      self.assertFalse(resume['ok']);self.assertIn('worktree for task_id',resume['error']);self.assertIn('is gone',resume['error'])
      self.assertIn('unique child result',x['branch_contents']['feature/implementation'])
 def test_expected_safe_invariant(self):
  if '--expected-safe' not in sys.argv:self.skipTest('intentionally red: use --expected-safe')
  x=json.loads((E/'branch-switched-summary.json').read_text())
  self.assertIn('unique child result',x['suggested_branch_merge']['root_base_after'],'reported integration branch must contain committed child result')
if __name__=='__main__':unittest.main(argv=[x for x in sys.argv if x!='--expected-safe'])
