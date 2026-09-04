# -*- coding: utf-8 -*-
r"""본보기 프로젝트의 자막을 **통째로 베껴** 우리 편에 입힌다.

왜 통째로 베끼나
  자막 서식은 압축된 플랫버퍼 덩어리다. 그 안에 무슨 자리가 있는지 어도비가
  공개하지 않는다. 한 자리씩 알아내 흉내내다 보면 **모르는 자리가 반드시 남는다** —
  실제로 그랬다(둘레 12/14/15/16/20, 색표의 «없으면 255» 같은 것들).
  그래서 **본보기의 덩어리를 그대로 복사하고 글자만 갈아 끼운다.**
  그러면 못 알아낸 자리까지 저절로 따라온다.

  클립 쪽 값(위치·비율 조정·가로 비율·기준점)도 본보기 것을 그대로 쓴다.

쓰는 법
  python <키트>/본떠서만들기.py <우리.prproj> <본보기.prproj> <우리자막.ass>
"""
import argparse
import base64
import gzip
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '도구'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import 소스텍스트 as S      # noqa: E402
import 플랫버퍼 as F        # noqa: E402

덩어리찾기 = r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>'


def 내덩어리(도막):
    """이 «소스 텍스트» **자신의** 덩어리만 집는다.

    ★MOGRT 클립은 한 칸 안에 «소스 텍스트» 말고 «경로»·«모양» 덩어리도 갖고 있다.
      제 덩어리가 빈 껍데기(BinaryHash 만)이면 그냥 찾으면 **다음 이름표의 덩어리**를
      집어 온다 — 2026-08-25 에 여기서 «매직이 다르다» 로 터졌다.
      그러니 **다음 <Name> 이 나오기 전까지**만 본다.
    """
    끝 = 도막.find('<Name>', 1)
    m = re.search(덩어리찾기, 도막 if 끝 < 0 else 도막[:끝])
    return m

