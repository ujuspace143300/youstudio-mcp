# -*- coding: utf-8 -*-
"""captions.ass 를 신병4 곳간 규격으로 갈아끼운다.

곳간 = 볼트 스크립트/린박스/키트/스타일/신병4_본.json
  쓰인03 Paperlogy-9Black    108.7 #E80003 선6.0 y208   → headline
  쓰인01 Paperlogy-5Medium    84.1 #EEE54A 선3.0 y1179  → band_narr (나레 노랑)
  쓰인02 GangwonEduAllBold    87.3 #FEFEFE 선3.0 y1179  → band_dlg  (대사 흰색)
  쓰인04 GangwonEduAllBold    76.9 #FEFEFE 선3.0        → effect_float
  쓰인08 GmarketSansTTFMedium 38.3 #FEFEFE 선2.0 y1488  → credit

쓰는 법  python restyle_sinbyeong4.py <captions.ass> <낼파일.ass>
"""
import io
import json
import os
import re
import sys


def ass색(hex색):
    """#RRGGBB → &H00BBGGRR"""
    h = hex색.lstrip('#')
    return '&H00%s%s%s' % (h[4:6], h[2:4], h[0:2])


# 층 이름 → (글꼴, 크기, 칠, 선굵기, 정렬)
#
# ★크기는 **ASS 단위**다 — 곳간의 값(84.1·87.3…)은 프리미어 단위라 그대로 쓰면 안 된다.
#   프리미어 크기 = ASS 크기 × upm/(winAscent+winDescent) 이고 그 환산비는 글꼴마다 다르다
#   (도구/글꼴표.py: Paperlogy 0.8491 · 강원교육모두 0.8734 · Gmarket 0.8696).
#   그래서 ASS 크기 = 곳간 크기 ÷ 환산비 로 되돌려 넣는다. 곱하면 곳간 값으로 되돌아온다:
#     99×0.8491=84.1 · 100×0.8734=87.3 · 88×0.8734=76.9 · 128×0.8491=108.7 · 44×0.8696=38.3
# ★대사를 Paperlogy 로 (2026-08-27 사장님 지시 «나레이션이랑 대사 글자체를 페이퍼로지로»).
#   나레는 이미 Paperlogy-5Medium 이었다. 대사는 GangwonEduAllBold → Paperlogy-7Bold.
#   화면에 찍히는 크기를 그대로 두려고 환산비로 다시 잡았다 —
#   곳간 87.3(프리미어) ÷ Paperlogy 0.8491 = 103 (강원교육모두일 때는 100 이었다).
# ★제목은 **서버 원본 그대로 둔다** (2026-08-27 사장님 지시 «제목 다 빨간색인데 이게 맞아?
#   이전에 잘했잖아»). 곳간 쓰인03 은 두 줄 다 빨강(#E80003)·크기 128 이라
#   ① 색이 뭉개지고 ② 두 줄이 매트(0~449)를 꽉 채워 아래 여백이 2px 밖에 안 남았다.
#   원본은 **1줄 노랑 · 2줄 빨강 · Gmarket Sans Bold 114/115 · 외곽선 0 · y214/y335** 다.
서식 = {
    'headline_l1':   ('Gmarket Sans Bold',   114, '#F7FD00', 0.0, 8),
    'headline_l2':   ('Gmarket Sans Bold',   115, '#FD0000', 0.0, 8),
    'band_narr':     ('Paperlogy-5Medium',    99, '#EEE54A', 3.0, 8),
    'band_dlg':      ('Paperlogy-7Bold',     103, '#FEFEFE', 3.0, 8),
    'band_emph':     ('Paperlogy-7Bold',     103, '#FEFEFE', 3.0, 8),
    'effect_float':  ('GangwonEduAllBold',    88, '#FEFEFE', 3.0, 5),
    'credit_cta_l1': ('GmarketSansTTFMedium', 44, '#FEFEFE', 2.0, 8),
    'credit_cta_l2': ('GmarketSansTTFMedium', 44, '#FEFEFE', 2.0, 8),
}

