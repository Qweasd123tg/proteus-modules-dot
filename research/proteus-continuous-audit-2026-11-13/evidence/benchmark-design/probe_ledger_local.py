from pathlib import Path
import sys,shutil,subprocess,json
ROOT=Path('/workspace/shared/benchmark-design-audit')
HERE=ROOT/'examples/performance/coding-harness'
sys.path.insert(0,str(HERE))
import corpus,long_corpus
E=Path(__file__).resolve().parent
case=E/'ledger-case'
if not (case/'case.json').exists():long_corpus.prepare('ledger-recovery',case)
work=E/'ledger-solution-local'
if work.exists():shutil.rmtree(work)
shutil.copytree(case/'repo',work)
shutil.copytree(case/'grader/reference/ledger',work/'ledger',dirs_exist_ok=True)
graders=E/'local-ledger-grader';graders.mkdir(exist_ok=True)
grader=graders/'test_outputs.py'
original=(case/'grader/test_outputs.py').read_text().replace('"/app"',repr(str(work)))
grader.write_text(original)
def run(label,cmd):
 p=subprocess.run(cmd,cwd=work,capture_output=True,text=True)
 corpus.write_json(E/f'{label}.json',{'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 print(label,p.returncode,p.stdout[-1500:],p.stderr[-200:]);return p
pytest=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',str(grader)]
base=run('ledger-gold-baseline-local',pytest)
# Standard Python import-style refactor only. Every fsync/replace call still
# resolves to exactly the same OS operation outside mocked test contexts.
for name in ('storage.py','store.py','migrate.py'):
 p=work/'ledger'/name
 source=p.read_text().replace('import os\n','import os\nfrom os import fsync, replace\n',1)
 source=source.replace('os.fsync(', 'fsync(').replace('os.replace(', 'replace(')
 p.write_text(source)
public=run('ledger-alias-public-local',[sys.executable,'-B','-m','unittest','discover','-s','tests','-v'])
broken=run('ledger-alias-existing-grader-local',pytest)
# In this controlled reference, patching its actual lookup sites recovers both
# probes without changing the implementation. Not proposed as a general fix.
fixed=original.replace('with patch("os.replace", side_effect=OSError("injected snapshot publication failure")):','with patch("ledger.storage.replace", side_effect=OSError("injected snapshot publication failure")):')
fixed=fixed.replace('with patch("os.fsync", side_effect=sync):','with patch("ledger.store.fsync", side_effect=sync), patch("ledger.storage.fsync", side_effect=sync):')
grader.write_text(fixed)
corrected=run('ledger-alias-correct-lookup-local',pytest)
assert base.returncode==public.returncode==corrected.returncode==0 and broken.returncode==1