# ── 층 맞춤표 — 우리 자막의 층 → 곳간의 본 이름 · 자리도 본보기 것을 쓸지 ──
#   곳간 목록은 스타일/<곳간>_본.md 에서 본다. 여기 이름만 바꾸면 모양이 바뀐다.
맞춤 = {
    '사장님1편': {
        # ★2026-08-26. 사장님이 프리미어에서 손수 고쳐 «이게 맞다» 고 하신 1편
        #   (ep_1455-1700/프리미어/…prproj) 을 그대로 캔 곳간이다.
        #   여기서 가져오면 **서식입히기.py 를 돌릴 필요가 없다** — 색·크기·선·그림자가
        #   이미 사장님 값이다. 밖에서 자리를 짚어 고치다 세 번 어긋났으므로,
        #   앞으로 린박스 포헨즈는 **이 곳간을 통째로 베끼는 길**로만 간다.
        'band_narr':     ('쓰인02', True),   # 노랑 #F8FE07  61.7px
        'band_dlg':      ('쓰인01', True),   # 흰색 #F0F0F0  61.7px
        'band_emph':     ('쓰인02', True),
        'effect_float':  ('쓰인07', False),  # 분홍 #F070C0  60px — 칠·둘레 다 분홍인 본
        'credit_cta_l1': ('쓰인01', True),
        'credit_cta_l2': ('쓰인01', True),
    },

    # ★포핸즈 캠페인 — 본보기는 **1화 1-1편 프로젝트**다 (2026-08-26 사장님 지시
    #   «1-1편의 프로젝트 파일을 가져와서 제작해»). 무비오션 곳간의 「쓰인01」은
    #   **칠 값이 아예 없어서**(플랫버퍼가 기본값이면 칸을 통째로 뺀다) 색을 못 덮는다.
    #   1-1 곳간의 본들은 칠 값을 실제로 갖고 있어 그 문제가 없다.
    '포핸즈': {
        # ★headline 은 **한 클립 2줄**이 됐다 (2026-09-02) — 자막과 같은 가운데 상자(쓰인01)를
        #   입혀야 가운데 정렬이 된다(안 입히면 왼끝에 붙는다). 크기·줄색은 서식입히기가 ass 로 덮는다.
        'headline_l1':   ('쓰인01', False),  # ★자리는 우리 것(자리잡기 y191) — True 면 곳간 자리로 끌려간다
        'band_narr':     ('쓰인02', True),   # 나레 노랑
        'band_dlg':      ('쓰인01', True),   # 대사 흰색 #F0F0F0
        'band_emph':     ('쓰인02', True),
        'effect_float':  ('쓰인06', False),  # 모션 분홍 #F070C0 — 자리는 우리 것을 지킨다
        'credit_cta_l1': ('쓰인01', True),
        'credit_cta_l2': ('쓰인01', True),
    },
    '신병4': {
        # ★소년심판 1화 본보기에서 뜬 곳간. 우리 신병4 서식과 짝지었다 (2026-08-26)
        #   쓰인03 = Paperlogy-9Black 2줄 108.7 y208  → 제목
        #   쓰인01 = Paperlogy-5Medium 84.1 노랑 y1179 → 나레
        #   쓰인02 = GangwonEduAllBold 87.3 흰 y1179   → 대사
        #   쓰인08 = GmarketSansTTFMedium 38.3 y1488   → 크레딧·뱃지·방영정보
        # ★제목을 2줄 본(쓰인03)에서 **1줄 본(쓰인02)** 으로 옮겼다 (2026-08-27 맥2).
        #   우리는 제목 두 줄을 **클립 두 장**으로 낸다. 그걸 2줄 본에 담으면 탈이 둘 난다.
        #     ① 빈 둘째 줄만큼 글자가 **108px 아래로** 밀린다 (실측 — 완성본 224 · 프리미어 332).
        #        1줄 본은 «위치 y + 16» 에 정확히 앉는다.
        #     ② 2줄 본의 옛 글자는 통째로 한 문자열이라 갈아 끼워도 **버퍼에 남는다.**
        #        그러면 서식입히기·자리잡기가 그 옛 글자를 읽고 «ass 에서 못 찾음» 으로 건너뛴다.
        #   1줄 본은 옛 글자가 제자리에서 덮이므로 둘 다 안 생긴다.
        #   제목의 «생김새»(Paperlogy-9Black 108.7 · 빨강 · 둘레 6.0)는 서식입히기.py 가
        #   ass 에서 읽어 입히므로 본을 바꿔도 그대로다.
        'headline_l1':   ('쓰인02', True),
        'headline_l2':   ('쓰인02', True),
        'band_narr':     ('쓰인01', True),
        'band_dlg':      ('쓰인02', True),
        'band_emph':     ('쓰인02', True),
        'effect_float':  ('쓰인04', False),
        'credit_cta_l1': ('쓰인08', True),
        'credit_cta_l2': ('쓰인08', True),
        'badge':         ('쓰인08', True),
        'airinfo':       ('쓰인08', True),
    },
    '무비오션': {
        'headline_l1':   ('쓰인10', True),   # 두 줄 제목 (빨강 + 노랑)
        'headline_l2':   ('쓰인10', True),
        # ★색은 **덮어쓰지 못한다** — 곳간 「쓰인01」은 칠 값이 아예 없어(None)
        #   서식입히기가 root/10 에 쓸 자리가 없다. 그래서 흰색으로만 나온다
        #   (2026-08-25 포핸즈 1-1: 나레·모션자막이 전부 흰색으로 나왔다).
        #   **그 색을 원래 가진 본**을 가져다 쓴다. 흰 자막만 「쓰인01」로 둔다.
        'band_narr':     ('쓰인05', True),   # ★run/2 가 있는 본 — 여기에 우리 색을 덮어쓴다
        'band_dlg':      ('쓰인01', True),   # run/2 없음 = 흰 글자 — 대사는 흰색이라 이대로 맞다
        'band_emph':     ('쓰인02', True),   # 강조 (진홍)
        'effect_float':  ('쓰인02', False),  # ★run/2 가 있는 본 (쓰인08 은 없어서 흰색이 됐다)
        'credit_cta_l1': ('쓰인04', True),
        'credit_cta_l2': ('쓰인04', True),
    },
    '불륜': {
        # ★《지금 불륜이 문제가 아닙니다》 (2026-09-03). 곳간 `불륜_본` 은 **신병4_본 과 같은 파일**(구조 도너).
        #   예시 `불륜 프프.prproj` 에서 뜬 곳간(불륜예시_본)은 프리미어 판이 달라 칸 배치가 어긋났다 —
        #   색이 둘레·2줄 칠에 들어가고 x 가 0.0185 로 앉고 아모르가 상자를 못 찾았다. 그래서 신병4 짝을 그대로 쓴다.
        #   생김새(Cafe24 Ohsquare 89·하늘/흰/분홍·y1355)는 불륜/서식.py 의 ASS 가 정하고 서식입히기·자리잡기가 입힌다.
        'headline_l1':   ('쓰인02', True),
        'headline_l2':   ('쓰인02', True),
        'band_narr':     ('쓰인01', True),
        'band_dlg':      ('쓰인02', True),
        'band_emph':     ('쓰인02', True),
        'effect_float':  ('쓰인04', False),
        'credit_cta_l1': ('쓰인08', True),
        'credit_cta_l2': ('쓰인08', True),
        'badge':         ('쓰인08', True),
        'airinfo':       ('쓰인08', True),
    },
    '미안해형': {
        'headline_l1':   ('쓰인10', True),   # 두 줄 제목 (빨강 + 노랑)
        'headline_l2':   ('쓰인10', True),
        # ★색은 **덮어쓰지 못한다** — 곳간 「쓰인01」은 칠 값이 아예 없어(None)
        #   서식입히기가 root/10 에 쓸 자리가 없다. 그래서 흰색으로만 나온다
        #   (2026-08-25 포핸즈 1-1: 나레·모션자막이 전부 흰색으로 나왔다).
        #   **그 색을 원래 가진 본**을 가져다 쓴다. 흰 자막만 「쓰인01」로 둔다.
        'band_narr':     ('쓰인05', True),   # ★run/2 가 있는 본 — 여기에 우리 색을 덮어쓴다
        'band_dlg':      ('쓰인01', True),   # run/2 없음 = 흰 글자 — 대사는 흰색이라 이대로 맞다
        'band_emph':     ('쓰인02', True),   # 강조 (진홍)
        'effect_float':  ('쓰인02', False),  # ★run/2 가 있는 본 (쓰인08 은 없어서 흰색이 됐다)
        'credit_cta_l1': ('쓰인04', True),
        'credit_cta_l2': ('쓰인04', True),
    }

}

