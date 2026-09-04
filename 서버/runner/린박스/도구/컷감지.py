# -*- coding: utf-8 -*-
r"""**판정하는 쪽과 똑같은 눈으로** 컷을 센다.

왜 따로 뽑았나
  `장면컷.py` 는 소재를 보고 컷을 찾고, `검수.py` 는 완성본을 보고 다시 찾는다.
  둘이 **다른 잣대**를 쓰면 계획은 «괜찮다» 인데 결과는 «번쩍인다» 가 된다.
  실제로 그랬다 — 더 글로리 ep_0605-0735 의 번쩍임 7곳이
  `scene_cuts.txt` 에는 **한 곳도 없었다.**

  규격 §24 와 같은 병이다: **재는 자가 그리는 자와 달랐다.**

여기 값은 `검수.py` 의 것을 그대로 옮긴 것이다. 고칠 때는 **둘 다** 고쳐라.
"""
import numpy as np

import 영상읽기

격자Y, 격자X = 12, 16
칸바닥 = 10.0        # 아무리 어두워도 이만큼은 바뀌어야 «바뀐 칸»
칸기울기 = 0.12      # 그 칸이 밝을수록 문턱도 함께 올린다
컷문턱 = 0.70        # 바뀐 칸이 이 비율을 넘으면 컷 후보
동무문턱 = 0.42      # 이보다 높으면 «저도 높은 프레임»
동무한계 = 3         # 둘레(±0.5초)에 동무가 이보다 많으면 컷이 아니라 «움직임»


def 컷들(경로, 잘라=None, 크기=(160, 151)):
    """그 영상에서 컷이 나는 시각 목록. 잘라=(위,아래) 면 그 띠만 본다."""
    fps = 영상읽기.초당프레임(경로)
    prev, D = None, []
    for _, t, g in 영상읽기.회색프레임(경로, 잘라=잘라, 크기=크기):
        if prev is not None:
            d = np.abs(g - prev)
            h, w = d.shape
            ch, cw = h // 격자Y, w // 격자X
            칸차 = np.empty((격자Y, 격자X), dtype=np.float32)
            칸밝 = np.empty((격자Y, 격자X), dtype=np.float32)
            for y in range(격자Y):
                for x in range(격자X):
                    ys, xs = slice(y * ch, (y + 1) * ch), slice(x * cw, (x + 1) * cw)
                    칸차[y, x] = d[ys, xs].mean()
                    칸밝[y, x] = max(g[ys, xs].mean(), prev[ys, xs].mean())
            바뀜 = 칸차 > np.maximum(칸바닥, 칸기울기 * 칸밝)
            D.append((t, float(바뀜.mean())))
        prev = g
    if not D:
        return []
    t = [x[0] for x in D]
    r = np.array([x[1] for x in D], dtype=np.float32)
    창 = max(3, int(round(fps * 0.5)))
    out = []
    for j in range(len(r)):
        a, b = max(0, j - 창), min(len(r), j + 창 + 1)
        둘레 = np.concatenate((r[a:j], r[j + 1:b]))
        if r[j] > 컷문턱 and int((둘레 > 동무문턱).sum()) <= 동무한계:
            out.append(t[j])
    # 붙어 있는 것은 하나로
    묶음 = []
    for x in out:
        if not 묶음 or x - 묶음[-1] > 0.08:
            묶음.append(x)
    return 묶음
