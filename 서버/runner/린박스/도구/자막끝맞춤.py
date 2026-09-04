# -*- coding: utf-8 -*-
r"""ASS 자막의 끝 시각을 **영상 총 프레임** 안으로 자른다. (2026-09-03 사장님 지적)
왜
  서버 captions.ass 의 헤드라인·크레딧은 «계획 길이»(블록 초의 합, 예 56.72초)까지 깔리는데,
  실제 구운 영상은 블록마다 프레임 단위로 잘려 그보다 짧다(예 1700프레임 = 56.667초).
  그 0.05초가 프리미어에선 **제목 클립 2프레임이 영상 뒤에 홀로 남는** 탈로 나온다 —
  EP6~EP20 열 편 전부 1~2프레임씩 그랬다.
무엇을 하나
  Dialogue 끝이 총 길이를 넘으면 총 길이로 자르고, 시작부터 넘는 줄은 뺀다. 되읽어 확인한다.
쓰는 법
  python 자막끝맞춤.py <captions.ass> <배치계획.json | 총프레임> [--fps 30]
  원본은 <ass>.끝맞춤전 으로 남긴다. 고친 줄 수를 찍는다.
"""
import argparse, io, json, os, shutil, sys

P = argparse.ArgumentParser()
P.add_argument('ass'); P.add_argument('총'); P.add_argument('--fps', type=float, default=30.0)
A = P.parse_args()

if A.총.endswith('.json'):
    총프레임 = int(json.load(io.open(A.총, encoding='utf-8'))['total'])
else:
    총프레임 = int(A.총)
한계 = 총프레임 / A.fps


def 초(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + float(s)


def 글(sec):
    sec = max(0.0, sec); h = int(sec // 3600); m = int(sec % 3600 // 60); s = sec - h * 3600 - m * 60
    return f'{h}:{m:02d}:{s:05.2f}'


줄들 = io.open(A.ass, encoding='utf-8').read().split('\n')
새, 자름, 뺌 = [], 0, 0
for L in 줄들:
    if L.startswith('Dialogue:'):
        p = L.split(',', 9)
        s, e = 초(p[1]), 초(p[2])
        if s >= 한계 - 0.005:
            뺌 += 1; continue
        if e > 한계 + 0.005:
            p[2] = 글(한계); L = ','.join(p); 자름 += 1
    새.append(L)
if 자름 or 뺌:
    shutil.copy2(A.ass, A.ass + '.끝맞춤전')
    io.open(A.ass, 'w', encoding='utf-8').write('\n'.join(새))
# 되읽기
남 = [L for L in io.open(A.ass, encoding='utf-8') if L.startswith('Dialogue:') and 초(L.split(',', 9)[2]) > 한계 + 0.005]
print(f'자막끝맞춤: 한계 {총프레임}프레임({한계:.3f}s) · 끝 자른 줄 {자름} · 뺀 줄 {뺌} · 되읽기 초과 {len(남)}')
sys.exit(1 if 남 else 0)
