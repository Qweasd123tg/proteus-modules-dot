from pathlib import Path
import re,subprocess
def build(root,override,here):
    def src(f):
        p=Path('src/ui/extensions/declarative')/(f+'.rs')
        if (override/p).exists():return (override/p).read_text()
        if (root/p).exists():return (root/p).read_text()
        return subprocess.check_output(['git','--git-dir='+str(root),'show','2307e9c:'+str(p)],text=True)
    def method(t,n):
        m=re.search(r'(?m)^    (?:pub(?:\(super\))? )?fn '+n+r'\(',t)
        first=t[m.start():].splitlines()[0]
        if first.endswith("{}"):return first
        return t[m.start():t.index('\n    }',m.start())+6]
    def block(t,a,b):
        i=t.index(a);return t[i:t.index(b,i)]
    F,R,T,G,L,La=map(src,['fields','rows','tree','graph','list','lanes'])
    patched='struct WidgetAction' in F
    frame=(here/'frame.rs.in').read_text()
    repl={}
    for k in ['Graph','Tree','Lanes','List']:
        i=F.index('            Node::'+k+' {',F.index('fn prepare_fields_in('))
        j=F.index('\n            }\n', F.index('=> {',i))+14
        repl[k]=F[i:j]
    repl['binding']=block(F,'pub(super) struct WidgetAction','pub(super) enum Text') if patched else ''
    repl['bind']=method(F,'widget_action' if patched else 'row_sender')
    repl['rows.struct']=block(R,'pub(super) struct Rows','impl<K: Kind> Rows')
    repl['rows.methods']='\n'.join(method(R,n) for n in ['new','set_rows','act_at','key'])
    repl['tree.struct']=block(T,'pub(super) struct Tree','/// Where a moving fold')
    repl['tree.methods']='\n'.join(method(T,n) for n in ['new','set_rows','fold_key','act_at','act','step','key'])
    repl['folds']=T[T.index('fn children(rows:'):].split('#[cfg(test)]')[0]
    repl['tree.action']= '' if patched else next(x for x in T.split('\n') if 'type RowAction' in x)
    repl['graph.struct']=block(G,'pub(super) struct Graph','impl Graph')
    repl['graph.methods']='\n'.join(method(G,n) for n in ['new','set_data'])
    repl['graph.click']=next(x.strip() for x in G.splitlines() if '(this.selected)(select.clone()' in x or 'this.action.emit(select.clone()' in x)
    repl['kind.lanes']='\n'.join(method(La,n) for n in ['id','selected','measure'])
    repl['kind.list']='\n'.join(method(L,n) for n in ['id','selected','measure'])
    repl['setcol']=method(La,'set_columns')
    repl["kind.list"]=repl["kind.list"].replace("Row","crate::list::Row");repl["kind.lanes"]=repl["kind.lanes"].replace("Row","crate::lanes::Row")
    for k,v in repl.items():frame=frame.replace('@'+k+'@',v)
    if not patched:frame=frame.replace('use super::fields::WidgetAction;', '')
    assert '@' not in frame
    return frame+(here/'oracle.rs.in').read_text()
