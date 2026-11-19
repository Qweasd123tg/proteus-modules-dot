import csv,collections,pathlib,statistics
p=pathlib.Path(__file__).parent
for v in ['base','after']:
 ds=collections.defaultdict(list)
 for i in range(1,5):
  groups=collections.defaultdict(list)
  for name,rep,wall,_,__,cpu,*_ in csv.reader((p/v/f'times-{i}.csv').open()):
   if int(rep)>0: groups[name].append(int(cpu))
  for name,x in groups.items(): ds[name].append(round(statistics.median(x)/1000,2))
 print(v,dict(ds))
