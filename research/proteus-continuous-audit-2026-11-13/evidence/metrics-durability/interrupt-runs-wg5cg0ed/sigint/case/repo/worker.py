
from pathlib import Path
import errno, json, os, resource, signal, sqlite3, sys
sys.path.insert(0, '/runtime')
from open_code_native import save_usage
state = Path('/state/native')
db = Path(os.environ['XDG_DATA_HOME']) / 'opencode/opencode.db'
db.parent.mkdir(parents=True, exist_ok=True)
model = {'id':'fixture-model', 'providerID':'openai', 'variant':'high'}
with sqlite3.connect(db) as c:
    c.executescript("""CREATE TABLE session_v2(id TEXT, model TEXT, tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER, idle_outcome TEXT);
CREATE TABLE session_message(session_id TEXT, type TEXT, data TEXT);
CREATE TABLE credential(id TEXT);""")
    c.execute('INSERT INTO session_v2 VALUES (?,?,?,?,?,?,?,?)', ('session', json.dumps(model), 30, 12, 0, 0, 0, 'succeeded'))
    c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','user','{}'))
    for i, (tokens, finish, content) in enumerate([(10,'tool-calls',[{'type':'tool','name':'read'}]),(20,'stop',[])]):
        msg = dict(model=model, tokens=dict(input=tokens, output=6, reasoning=0, cache=dict(read=0,write=0)), finish=finish, time=dict(created=100+i*10,completed=101+i*10), content=content)
        c.execute('INSERT INTO session_message VALUES (?,?,?)', ('session','assistant',json.dumps(msg)))
# Control snapshot proves all data had been committed and extractor can read it.
control=Path('/state/fresh-snapshot-control')
control.mkdir()
save_usage(control, db, after_logout=False)

Path('/state/ready').write_text('committed 30 input tokens; 1 tool')
import time
while True:
    time.sleep(10)
