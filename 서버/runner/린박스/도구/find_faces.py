# -*- coding: utf-8 -*-
r"""촬영본마다 **화면 어디를 보여줄지** 정한다 → faces.json

서버는 소재를 세로창(1080x1020)에 담을 때 가로 가운데의 일부만 쓴다.
영화는 인물을 가운데 두지 않으니, 그 창을 촬영본마다 옮겨 줘야 한다.

  쓸 창 폭(WIN) = 소재높이 x 1080 / 1020
    소년심판 1920x1080 → 1143      타짜 1920x804 → 852
  ★레터박스(위아래 검은 띠)가 있으면 **먼저 잘라낸 뒤** 재라.
    띠까지 높이에 넣으면 창이 실제보다 넓게 잡혀 인물이 도로 잘린다.

무엇을 잡는가 — 순서대로
  ① 얼굴이 하나면 그 얼굴을 가운데로
  ② 얼굴이 여럿이면
       · 창 안에 다 들어오면 → 무게중심
       · 안 들어오면 → **가장 큰 얼굴 하나만** 온전히 담는다
         ★평균을 내면 창이 두 사람 **사이**에 놓여 둘 다 반씩 잘린다.
           실제로 그래서 «사람이 계속 잘린다» 는 지적을 받았다.
  ③ 얼굴이 없으면 (손·패·뒷모습 클로즈업) → **결이 가장 촘촘한 곳**을 가운데로.
       손이나 화투패가 거기 있다. 가운데 고정보다 낫다.

먼저 있어야 하는 것
  구간.mp4 · scene_cuts.txt (장면컷.py) · yunet.onnx (자산\yunet.onnx 를 편 폴더로)

쓰는 법
  편 폴더에서:  python 도구\find_faces.py
"""
import json
import sys
from collections import Counter

import cv2
import numpy as np

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ▼편별 ─── 여기를 이 편 것으로 바꾼다 ────────────────────────────────
SRC = '구간.mp4'
# 서버가 실제로 쓰는 가로 폭 = 소재높이 x 1080/1020 (위 설명 참고)
#   1920x1080 (레터박스 없음) → 1143
#   1920x804  (2.39:1 시네마) → 852
WIN = 1143
# ▲편별 ──────────────────────────────────────────────────

MARGIN = 40                     # 얼굴이 창 끝에 딱 붙지 않게
SC = sorted(float(x) for x in open('scene_cuts.txt'))

cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
권장 = int(round(H * 1080 / 1020))
if abs(권장 - WIN) > 8:
    print(f"  ★소재가 {W}x{H} 이면 창 폭은 {권장} 이어야 한다 — 지금 WIN={WIN}.")
    print(f"    레터박스를 안 잘랐거나 ▼편별 값을 안 고쳤다.")
SRC_DUR = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
edges = [0.0] + SC + [SRC_DUR]
shots = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
det = cv2.FaceDetectorYN.create('yunet.onnx', '', (W, H), 0.6, 0.3, 5000)

want = {}
for si, (a, b) in enumerate(shots):
    t = a + 0.10
    while t < b - 0.05:
        want.setdefault(int(round(t * fps)), si)
        t += 0.25
    want.setdefault(int(round((a + b) / 2 * fps)), si)

faces = {i: [] for i in range(len(shots))}
detail = {i: [] for i in range(len(shots))}
i = 0
while True:
    ok, img = cap.read()
    if not ok:
        break
    if i in want:
        si = want[i]
        _, fs = det.detect(img)
        got = []
        if fs is not None:
            for f in fs:
                x, y, w, h, sc = f[0], f[1], f[2], f[3], f[-1]
                if sc < 0.65 or w < 22:
                    continue
                got.append((float(x + w / 2), float(w), float(h), float(sc)))
        faces[si].append(got)
        if not got:
            # 얼굴이 없다 — 결(가장자리)이 촘촘한 가로 위치를 잡는다. 손·패가 거기 있다.
            g = cv2.cvtColor(cv2.resize(img, (240, 100)), cv2.COLOR_BGR2GRAY)
            e = (np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
                 + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)))
            col = e.sum(axis=0)
            if col.sum() > 1e-6:
                detail[si].append(float((col * np.arange(240)).sum() / col.sum()) / 240 * W)
    i += 1
cap.release()

res = []
for si, (a, b) in enumerate(shots):
    frames = [f for f in faces[si] if f]
    if frames:
        allf = [f for fr in frames for f in fr]
        xs = np.array([f[0] for f in allf])
        area = np.array([f[1] * f[2] for f in allf])
        spread = float(xs.max() - xs.min())
        # ★«전체에서 가장 큰 얼굴 하나» 를 기준으로 삼으면 안 된다 (2026-08-27).
        #   촬영본 끝자락 한 프레임에 큰 얼굴이 잡히면 그 한 장이 촬영본 전체의
        #   창을 끌고 간다 — 포헨즈 9편 52.88~54.72 가 그랬다. 얼굴은 내내
        #   x765 였는데 54.65초 한 프레임(x1280·폭381) 때문에 창이 1249 로 갔고
        #   완성본에서 얼굴이 가운데서 −435px 밀렸다.
        #   → **프레임마다 가장 큰 얼굴**을 고른 뒤 그 x·폭의 **중앙값**을 쓴다.
        _프레임큰것 = [max(fr, key=lambda f: f[1] * f[2]) for fr in frames]
        big = (float(np.median([f[0] for f in _프레임큰것])),
               float(np.median([f[1] for f in _프레임큰것])))
        if spread + big[1] <= WIN - 2 * MARGIN:
            cx = float(np.average(xs, weights=area))
            how = f'얼굴 모두 담김({len(frames)}프레임)'
        else:
            cx = float(big[0])                 # 가장 큰 얼굴 하나를 온전히
            how = f'큰 얼굴만(퍼짐 {spread:.0f}px)'
    elif detail[si]:
        cx = float(np.median(detail[si]))
        how = '얼굴 없음 · 손/패 쪽'
    else:
        cx = W / 2
        how = '단서 없음 · 가운데'
    LIM = (W - WIN) // 2        # 창이 화면 밖으로 나가지 않는 한계
    dx = max(-LIM, min(LIM, int(round(W / 2 - cx))))
    res.append({'i': si, 'a': round(a, 3), 'b': round(b, 3),
                'cx': round(cx, 1), 'dx': dx, 'how': how})

json.dump(res, open('faces.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
c = Counter(r['how'].split('(')[0].strip() for r in res)
print(f"소재 {W}x{H} · 창 {WIN}px · 촬영본 {len(res)}개 — "
      + " · ".join(f"{k} {v}" for k, v in c.most_common()))
for r in sorted(res, key=lambda r: -abs(r['dx']))[:8]:
    print(f"  {r['a']:6.2f}~{r['b']:6.2f}  중심 {r['cx']:6.1f}  밀기 {r['dx']:+5d}  {r['how']}")