클립값 = ('위치', '비율 조정', '가로 비율', '회전', '기준점')


def 칸나누기(쪽):
    표 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', 쪽)]
    return [(표[i], 표[i + 1] if i + 1 < len(표) else len(쪽)) for i in range(len(표))]


def 글줄들(raw):
    """덩어리 안의 글줄 글자를 차례대로."""
    buf, _ = S.unwrap(raw)
    f = S._fields(buf, S._root0(buf))
    if 0 not in f:
        return []
    p = f[0]; v = p + F.u32(buf, p); n = F.u32(buf, v)
    out = []
    for i in range(n):
        ep = v + 4 + 4 * i
        e = ep + F.u32(buf, ep)
        g = S._fields(buf, e)
        if 0 not in g:
            continue
        t = g[0] + F.u32(buf, g[0])
        out.append(bytes(buf[t + 4:t + 4 + F.u32(buf, t)]).decode('utf-8', 'replace'))
    return out


def 본뜨기(쪽):
    """본보기에서 {이름: (덩어리 base64, {클립값})}"""
    나옴 = {}
    for a, b in 칸나누기(쪽):
        도막 = 쪽[a:b]
        m = 내덩어리(도막)
        if not m:
            continue
        try:
            글 = ''.join(글줄들(base64.b64decode(m.group(1))))
        except Exception:
            continue
        for 이름, 씨 in 본.items():
            if 이름 in 나옴 or 씨 not in 글:
                continue
            값 = {}
            for k in 클립값:
                mm = re.search(r'<Name>' + k + r'</Name>\s*<StartKeyframe>[^,]+,([^,]+),', 도막)
                if mm:
                    값[k] = mm.group(1)
            나옴[이름] = (m.group(1), 값)
    return 나옴


