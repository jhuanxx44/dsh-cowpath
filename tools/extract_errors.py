#!/usr/bin/env python3
"""提取全部会话的每条 isError 报错：模板、原始文本(截断)、是否配对、tool、会话。"""
import json, os, re, sys
from collections import defaultdict

def text_of(c):
    if isinstance(c, str): return c
    if isinstance(c, list): return ' '.join(text_of(x) for x in c)
    if isinstance(c, dict):
        if c.get('type')=='text': return c.get('text','')
        if c.get('type')=='tool-result': return text_of(c.get('content'))
        return ''
    return ''

def template(s, maxlen=160):
    s = s[:maxlen]
    s = re.sub(r'/[\w./\-]+(?:\.\w+)?', '<path>', s)
    s = re.sub(r'"[^"]*"', '<str>', s)
    s = re.sub(r'\b[\w-]{20,}\b', '<id>', s)
    s = re.sub(r'\b\d+(?:\.\d+)?\b', '<num>', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:130]

paths = [l.strip() for l in open('/tmp/ppt_all.txt') if l.strip()]
out = []
for f in paths:
    raw = os.popen(f'zstd -d -c "{f}" 2>/dev/null').read()
    turns = defaultdict(list)
    for line in raw.splitlines():
        if not line.strip(): continue
        try: o=json.loads(line)
        except: continue
        t=o.get('type')
        if t=='tool/call':
            d=o['data']; key=(d.get('turn'),d.get('step'))
            turns.setdefault(key,[]).append({'name':d.get('name'),'ok':None,'err':'','callId':d.get('callId')})
        elif t=='tool/result':
            d=o['data']; key=(d.get('turn'),d.get('step'))
            seq=turns.get(key)
            if not seq: continue
            rec=seq[-1]
            if rec['ok'] is not None: continue
            msg=d.get('message',{})
            for c in msg.get('content',[]):
                if isinstance(c,dict) and c.get('type')=='tool-result':
                    rec['ok'] = not c.get('isError')
                    rec['err'] = text_of(c.get('content'))[:500] if c.get('isError') else ''
    for key, seq in turns.items():
        for i, rec in enumerate(seq):
            if rec['ok'] is False:
                paired = any(r['name']==rec['name'] and r['ok'] for r in seq[i+1:])
                out.append({'tool':rec['name'],'err':rec['err'],'paired':paired,
                            'tpl':template(rec['err']),'sess':os.path.basename(os.path.dirname(f))})
print(f'total errors: {len(out)}')
with open('/tmp/all_errors.json','w') as fh:
    json.dump(out, fh, ensure_ascii=False)
# 模板汇总（含配对率）
agg = defaultdict(lambda: [0,0,0])  # tpl -> [count, paired, tool_set]
for e in out:
    a = agg[e['tpl']]
    a[0]+=1
    a[1]+= 1 if e['paired'] else 0
for tpl,(c,p,_) in sorted(agg.items(), key=lambda x:-x[1][0]):
    print(f'{c:4d}  pair={p:4d} ({100*p/max(c,1):3.0f}%)  {tpl}')
