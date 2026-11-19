"""Check a pinned checkout's legacy AgentControl harness without building Core."""
import argparse,json,sys,tomllib,uuid
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument('core',type=Path);core=a.parse_args().core.resolve()
hs=core/'examples/performance/history-scale';sys.path.insert(0,str(hs))
from fixtures import profile
from launcher import plan
raw=tomllib.loads(profile('synthetic_reference_module',1));modules=raw['modules']
assert 'session_storage' not in modules
assert not any('session_storage' in comp['exports'] for comp in raw['components'].values())
src=core/'crates/proteus-core/src'
http=(src/'app_server/http.rs').read_text()
assert 'config.modules.session_storage.is_some()' in http
child=(src/'core/agent_control/process/child.rs').read_text()
flagseq=['.arg("--new-session")','.arg("--parent-session-id")','.arg(parent_session_id.to_string())','.args(extra_args)','.arg("server")','.arg("stdio")']
assert sorted(child.index(s) for s in flagseq)==[child.index(s) for s in flagseq]
try: plan(['--config','<config>','--cwd','<workspace>','--new-session','--parent-session-id',str(uuid.uuid4()),'server','stdio'],{'version':1})
except ValueError as error: actual_error=str(error)
else: raise AssertionError('fixture unexpectedly accepted pinned argv')
assert 'while self.session.is_none()' in child and 'fn observe_session(' in child
observer=child.split('fn observe_session(')[1]
assert 'AppServerEvent::Runtime' in observer and 'Event::SessionStarted' in observer and 'SessionSnapshot' not in observer
builder=(src/'core/runtime/builder.rs').read_text()
assert 'resume_history && resumed_view.map_or(!history.is_empty(), |(_, count)| count > 0)' in builder
stdio=(src/'app_server/stdio/session.rs').read_text()
assert 'emit no second' in stdio and 'SessionStarted' in stdio
metrics=(hs/'measurement.py').read_text()
assert 'if executable == str(args.module):' in metrics
print(json.dumps({'real_profile_has_storage_slot':False,'real_profile_has_storage_export':False,'actual_launcher_result':actual_error,'source_checks':['HTTP requires storage selection','parent startup includes --parent-session-id UUID','resumed populated runtime suppresses duplicate SessionStarted','AgentControl bootstrap only observes Runtime/SessionStarted','storage process omitted from legacy subject classifier'],'scope':'profile/launcher executed; protocol checks source-based, not timed runs'},indent=2))