def ass층(경로):
    """우리 자막의 «글자 → 층 이름»"""
    차림, 표 = None, {}
    for 줄 in open(경로, encoding='utf-8'):
        줄 = 줄.rstrip('\n')
        if 줄.startswith('Format:') and 차림 is None and 'Name' in 줄:
            차림 = [t.strip() for t in 줄[7:].split(',')]
        if 줄.startswith('Dialogue:'):
            f = 줄.split(',', 9)
            글 = re.sub(r'\{[^}]*\}', '', f[9]).strip()
            if 글:
                표.setdefault(글, f[3].strip())
    return 표


P = argparse.ArgumentParser()
P.add_argument('우리')
P.add_argument('곳간')
P.add_argument('자막')
P.add_argument('--보기만', action='store_true', dest='보기만')
P.add_argument('--자막층', default=None, dest='자막층',
               help='프리미어/자막층.json — 글자가 겹쳐 «빈 껍데기» 가 생긴 편에서, '
                    '글자 대신 **차례**로 층을 정한다')
A = P.parse_args()

import io
import json
# ★«내 옆의 스타일/» 로 못 박으면 안 된다 (2026-08-27).
#   도구맞추기.py 가 이 파일을 **편 폴더에** 내려보내면, 편 폴더엔 스타일/ 이 없어서
#   「그런 곳간이 없다」로 죽는다. 아모르입히기.py 가 같은 함정에 빠졌던 것과 같다.
#   → 있는 데를 **찾아 올라간다.**
def _곳간찾기(이름):
    길 = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        for 뒤 in (os.path.join(길, '스타일', 이름 + '_본.json'),
                   os.path.join(길, '린박스_배포키트', '스타일', 이름 + '_본.json')):
            if os.path.exists(뒤):
                return 뒤
        위 = os.path.dirname(길)
        if 위 == 길:
            break
        길 = 위
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '스타일', 이름 + '_본.json')


곳간길 = _곳간찾기(A.곳간)
if not os.path.exists(곳간길):
    raise SystemExit(f'그런 곳간이 없다: {곳간길}' + chr(10) +
                     f'먼저 — python 스타일모으기.py <본보기.prproj> {A.곳간}')
곳간 = json.load(open(곳간길, encoding='utf-8'))['본']
if A.곳간 not in 맞춤:
    raise SystemExit(f'{A.곳간} 의 층 맞춤표가 없다 — 본떠서만들기.py 의 «맞춤» 에 넣어라')
층 = 맞춤[A.곳간]

print('═' * 76)
print(f'  본떠서 만들기 — 곳간 {A.곳간} (본 {len(곳간)}개)')
print('═' * 76)
본표 = {}
for 층이름, (본이름, _) in 층.items():
    if 본이름 not in 곳간:
        raise SystemExit(f'곳간에 «{본이름}» 이 없다 — 스타일/{A.곳간}_본.md 를 봐라')
    v = 곳간[본이름]
    본표[본이름] = (v['덩어리'], v.get('클립', {}))
for 본이름, (b64, 값) in 본표.items():
    sh = 곳간[본이름]['모양']
    print(f'  본 «{본이름}» {sh["글꼴"]} 크기 {sh["글줄"][0].get("크기")} 칠 {sh["글줄"][0].get("칠")} '
          f'선굵기 {sh["글줄"][0].get("선굵기")} 둘레색 {sh["둘레색"]} · 글줄 {sh["글줄수"]}')

층표 = ass층(A.자막)

# ★같은 문구가 되풀이되는 편에서는 글자로 층을 못 찾는다 (2026-08-25).
#   프리미어는 **내용이 같은 덩어리를 한 번만 저장하고** 나머지는 BinaryHash 로 가리킨다.
#   포헨즈 1화는 모션자막이 6문구 × 6번이라 30장이 «빈 껍데기» 였다.
#   그때는 `프리미어/자막층.json`(export_premiere.py 가 낸다) 의 **차례**로 정한다.
#   ★차례가 믿을 만한 근거: XML 이 V3 나레 → V4 대사 → V5 모션 순으로 선언하고
#     프리미어가 그 순서대로 오브젝트를 쓴다. 포헨즈 편에서 실측 —
#     읽힌 45장 중 **어긋남 0장**. 껍데기 30장도 같은 줄에 앉는다.
_층이름맞춤 = {'나레자막': 'band_narr', '대사자막': 'band_dlg', '모션자막': 'effect_float'}
차례층 = None
if A.자막층:
    _j = json.load(io.open(A.자막층, encoding='utf-8'))
    차례층 = [_층이름맞춤.get(d['층'], d['층']) for 이름 in ('나레자막', '대사자막', '모션자막', '제목자막')
              for d in _j if d['층'] == 이름]
    차례글 = [d['글'] for 이름 in ('나레자막', '대사자막', '모션자막', '제목자막') for d in _j if d['층'] == 이름]
    print(f'  자막층.json {len(차례층)}장 — 차례로 층을 정한다')
