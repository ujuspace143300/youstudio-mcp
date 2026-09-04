# -*- coding: utf-8 -*-
r"""**누가 말했는가** 를 정하고 얼굴로 확인시킨다. 대본을 쓰기 전에 돈다.

왜 필요한가 — 더 글로리 1편에서 실제로 난 사고
  보건실 장면에서 「제가요」 라고 답한 사람은 **연진** 인데, 나레이션이
  「동은이 답한 건 세 글자」 라고 못 박았다. 사장님이 잡아 내셨다.

  더 뼈아픈 것 — **서버는 진작 알려 줬다.**
    11.69 [S2] 주시면 제가 할게요        ← 동은
    67.19 [S3] 제가요                    ← 다른 사람이다
  `전사.py` 는 낱말마다 `spk` 를 받아 `대사.json` 에 넣어 둔다. 그런데
  `author.py` 에는 `spk` 라는 낱말이 **한 번도 안 나온다.** 대본은 «무슨 말을
  했나» 만 보고 «누가 했나» 는 버린 채 쓰였다. 검수기도 자막 글자와 ASR 글자를
  견줄 뿐이라 — 둘 다 같은 소리에서 나오니 — 사람을 바꿔 붙여도 통과한다.

무엇을 하나
  ① `대사.json` 의 낱말을 화자 덩이로 묶는다
  ② 덩이마다 그 순간 화면의 **얼굴을 오려** 한 장에 붙인다
  ③ 사람이 보고 `화자.json` 에 이름을 적는다  {"S2":"동은","S3":"연진"}
  ④ 그 뒤 `화자검사.py` 가 대본과 대조한다 — 이름이 어긋나면 렌더를 막는다

  ★ASR 이 **전부 한 뭉치로 묶어 버리는 일이 흔하다** — 실측 11편 중 4편이 그랬다.
    그러면 뭉치별 표는 쓸모가 없다. 그래서 **발화 한 줄마다 얼굴을 따로** 뽑아
    `_화자줄.jpg` 를 함께 낸다. 사람은 거기에 줄마다 이름을 적는다(`화자줄.json`).
    화자검사는 줄별 이름이 있으면 그걸 먼저 쓴다.

  ★ASR 의 S1·S2 는 **목소리 뭉치**지 사람이 아니다. 한 사람이 두 표로 갈리거나
    두 사람이 한 표에 섞이기도 한다. 그래서 «자동으로 이름 붙이기» 는 안 한다.
    이 도구는 판정하지 않고 **보여 준다.** 이름은 사람이 적는다.

쓰는 법
  python 화자표.py [소재.mp4]     → _화자표.jpg 와 화자.json(빈칸) 을 낸다
"""
import io
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont


def 한글글꼴(크기):
    """PIL 기본 글꼴은 한글이 **모두 두부(네모)** 로 나온다 — 대사를 못 읽으면
    표가 쓸모없다. 키트 글꼴 → 윈도우 맑은고딕 차례로 찾는다."""
    여기 = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(여기, '..', '자산', 'fonts', 'malgun.ttf'),
              os.path.join(여기, 'fonts', 'malgun.ttf'),
              'fonts/malgun.ttf',
              'C:/Windows/Fonts/malgun.ttf',
              'C:/Windows/Fonts/NanumGothic.ttf'):
        if os.path.exists(c):
            return ImageFont.truetype(c, 크기)
    return ImageFont.load_default()

SRC = sys.argv[1] if len(sys.argv) > 1 else '구간_인물.mp4'
GAP = 0.9          # 이만큼 쉬면 다른 덩이로 본다
SHOTS = 3          # 화자 한 명당 보여 줄 얼굴 수

D = json.load(io.open('대사.json', encoding='utf-8'))['words']

# ── ① 화자 덩이로 묶는다
그룹, 현재 = [], None
for w in D:
    if 현재 and w['spk'] == 현재[-1]['spk'] and w['s'] - 현재[-1]['e'] < GAP:
        현재.append(w)
    else:
        if 현재:
            그룹.append(현재)
        현재 = [w]
if 현재:
    그룹.append(현재)

화자 = {}
for g in 그룹:
    화자.setdefault(g[0]['spk'], []).append(g)

print("화자 %d명 · 발화 %d덩이" % (len(화자), len(그룹)))

# ── ② 얼굴을 오린다
try:
    import cv2
    YN = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '자산', 'yunet.onnx')
    if not os.path.exists(YN):
        YN = 'yunet.onnx'
    det = cv2.FaceDetectorYN.create(YN, "", (320, 320), 0.6) if os.path.exists(YN) else None
except Exception:
    cv2, det = None, None
if det is None:
    print("  ※ yunet 이 없어 얼굴을 못 오린다 — 화면 전체를 보여 준다")

os.makedirs('_화자표', exist_ok=True)


def 뽑기(t, 이름):
    p = '_화자표/%s.jpg' % 이름
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '%.3f' % t, '-i', SRC,
                    '-frames:v', '1', '-q:v', '3', p], check=True)
    if det is None:
        return Image.open(p)
    # ★cv2.imread 는 **한글 경로를 못 읽는다** — 조용히 None 을 돌려준다.
    #   이 폴더 이름이 한글이라 그대로 두면 여기서 죽는다. 바이트로 읽어 푼다.
    import numpy as np
    im = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        return Image.open(p)
    h, w = im.shape[:2]
    det.setInputSize((w, h))
    _, fs = det.detect(im)
    pic = Image.open(p)
    if fs is None or len(fs) == 0:
        return pic
    # 가장 큰 얼굴을 넉넉히 오린다 (턱·머리까지 보이게)
    x, y, fw, fh = max(fs, key=lambda f: f[2] * f[3])[:4]
    m = fw * 0.85
    box = (max(0, int(x - m)), max(0, int(y - m * 1.1)),
           min(w, int(x + fw + m)), min(h, int(y + fh + m * 1.3)))
    return pic.crop(box)


