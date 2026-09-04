# -*- coding: utf-8 -*-
"""프리미어 트랙에 얹을 **그래픽 PNG** 를 짓는다 — 매트 · 로고 · 제목 · 효과자막.

왜 PNG 인가
  제목과 효과자막은 프리미어에서 **진짜 텍스트 그래픽**으로도 들어가지만(§52),
  매트·로고는 그림이라 PNG 트랙으로 얹는다. 제목·효과 PNG 는 «완성본과 프로젝트가
  같은 그림인가» 를 눈으로 대조할 때 쓴다.

무엇을 내나 (편 폴더의 `그래픽/` 안)
  `매트.png`     위 0~(창위-1) · 아래 (창아래+1)~1919 검정, 가운데는 투명
  `로고.png`     로고를 캔버스 제자리에 놓은 투명 배경 판
  `제목.png`     ass 의 headline_l1·l2 를 그대로 렌더
  `효과NN.png`   효과자막 한 장씩 + `효과계획.json` (시작·끝 프레임과 글)

알파를 어떻게 뽑나
  libass 는 알파 채널을 안 준다. 그래서 **검정 바탕과 흰 바탕에 두 번 그려**
  두 장의 차이로 알파를 역산한다 (mk_png 방식 — EP1 에서 검증).

쓰는 법
  python 그래픽짓기.py <편폴더> [--자막 captions_신병4.ass] [--로고 <png>]
                       [--로고윗선 1500] [--로고높이 190]
  로고를 안 쓰면 `--로고 없음`.
"""
import argparse
import io
import json
import os
import re
import subprocess

import numpy as np
from PIL import Image

P = argparse.ArgumentParser()
P.add_argument('편')
P.add_argument('--자막', default='captions_신병4.ass')
P.add_argument('--로고', default='')
P.add_argument('--로고윗선', type=int, default=None)   # 없으면 편정보.json 의 로고y (2026-09-03 불륜 — 기본값 1500/190 은 신병4 값이라 다른 작품에서 로고가 어긋났다)
P.add_argument('--로고높이', type=int, default=None)   # 없으면 편정보.json 의 로고높이
P.add_argument('--가로', type=int, default=1080)
P.add_argument('--세로', type=int, default=1920)
P.add_argument('--창위', type=int, default=450)
P.add_argument('--창아래', type=int, default=1470, help='아랫 매트가 시작하는 y')
P.add_argument('--fps', type=int, default=30)
A = P.parse_args()

# ★로고 자리·높이는 편정보.json 이 정본이다 (규격 §70). 인자로 안 주면 거기서 읽는다.
def _편정보값(키, 기본):
    for _p in (os.path.join(A.편 if hasattr(A, '편') else '.', '편정보.json'), '편정보.json'):
        if os.path.exists(_p):
            try:
                _v = json.load(open(_p, encoding='utf-8')).get(키)
                if _v: return int(_v)
            except Exception: pass
    return 기본
if A.로고윗선 is None: A.로고윗선 = _편정보값('로고y', 1500)
if A.로고높이 is None: A.로고높이 = _편정보값('로고높이', 190)

편 = os.path.abspath(A.편)
G = os.path.join(편, '그래픽')
글꼴방 = os.path.join(편, 'fonts')
os.makedirs(G, exist_ok=True)

자막길 = A.자막 if os.path.isabs(A.자막) else os.path.join(편, A.자막)
줄들 = io.open(자막길, encoding='utf-8').read().splitlines()
머리 = []
for l in 줄들:
    if l.startswith('Dialogue:'):
        break
    머리.append(l)
HEAD = '\n'.join(머리)


