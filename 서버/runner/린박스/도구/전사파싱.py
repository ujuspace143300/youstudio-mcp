# -*- coding: utf-8 -*-
"""Speechmatics json-v2 전문 → 낱말표 · 30초 밀도표 · 화자 덩이 대본 (사람이 읽는 용)
쓰는 법: python 전사파싱.py <전사.json> <출력접두>   (전사_한벌.py 결과 → 낱말표·30초 밀도표·화자 덩이 대본)
"""
import json, sys, collections

src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding='utf-8'))
W = []
for r in d.get('results', []):
    if r.get('type') != 'word':
        continue
    a = (r.get('alternatives') or [{}])[0]
    W.append({'s': float(r['start_time']), 'e': float(r['end_time']),
              't': a.get('content', ''), 'c': float(a.get('confidence', 0) or 0),
              'spk': a.get('speaker', '')})
json.dump({'words': W}, open(out + '_words.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)

# 30초 밀도
end = max((w['e'] for w in W), default=0)
n = int(end // 30) + 1
dens = [0] * n
for w in W:
    dens[int(w['s'] // 30)] += len(w['t'])
with open(out + '_밀도30s.txt', 'w', encoding='utf-8') as f:
    f.write('구간(초)\t글자수\t막대\n')
    for i, c in enumerate(dens):
        f.write(f'{i*30:5d}-{i*30+30:<5d}\t{c:4d}\t{"#" * (c // 10)}\n')

# 화자 덩이 (같은 화자 · 1.2초 안 이어짐)
turns = []
for w in W:
    if turns and w['spk'] == turns[-1]['spk'] and w['s'] - turns[-1]['e'] <= 1.2:
        turns[-1]['e'] = w['e']; turns[-1]['t'] += ' ' + w['t']
    else:
        turns.append({'s': w['s'], 'e': w['e'], 'spk': w['spk'], 't': w['t']})
with open(out + '_덩이.txt', 'w', encoding='utf-8') as f:
    for t in turns:
        f.write(f"{t['s']:7.2f}-{t['e']:7.2f} [{t['spk']}] {t['t']}\n")
print(f'낱말 {len(W)} · 길이 {end:.0f}초 · 덩이 {len(turns)} · 화자 {len(set(w["spk"] for w in W))}')
