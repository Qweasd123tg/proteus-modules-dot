from pathlib import Path
import sys,csv,subprocess as s,statistics as st
h=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
out=csv.writer(sys.stdout);out.writerow('round build archive batch active text_bytes fold_ns final_ns fold_allocs fold_alloc_bytes final_allocs final_alloc_bytes'.split())
for i in range(4):
 for args in [(2000,100,100,160),(10000,100,100,160),(20000,100,100,160)]:
  for mode in (('base','after') if i%2==0 else ('after','base')):
   vals=s.check_output([str(h/mode/'probe'),*map(str,args)],text=True).strip().split(',')
   out.writerow((i+1,mode,*vals));sys.stdout.flush()