def 그려서알파(ass본문, 낼길):
    """검정판·흰판을 겹쳐 알파를 역산한 RGBA 를 쓴다. 불투명 픽셀 수를 돌려준다."""
    ap = os.path.join(G, '_tmp.ass')
    io.open(ap, 'w', encoding='utf-8').write(ass본문 + '\n')
    판 = {}
    for 바탕, 이름 in (('black', 'b'), ('white', 'w')):
        p = os.path.join(G, '_tmp_%s.png' % 이름)
        subprocess.run(
            ['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
             'color=c=%s:s=%dx%d:d=1,format=rgb24' % (바탕, A.가로, A.세로),
             '-vf', "format=rgb24,ass=filename='%s':fontsdir='%s',format=rgb24"
             % (ap, 글꼴방), '-frames:v', '1', p], check=True)
        판[이름] = np.array(Image.open(p).convert('RGB'), dtype=float) / 255.0
    Rb, Rw = 판['b'], 판['w']
    알파 = np.clip(1.0 - (Rw - Rb).mean(axis=2), 0.0, 1.0)
    알파[알파 < 0.08] = 0.0
    with np.errstate(divide='ignore', invalid='ignore'):
        앞 = np.where(알파[..., None] > 0.002,
                     Rb / np.maximum(알파[..., None], 1e-6), 0.0)
    앞 = np.clip(앞, 0, 1)
    Image.fromarray(np.dstack([(앞 * 255).astype(np.uint8),
                               (알파 * 255).astype(np.uint8)]), 'RGBA').save(낼길)
    return int((알파 > 0.01).sum())


def 초프레임(t):
    h, m, s = t.split(':')
    return int(round((int(h) * 3600 + int(m) * 60 + float(s)) * A.fps))


# ── 매트 ──────────────────────────────────────────────────────
매트 = np.zeros((A.세로, A.가로, 4), dtype=np.uint8)
매트[:A.창위, :, 3] = 255
매트[A.창아래:, :, 3] = 255
Image.fromarray(매트, 'RGBA').save(os.path.join(G, '매트.png'))
print('매트.png — 위 0~%d · 아래 %d~%d (가운데 투명)'
      % (A.창위 - 1, A.창아래, A.세로 - 1))

# ── 로고 ──────────────────────────────────────────────────────
if A.로고 and A.로고 != '없음':
    src = A.로고 if os.path.isabs(A.로고) else os.path.join(편, A.로고)
    im = Image.open(src).convert('RGBA')
    비 = A.로고높이 / float(im.height)
    im = im.resize((max(1, int(round(im.width * 비))), A.로고높이), Image.LANCZOS)
    판 = Image.new('RGBA', (A.가로, A.세로), (0, 0, 0, 0))
    판.paste(im, ((A.가로 - im.width) // 2, A.로고윗선), im)
    판.save(os.path.join(G, '로고.png'))
    print('로고.png — %dx%d · 윗선 y%d · 가운데 정렬'
          % (im.width, im.height, A.로고윗선))
else:
    Image.new('RGBA', (A.가로, A.세로), (0, 0, 0, 0)).save(os.path.join(G, '로고.png'))
    print('로고.png — 빈 판 (로고를 안 쓴다)')

# ── 제목 ──────────────────────────────────────────────────────
제목줄 = [l for l in 줄들 if l.startswith('Dialogue:') and ',headline_l' in l]
if 제목줄:
    n = 그려서알파(HEAD + '\n' + '\n'.join(제목줄), os.path.join(G, '제목.png'))
    print('제목.png — 불투명 픽셀 %s' % format(n, ','))

# ── 효과자막 ──────────────────────────────────────────────────
효과줄 = [l for l in 줄들 if l.startswith('Dialogue:') and ',effect_float,' in l]
계획 = []
for i, l in enumerate(효과줄):
    칸 = l.split(',', 9)
    글 = re.sub(r'\{[^}]*\}', '', 칸[9]).strip()
    # 한 장짜리 PNG 를 뽑을 때는 시간을 고정한다 (페이드가 섞이면 알파가 흐려진다)
    고정 = ('Dialogue: ' + ','.join(['0', '0:00:00.00', '0:00:10.00'] + 칸[3:9])
            + ',' + 칸[9])
    수 = 그려서알파(HEAD + '\n' + 고정, os.path.join(G, '효과%02d.png' % i))
    계획.append({'file': '효과%02d.png' % i, 'start': 초프레임(칸[1]),
                'end': 초프레임(칸[2]), 'text': 글})
    print('  효과%02d.png 「%s」 %d~%df · 픽셀 %s'
          % (i, 글, 계획[-1]['start'], 계획[-1]['end'], format(수, ',')))

json.dump(계획, io.open(os.path.join(G, '효과계획.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)
for f in ('_tmp.ass', '_tmp_b.png', '_tmp_w.png'):
    p = os.path.join(G, f)
    if os.path.exists(p):
        os.remove(p)
print('효과자막 %d장' % len(계획))