# 새 자리 (곳간 «자리» = 잉크 윗선, an8 기준)
자리 = {
    # ★서버 원본 자리(214·335)에서 **20px 올렸다** (2026-08-27 실측).
    #   프리미어는 libass 보다 글자를 약 20px 아래에 앉힌다(글꼴 지표 차이) —
    #   원본 자리 그대로면 완성본은 아래 여백 24px 인데 프리미어는 **1px** 밖에 안 남아
    #   상단 매트(0~449)를 넘어 영상으로 내려온다. 20px 올리면 둘 다 여유가 생긴다.
    'headline_l1': 194,
    'headline_l2': 315,
    'band_narr': 1179,
    'band_dlg': 1179,
    'band_emph': 1179,
    'credit_cta_l1': 1488,
    'credit_cta_l2': 1488 + 45,
}

# 새 제목 — 바이럴 지침서 단계2 (2줄 · 각 10자 이내 · 이모지 없음)
# ★제목은 **편마다 다르다 — 도구에 박지 않는다** (키트 규격 §70).
#   편 폴더의 `편정보.json` 의 «제목»(2줄)에서 읽는다. 없으면 서버 원본 제목을 그대로 둔다.
#   2026-08-27: 여기에 EP1 제목이 박혀 있어 EP2 완성본에 EP1 제목이 찍혔다.
_정보 = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), '편정보.json')
_두줄 = (json.load(io.open(_정보, encoding='utf-8')).get('제목')
        if os.path.exists(_정보) else None)
제목 = ({'headline_l1': _두줄[0], 'headline_l2': _두줄[1]} if _두줄 else {})
if not 제목:
    print('  ※ 편정보.json 에 «제목» 이 없어 서버 원본 제목을 그대로 둔다')

들, 낼 = sys.argv[1], sys.argv[2]
줄들 = io.open(들, encoding='utf-8').read().split('\n')
낸줄, 바꾼서식, 바꾼자리, 바꾼글자 = [], 0, 0, 0

for 줄 in 줄들:
    if 줄.startswith('Style:'):
        칸 = 줄[len('Style:'):].split(',')
        이름 = 칸[0].strip()
        if 이름 in 서식:
            글꼴, 크기, 칠, 선, 정렬 = 서식[이름]
            c = ass색(칠)
            칸[1] = 글꼴
            칸[2] = str(크기)
            칸[3] = c          # PrimaryColour
            칸[4] = c          # SecondaryColour
            칸[5] = '&H00000000'   # OutlineColour = 검정
            칸[6] = '&H00000000'   # BackColour
            칸[16] = str(선)       # Outline
            칸[18] = str(정렬)     # Alignment
            바꾼서식 += 1
            줄 = 'Style:' + ','.join(칸)
        낸줄.append(줄)
        continue

    if 줄.startswith('Dialogue:'):
        머리, _, 글 = 줄.partition(',,')
        층 = 머리.split(',')[3].strip()

        # 제목 글자 갈기
        if 층 in 제목:
            글 = re.sub(r'\}[^{}]*$', '}' + 제목[층], 글)
            바꾼글자 += 1

        # 자리 옮기기
        if 층 in 자리:
            새 = 자리[층]
            글2, n = re.subn(r'\\pos\(540(?:\.\d+)?,\s*[\d.]+\)',
                             r'\\pos(540,%d)' % 새, 글)
            if n == 0:   # \pos 가 없던 줄이면 넣어 준다
                글2, n = re.subn(r'\{\\an8', r'{\\an8\\pos(540,%d)' % 새, 글, count=1)
            글 = 글2
            바꾼자리 += n

        줄 = 머리 + ',,' + 글

    낸줄.append(줄)

io.open(낼, 'w', encoding='utf-8').write('\n'.join(낸줄))
print('서식 %d줄 · 자리 %d줄 · 제목 %d줄 바꿈 → %s' % (바꾼서식, 바꾼자리, 바꾼글자, 낼))
