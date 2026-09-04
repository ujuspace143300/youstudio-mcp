# -*- coding: utf-8 -*-
r"""소재의 **장면전환을 빠짐없이** 찾아 scene_cuts.txt 로 낸다.

왜 이 도구가 필요한가
  화면 튐의 뿌리는 여기다. `fix_cuts.py` 는 scene_cuts.txt 를 **절대적으로 믿고**
  나레 컷을 «촬영본 안» 에 앉힌다. 그런데 그 표에 빠진 컷이 있으면, 사실은 두
  촬영본인 자리를 하나로 알고 컷을 가로질러 앉힌다 — 그리고 0.1초짜리가 번쩍인다.

  ★단, 무전환 구간이 길다고 **표가 틀린 것은 아니다**. 4편 scene_cuts.txt 는
    45.1초 다음이 121.4초 — 76초가 비어 있어 «표가 깨졌다» 고 의심했지만,
    프레임을 뽑아 보니 중국집 고정 카메라 **롱테이크** 로 표가 정확했다.
    이 도구는 그럴 때 «놓친 전환 0개» 라고 알려 준다. 의심이 들면 먼저 재라.

어떻게 찾는가 — 세 가지를 함께 본다
  ① 화소 차   앞 프레임과 얼마나 다른가 (가장 기본)
  ② 히스토그램 차  밝기 분포가 통째로 바뀌었는가 (카메라가 움직여도 안 속는다)
  ③ 이웃 대비  그 순간이 **주변보다 유난히** 튀는가 (전체 문턱 하나로는 밝은
               장면의 컷을 놓치고 어두운 장면에서 헛것을 잡는다)

  ①②를 각각 정규화해 합치고, 그 값이 «이웃 3초의 중앙값 + 편차*배수» 를 넘으면
  컷으로 본다. 고정 문턱 하나만 쓰면 반드시 놓친다 — 그게 지금까지의 문제였다.

쓰는 법
  python <키트>/장면컷.py [소재.mp4] [--쓰기] [--최소 0.35]
    --쓰기 를 주면 scene_cuts.txt 를 덮어쓴다 (기존 것은 scene_cuts.bak 으로)
    안 주면 재기만 하고 기존 표와 견줘 보여 준다
"""
import argparse
import os
import sys

import numpy as np

import 영상읽기

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = argparse.ArgumentParser()
P.add_argument('소재', nargs='?', default='구간.mp4')
P.add_argument('--쓰기', action='store_true')
P.add_argument('--최소', type=float, default=0.35, help='이보다 가까운 컷은 하나로 본다')
P.add_argument('--민감', type=float, default=5.0, help='낮출수록 더 많이 잡는다')
A = P.parse_args()

if not os.path.exists(A.소재):
    raise SystemExit(f'소재가 없다: {A.소재}')

W, H = 128, 72
fps = 영상읽기.초당프레임(A.소재)

전, 화소, 히스, 시각 = None, [], [], []
밝기모음 = []
전히 = None
i = 0
for i, _t, g in 영상읽기.회색프레임(A.소재, 크기=(W, H)):
    h = np.histogram(g, bins=32, range=(0, 255))[0].astype(np.float32)
    h /= max(h.sum(), 1.0)
    밝기모음.append(float(g.mean()))
    if 전 is not None:
        화소.append(float(np.abs(g - 전).mean()))
        히스.append(float(np.abs(h - 전히).sum()))
        시각.append(_t)
    전, 전히 = g, h
i += 1
길이 = i / fps
if not 화소:
    raise SystemExit('프레임을 못 읽었다')

밝기평균 = float(np.mean(밝기모음)) if 밝기모음 else 128.0
화소 = np.array(화소)
히스 = np.array(히스)


def 정규(x):
    m = np.median(x)
    s = np.median(np.abs(x - m)) * 1.4826 + 1e-6
    return (x - m) / s


점수 = 정규(화소) + 정규(히스)

# 이웃 대비 — 앞뒤 3초 안에서 유난히 튀는 자리만 컷으로 본다.
# 고정 문턱 하나로는 밝은 장면의 컷을 놓친다(4편 45~121초가 그랬다).
반 = max(int(1.5 * fps), 8)
바닥 = np.empty_like(점수)
퍼짐 = np.empty_like(점수)
for j in range(len(점수)):
    a, b = max(0, j - 반), min(len(점수), j + 반 + 1)
    이웃 = 점수[a:b]
    바닥[j] = np.median(이웃)
    퍼짐[j] = np.median(np.abs(이웃 - 바닥[j])) * 1.4826 + 1e-6

