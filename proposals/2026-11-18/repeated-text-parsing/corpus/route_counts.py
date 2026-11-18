"""Count actual parser invocations on fresh complete documents and unchanged redelivery."""
import argparse
import collections
import json
from pathlib import Path
import subprocess
import tempfile

from equivalence import as_line, sources


def run(binary, corpus):
    names = [name for name, _ in corpus for _ in range(2)]
    stats = {}
    for group in ('commonmark', 'project_docs'):
        for stage in ('fresh','unchanged'):
            stats[group + '/' + stage] = {'views':0,'parser_calls':collections.Counter(),
                                         'parser_input_bytes':collections.Counter()}
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp)/'inputs'
        with inp.open('wb') as out:
            out.write(as_line({'type':'hello','protocol':4,'workspace':'/fixture','features':['surfaces.content.v1','widgets.rich_text.v1','widgets.rich_text.inlines.v1','widgets.content.v1','widgets.code_embedded.v1']}))
            for ix, (_, source) in enumerate(corpus):
                view = f'content:count-{ix}'
                for rev in (1,2):
                    out.write(as_line({'type':'render','context':'scope','surface':'content','session_dir':'/fixture-session','view':view,
                        'content':{'language':'text/markdown','source':source,'source_revision':rev,'context':{'languages':['mermaid','latex']}}}))
                out.write(as_line({'type':'close','view':view}))
        with inp.open('rb') as src:
            p = subprocess.run([binary.resolve()],stdin=src,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=90)
    seen=0
    for line in p.stderr.decode().splitlines():
        fields = line.split()
        if not fields: continue
        if fields[0]=='MDFRAME':
            stage=('fresh','unchanged')[seen%2]
            assert int(fields[1]) == seen % 2 + 1
            group='commonmark' if names[seen].startswith('commonmark-') else 'project_docs'
            assert int(fields[2])==len(corpus[seen//2][1].encode())
            row=stats[group+'/'+stage]
            row['views']+=1
            seen+=1
        elif fields[0]=='MDPASS':
            assert seen and fields[1] in ('route','html','inline','guard')
            row['parser_calls'][fields[1]] += 1
            row['parser_input_bytes'][fields[1]] += int(fields[2])
        else: raise ValueError('Unexpected line from instrumented renderer: '+line[:100])
    assert seen == len(names)
    return stats


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('instrumented_before','instrumented_after','spec','core'):
        parser.add_argument(name,type=Path)
    args=parser.parse_args()
    data=list(sources(args.spec,args.core))
    print(json.dumps({side:run(path,data) for side,path in [('before',args.instrumented_before),('after',args.instrumented_after)]},indent=2))
