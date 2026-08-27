#!/usr/bin/env python3
"""cowpath 存量轨迹扫描器：对一组会话 JSONL 做弯路统计 + 报错模板聚类。

用法: python3 /tmp/trail_scan.py <list_file>
list_file: 每行一个 session.jsonl.zstd 的绝对路径
输出: 单个 JSON 对象到 stdout
"""
import json, os, re, sys
from collections import Counter, defaultdict

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
    return s[:120]

def main():
    list_file = sys.argv[1]
    paths = [l.strip() for l in open(list_file) if l.strip()]
    stats = dict(sessions=len(paths), tool_calls=0, errors=0, pair=0,
                 env_like=0, retry=0, error_tools=Counter(),
                 templates=Counter(), examples={}, retry_reasons=Counter())
    turns = defaultdict(list)
    for f in paths:
        raw = os.popen(f'zstd -d -c "{f}" 2>/dev/null').read()
        turn = None
        for line in raw.splitlines():
            if not line.strip(): continue
            try: o=json.loads(line)
            except: continue
            t=o.get('type')
            if t=='tool/call':
                stats['tool_calls']+=1
                d=o['data']; key=(d.get('turn'),d.get('step'))
                turns.setdefault(key,[]).append({'name':d.get('name'),'ok':None,'err':''})
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
                        rec['err'] = text_of(c.get('content'))[:300] if c.get('isError') else ''
            elif t=='llm/retry':
                stats['retry']+=1
                d=o.get('data',{})
                stats['retry_reasons'][(d.get('failure',{}).get('message','?') or '?')[:60]]+=1
    # 配对 + 聚类（按模板）
    for key, seq in turns.items():
        for i, rec in enumerate(seq):
            if rec['ok'] is False:
                stats['errors']+=1
                stats['error_tools'][rec['name']]+=1
                tp = template(rec['err'])
                stats['templates'][tp]+=1
                if tp not in stats['examples']:
                    stats['examples'][tp] = (rec['name'], rec['err'][:240])
                env = any(k in rec['err'] for k in ['429','rate_limit','timeout','overloaded','502','500','stream idle','upstream','no cluster','terminated','ETIMEDOUT','ECONN'])
                if env: stats['env_like']+=1
                if any(r['name']==rec['name'] and r['ok'] for r in seq[i+1:]):
                    stats['pair']+=1
    out = dict(
        sessions=stats['sessions'], tool_calls=stats['tool_calls'],
        errors=stats['errors'], pair_rate=round(stats['pair']/max(stats['errors'],1),3),
        env_like=stats['env_like'], llm_retry=stats['retry'],
        error_tool_dist={k:v for k,v in stats['error_tools'].most_common(20)},
        retry_reasons={k:v for k,v in stats['retry_reasons'].most_common(8)},
        error_clusters=[{'template':tp,'count':c,'tool':stats['examples'][tp][0],
                         'example':stats['examples'][tp][1]}
                        for tp,c in stats['templates'].most_common(30)],
    )
    print(json.dumps(out, ensure_ascii=False, indent=1))

main()