# ★화소차 바닥을 **밝기에 따라 움직인다** (2026-09-01).
#   고정 6.0 으로 두면 **어두운 소재의 컷을 통째로 놓친다.** 들쥐 9화 밤산은
#   창 안 밝기 중앙값이 7/255 였다 — 진짜 컷이 나도 평균 화소차가 6 을 못 넘어
#   표에 안 실렸다. 그 표를 믿고 블록을 앉히니 «표에 없는 컷» 위에 경계가 얹혀
#   완성본에서 0.46초짜리가 번쩍였다. 검수기는 이미 같은 이유로 문턱을 밝기에
#   맞춰 움직이게 고쳐 두었는데(칸바닥 10 · 기울기 0.12) 정작 **표를 만드는 이 자리**가
#   고정값이었다. 컷 표가 틀리면 그 뒤는 다 틀린다.
_밝기 = float(np.mean([np.mean(x) for x in (화소,)])) if False else None
_평균밝기 = 밝기평균
_화소바닥 = max(2.0, min(6.0, 0.06 * _평균밝기))
print('  화소차 바닥 %.2f (소재 평균 밝기 %.1f/255)' % (_화소바닥, _평균밝기))

후보 = [(시각[j], float(점수[j]))
        for j in range(len(점수))
        if 점수[j] > 바닥[j] + A.민감 * 퍼짐[j] and 화소[j] > _화소바닥]

# 가까운 후보는 가장 센 것 하나로 모은다 (디졸브는 여러 프레임에 걸쳐 걸린다)
컷 = []
for t, sc in 후보:
    if 컷 and t - 컷[-1][0] < A.최소:
        if sc > 컷[-1][1]:
            컷[-1] = (t, sc)
        continue
    컷.append((t, sc))
컷시각 = [round(t, 3) for t, _ in 컷]

print(f'소재 {os.path.basename(A.소재)} — {길이:.1f}초 · {fps:.2f}fps · 프레임 {i}개')
print(f'찾은 장면전환 {len(컷시각)}개  ({len(컷시각)/길이*60:.1f}개/분)')

# 가장 긴 «전환 없는 구간» — 여기가 비정상적으로 길면 놓친 컷이 있다는 뜻이다
경계 = [0.0] + 컷시각 + [길이]
구간 = [(경계[k], 경계[k + 1] - 경계[k]) for k in range(len(경계) - 1)]
구간.sort(key=lambda x: -x[1])
print('가장 긴 무전환 구간:', ' · '.join(f'{a:.1f}s에서 {d:.1f}초' for a, d in 구간[:3]))

기존 = 'scene_cuts.txt'
if os.path.exists(기존):
    옛 = sorted(float(x) for x in open(기존) if x.strip())
    놓친 = [t for t in 컷시각 if all(abs(t - o) > 0.30 for o in 옛)]
    헛것 = [o for o in 옛 if all(abs(o - t) > 0.30 for t in 컷시각)]
    print(f'\n기존 {기존}: {len(옛)}개  →  새로 잰 것 {len(컷시각)}개')
    print(f'  기존이 **놓친** 전환 {len(놓친)}개'
          + (': ' + ' '.join(f'{t:.1f}' for t in 놓친[:14])
             + (' …' if len(놓친) > 14 else '') if 놓친 else ''))
    print(f'  기존에만 있던 것 {len(헛것)}개'
          + (': ' + ' '.join(f'{t:.1f}' for t in 헛것[:14]) if 헛것 else ''))
    if 놓친:
        옛경계 = [0.0] + 옛 + [길이]
        빈 = max((옛경계[k + 1] - 옛경계[k], 옛경계[k])
                 for k in range(len(옛경계) - 1))
        print(f'  ★기존 표가 {빈[1]:.1f}s 부터 {빈[0]:.1f}초를 «한 촬영본» 으로 보고 있다 — '
              f'그 안에 실제 전환이 '
              f'{sum(1 for t in 컷시각 if 빈[1] < t < 빈[1] + 빈[0])}개 있다')

if A.쓰기:
    if os.path.exists(기존):
        os.replace(기존, 'scene_cuts.bak')
        print(f'\n기존 표는 scene_cuts.bak 으로 옮겼다')
    open(기존, 'w', encoding='utf-8', newline='\n').write(
        '\n'.join(f'{t:.3f}' for t in 컷시각) + '\n')
    print(f'{기존} 에 {len(컷시각)}개를 적었다.')
    print('★ 이제 fix_cuts.py 를 다시 돌려야 컷이 촬영본 안으로 들어간다.')
else:
    print('\n(재기만 했다. 표를 고치려면 --쓰기 를 준다)')