쪽 = gzip.open(A.우리, 'rb').read().decode('utf-8')
칸 = 칸나누기(쪽)
print(f'\n  우리 자막 {len(칸)}장')

# ── ★빈 껍데기 — 겁낼 것이 아니라 «주인이 있는지»를 보면 된다 (2026-08-25) ──────
#   프리미어는 **같은 내용의 덩어리를 한 번만 저장하고** 나머지는 BinaryHash 로 가리킨다.
#   린박스 모션자막은 같은 문구를 여러 번 띄우므로(포헨즈 1화: 6문구 × 6장) 껍데기가 30장 나온다.
#
#   ★그런데 그건 **탈이 아니다.** 이 도구는 덩어리를 «읽어서 고치는» 게 아니라
#     곳간 덩어리를 **통째로 써 넣는다.** 한 무리에 «내용 담은 태그» 가 하나만 있으면
#     그 하나를 고치는 것으로 **그 무리 전부가 함께 바뀐다.** 껍데기는 저절로 따라온다.
#     (포헨즈 1화 실측: 해시 무리 45개 · 전부 내용 담은 태그 하나씩 · 껍데기 30장 = 6문구×5)
#
#   ★진짜 탈은 «**주인 없는 껍데기**» 다 — 그 해시의 내용이 파일 어디에도 없는 것.
#     그때만 멈춘다. [[premiere-private-data-hash]] 와 같은 규칙이다.
import collections as _c
무리 = _c.defaultdict(lambda: [0, 0])
for a, b in 칸:
    도막 = 쪽[a:b]
    끝 = 도막.find('<Name>', 1)
    seg = 도막 if 끝 < 0 else 도막[:끝]
    h = re.search(r'<StartKeyframeValue[^>]*BinaryHash="([^"]+)"', seg)
    무리[h.group(1) if h else '?'][0 if 내덩어리(도막) else 1] += 1
껍데기 = sum(v[1] for v in 무리.values())
주인없음 = [h for h, v in 무리.items() if v[0] == 0]
if 껍데기:
    print(f'  덩어리를 나눠 쓰는 장 {껍데기}장 — 같은 문구를 여러 번 띄우는 층(모션자막 등)이다.')
    print(f'    해시 무리 {len(무리)}개 · 한 무리를 고치면 그 무리가 함께 바뀐다.')
if 주인없음:
    print(f'  ★주인 없는 껍데기 {len(주인없음)}무리 — 그 해시의 내용이 파일 어디에도 없다.')
    if 차례층:
        print('    → --자막층 을 받았다. **글자 대신 차례로** 층을 정한다 (껍데기도 함께 고친다)')
    elif not A.보기만:
        raise SystemExit('    멈춘다. (--보기만 으로는 그냥 볼 수 있다 · --자막층 을 주면 뚫린다)')

고침, 못 = [], []
셈 = {}
if 차례층 is not None and len(차례층) != len(칸):
    raise SystemExit(f'자막층.json 은 {len(차례층)}장인데 프로젝트엔 {len(칸)}장이다 — 짝이 안 선다')
