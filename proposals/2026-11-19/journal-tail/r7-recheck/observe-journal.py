"""Extra run, no changes to the timed AB/BA. Observe only our synthetic journal's six terminal events."""
from pathlib import Path
import subprocess, os, json, tempfile, re, time
repo=Path(__file__).resolve().parents[1]
out=repo/'perf-r8-baseline'
bench=repo/'perf-r7-parent/bench-candidate'
while not (out/'A2.exit').is_file(): time.sleep(1)
with tempfile.TemporaryDirectory(prefix='proteus-r8-explicit-mock-events-') as td, (out/'observe.log').open('w') as log:
    env=dict(os.environ, TMPDIR=td, PERF7_CASES='50000', PROTEUS_TEST_SESSION_STORAGE_MODULE=str(repo/'perf-r7-storage/after/worker'), PROTEUS_TEST_REFERENCE_MODULE=str(repo/'perf-round3-core/module-target/debug/proteus-reference-module'))
    with subprocess.Popen(['taskset','-c','2',str(bench),'--exact','app_server::http::tests::session_reads::perf7_real_turn_fixed_active_history','--nocapture','--test-threads=1'],cwd=repo/'perf-r7-parent/candidate',env=env,stdout=log,stderr=subprocess.STDOUT) as p:
        while p.poll() is None:
            m=re.search(r'CASE display=50000 active=100 journal_bytes=(\d+)\nSETTLE_BEGIN',(out/'observe.log').read_text())
            if m:
                journals=list(Path(td).rglob('journal.jsonl'))
                if len(journals)!=1: raise AssertionError(journals)
                import runpy
                data=runpy.run_path(str(out/'read-events.py'))['snapshot'](journals[0],int(m[1]))
                (out/'observe-events.json').write_text(json.dumps(data,indent=2)+'\n')
                break
            time.sleep(.2)
        code=p.wait()
        (out/'observe.exit').write_text(str(code)+'\n')
        assert code==0 and (out/'observe-events.json').exists()
