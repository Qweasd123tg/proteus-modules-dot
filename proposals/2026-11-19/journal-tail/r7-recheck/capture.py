from pathlib import Path
import json,re,time,runpy
out=Path(__file__).resolve().parent
snapshot=runpy.run_path(str(out/'read-events.py'))['snapshot']
deadline=time.monotonic()+155
while time.monotonic()<deadline:
  runs=list(Path('/tmp').glob('proteus-r8-explicit-mock-events-*'))
  if len(runs)==1 and (out/'observe.log').is_file():
    m=re.search(r'CASE display=50000 active=100 journal_bytes=(\d+)\nSETTLE_BEGIN',(out/'observe.log').read_text())
    if m:
      js=list(runs[0].rglob('journal.jsonl'))
      assert len(js)==1
      data=snapshot(js[0],int(m[1]))
      (out/'observe-events.json').write_text(json.dumps(data,indent=2)+'\n')
      print(data)
      break
  time.sleep(.2)
else: raise TimeoutError('no complete newly generated case')
