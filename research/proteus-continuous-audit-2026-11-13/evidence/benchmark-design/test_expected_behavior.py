"""Desired-behavior regressions; expected to fail on audited Core 89997df9.
Run the two local oracle probes and comparability probe first to stage fixtures.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

E=Path(__file__).resolve().parent
ROOT=Path('/workspace/shared/benchmark-design-audit')
HERE=ROOT/'examples/performance/coding-harness'
sys.path.insert(0,str(HERE))
import long_report

class ExpectedBenchmarkBehavior(unittest.TestCase):
    def grade(self, case, workspace, grader_dir):
        directory=E/grader_dir;directory.mkdir(exist_ok=True)
        target=directory/'test_outputs.py'
        source=(E/case/'grader/test_outputs.py').read_text()
        source=source.replace("ROOT = Path('/app')",f'ROOT = Path({str(E/workspace)!r})')
        source=source.replace('"/app"',repr(str(E/workspace)))
        target.write_text(source)
        result=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',str(target)],
                              cwd=E/workspace,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout[-1800:]+result.stderr)

    def test_correct_dataclass_archive_is_not_rejected_by_loader(self):
        self.grade('journal-case','journal-solution-local','red-journal-grader')

    def test_correct_os_function_aliases_are_not_rejected_by_spy(self):
        self.grade('ledger-case','ledger-solution-local','red-ledger-grader')

    def test_paired_report_rejects_mixed_reasoning_effort(self):
        with self.assertRaisesRegex(ValueError,'effort|reasoning|model|condition|compar'):
            long_report.build(E/'mixed-effort-runs',[],['journal-segments'],['pi','proteus-pi'],E/'no-baseline',[])

if __name__=='__main__':unittest.main()