for _차, (a, b) in enumerate(칸):
    도막 = 쪽[a:b]
    m = 내덩어리(도막)
    if not m and 차례층 is None:
        continue
    if m:
        raw = base64.b64decode(m.group(1))
        우리글 = 글줄들(raw)
        본문 = ''.join(우리글)
    else:
        우리글, 본문 = [차례글[_차]], 차례글[_차]      # 껍데기 — 표에서 글자를 가져온다
    이름 = 층표.get(본문.replace('\r', '\n')) or 층표.get(우리글[0].replace('\r', '\n').strip() if 우리글 else '')
    if 이름 is None:
        for q in 본문.replace('\r', '\n').split('\n'):
            이름 = 층표.get(q.strip())
            if 이름:
                break
    if 차례층 is not None:
        이름 = 차례층[_차]                 # ★차례가 이긴다 (글자가 겹쳐도 흔들리지 않는다)
    if 이름 is None or 이름 not in 층:
        못.append(본문[:20]); continue
    본이름, 자리도 = 층[이름]
    본b64, 본값 = 본표[본이름]
    새raw = base64.b64decode(본b64)
    본글 = 글줄들(새raw)
    # 글줄 수가 다르면 첫 글줄에 우리 글자를 통째로 넣는다
    if len(본글) == len(우리글):
        짝 = list(zip(본글, 우리글))
    else:
        짝 = [(본글[0], 본문)] + [(t, '') for t in 본글[1:]]
    for 옛, 새 in 짝:
        if 옛 == 새:
            continue
        새raw = S.replace_text(새raw, 옛, 새 if 새 else ' ')
    # ★껍데기(BinaryHash 만 가리키는 자기닫힘 장)에는 바꿔 넣을 본문이 없다.
    #   그 무리의 **주인**이 제 차례에 고쳐지면 껍데기도 함께 바뀐다.
    #   전에는 여기서 m.group(1) 을 그냥 불러 AttributeError 로 죽었다 (2026-08-26).
    if m:
        도막 = 도막.replace(m.group(1), base64.b64encode(새raw).decode('ascii'), 1)
    for k in 클립값:
        if not 자리도 and k == '위치':
            continue                      # 모션자막은 우리 자리를 지킨다
        if k in 본값:
            도막 = re.sub(r'(<Name>' + k + r'</Name>\s*<StartKeyframe>)(-?\d+),([^,]+)(,)',
                          lambda z: z.group(1) + z.group(2) + ',' + 본값[k] + z.group(4), 도막, count=1)
    고침.append((a, b, 도막))
    셈[이름] = 셈.get(이름, 0) + 1

print()
for 이름, n in sorted(셈.items()):
    print(f'   {이름:<14} → 본 «{층[이름][0]}»  {n}장')
if 못:
    print(f'   ★못 찾은 것 {len(못)}장: {못[:5]}')

if A.보기만:
    print('\n(--보기만)')
    raise SystemExit(0)

새쪽, 끝 = [], 0
for a, b, 도막 in 고침:
    새쪽.append(쪽[끝:a]); 새쪽.append(도막); 끝 = b
새쪽.append(쪽[끝:])
새쪽 = ''.join(새쪽)

확 = re.findall(덩어리찾기, 새쪽)
# ★«내용 담은 덩어리» 수로 잰다 — len(칸) 이 아니다 (2026-08-25).
#   같은 문구가 되풀이되는 편에서는 프리미어가 덩어리를 한 무리에 하나만 저장하고
#   나머지는 BinaryHash 로 가리킨다(포헨즈 1화: 75칸 · 무리 45 · 껍데기 30).
#   그때 len(확) 는 75가 아니라 45다. 그걸 «달라졌다» 로 읽어 애먼 곳에서 멈췄다.
전 = re.findall(덩어리찾기, 쪽)
if len(확) != len(전):
    raise SystemExit(f'덩어리 수가 달라졌다 — 전 {len(전)} · 후 {len(확)}')
for b64 in 확:
    buf, _ = S.unwrap(base64.b64decode(b64))
    S.runs(buf); S._fields(buf, S._root0(buf))
print(f'  되읽기 확인 — {len(확)}/{len(전)} 정상'
      + (f'  (칸 {len(칸)} 중 껍데기 {len(칸) - len(전)}장은 무리로 따라온다)'
         if len(전) != len(칸) else ''))

백업 = A.우리.replace('.prproj', f'_본뜨기전_{time.strftime("%m%d_%H%M")}.prproj')
shutil.copy2(A.우리, 백업)
with gzip.open(A.우리, 'wb') as fh:
    fh.write(새쪽.encode('utf-8'))
print(f'  전 판은 옆에 두었다: {os.path.basename(백업)}')
print(f'  다 됐다 → {A.우리}')
