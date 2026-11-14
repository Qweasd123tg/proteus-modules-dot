import sys,signal,pathlib,os
signal.alarm(12)
label=sys.argv[1]
pathlib.Path(label+'.pid').write_text(str(os.getpid()))
print(label+':ready',flush=True)
with open(label+'.received','a') as out:
 for line in sys.stdin:
  out.write(line); out.flush(); print(label+':'+line.strip(),flush=True)
  if line.strip()=='intended-A': break
