# -*- coding: utf-8 -*-
r"""**한 촬영본 안에서 인물이 움직여 창을 벗어나는** 자리를 따라간다. find_faces 뒤에 돈다.

왜 있나 (2026-08-27 · 사장님 지적 「말하는 사람이 화면 밖으로 나가는 장면이 있다」)
  `find_faces.py` 는 촬영본마다 **창 자리를 하나** 정한다(`dx` 하나). 그런데
  · 인물이 그 촬영본 안에서 걸어가거나
  · 카메라가 따라가거나
  · 말하는 사람이 바뀌면
  얼굴이 창(가로 1143px) 밖으로 나간다. **그러면 말하는 사람이 안 보인다.**

  ★`화자추적.py` 와 다른 문제다. 그쪽은 «두 사람이 창보다 멀리 떨어져 한 명이 잘림» 을 본다.
    이쪽은 **한 사람이 움직여 벗어나는 것**이다 — 여태 아무도 안 봤다.
    실측: 포헨즈 1-7편 촬영본 33개 중 **15개**가 그랬다.

어떻게 푸나
  촬영본을 0.4초마다 훑어 **가장 큰 얼굴**의 가로 자리를 잰다.
  창 가장자리(여유 60px) 밖으로 나가면 그 자리에서 촬영본을 **잘라** 새 창 자리를 준다.
  `reframe.py` 는 이미 «누적 이동» 식을 쓰므로, `ease` 를 주면 **부드럽게 밀린다** —
  뚝 끊으면 없던 컷이 하나 생긴 것처럼 보이기 때문이다 (규격 §47).

쓰기
  python 도구\인물따라가기.py            재기만 한다
  python 도구\인물따라가기.py --쓰기      faces.json 에 반영 → 그 뒤 reframe.py 를 다시 돌려라
"""
import argparse
import io
import json
import os
import sys

import cv2

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

여유 = 60          # 창 가장자리에서 이만큼 안쪽에 있어야 «담겼다»
샘플 = 0.40        # 이 간격으로 훑는다
최소길이 = 1.20    # 이보다 짧은 촬영본은 안 나눈다 (나눠 봐야 조각이 된다)
최소조각 = 0.90    # 나눈 조각이 이보다 짧으면 안 나눈다
                   # ★0.60 으로 두었더니 미는 시간(0.35~0.9)보다 조각이 짧아
                   #   «미는 도중에 또 미는» 꼴이 됐다. 조각이 미는 시간보다 길어야 한다.
미는시간 = 0.35    # 밑값 — 실제로는 **옮기는 거리에 맞춰 늘린다** (아래 _미는시간)
최대미는시간 = 1.60
초당이동 = 260.0   # 1초에 이만큼(px)보다 빨리 밀면 «휙» 지나가 눈에 걸린다


def _미는시간(거리):
    """멀리 옮길수록 오래 민다 (2026-08-27).

    ★거리와 상관없이 0.35초로 밀었더니 **0.22초 만에 화면이 확 바뀌어** 튐으로 잡혔다.
      사람 눈에도 «휙» 지나가는 팬으로 보인다.

    ★2026-08-27 다시 잼 — 900px/초는 여전히 너무 빠르다. 완성본 프레임을 훑어
      «튄 자리» 를 골라 속도를 재 보니 이렇게 갈렸다:
          1432 · 1355 · 545 px/초 → 튄다        290 · 262 px/초 → 안 튄다
      그래서 **260px/초** 로 내리고, 미는 시간 한도를 1.60초로 올린다.
      시간이 모자라면 다 못 가는 편이 낫다 — 휙 도는 것보다 조금 치우친 게 낫다.
    """
    import math
    return max(미는시간, min(최대미는시간, abs(거리) / 초당이동))
최소얼굴 = 2500    # 이보다 작은 얼굴은 배경이라 안 본다


