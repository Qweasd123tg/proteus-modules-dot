"""Integer/fraction reference for every two-exercise count combination of sizes 1..4."""
from fractions import Fraction as F
from itertools import product
from math import isclose
from pathlib import Path
import importlib.util
import random
import sys
if len(sys.argv) != 3:
    raise SystemExit("usage: python3 -B paired-oracle.py BASE_CORE_TREE PATCHED_CORE_TREE")
roots = dict(zip(("base", "candidate"), map(Path, sys.argv[1:])))
src=Path('examples/performance/coding-harness/polyglot_report.py')
def load(variant):
    spec=importlib.util.spec_from_file_location(variant,roots[variant]/src)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.cluster_interval

def quantile(values,fraction):
    x=sorted(values); pos=F(len(x)-1)*fraction
    i=pos.numerator//pos.denominator
    return x[i]+(x[min(i+1,len(x)-1)]-x[i])*(pos-i)

def pair_from(group,traits):
    size,first,second=traits
    return [{'a':{'exercise':group,'passed':i<first},'b':{'exercise':group,'passed':i<second}} for i in range(size)]

seed=17
reps=32
rng=random.Random(seed)
multiplicities=[rng.choices((0,1),k=2).count(0) for _ in range(reps)]
assert set(multiplicities)=={0,1,2}
funcs=[load(v) for v in ['base','candidate']]
variants=[(n,a,b) for n in range(1,5) for a,b in product(range(n+1),repeat=2)]
cases=constant=nonconstant=0; mismatches=[0,0]; arms_moved=0
for left,right in product(variants,repeat=2):
    cases+=1
    (n1,a1,b1),(n2,a2,b2)=left,right
    deltas=[F(k*(a1-b1)+(2-k)*(a2-b2), k*n1+(2-k)*n2) for k in multiplicities]
    pure_const = min(deltas)==max(deltas)
    if pure_const: constant+=1
    else: nonconstant+=1
    bounds=None if pure_const else [quantile(deltas,F(1,40)),quantile(deltas,F(39,40))]
    rows=pair_from('l',left)+pair_from('r',right)
    outputs=[fn(rows,['a','b'],'passed',reps,seed) for fn in funcs]
    arms_moved+=int(outputs[0]['arms']!=outputs[1]['arms'])
    for version,got in enumerate(outputs):
        d=got['delta']
        checks=[d['rate']==float(F(a1-b1+a2-b2,n1+n2)),d['bootstrap_degenerate']==pure_const,
                d['interval_informative']==(not pure_const)]
        if pure_const:
            checks.append(d['ci95'] is None)
        else:
            checks.append(d['ci95'] is not None and all(isclose(obs,float(truth),rel_tol=0,abs_tol=3e-16) for obs,truth in zip(d['ci95'],bounds)))
        mismatches[version]+=int(not all(checks))
print(f'{cases} ordered two-cluster scenarios (sizes 1..4; all possible marginal pass counts).')
print(f'Exact rational constant: {constant}; genuinely nonconstant: {nonconstant}.')
print(f'Passed point-rate and interval-status/bounds checks: before {cases-mismatches[0]}/{cases}, after {cases-mismatches[1]}/{cases}.')
print(f'Comparison of full arm summaries before/after: {arms_moved} changes.')
assert mismatches[0]>0 and mismatches[1]==0 and not arms_moved
