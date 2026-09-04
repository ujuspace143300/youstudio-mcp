# -*- coding: utf-8 -*-
"""captions_신병4.ass 에서 납품 SRT 4벌을 낸다 (v2 납품 형식 그대로).
  <편>_자막.srt = 나레+대사+효과 통합(시각순) · 자막_나레이션 · 자막_대사 · 자막_효과"""
import re
import sys

편, ass경로, 낼방 = sys.argv[1], sys.argv[2], sys.argv[3]

층 = {'band_narr': [], 'band_dlg': [], 'effect_float': []}
for L in open(ass경로, encoding='utf-8'):
    if not L.startswith('Dialogue:'):
        continue
    p = L.split(',', 9)
    style = p[3]
    if style not in 층:
        continue
    txt = re.sub(r'{[^}]*}', '', p[9]).strip().replace(r'\N', '\n')
    층[style].append((p[1], p[2], txt))


def srt시각(t):  # 0:00:00.06 → 00:00:00,060
    h, m, s = t.split(':')
    sec, cs = s.split('.')
    return f'{int(h):02d}:{m}:{sec},{cs}0'


def 쓰기(이름, 줄들):
    with open(f'{낼방}/{이름}', 'w', encoding='utf-8') as f:
        for i, (s, e, txt) in enumerate(줄들, 1):
            f.write(f'{i}\n{srt시각(s)} --> {srt시각(e)}\n{txt}\n\n')
    print(f'  {이름}  {len(줄들)}장')


통합 = sorted(층['band_narr'] + 층['band_dlg'] + 층['effect_float'], key=lambda x: x[0])
쓰기(f'{편}_자막.srt', 통합)
쓰기('자막_나레이션.srt', 층['band_narr'])
쓰기('자막_대사.srt', 층['band_dlg'])
쓰기('자막_효과.srt', 층['effect_float'])
