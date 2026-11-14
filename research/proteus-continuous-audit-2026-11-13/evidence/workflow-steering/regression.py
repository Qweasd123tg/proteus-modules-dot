"""Desired invariant against recorded isolated runs. Two expected failures on pinned code."""
import json,pathlib,unittest
E=pathlib.Path(__file__).resolve().parent
class PrivateDraftSteering(unittest.TestCase):
    def check(self,name):
        result=json.loads((E/name/'summary.json').read_text())['result']
        self.assertTrue(result['ok'],result.get('error'))
    def test_no_steering_control(self):self.check('plan_control')
    def test_single_loop_steering_control(self):self.check('single_steering')
    def test_persistent_execute_tool_anchor_control(self):self.check('plan_execute_tool')
    def test_steering_after_plan_tool_must_finish(self):self.check('plan_steering')
    def test_steering_after_execute_tool_must_finish(self):self.check('execute_steering')
if __name__=='__main__':unittest.main()
