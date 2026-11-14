from pathlib import Path
import sys, shutil, json, subprocess
ROOT=Path('/workspace/shared/benchmark-design-audit')
HERE=ROOT/'examples/performance/coding-harness'
sys.path.insert(0,str(HERE))
import corpus,long_corpus
E=Path(__file__).resolve().parent
case=E/'journal-case'
if not (case/'case.json').exists():long_corpus.prepare('journal-segments',case)
work=E/'journal-solution-local'
if work.exists():shutil.rmtree(work)
shutil.copytree(case/'repo',work)
code=work/'examples/performance/history-scale'
for name in ('archive.py','journal.py'):shutil.copy2(case/'grader/reference'/name,code/name)
graders=E/'local-grader';graders.mkdir(exist_ok=True)
grader=graders/'test_outputs.py'
original=(case/'grader/test_outputs.py').read_text()
# Only map the unavailable bubblewrap /app mount to this disposable workspace.
original=original.replace("ROOT = Path('/app')",f'ROOT = Path({str(work)!r})')
grader.write_text(original)
def run(label,cmd,cwd=work):
    p=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True)
    data={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    corpus.write_json(E/f'{label}.json',data)
    print(label, p.returncode, p.stdout[-1500:],p.stderr[-500:])
    return p
pytest=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',str(grader)]
baseline=run('journal-gold-baseline-local',pytest)
source=(code/'archive.py').read_text()
source='from __future__ import annotations\n'+source
source=source.replace('import argparse','from dataclasses import dataclass, asdict\nimport argparse',1)
source=source.replace('\ndef archive(','''\n@dataclass
class Segment:
    relative_path: str
    sha256: str
    bytes: int
    first_seq: int
    last_seq: int

def archive(''',1)
source=source.replace('segments.append(dict(relative_path=relative, sha256=sha.hexdigest(), bytes=size, first_seq=first, last_seq=last))','segments.append(asdict(Segment(relative, sha.hexdigest(), size, first, last)))')
(code/'archive.py').write_text(source)
# Normal import plus CLI both have correct ordinary sys.modules registration.
normal=run('journal-dataclass-normal-import-local',[sys.executable,'-B','-c',f'import sys; sys.path.insert(0,{str(code)!r}); import archive; assert archive.Segment("a", "b", 0, 1, 1).bytes == 0'])
broken=run('journal-dataclass-existing-grader-local',pytest)
# Minimal correction to the local grader alone, analogous to current sampler grader.
fixed=original.replace('    spec.loader.exec_module(module)\n','    sys.modules[spec.name] = module\n    try:\n        spec.loader.exec_module(module)\n    except BaseException:\n        sys.modules.pop(spec.name, None)\n        raise\n',1)
grader.write_text(fixed)
corrected=run('journal-dataclass-fixed-grader-local',pytest)
assert baseline.returncode==normal.returncode==corrected.returncode==0 and broken.returncode==1
