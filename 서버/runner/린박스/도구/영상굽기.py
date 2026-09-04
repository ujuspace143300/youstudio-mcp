# -*- coding: utf-8 -*-
"""컷 배율을 **전부 같은 값(1:1)** 로 맞춰 영상 트랙을 다시 굽는다 — 정본 맥 사슬 `신병4/영상굽기.py` 의 유스튜디오판.

왜
  서버가 컷마다 준 배율은 94.57~137.06% 로 45% 널뛰는데, 크롭 중심이 전부 원본 한가운데라
  **인물을 잡기 위한 확대가 아니다.** 컷이 바뀔 때마다 화면이 작아졌다 커졌다 하고 137% 컷은 머리 위가 잘린다.
  (2026-08-27 사장님: «영상배율을 적절하게 모두 맞춰서 일관되게 보이게 해줘»)

무엇으로 맞추나 — crop=<W>:<H>:<X>:<Y> → scale=1080:1020
  원본에 위아래 레터박스가 있으면 그 띠가 매트 창 안으로 들어오지 않게 **레터박스를 뺀 그림**만 잘라 1020 으로 늘린다.
  신병4 EPK(1920x1080 · 위아래 60px 띠 · 그림 960px) 는 crop=1016:960:452:60 (기본값).
  ★정본과 다른 점: 크롭을 `--크롭 W:H:X:Y` 로 받는다 — lb_render 가 lb_probe 의 레터박스(content_h·top·width)로 짓는다.
    W = round(H × 1080/1020) · X = (가로 − W)/2 · Y = 위 띠.

쓰는 법
  python 영상굽기.py <편폴더> <편집용마스터.mp4> [--크롭 1016:960:452:60]
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

P = argparse.ArgumentParser()
P.add_argument('편')
P.add_argument('마스터')
P.add_argument('--크롭', default='1016:960:452:60', dest='크롭')
A = P.parse_args()

편 = A.편
마스터 = A.마스터
FPS = 30
컷들 = json.load(io.open(os.path.join(편, '컷계획.json'), encoding='utf-8'))
낼방 = os.path.join(편, '_균일컷')
os.makedirs(낼방, exist_ok=True)

# ★캐시 무효화 — 컷계획이 바뀌면 옛 컷을 **버린다.**
#   2026-08-27: 컷 시각을 마스터 기준으로 고쳤는데 «있으면 건너뛴다» 때문에 옛 컷이
#   그대로 이어붙어, 완성본에 **엉뚱한 장면**이 깔렸다. 눈으로 보기 전엔 안 잡혔다.
크롭필터 = 'crop=%s,scale=1080:1020,fps=30' % A.크롭   # ★도장에 넣는다 — 크롭·배율이 바뀌면 옛 컷을 버려야 한다 (2026-09-03 불륜 EP1)
_도장 = hashlib.sha256(
    (io.open(os.path.join(편, '컷계획.json'), encoding='utf-8').read()
     + '|' + os.path.abspath(마스터) + '|' + 크롭필터).encode('utf-8')).hexdigest()
_도장길 = os.path.join(낼방, '_도장.txt')
_옛 = io.open(_도장길, encoding='utf-8').read().strip() if os.path.exists(_도장길) else ''
if _옛 != _도장:
    for _f in os.listdir(낼방):
        os.remove(os.path.join(낼방, _f))
    io.open(_도장길, 'w', encoding='utf-8').write(_도장)
    print('컷계획이 바뀌었다 — 옛 컷을 버리고 다시 굽는다 (%s)' % 크롭필터)

목록 = []
for i, c in enumerate(sorted(컷들, key=lambda x: x['타임라인시작'])):
    p = os.path.join(낼방, '%02d.mp4' % i)
    if not os.path.exists(p):
        # ★앞에서 대충(-ss 앞) + 뒤에서 정확히(-ss 뒤). 긴 파일을 처음부터 디코딩하면 컷 하나에 2분씩 걸린다.
        앞 = max(0.0, c['원본시작'] - 2.0)
        뒤 = c['원본시작'] - 앞
        subprocess.run([
            'ffmpeg', '-v', 'error', '-y',
            '-ss', str(앞), '-i', 마스터, '-ss', str(뒤),
            '-frames:v', str(int(c['프레임'])),
            '-vf', 크롭필터,
            '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
            '-pix_fmt', 'yuv420p', p], check=True)
    목록.append(p)
    if (i + 1) % 10 == 0:
        print('  컷 %d/%d' % (i + 1, len(컷들)))

목 = os.path.join(낼방, '목록.txt')
# ★concat 목록의 상대경로는 목록 파일이 있는 폴더 기준으로 풀린다 — 절대경로로 적는다 (2026-08-27 EP4).
io.open(목, 'w', encoding='utf-8').write(
    '\n'.join("file '%s'" % os.path.abspath(x) for x in 목록) + '\n')
낼 = os.path.join(편, 'blocks', 'merged_균일.mp4')
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0',
                '-i', 목, '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
                '-pix_fmt', 'yuv420p', '-r', '30', 낼], check=True)
r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,nb_frames',
                    '-of', 'default=nw=1', 낼], capture_output=True, text=True)
print('→', 낼)
print(r.stdout.strip())