칸 = []
for s in sorted(화자, key=lambda k: 화자[k][0][0]['s']):
    gs = sorted(화자[s], key=lambda g: -(g[-1]['e'] - g[0]['s']))[:SHOTS]
    말 = ' / '.join(''.join(w['t'] for w in g) for g in
                   sorted(화자[s], key=lambda g: g[0]['s']))
    임 = []
    for n, g in enumerate(gs):
        t = (g[0]['s'] + g[-1]['e']) / 2
        임.append((뽑기(t, '%s_%d' % (s, n)), t))
    칸.append((s, 말, 임, sum(g[-1]['e'] - g[0]['s'] for g in 화자[s])))

# ── ③ 한 장으로 붙인다
TW, TH = 300, 380
LH = 46
sheet = Image.new('RGB', (TW * SHOTS, (TH + LH) * len(칸)), (16, 16, 16))
dr = ImageDraw.Draw(sheet)
F크, F작 = 한글글꼴(17), 한글글꼴(14)
for r, (s, 말, 임, tot) in enumerate(칸):
    y = r * (TH + LH)
    for c, (im, t) in enumerate(임):
        im = im.copy()
        im.thumbnail((TW, TH))
        sheet.paste(im, (c * TW + (TW - im.size[0]) // 2, y + (TH - im.size[1]) // 2))
        dr.text((c * TW + 6, y + TH - 18), "%.1fs" % t, fill=(150, 200, 255), font=F작)
    dr.rectangle([0, y + TH, TW * SHOTS, y + TH + LH], fill=(0, 0, 0))
    dr.text((8, y + TH + 3), "%s  (%.0f초)" % (s, tot), fill=(255, 230, 0), font=F크)
    dr.text((8, y + TH + 24), 말[:90], fill=(210, 210, 210), font=F작)
    dr.line([0, y, TW * SHOTS, y], fill=(90, 90, 90))
sheet.save('_화자표.jpg', quality=88)

# ── ④ 사람이 채울 빈칸
if os.path.exists('화자.json'):
    print("→ _화자표.jpg   (화자.json 은 이미 있어 그대로 둔다)")
else:
    json.dump({s: "" for s, _, _, _ in 칸},
              io.open('화자.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print("→ _화자표.jpg · 화자.json (빈칸)")
print("★ _화자표.jpg 를 보고 화자.json 에 이름을 적어라. 그 뒤 화자검사.py 를 돌린다.")
print("  한 표에 두 사람이 섞였으면 이름을 «연진+동은» 처럼 적어 두면 검사가 넘어간다.")

# ── ⑤ 발화 **한 줄마다** 얼굴 — 뭉치가 뭉개졌을 때 이게 진짜 쓰인다
줄수 = len(그룹)
if 줄수 <= 60:
    칸W, 칸H, 글H = 210, 250, 40
    C = 6
    R = (줄수 + C - 1) // C
    장 = Image.new('RGB', (칸W * C, (칸H + 글H) * R), (16, 16, 16))
    d2 = ImageDraw.Draw(장)
    F2, F3 = 한글글꼴(15), 한글글꼴(13)
    표 = []
    for n, g in enumerate(그룹):
        t = (g[0]['s'] + g[-1]['e']) / 2
        말 = ''.join(w['t'] for w in g)
        im = 뽑기(t, '줄%02d' % n).copy()
        im.thumbnail((칸W, 칸H))
        x, y = (n % C) * 칸W, (n // C) * (칸H + 글H)
        장.paste(im, (x + (칸W - im.size[0]) // 2, y + (칸H - im.size[1]) // 2))
        d2.rectangle([x, y + 칸H, x + 칸W, y + 칸H + 글H], fill=(0, 0, 0))
        d2.text((x + 5, y + 3), '#%d' % n, fill=(255, 230, 0), font=F2)
        d2.text((x + 5, y + 칸H + 2), '#%d  %.1fs [%s]' % (n, g[0]['s'], g[0]['spk']),
                fill=(255, 230, 0), font=F3)
        d2.text((x + 5, y + 칸H + 20), 말[:16], fill=(210, 210, 210), font=F3)
        d2.line([x, y, x, y + 칸H + 글H], fill=(80, 80, 80))
        표.append({'n': n, 't': round(g[0]['s'], 2), 'e': round(g[-1]['e'], 2),
                   '뭉치': g[0]['spk'], '말': 말, '이름': ''})
    장.save('_화자줄.jpg', quality=88)
    if os.path.exists('화자줄.json'):
        print('→ _화자줄.jpg   (화자줄.json 은 이미 있어 그대로 둔다)')
    else:
        json.dump(표, io.open('화자줄.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('→ _화자줄.jpg · 화자줄.json (줄 %d개, 이름 빈칸)' % 줄수)
    print('★뭉치가 하나로 뭉개졌으면 **이쪽**에 줄마다 이름을 적어라.')
