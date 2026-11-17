"""Exercise only the report's source-list expression, then parse and resolve its actual links."""
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urljoin, urlsplit, unquote

import sys
if len(sys.argv) != 3:
    raise SystemExit("usage: python3 report-links.py BASE_CORE_TREE PATCHED_CORE_TREE")
TREES = dict(zip(("base", "candidate"), map(Path, sys.argv[1:])))
FILE = Path('examples/performance/summarize.py')

def emit(variant, cases):
    body=ast.parse((TREES[variant] / FILE).read_text()).body
    display=[x for x in body if isinstance(x, ast.FunctionDef) and x.name in ('escape','source_link')]
    imports=[x for x in body if isinstance(x,ast.ImportFrom) and x.module=='urllib.parse']
    main=next(x for x in body if isinstance(x,ast.FunctionDef) and x.name=='main')
    exact=[x for x in main.body if isinstance(x,ast.AugAssign) and any(isinstance(n,ast.Constant) and n.value=='## Исходные отчёты' for n in ast.walk(x))]
    assert len(exact)==1
    g={'lines':[],'sources':[('build','before',path) for path in cases]}
    exec(compile(ast.Module(imports+display+exact,type_ignores=[]),str(FILE),'exec'),g)
    return '\n'.join(g['lines'])

class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data=[]
        self.lis=[]
        self.in_anchor=False
    def handle_starttag(self,name,attrs):
        if name=='li': self.lis.append([])
        if name=='a':
            self.in_anchor=True
            self.lis[-1].append([dict(attrs)['href'],''])
    def handle_endtag(self,name):
        if name=='a': self.in_anchor=False
    def handle_data(self,txt):
        if self.in_anchor: self.lis[-1][-1][1]+=txt

def open_targets(text,files,summary):
    rendered=subprocess.check_output(['pandoc','-f','gfm','-t','html5','--wrap=none'],input=text.encode())
    parser=Anchors();parser.feed(rendered.decode())
    assert len(parser.lis)==len(files)
    outcomes={}
    for path,links in zip(files,parser.lis):
        if len(links)!=1:
            outcomes[path.name]=('no single link',None);continue
        href,label=links[0]
        dest=urlsplit(urljoin(summary.as_uri(),href))
        # All inputs are controlled local paths. No HTTP request is made.
        assert dest.scheme=='file' and not dest.netloc
        local=Path(unquote(dest.path))
        if local!=path or dest.query or dest.fragment:
            other=json.loads(local.read_text())['fixture'] if local in files else None
            outcomes[path.name]=('wrong destination',other);continue
        assert json.loads(local.read_text())['fixture']==path.name
        if label!=str(path):
            outcomes[path.name]=('incorrect visible path',None);continue
        outcomes[path.name]=('ok',None)
    return outcomes

def check():
    names=['plain.json','name with space.json','Замер №2.json','a(b).json',
           'build #2.json','delta?baseline.json','literal%20space.json','literal space.json',
           'a>b.json','part[work.json','part]work.json','work[2].json','a|b.json',
           r'posix\[test].json','part%2Flog.json','at#stage?x%20[1].json']
    with tempfile.TemporaryDirectory(prefix='perf-links-') as td:
        paths=[Path(td)/name for name in names]
        for path in paths: path.write_text(json.dumps({'fixture':path.name}))
        summary=Path(td)/'summary.md'
        products={}
        for variant in ('base','candidate'):
            raw=emit(variant,paths)
            outcomes=open_targets(raw,paths,summary)
            failures={p:result for p,result in outcomes.items() if result[0]!='ok'}
            print(f'{variant}: {len(outcomes)-len(failures)}/{len(outcomes)} opened exact file and displayed same path')
            for p,(why,other) in failures.items():
                print(f'  {p!r}: {why}'+(f' -> different existing source {other!r}' if other else ''))
            products[variant]=outcomes
        for p in ['plain.json','name with space.json','Замер №2.json','a(b).json','work[2].json','a|b.json']:
            assert products['base'][p][0]=='ok'
        assert products['base']['literal%20space.json']==('wrong destination','literal space.json')
        assert products['base']['build #2.json'][0]=='wrong destination'
        assert products['base']['a>b.json'][0]=='no single link'
        assert all(state=='ok' for state,_ in products['candidate'].values())
if __name__=='__main__': check()