def main():
    P = argparse.ArgumentParser()
    P.add_argument('--쓰기', action='store_true', dest='쓰기')
    P.add_argument('--소재', default='구간.mp4', dest='소재')
    A = P.parse_args()

    if not os.path.exists('faces.json'):
        print('★faces.json 이 없다 — find_faces.py 를 먼저 돌려라')
        return 2
    F = json.load(io.open('faces.json', encoding='utf-8'))

    cap = cv2.VideoCapture(A.소재)
    if not cap.isOpened():
        print('★소재를 못 열었다: %s' % A.소재)
        return 2
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    WIN = int(round(H * 1080.0 / 1020.0))
    MAXX = W - WIN

    det = cv2.FaceDetectorYN.create('yunet.onnx', '', (320, 320), 0.6, 0.3, 5000)
    det.setInputSize((W, H))

    def 창x(dx):
        return max(0, min(MAXX, round(W / 2.0 - dx - WIN / 2.0)))

    def dx로(cx):
        """얼굴 가운데를 창 가운데에 두는 dx"""
        want = max(0, min(MAXX, round(cx - WIN / 2.0)))
        return round(W / 2.0 - want - WIN / 2.0)

    새목록, 나눈수, 본자리 = [], 0, 0
    for r in F:
        a, b = float(r['a']), float(r['b'])
        새목록.append(dict(r))
        if b - a < 최소길이:
            continue
        x0 = 창x(r['dx'])
        점 = []
        n = max(3, int((b - a) / 샘플))
        for k in range(n):
            t = a + (b - a) * (k + 0.5) / n
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, f = cap.read()
            if not ok:
                continue
            _, fa = det.detect(f)
            if fa is None:
                continue
            큰 = max(fa, key=lambda z: z[2] * z[3])
            if 큰[2] * 큰[3] < 최소얼굴:
                continue
            점.append((t, float(큰[0] + 큰[2] / 2.0)))
        본자리 += len(점)
        밖 = [(t, cx) for t, cx in 점 if cx < x0 + 여유 or cx > x0 + WIN - 여유]
        if not 밖:
            continue

        # 나갈 때마다 조각을 만든다 — 이어지는 «밖» 은 한 덩어리로 묶는다
        조각 = []
        지금 = None
        for t, cx in 점:
            난가 = cx < x0 + 여유 or cx > x0 + WIN - 여유
            if 난가:
                if 지금 is None:
                    지금 = [t, t, [cx]]
                else:
                    지금[1] = t
                    지금[2].append(cx)
            elif 지금 is not None:
                조각.append(지금)
                지금 = None
        if 지금 is not None:
            조각.append(지금)

        붙임 = []
        for s0, e0, cxs in 조각:
            s0 = max(a + 0.05, s0 - 샘플 / 2)
            e0 = min(b - 0.05, e0 + 샘플 / 2)
            if e0 - s0 < 최소조각:
                continue
            가운데 = sorted(cxs)[len(cxs) // 2]
            붙임.append((s0, e0, dx로(가운데)))
        if not 붙임:
            print('  ! 촬영본 %2d  %6.2f~%6.2f  나갔지만 조각이 %.2f초 미만이라 안 나눈다'
                  % (r['i'], a, b, 최소조각))
            continue

        # 촬영본을 [원래 | 붙임 | 원래] 로 자른다
        새목록.pop()
        경계 = [a]
        토막 = []
        for s0, e0, dx2 in 붙임:
            if s0 - 경계[-1] >= 0.05:
                토막.append((경계[-1], s0, r['dx'], 0.0))
            토막.append((s0, e0, dx2, _미는시간(dx2 - r['dx'])))
            경계.append(e0)
        if b - 경계[-1] >= 0.05:
            토막.append((경계[-1], b, r['dx'], _미는시간(r['dx'] - 붙임[-1][2])))
        for s0, e0, dx2, ease in 토막:
            새 = dict(r)
            새['a'], 새['b'], 새['dx'] = round(s0, 3), round(e0, 3), int(dx2)
            새['ease'] = ease
            새['how'] = (r.get('how') or '') + ' · 인물따라가기'
            새목록.append(새)
        나눈수 += 1
        print('  ✓ 촬영본 %2d  %6.2f~%6.2f  →  %d토막 (창 %d~%d 밖으로 %d번 나감)'
              % (r['i'], a, b, len(토막), x0, x0 + WIN, len(밖)))
    cap.release()

    print()
    print('  잰 얼굴 %d개 · 나눈 촬영본 %d개 · 줄 %d → %d'
          % (본자리, 나눈수, len(F), len(새목록)))
    if not 나눈수:
        print('  인물이 창을 벗어나는 자리 없음 ✓')
        return 0
    if A.쓰기:
        for k, r in enumerate(새목록):
            r['i'] = k
        json.dump(새목록, io.open('faces.json', 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('  faces.json 에 반영했다 — **reframe.py 를 다시 돌려라**')
    else:
        print('  (재기만 했다. 반영하려면 --쓰기 를 준다)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
