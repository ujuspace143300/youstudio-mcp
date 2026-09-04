# -*- coding: utf-8 -*-
"""ass 가 쓰는 글꼴이 **정말 그 글꼴로 그려지는지** 본다 (완성 검사 6번).

왜 어려운가
  libass 는 글꼴을 못 찾아도 **오류 없이 다른 글꼴로 그린다.** `fc-match` 는 없는
  이름에도 답을 주므로 그것만으로는 판정이 안 된다.

어떻게 판정하나
  **없는 글꼴 이름**을 하나 같이 그려서 «폴백 그림» 을 만들고, 각 글꼴의 그림과
  **겹침률**을 잰다. 100% 면 같은 그림 = 폴백이다.
  ★잉크 픽셀 «개수» 만 비교하면 안 된다 — 다른 글꼴이 우연히 비슷한 개수를 낼 수 있다
  (2026-08-27: GangwonEduAllBold 12,905 vs 폴백 13,129 — 개수는 붙었지만 겹침률은 12%).

쓰는 법
  python 글꼴폴백검사.py <captions.ass> <글꼴방>
  종료코드 0 = 다 제 글꼴 · 1 = 폴백이 있다
"""
import argparse
import io
import os
import subprocess
import sys

import numpy as np
from PIL import Image

P = argparse.ArgumentParser()
P.add_argument('ass')
P.add_argument('글꼴방')
P.add_argument('--맛보기글', default='가나다라마바사')
P.add_argument('--겹침문턱', type=float, default=90.0, help='이보다 겹치면 폴백으로 본다(%%)')
A = P.parse_args()

tmp = '/tmp/_글꼴폴백검사'
os.makedirs(tmp, exist_ok=True)

머리 = """[Script Info]
ScriptType: v4.00+
PlayResX: 2560
PlayResY: 384
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: t,%s,120,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:10.00,t,,0,0,0,,{\\pos(20,20)}%s
"""


def 그림(글꼴):
    p = os.path.join(tmp, 't.ass')
    io.open(p, 'w', encoding='utf-8').write(머리 % (글꼴, A.맛보기글))
    o = os.path.join(tmp, 't.png')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=black:s=2560x384:d=1', '-vf',
                    "ass=filename='%s':fontsdir='%s'" % (p, A.글꼴방),
                    '-frames:v', '1', o], check=True)
    return np.array(Image.open(o).convert('L')) > 40


글꼴들 = []
for l in io.open(A.ass, encoding='utf-8'):
    if l.startswith('Style:'):
        g = l[6:].split(',')[1].strip()
        if g not in 글꼴들:
            글꼴들.append(g)

폴백 = 그림('절대없는글꼴9999')
탈 = []
print('글꼴                      폴백과 겹침률   판정')
for g in 글꼴들:
    a = 그림(g)
    합 = (폴백 | a).sum()
    율 = 100.0 * (폴백 & a).sum() / 합 if 합 else 100.0
    나쁨 = 율 >= A.겹침문턱
    if 나쁨:
        탈.append(g)
    print('%-26s %8.1f%%      %s' % (g, 율, '★폴백이다' if 나쁨 else '✔ 제 글꼴'))

if 탈:
    print()
    print('★ 폴백으로 그려지는 글꼴 %d개 — 깔거나 글꼴방에 넣어라: %s'
          % (len(탈), ', '.join(탈)))
    sys.exit(1)
print()
print('글꼴 %d종 모두 제 글꼴로 그려진다' % len(글꼴들))
