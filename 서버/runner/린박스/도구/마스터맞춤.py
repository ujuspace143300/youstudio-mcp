# -*- coding: utf-8 -*-
r"""마스터 소리를 **블록 영상 길이에 표본 단위로** 맞춰 다시 잇는다.

왜 필요한가
  블록 소리를 그냥 디코딩해 이어 붙이면 AAC 의 앞뒤 패딩이 블록마다 10ms 씩
  얹혀 29개를 지나며 0.30초가 밀린다. 끝에 가면 입 모양과 소리가 눈에 띄게
  어긋난다. (1편에서는 이걸 fix_drift.py 로 상관관계를 재서 잡았는데,
  블록 길이를 알고 있으면 그냥 **그 길이만큼 잘라 쓰면** 된다.)

  블록 i 의 소리는 정확히 round(영상길이_i x 48000) 표본이다. 모자라면 무음을
  채우고 남으면 버린다. 그러면 이어 붙인 소리 길이 = 이어 붙인 영상 길이다.
"""
import io
import glob
import json
import os
import re
import subprocess

import numpy as np

SR = 48000
# ★★블록을 «파일 훑기» 로 모으면 안 된다 (2026-08-26 실측으로 밝힘).
#   대본이 줄면 지난번 블록 파일이 **고아로 남는다.** 영상은 목록(blocks/concat.txt)대로
#   이어 붙는데 소리는 훑은 파일 전부로 만들어져 **길이가 어긋난다.**
#   1화 「1등만하던…」이 그랬다 — 대본 25블록 · 파일 27개 →
#   영상 51.90초 · 소리 56.73초. 끝 4.83초가 **정지 화면**으로 나갔다.
#   ★사람 눈에는 «튐» 이 아니라 «영상이 멎었다» 로 보인다. 더 나쁘다.
#   → 서버가 준 목록(concat.txt)이 정본이다. 없으면 authored.json 의 블록 수로 자른다.
def _블록목록():
    목록 = 'blocks/concat.txt'
    if os.path.exists(목록):
        난것 = []
        for 줄 in io.open(목록, encoding='utf-8'):
            줄 = 줄.strip()
            if 줄.startswith('file '):
                난것.append(줄[5:].strip().strip("'").strip('"'))
        if 난것:
            return 난것
    모두 = sorted(glob.glob('blocks/b*.mp4'),
                  key=lambda p: int(re.search(r'b(\d+)', p).group(1)))
    try:
        n = len(json.load(io.open('authored.json', encoding='utf-8'))['BLOCKS'])
        if len(모두) > n:
            print('  ★블록 파일이 %d개인데 대본은 %d개다 — 뒤 %d개는 고아라 뺀다'
                  % (len(모두), n, len(모두) - n))
            모두 = 모두[:n]
    except Exception:
        pass
    return 모두


files = _블록목록()


def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                 '-of', 'csv=p=0', p], capture_output=True, text=True,
                                encoding='utf-8', errors='replace').stdout.strip().split()[0])   # ffprobe 가 두 줄 내는 파일이 있다 (2026-09-03 불륜 merged.mp4)


chunks, drift = [], 0.0
for p in files:
    d = dur(p)
    want = int(round(d * SR))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-vn', '-f', 'f32le',
                          '-acodec', 'pcm_f32le', '-ac', '2', '-ar', str(SR), '-'],
                         capture_output=True).stdout
    a = np.frombuffer(raw, dtype='<f4').reshape(-1, 2)
    drift += (len(a) - want) / SR
    if len(a) < want:
        a = np.vstack([a, np.zeros((want - len(a), 2), dtype='<f4')])
    chunks.append(a[:want])

m = np.concatenate(chunks)
m.astype('<f4').tofile('_m.f32')
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR),
                '-ac', '2', '-i', '_m.f32', '-c:a', 'pcm_s24le',
                'blocks/master_sync.wav'], check=True)
os.remove('_m.f32')
print("블록 %d개 · 잘라낸 패딩 합 %.3f초" % (len(files), drift))
print("→ blocks/master_sync.wav  %.3f초 (영상 %.3f초)"
      % (len(m) / SR, dur('blocks/merged.mp4')))
