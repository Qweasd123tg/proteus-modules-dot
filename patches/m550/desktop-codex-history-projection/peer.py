import json,sys

def history(cursor):
    if cursor == 'malformed-object':
        return {'data': {'unexpected': []}}
    if cursor == 'malformed-envelope':
        return ['not', 'an', 'object']
    if cursor == 'alternate':
        return {
          'data': [None, 7, [], {}, {'item': None}, {'item': {'type':'agentMessage', 'text':'invalid id'}},
                   {'item': {'id':'without-type'}},
                   {'turnId':3,'startedAtMs':'2','item': {'id':'fallback', 'type':'agentMessage', 'text': [], 'status': 3}},
                   {'turnId':'then','startedAtMs':0,'item': {'id':'view', 'type':'futureKind', 'review':'🦀 then'}}],
          'nextCursor': 19,
        }
    assert cursor == 'stored-cursor', cursor
    rows = []
    for i in range(50):
        item = {'id':f'row:{i}', 'type':'agentMessage' if i%2==0 else 'plan',
                'text':(f'стр:{i} ' + 'я🦀\n'*15200)}
        if i == 0:
            # Multibyte code point straddles the display cap (but not the wire cap).
            item['text'] = 'x'*(128*1024-1)+'🦀 beyond the cap'
            item['status'] = 'inProgress'
        elif i == 1:
            # Exactly the display cap: no suffix and no truncation.
            item['text'] = 'Я'*(64*1024)
        elif i == 2:
            item = {'id':'row:2','type':'mcpToolCall','server':'fixture','tool':'read',
                    'arguments':{'beta':[2,1],'alpha':{'path':'fixture'}}, 'result':{'zeta':0,'alpha': True}}
        elif i == 3:
            item = {'id':'row:3','type':'reasoning','summary':[{'text':'a'},'β',{'noise':5}]}
        rows.append({'turnId':f'turn:{i//5}','startedAtMs':1000+i,'item':item})
    return {'data':rows, 'nextCursor':'alternate', 'ignored': 'x'*65536}

for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    p=msg.get('params',{})
    if msg['method']=='initialize':
        result={}
    elif msg['method']=='thread/resume':
        assert p=={'threadId':'opaque-thread','excludeTurns':True}, p
        result={'thread':{'id':'opaque-thread', 'cwd':'/synthetic','name':'Fixture',
                          'status':{'type':'active'}},
                'itemsBackwardsCursor':'stored-cursor'}
    elif msg['method']=='thread/turns/list':
        assert p=={'threadId':'opaque-thread','limit':1,'sortDirection':'desc','itemsView':'notLoaded'},p
        result={'data':[{'id':'live-turn','status':'inProgress'}]}
    elif msg['method']=='thread/items/list':
        assert p['threadId']=='opaque-thread' and p['limit']==50 and p['sortDirection']=='desc',p
        result=history(p.get('cursor'))
    elif msg['method']=='thread/unsubscribe':
        result={}
    else:
        assert False,msg
    data=json.dumps({'id':msg['id'],'result':result},ensure_ascii=False,separators=(',',':'))
    if msg['method']=='thread/items/list' and p.get('cursor')=='stored-cursor':
        assert 4*1024*1024 < len(data.encode('utf8')) < 8*1024*1024
    print(data,flush=True)
