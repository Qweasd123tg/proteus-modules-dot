"""Run real benchmark/extractor with an OS-enforced partial export failure.
No model, native credentials, or production files are used.
"""
from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

SOURCE = Path('/workspace/shared/proteus-review-20261112/core')
HARNESS = SOURCE / 'examples/performance/coding-harness'
sys.path.insert(0, str(HARNESS))
import runner
import adapters

WORKER = r'''
from pathlib import Path
import errno, json, os, resource, signal, sqlite3, sys
sys.path.insert(0, '/runtime')
from open_code_native import save_usage
state = Path('/state/native')
db = Path(os.environ['XDG_DATA_HOME']) / 'opencode/opencode.db'
db.parent.mkdir(parents=True, exist_ok=True)
model = {'id':'fixture-model', 'providerID':'openai', 'variant':'high'}
with sqlite3.connect(db) as c:
    c.executescript(''' + '"""' + '''CREATE TABLE session_v2(id TEXT, model TEXT, tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER, idle_outcome TEXT);
CREATE TABLE session_message(session_id TEXT, type TEXT, data TEXT);
CREATE TABLE credential(id TEXT);''' + '"""' + ''')
    c.execute('INSERT INTO session_v2 VALUES (?,?,?,?,?,?,?,?)', ('session', json.dumps(model), 30, 12, 0, 0, 0, 'succeeded'))
    c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','user','{}'))
    for i, (tokens, finish, content) in enumerate([(10,'tool-calls',[{'type':'tool','name':'read'}]),(20,'stop',[])]):
        msg = dict(model=model, tokens=dict(input=tokens, output=6, reasoning=0, cache=dict(read=0,write=0)), finish=finish, time=dict(created=100+i*10,completed=101+i*10), content=content)
        c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','assistant',json.dumps(msg)))
# Control snapshot proves all data had been committed and extractor can read it.
control=Path('/state/fresh-snapshot-control')
control.mkdir()
save_usage(control, db, after_logout=False)
# Affect only this synthetic subprocess. Real Path.write_text gets a short write
# and EFBIG, as it could on a bounded output filesystem. Parent can still export.
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (256,256))
try:
    save_usage(state, db)
except OSError as error:
    assert error.errno == errno.EFBIG, repr(error)
    print('synthetic export failed with EFBIG after partial write', file=sys.stderr)
    sys.exit(1)
raise AssertionError('export unexpectedly succeeded')
'''


def run_case(root, remove_invalid=False):
    case=root/'case'; (case/'repo').mkdir(parents=True)
    (case/'repo/worker.py').write_text(WORKER)
    (case/'prompt.txt').write_text('synthetic metrics test\n')
    output=root/'output'
    def prepare(args, runtime):
        (runtime/'home').mkdir()
        (runtime/'native').mkdir()
        (runtime/'native/registry.json').write_text('{}')
        return ['/usr/bin/python3','/workspace/worker.py'], [(HARNESS/'open_code_native.py','/runtime/open_code_native.py')]
    original = runner.run_turns
    def run_then_control(*args, **kwargs):
        original(*args, **kwargs)
        invalid=output/'runtime/native/usage.json'
        assert invalid.stat().st_size == 256
        (root/'invalid-usage.json').write_bytes(invalid.read_bytes())
        if remove_invalid:
            invalid.unlink()
    argv=['runner.py','--agent','opencode','--case-dir',str(case),'--output',str(output),'--binary','/usr/bin/python3','--model','openai/fixture-model','--reasoning','high','--timeout','10']
    with patch.object(sys,'argv',argv), patch.object(adapters,'prepare',side_effect=prepare), patch.object(runner,'run_turns',side_effect=run_then_control):
        code=runner.main()
    report=json.loads((output/'result.json').read_text())
    expected=json.loads((output/'runtime/fresh-snapshot-control/usage.json').read_text())
    result=dict(exit_code=code, pipeline_ok=report['pipeline_ok'], timed_out=report['timed_out'],
                metrics_error=report['metrics'].get('error'),
                recorded_input=report['metrics'].get('provider_usage',{}).get('input_tokens'),
                expected_input=expected['sessions'][0]['tokens_input'],
                recorded_actions=report['metrics'].get('all_tool_calls'),
                expected_actions=sum(len(m['tools']) for m in expected['assistant_messages']),
                usage_file_bytes=(output/'runtime/native/usage.json').stat().st_size,
                database_removed=not(output/'runtime/home/.local/share/opencode/opencode.db').exists(),
                auth_removed=report['auth_removed'])
    return result

if __name__=='__main__':
    evidence=Path(__file__).parent
    root=Path(tempfile.mkdtemp(prefix='export-runs-',dir=evidence))
    actual=run_case(root/'invalid-exists')
    control=run_case(root/'remove-invalid',remove_invalid=True)
    result=dict(head='89997df995df7c39b713e16aba216ecb19c8f497', root=str(root), actual=actual, control=control)
    (evidence/'partial-export-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    assert actual['metrics_error'] and actual['recorded_input'] is None and actual['database_removed']
    assert control['metrics_error'] is None and control['recorded_input']==30 and control['recorded_actions']==1
    assert not actual['pipeline_ok'] and not control['pipeline_ok']
