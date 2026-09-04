# -*- coding: utf-8 -*-
"""너무 넓은 자막 줄을 «\\fscx» 로 좁힌다 — **넓은 화포**에서 재서 잘림을 피한다.

왜 넓은 화포인가
  1080 화면에서 재면 글자가 화면 밖으로 나간 만큼이 **잘려서** 폭이 1080 으로 나온다.
  그 값으로 비율을 잡으면 덜 좁혀진다. 그래서 2400 폭에 그려 **참 폭**을 잰다.
  (PlayResX 는 그대로 두고 화포만 넓힌다 — 글자 크기는 PlayResX 기준이라 안 변한다.)
"""
import io
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

ass경로, 글꼴방 = sys.argv[1], sys.argv[2]
목표 = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
tmp = '/tmp/_폭맞춤2'
os.makedirs(tmp, exist_ok=True)
화포 = 2400


def 재기(머리, 줄):
    본 = 줄.split(',', 9)
    본[1], 본[2] = '0:00:00.00', '0:00:10.00'
    # an5 가운데로 바꿔 잘리지 않게 한다
    본[9] = re.sub(r'\\an\d', '', 본[9])
    본[9] = re.sub(r'\\pos\([^)]*\)', '', 본[9])
    # ★페이드를 걷어낸다 — `\fad(133,…)` 이 있으면 **첫 프레임에서 글자가 투명**이라
    #   폭이 0 으로 나오고, 그 줄은 안 좁혀진 채 화면 밖으로 나간다.
    #   2026-08-27 EP3 에서 실제로 그랬다 (대사 3줄이 좌우로 잘렸다).
    본[9] = re.sub(r'\\fade?\([^)]*\)', '', 본[9])
    본[9] = re.sub(r'^\{', r'{\\an5\\pos(540,960)', 본[9], count=1)
    p = os.path.join(tmp, 'one.ass')
    io.open(p, 'w', encoding='utf-8').write('\n'.join(머리 + [','.join(본)]))
    png = os.path.join(tmp, 'one.png')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi',
                    '-i', f'color=c=black:s={화포}x1920:d=0.1', '-vf',
                    f'ass={p}:fontsdir={글꼴방}', '-frames:v', '1', '-y', png],
                   capture_output=True)
    a = np.array(Image.open(png).convert('L'))
    ys, xs = np.nonzero(a > 40)
    return 0 if len(xs) == 0 else int(xs.max() - xs.min() + 1)


원 = io.open(ass경로, encoding='utf-8').read().split('\n')
머리 = [x for x in 원 if not x.startswith('Dialogue:')]
낸줄, 고친 = [], []
for 줄 in 원:
    if not 줄.startswith('Dialogue:'):
        낸줄.append(줄)
        continue
    f = 줄.split(',', 9)
    글 = re.sub(r'\{[^}]*\}', '', f[9]).strip()
    층 = f[3].strip()
    if not 글 or 층.startswith('headline') or 층.startswith('credit'):
        낸줄.append(줄)
        continue
    f[9] = re.sub(r'\\fscx\d+', '', f[9])           # 전에 넣은 것을 걷어내고 다시 잡는다
    민 = ','.join(f)
    폭 = 재기(머리, 민)
    if 폭 > 목표:
        비 = max(70, int(목표 * 100 / 폭))
        f[9] = re.sub(r'^\{', r'{\\fscx%d' % 비, f[9], count=1)
        새줄 = ','.join(f)
        새폭 = 재기(머리, 새줄)
        while 새폭 > 목표 and 비 > 70:              # 한 번에 안 맞으면 더 조인다
            비 -= 1
            f[9] = re.sub(r'\\fscx\d+', r'\\fscx%d' % 비, f[9], count=1)
            새줄 = ','.join(f)
            새폭 = 재기(머리, 새줄)
        고친.append((글, 폭, 비, 새폭))
        낸줄.append(새줄)
    else:
        낸줄.append(민)

io.open(ass경로, 'w', encoding='utf-8').write('\n'.join(낸줄))
print('좁힌 줄 %d개 (참 폭으로 다시 잼)' % len(고친))
for 글, 폭, 비, 새폭 in 고친:
    print('  %4dpx → fscx%d → %4dpx   %s' % (폭, 비, 새폭, 글))
