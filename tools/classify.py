#!/usr/bin/env python3
"""B: 量化报错自解释性。五分类：
self-fixing   报错文本自带修复指令（agent 读了就会修）
diagnosable   原因明确、修复需推断（可能缺领域知识）
opaque        现象不明/中断/半截输出（最需要诊断技能）
session-noise sandbox 升级空转（会话上下文噪声，需前置过滤）
env           环境类（429/超时/502，过滤）
"""
import argparse
import json
from collections import defaultdict, Counter

def classify(err):
    e = err.lower()
    if any(k in e for k in ['timed out','429','rate_limit','502','500','overloaded','stream idle','upstream','no cluster']):
        return 'env'
    if any(k in e for k in ['escalation','justification','sandbox']):
        return 'session-noise'
    if any(k in e for k in ['interrupted','aborted','was cancelled','subagent run failed','partial output','outcome is unknown']):
        return 'opaque'
    if any(k in e for k in ['read the file','re-read','narrow pattern','provide a more specific','must be a number','positive number','current is']):
        return 'self-fixing'
    if any(k in e for k in ['not strictly wider','expected a non-empty','exceeds maxdepth','is out of range','not found',
                            'no longer exists','file changed since','old_string was not found','no files were searched',
                            'belongs to another session','io error','only valid together with','must differ','file access denied']):
        return 'diagnosable'
    return 'opaque'

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_file', nargs='?', default='data/all_errors.json',
                        help='extract_errors.py 生成的 JSON（默认：data/all_errors.json）')
    args = parser.parse_args(argv)
    with open(args.input_file, encoding='utf-8') as fh:
        data = json.load(fh)

    buckets = defaultdict(lambda: {'n':0,'pair':0,'tpls':Counter(),'ex':[]})
    for e in data:
        c = classify(e['err'])
        b = buckets[c]
        b['n']+=1
        b['pair']+= 1 if e['paired'] else 0
        b['tpls'][e['tpl']]+=1
        if len(b['ex'])<2: b['ex'].append(e['err'][:180])

    print(f"{'类别':<14}{'数量':>5}{'占比':>7}{'配对':>6}{'配对率':>8}   示例模板(计数)")
    print('-'*100)
    total = len(data)
    order = ['session-noise','self-fixing','diagnosable','opaque','env']
    labels = {'session-noise':'会话上下文噪声','self-fixing':'自带修复指令','diagnosable':'原因明确需推断','opaque':'现象不明/中断','env':'环境类'}
    for c in order:
        b = buckets[c]
        print(f"{labels[c]:<14}{b['n']:>5}{100*b['n']/max(total,1):>6.1f}%{b['pair']:>6}{100*b['pair']/max(b['n'],1):>7.1f}%")
        for tpl,cnt in b['tpls'].most_common(3):
            print(f"    {cnt:>3}  {tpl[:95]}")
    print()
    print('代表例子：')
    for c in order:
        b = buckets[c]
        print(f'  [{labels[c]}]')
        for ex in b['ex']: print('    ', ex.replace(chr(10),' ⏎ ')[:160])


if __name__ == '__main__':
    main()
