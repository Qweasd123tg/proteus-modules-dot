"""Benign local Stop command fixture, only checks returned text."""
import json,sys,pathlib
payload=json.load(sys.stdin)
with pathlib.Path(sys.argv[1]).open('a') as f:f.write(json.dumps(payload)+'\n')
if 'REVIEW_ACK' not in payload.get('last_assistant_message',''):
    print('The candidate lacks the required completion acknowledgement. Append exactly REVIEW_ACK to your next final answer.',file=sys.stderr)
    sys.exit(2)
