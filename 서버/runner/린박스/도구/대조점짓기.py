# -*- coding: utf-8 -*-
r"""`_synccheck.py` 3단계(완성본 원음 대조)가 읽는 대조점을 짓는다.

왜 필요한가 (2026-09-01 EP6)
  3단계는 `_synccheck_points.json`([{blk,final_start,src_start,dur,label}])이 없으면
  건너뛴다 — 그런데 이 파일을 만드는 도구가 없어서 검사가 조용히 빠졌다.
  EP6 에서 이 검사로 서버 master.wav 의 **블록당 ~29ms 누적 밀림**(끝 0.77초)을
  잡았다. D(원음) 블록마다 완성본 타임라인 시각과 소재 시각을 짝지어 놓는다.

무엇으로 짓나
  · authored.json 의 BLOCKS — D 블록의 소재 시각과 자막
  · state_payload.json 의 clip_secs — 블록별 실측 길이(누적 = 완성본 타임라인)

쓰는 법
  편 폴더에서:  python 대조점짓기.py
  그 다음:      python <스크립트>/_synccheck.py <편폴더> --final
  ★완성본 파일 이름이 «완성» 으로 시작해야 3단계가 찾는다 (ln -f 로 걸어 둔다).
"""
import io
import json
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

a = json.load(io.open('authored.json', encoding='utf-8'))
cs = json.load(io.open('state_payload.json', encoding='utf-8'))['clip_secs']

# ★소재 시각은 서버가 **실제로 절단한 시각**(컷계획 원본시작 − 구간오프셋)을 쓴다 (2026-09-03 EP18).
#   서버는 crop 일감 블록을 대본 시각보다 0.1초쯤 앞에서 자르기도 해서, 대본 시각으로 대조하면
#   완성본 A/V 가 맞는데도 −120ms «실패» 로 찍힌다. 컷계획이 없으면 대본 시각으로 돌아간다.
실제시작 = {}
import os
if os.path.exists('컷계획.json') and os.path.exists('편정보.json'):
    오프셋 = float(json.load(io.open('편정보.json', encoding='utf-8')).get('구간오프셋', 0) or 0)
    for c in json.load(io.open('컷계획.json', encoding='utf-8')):
        실제시작.setdefault(int(c['블록']), float(c['원본시작']) - 오프셋)

tl = 0.0
점들 = []
for i, b in enumerate(a['BLOCKS']):
    d = float(cs[str(i)])
    if b[0] == 'D':
        점들.append({'blk': i, 'final_start': round(tl, 3),
                    'src_start': round(실제시작.get(i, float(b[1][0][0])), 3),
                    'dur': round(d, 3), 'label': b[1][0][2][:12]})
    tl += d

json.dump(점들, io.open('_synccheck_points.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
print('대조점 %d개 · 전체 타임라인 %.2fs → _synccheck_points.json' % (len(점들), tl))
