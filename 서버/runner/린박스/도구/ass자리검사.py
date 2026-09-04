# -*- coding: utf-8 -*-
"""자막을 **제자리 그대로** 그려서 화면·매트를 벗어나는 줄을 찾는다.

왜 이 검사가 따로 필요한가
  앞서 쓰던 «폭 검사» 는 줄을 재려고 `\\pos` 를 지우고 화면 한가운데로 옮겨 그렸다.
  그래서 **폭만 봤지 자리는 한 번도 안 봤다.** 효과자막은 `\\an5` 로 x 가 제각각이라
  폭이 좁아도 자리가 치우치면 화면 밖으로 나간다 (2026-08-27 사장님: 「?!」가 잘림).

무엇을 보나 — 낱장을 **원래 태그 그대로** 1080x1920 에 그리고 잉크 상자를 잰다.
  · 가로: 안전선 <여백> ~ 1080-<여백> 안에 있나
  · 세로: 대사·나레는 매트 창(450~1470), 효과자막은 안전대(520~1400) 안에 있나
"""
import io
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

ass경로 = sys.argv[1]
글꼴방 = sys.argv[2]
여백 = int(sys.argv[3]) if len(sys.argv) > 3 else 20
tmp = '/tmp/_자리검사'
os.makedirs(tmp, exist_ok=True)

원 = io.open(ass경로, encoding='utf-8').read().split('\n')
머리 = [x for x in 원 if not x.startswith('Dialogue:')]

세로한계 = {
    'band_narr': (450, 1470), 'band_dlg': (450, 1470), 'band_emph': (450, 1470),
    'effect_float': (520, 1400),
    'headline_l1': (0, 449), 'headline_l2': (0, 449),
    'credit_cta_l1': (1470, 1920), 'credit_cta_l2': (1470, 1920),
}


def 재기(줄):
    """그 줄 하나만 원래 태그 그대로 그린다"""
    본 = 줄.split(',', 9)
    본[1], 본[2] = '0:00:00.00', '0:00:10.00'
    본[9] = re.sub(r'\\fad\([^)]*\)', '', 본[9])      # 페이드는 잉크를 흐리게 하니 뺀다
    본[9] = re.sub(r'\\t\([^)]*\)', '', 본[9])        # 움직임도 뺀다 (시작값으로 잰다)
    p = os.path.join(tmp, 'one.ass')
    io.open(p, 'w', encoding='utf-8').write('\n'.join(머리 + [','.join(본)]))
    png = os.path.join(tmp, 'one.png')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi',
                    '-i', 'color=c=black:s=1080x1920:d=0.1', '-vf',
                    f'ass={p}:fontsdir={글꼴방}', '-frames:v', '1', '-y', png],
                   capture_output=True)
    a = np.array(Image.open(png).convert('L'))
    ys, xs = np.nonzero(a > 30)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


탈, 잰것 = [], 0
for 줄 in 원:
    if not 줄.startswith('Dialogue:'):
        continue
    f = 줄.split(',', 9)
    층 = f[3].strip()
    글 = re.sub(r'\{[^}]*\}', '', f[9]).strip()
    if not 글:
        continue
    상자 = 재기(줄)
    if 상자 is None:
        continue
    잰것 += 1
    x0, x1, y0, y1 = 상자
    왜 = []
    if x0 < 여백:
        왜.append(f'왼쪽 {x0}px (한계 {여백})')
    if x1 > 1080 - 여백:
        왜.append(f'오른쪽 {x1}px (한계 {1080 - 여백})')
    위, 아래 = 세로한계.get(층, (0, 1920))
    if y0 < 위:
        왜.append(f'위 {y0}px (한계 {위})')
    if y1 > 아래:
        왜.append(f'아래 {y1}px (한계 {아래})')
    if 왜:
        탈.append((층, 글, x0, x1, y0, y1, ' · '.join(왜)))

print('잰 자막 %d장 · **벗어난 것 %d장**' % (잰것, len(탈)))
if 탈:
    print()
    print('%-14s %-18s %-22s %s' % ('층', '글', '상자(x0~x1 / y0~y1)', '무엇이 벗어났나'))
    print('-' * 104)
    for 층, 글, x0, x1, y0, y1, 왜 in 탈:
        print('%-14s %-18s %-22s %s'
              % (층, 글[:18], f'{x0}~{x1} / {y0}~{y1}', 왜))

# ★벗어난 것이 있으면 **종료코드 1** 을 낸다 — 이 검사는 관문이다.
#   2026-08-27 까지 0 을 냈고, 그래서 `한번에.sh` 의 «|| 멈춤» 이 한 번도 안 걸렸다.
#   EP3 이 대사 3줄이 잘린 채 완성본까지 갔다.
sys.exit(1 if 탈 else 0)
