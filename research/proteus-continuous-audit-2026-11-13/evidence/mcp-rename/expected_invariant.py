from pathlib import Path
import json,sys
r=json.loads(Path(sys.argv[1]).read_text())
assert r['stepped']['runtime_enabled']=={'db20':False,'db2':True}, 'Typing a name must preserve both servers effective enabled state'
assert r['undo']['runtime_enabled']=={'db':False,'db2':True}, 'Restoring the original name must restore the original draft'
