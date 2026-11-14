import json,pathlib,sys,unittest
E=pathlib.Path(__file__).resolve().parent
class Reproduction(unittest.TestCase):
 def test_real_process_four_scenarios(self):
  for directory in [E,E/'repeat1']:
   for mode in ['default-untracked','hidden-untracked','hidden-staged','hidden-modified']:
    with self.subTest(run=str(directory),mode=mode):
     x=json.loads((directory/(mode+'-summary.json')).read_text())
     self.assertIsNotNone(x['response']);self.assertTrue(x['task_result']['ok']);self.assertEqual(x['task_result']['metadata']['status'],'completed')
     if mode=='hidden-untracked':
      self.assertEqual(x['child_written']['extra']['default_status'],'')
      self.assertEqual(x['child_written']['extra']['explicit_all_status'],'?? new_algorithm.py\n')
      self.assertFalse(x['target_exists']);self.assertFalse(x['checkout_exists'])
      self.assertIn('[worktree: no changes, removed]',x['task_result']['output'])
      self.assertEqual(x['branches'],'* main\n');self.assertEqual(x['tracked_new_file'],'')
     else:
      self.assertTrue(x['target_exists']);self.assertTrue(x['checkout_exists'])
      self.assertIn('[task_id:',x['task_result']['output'])
 def test_expected_safe_invariant(self):
  if '--expected-safe' not in sys.argv:self.skipTest('intentionally red invariant: use --expected-safe')
  x=json.loads((E/'hidden-untracked-summary.json').read_text())
  self.assertTrue(x['target_exists'],'ordinary untracked source file must survive child cleanup regardless of status.showUntrackedFiles')
if __name__=='__main__':unittest.main(argv=[x for x in sys.argv if x!='--expected-safe'])
