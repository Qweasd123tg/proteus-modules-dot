"""Desired invariant: a terminal peer timeout/cancel must leave no active helper."""
import json,sys
failed=0
for c in json.load(open(sys.argv[1]))['cases']:
    good=(c['marker'] is None and (c['helper'] is None or c['helper']['state']=='Z'))
    print(('PASS' if good else 'FAIL'),c['mode'],': helper must stop before reporting peer terminal outcome')
    failed+=not good
sys.exit(bool(failed))
