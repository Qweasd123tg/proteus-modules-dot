"""Offline two-turn runner regression using an owned synthetic SQLite DB."""
from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

SOURCE = Path('/workspace/shared/benchmark-execution-audit')
HARNESS = SOURCE / 'examples/performance/coding-harness'
sys.path.insert(0, str(HARNESS))
import runner
import adapters

WORKER = r"""
from pathlib import Path
import json, os, sqlite3, sys, time
sys.path.insert(0, '/runtime')
from open_code_native import save_usage
state = Path('/state/native')
db = Path(os.environ['XDG_DATA_HOME']) / 'opencode/opencode.db'
db.parent.mkdir(parents=True, exist_ok=True)
model = {'id': 'fixture-model', 'providerID': 'openai', 'variant': 'high'}
first = not db.exists()
with sqlite3.connect(db) as c:
    if first:
        c.executescript('''CREATE TABLE session_v2(id TEXT, model TEXT, tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER, idle_outcome TEXT);
CREATE TABLE session_message(session_id TEXT, type TEXT, data TEXT);
CREATE TABLE credential(id TEXT);''')
        c.execute('INSERT INTO session_v2 VALUES (?,?,?,?,?,?,?,?)', ('session', json.dumps(model), 10, 5, 0, 0, 0, 'succeeded'))
        c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session', 'user', '{}'))
        msg = dict(model=model, tokens=dict(input=10, output=5, reasoning=0, cache=dict(read=0,write=0)), finish='stop', time=dict(created=100,completed=101), content=[])
        c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','assistant',json.dumps(msg)))
    else:
        c.execute("UPDATE session_v2 SET tokens_input=30, tokens_output=12, idle_outcome='running'")
        c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','user','{}'))
        msg = dict(model=model, tokens=dict(input=20, output=7, reasoning=0, cache=dict(read=0,write=0)), finish='tool-calls', time=dict(created=200,completed=201), content=[dict(type='tool', name='read')])
        c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','assistant',json.dumps(msg)))
if first:
    save_usage(state, db)
else:
    # Independent read proves the committed DB contains the second turn.
    expected = Path('/state/fresh-snapshot-control')
    expected.mkdir()
    save_usage(expected, db, after_logout=False)
    while True:
        time.sleep(10)
"""

def run_case(root, remove_snapshot=False):
    case = root / 'case'
    (case / 'repo').mkdir(parents=True)
    (case / 'repo/fake_native.py').write_text(WORKER)
    (case / 'prompt.txt').write_text('first prompt\n')
    (case / 'followups.json').write_text(json.dumps(['second prompt']))
    output = root / 'result'
    def prepare(args, runtime):
        (runtime/'home').mkdir()
        state = runtime/'native'
        state.mkdir()
        (state/'registry.json').write_text('{}')
        return ['/usr/bin/python3','/workspace/fake_native.py','--prompt','first prompt'], [(HARNESS/'open_code_native.py','/runtime/open_code_native.py')]
    original_run_turns = runner.run_turns
    def run_then_mark_absent(*args, **kwargs):
        original_run_turns(*args, **kwargs)
        if remove_snapshot:
            (output/'runtime/native/usage.json').unlink()
    argv = ['runner.py','--agent','opencode','--case-dir',str(case),'--output',str(output), '--binary','/usr/bin/python3','--model','openai/fixture-model','--reasoning','high','--timeout','1']
    with patch.object(sys, 'argv', argv), patch.object(adapters,'prepare',side_effect=prepare), patch.object(runner,'run_turns',side_effect=run_then_mark_absent):
        exit_code = runner.main()
    report = json.loads((output/'result.json').read_text())
    stale = json.loads((output/'runtime/native/usage.json').read_text())
    expected = json.loads((output/'runtime/fresh-snapshot-control/usage.json').read_text())
    return dict(exit_code=exit_code, timed_out=report['timed_out'], pipeline_ok=report['pipeline_ok'],
                turn_returncodes=[r['returncode'] for r in report['turns']],
                actual_user_turns=stale['user_turns'], expected_user_turns=expected['user_turns'],
                actual_assistant_messages=len(stale['assistant_messages']), expected_assistant_messages=len(expected['assistant_messages']),
                actual_input=report['metrics']['provider_usage']['input_tokens'], expected_input=expected['sessions'][0]['tokens_input'],
                actual_actions=report['metrics']['all_tool_calls'], expected_actions=sum(len(m['tools']) for m in expected['assistant_messages']),
                actual_partial=stale['partial'], actual_settled=report['metrics']['settled'],
                runtime_database_removed=not (output/'runtime/home/.local/share/opencode/opencode.db').exists())

root = Path(tempfile.mkdtemp(prefix='stale-snapshot-runs-', dir=Path(__file__).parent))
actual = run_case(root/'existing-snapshot')
control = run_case(root/'missing-snapshot', remove_snapshot=True)
result = dict(source_head='89997df995df7c39b713e16aba216ecb19c8f497', existing_snapshot=actual, missing_snapshot_control=control)
(Path(__file__).parent/'stale-snapshot-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
assert actual['timed_out'] and not actual['pipeline_ok']
assert actual['actual_user_turns'] == {'session':1} and actual['expected_user_turns'] == {'session':2}
assert actual['actual_input'] == 10 and actual['expected_input'] == 30
assert control['actual_user_turns'] == {'session':2} and control['actual_input'] == 30
