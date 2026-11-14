"""Confirm observed current-HEAD bug and controls; not a green product gate."""
import json,sys
from pathlib import Path
for path in map(Path,sys.argv[1:]):
    r=json.loads(path.read_text()); assert len(r['cases'])==4
    for c in r['cases']:
        assert c['response']['ok'],c
        status=json.loads(c['response']['output']['text'])['agents'][0]['status']
        if c['mode'] in ('role_timeout','shell_timeout'):
            assert status=='timed_out',c
            assert c['marker'] and c['marker']['time']>c['response_time'],c
            assert c['helper'] and c['helper']['state']!='Z',c
            assert c['child_core'] is None,c
            print('BUG reproduced:',c['mode'],'writes after timeout by',round(c['marker']['time']-c['response_time'],3),'s')
        else:
            assert c['marker'] is None and (c['helper'] is None or c['helper']['state']=='Z'),c
            assert status==('cancelled' if c['mode']=='shell_cancel' else 'errored'),c
            print('CONTROL pass:',c['mode'])
