import asyncio,json,pathlib,time
ROOT=pathlib.Path('/workspace/shared/proteus-review-20261112')
LOG=ROOT/'evidence/stdio-stress.jsonl'
async def main():
 p=await asyncio.create_subprocess_exec(str(ROOT/'core/target/debug/proteus'),'--config',str(ROOT/'practical/config.json'),'--cwd',str(ROOT/'practical/workspace'),'--new-session','server','stdio',stdin=-1,stdout=-1,stderr=-1)
 responses={}; events=[]; q=asyncio.Queue()
 async def read():
  with LOG.open('w') as log:
   while line:=await p.stdout.readline():
    log.write(line.decode()); x=json.loads(line)
    if x['type']=='response':await q.put(x)
    else:events.append(x)
 task=asyncio.create_task(read())
 async def request(typ,id,**kw):
  p.stdin.write((json.dumps({'type':typ,'id':id,**kw})+'\n').encode());await p.stdin.drain()
  while id not in responses:
   x=await asyncio.wait_for(q.get(),10);responses[x['id']]=x
  return responses.pop(id)
 results=[]; dirs=[]
 try:
  for n in range(30):
   # Unknown cancel and malformed frames must not poison the subsequent valid turn.
   bad=await request('cancel',f'bad-{n}',target_id='does-not-exist')
   assert not bad['ok'],bad
   p.stdin.write(b'{not json}\n');await p.stdin.drain()
   r=await request('send',f'send-{n}',text=f'unique-turn-{n}')
   assert r['ok'] and f'unique-turn-{n}' in r['output']['text'],r
   h=await request('history_summary',f'hist-{n}');assert h['ok'],h
   rot=await request('new_session',f'new-{n}');assert rot['ok'],rot
   dirs.append(rot['output']['session_dir'])
   results.append({'n':n,'send_ok':r['ok'],'history':h['output'],'new':rot['output']})
  assert len(dirs)==len(set(dirs)),dirs
  r=await request('shutdown','shutdown');assert r['ok'],r
  p.stdin.close();await asyncio.wait_for(p.wait(),10);await task
  assert p.returncode==0,await p.stderr.read()
  (ROOT/'evidence/stdio-stress-results.json').write_text(json.dumps({'rounds':30,'exit':p.returncode,'events':len(events),'results':results},indent=2))
  print('PASS: 30 turns + invalid cancellation + malformed request recovery + 30 session rotations; unique durable directories; graceful shutdown')
 finally:
  if p.returncode is None:p.kill();await p.wait()
asyncio.run(main())
