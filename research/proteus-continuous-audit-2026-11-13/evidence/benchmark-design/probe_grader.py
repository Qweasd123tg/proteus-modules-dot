from pathlib import Path
import sys, shutil, json
ROOT=Path('/workspace/shared/benchmark-design-audit')
HERE=ROOT/'examples/performance/coding-harness'
sys.path.insert(0,str(HERE))
import corpus, long_corpus
E=Path(__file__).resolve().parent
corpus.PYTHON=E/'venv/bin/python'
case=E/'journal-case'
if case.exists() and not (case/'case.json').exists(): shutil.rmtree(case)
if not case.exists(): long_corpus.prepare('journal-segments',case)
base=corpus.grade(case,case/'repo',E/'journal-gold-baseline.json',True)
print('baseline',base['passed'],base['output'][-500:])
# Construct an equivalently implemented solution using a standard-library dataclass
# for the manifest segment metadata. No test/grader files are changed.
work=E/'journal-dataclass-solution'
if work.exists(): shutil.rmtree(work)
shutil.copytree(case/'repo',work)
code=work/'examples/performance/history-scale'
shutil.copy2(case/'grader/reference/journal.py',code/'journal.py')
source=(case/'grader/reference/archive.py').read_text()
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
# Direct regular import and CLI invocation are checked in the same grading sandbox.
probe='''import sys,json
from pathlib import Path
sys.path.insert(0,"examples/performance/history-scale")
from archive import archive
s=Path("/tmp/source");s.mkdir();(s/"journal.jsonl").write_text("")
archive(s,"/tmp/target")
assert json.loads(Path("/tmp/target/journal-manifest.json").read_text())=={"version":1,"segments":[]}
'''
control=corpus.sandbox(work,case/'grader',['/venv/bin/python','-c',probe])
corpus.write_json(E/'journal-dataclass-normal-import.json',control)
print('ordinary import',control)
result=corpus.grade(case,work,E/'journal-dataclass-existing-grader.json')
print('existing grader',result['passed'],result['output'][-1000:])
# Only a disposable grader copy gets the importlib registration correction.
fixed=E/'journal-case-fixed-loader'
if fixed.exists(): shutil.rmtree(fixed)
shutil.copytree(case,fixed)
p=fixed/'grader/test_outputs.py'
text=p.read_text().replace('    spec.loader.exec_module(module)\n','    sys.modules[spec.name] = module\n    try:\n        spec.loader.exec_module(module)\n    except BaseException:\n        sys.modules.pop(spec.name, None)\n        raise\n',1)
p.write_text(text)
info=json.loads((fixed/'case.json').read_text());info['grader_hashes']=corpus.manifest(fixed/'grader');corpus.write_json(fixed/'case.json',info)
result_fixed=corpus.grade(fixed,work,E/'journal-dataclass-fixed-grader.json')
print('fixed grader',result_fixed['passed'],result_fixed['output'][-1000:])
assert base['passed'] and control['returncode']==0 and not result['passed'] and result_fixed['passed']
