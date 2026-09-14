#!/usr/bin/env python3
"""提取全部会话的每条 isError 报错：模板、原始文本(截断)、是否配对、tool、会话。"""
import argparse
import json
import re
import subprocess
from pathlib import Path
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

def read_session(path):
    """Read one zstd-compressed JSONL session without invoking a shell."""
    result = subprocess.run(
        ['zstd', '-d', '-c', path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'zstd failed for {path}: {result.stderr.strip()}')
    return result.stdout


def extract(paths):
    out = []
    for f in paths:
        raw = read_session(f)
        # Turn/step identifiers are scoped to a session.
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
                                'tpl':template(rec['err']),'sess':Path(f).parent.name})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('list_file', nargs='?', default='data/ppt_all.txt',
                        help='文本文件，每行一个 session.jsonl.zstd 路径')
    parser.add_argument('-o', '--output', default='data/all_errors.json',
                        help='JSON 输出路径（默认：data/all_errors.json）')
    args = parser.parse_args(argv)
    with open(args.list_file, encoding='utf-8') as fh:
        paths = [line.strip() for line in fh if line.strip()]
    out = extract(paths)
    print(f'total errors: {len(out)}')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False)
    # 模板汇总（含配对率）
    agg = defaultdict(lambda: [0,0,0])  # tpl -> [count, paired, tool_set]
    for e in out:
        a = agg[e['tpl']]
        a[0]+=1
        a[1]+= 1 if e['paired'] else 0
    for tpl,(c,p,_) in sorted(agg.items(), key=lambda x:-x[1][0]):
        print(f'{c:4d}  pair={p:4d} ({100*p/max(c,1):3.0f}%)  {tpl}')


if __name__ == '__main__':
    main()
