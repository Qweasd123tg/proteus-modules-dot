import unittest
from reproduce_phase_cpu import scenario

class PhaseBoundaryRegression(unittest.TestCase):
    def test_idle_excludes_all_cpu_consumed_before_its_marker(self):
        result = scenario(False)
        self.assertEqual(result['actual_idle_cpu_percent'], 0,
                         'CPU consumed before resident_idle must not be reported as idle CPU')
        self.assertEqual(result['idle_cpu_ticks'], 0)

    def test_explicit_old_phase_boundary_sample_positive_control(self):
        result = scenario(True)
        self.assertEqual(result['actual_idle_cpu_percent'], 0)
        self.assertEqual(result['idle_cpu_ticks'], 0)
        self.assertEqual(result['launch_cpu_ticks'], 100)

if __name__ == '__main__':
    unittest.main(verbosity=2)
