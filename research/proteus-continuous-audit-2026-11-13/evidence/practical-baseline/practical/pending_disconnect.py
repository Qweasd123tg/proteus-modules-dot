import asyncio,json,pathlib,time,hashlib,subprocess
ROOT=pathlib.Path('/workspace/shared/proteus-review-20261112'); BIN=ROOT/'core/target/debug/proteus'; CONF=ROOT/'practical/config.json'; WORK=ROOT/'practical/workspace'
async def main():
 results=[]
 for how in ['eof','cancel','shutdown']:
  p=await asyncio.create_subprocess_exec(str(BIN),'--config',str(CONF),'--cwd',str(WORK),'--new-session','server','stdio',stdin=-1,stdout=-1,stderr=-1)
  rows=[]; p.stdin.write(json.dumps({'type':'send','id':'send','text':'request_user_input choose one'}).encode()+b'\n');await p.stdin.drain()
  deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   line=await asyncio.wait_for(p.stdout.readline(),5); assert line,'EOF before prompt';x=json.loads(line);rows.append(x)
   if x.get('event',{}).get('type')=='user_input_requested':break
  else:raise AssertionError('no input prompt')
  started=time.monotonic()
  if how=='eof':p.stdin.close()
  else:
   command={'type':how,'id':'stop'}
   if how=='cancel':command['target_id']='send'
   p.stdin.write(json.dumps(command).encode()+b'\n');await p.stdin.drain()
  if how=='cancel':
   while True:
    x=json.loads(await asyncio.wait_for(p.stdout.readline(),5));rows.append(x)
    if x.get('type')=='response' and x.get('id')=='send':break
   p.stdin.write(b'{"type":"shutdown","id":"shutdown"}\n');await p.stdin.drain();p.stdin.close()
  async def rest():
   while line:=await p.stdout.readline():rows.append(json.loads(line))
  await asyncio.wait_for(asyncio.gather(rest(),p.wait()),10)
  assert p.returncode==0,(how,p.returncode,(await p.stderr.read()).decode())
  session=[r['event']['envelope']['event']['SessionStarted']['session_dir'] for r in rows if r.get('event',{}).get('type')=='runtime' and 'SessionStarted' in r['event']['envelope']['event']][0]
  session=pathlib.Path(session); journal=session/'journal.jsonl'
  jrows=[json.loads(x) for x in journal.read_text().splitlines()];settled=[x for x in jrows if x['kind']=='turn_settled']
  assert len(settled)==1 and settled[0]['payload']['value']['status']=='canceled',(how,settled)
  resumed=await asyncio.create_subprocess_exec(str(BIN),'--config',str(CONF),'--cwd',str(WORK),'--resume-session',str(session),'after disconnect',stdout=-1,stderr=-1)
  stdout,stderr=await asyncio.wait_for(resumed.communicate(),10);assert resumed.returncode==0,(stdout,stderr)
  assert b'after disconnect' in stdout,stdout
  (ROOT/f'evidence/pending-{how}.json').write_text(json.dumps(rows,indent=2))
  results.append({'method':how,'shutdown_seconds':round(time.monotonic()-started,3),'canceled_record':settled[0],'resume_exit':resumed.returncode,'resume_output':stdout.decode()})
 print(json.dumps(results,indent=2));(ROOT/'evidence/pending-disconnect-results.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
