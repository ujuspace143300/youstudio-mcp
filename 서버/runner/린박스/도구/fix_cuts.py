# -*- coding: utf-8 -*-
r"""나레 블록의 컷을 **한 촬영본 안으로** 옮긴다.

왜 필요한가
  나레 컷을 손으로 찍으면 그 구간 안에서 원본이 스스로 컷한다. 그러면 0.3초짜리
  조각이 화면에 번쩍이고 지나간다 — 4편 첫 렌더에서 그런 자리가 네 곳 나왔다.
  D(원음) 블록은 tighten.py 가 이미 막고 있지만, N 블록은 아무도 안 보고 있었다.

규칙 (1편에서 굳힌 것과 같다)
  · 컷 하나는 장면전환을 **가로지르지 않는다**
  · 원음이 쓰는 구간과 겹치지 않는다 (같은 그림이 두 번 나온다)
  · 되도록 원래 자리에서 **가장 가까운** 촬영본으로 옮긴다 — 이야기가 안 튄다

쓰는 법
  편 폴더에서:  python 도구\fix_cuts.py   (authored.json 을 그 자리에서 고친다)
"""
import json
import os
import subprocess
import sys

# ★나레 속도는 **10.2자/초** 다 (규격 §6). RATE x SPEED 가 그 값이어야 한다.
#   옛 7.25(=RATE 7.9 x 1.2 도 9.48) 는 틀렸다 — 1.2배속으로 구운 소리를
#   실측하니 10.2 였다. 이 값이 작으면 컷 하나를 실제보다 길게 잡아,
#   자리를 못 찾았다며 컷을 엉뚱한 촬영본으로 옮긴다.
RATE, SPEED = 8.5, 1.2      # 8.5 x 1.2 = 10.2 자/초
GUARD = 0.12                # 촬영본 경계에서 이만큼 떨어뜨린다

# ▼편별 ─── 여기를 이 편 것으로 바꾼다 ────────────────────────────
SRC = '구간_인물.mp4'        # 재프레이밍을 마친 소재 (reframe.py 가 낸 것)

# ★쓰면 안 되는 구간 — [[시작, 끝], …] (소재 시각, 초)
#   드라마 제목 카드 · 로고 · 예고편 · 자막이 박힌 화면처럼 **그림으로 못 쓰는 자리**다.
#   나레 컷이 여기 앉으면 «이상한 장면» 이 튀어나온다 —
#   소년심판 1편에서 나레 컷 하나가 「소년심판」 제목 카드 위에 앉았다.
#   장면검사는 이런 걸 못 잡는다. **사람이 한 번 보고 적어 줘야 한다.**
금지구간 = []
# ▲편별 ──────────────────────────────────────────────────

A = json.load(open('authored.json', encoding='utf-8'))
SC = sorted(float(x) for x in open('scene_cuts.txt'))
SRC_END = float(subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
     SRC], capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip())

edges = [0.0] + SC + [SRC_END]
shots = [(edges[i] + GUARD, edges[i + 1] - GUARD) for i in range(len(edges) - 1)
         if edges[i + 1] - edges[i] > 2 * GUARD + 0.35]
busy = [(x[0] - 0.05, x[1] + 0.05) for b in A['BLOCKS'] if b[0] == 'D' for x in b[1]]


def shot_of(x):
    """이 시각이 속한 촬영본의 시작."""
    return max([c for c in SC if c <= x], default=0.0)


def 금지(s, e):
    return any(s < z and e > a for a, z in 금지구간)


def free(s, e, taken):
    if 금지(s, e):
        return False
    # ★시간이 안 겹쳐도 **같은 촬영본이면 같은 그림**이다.
    #   4편에 76초짜리 통짜 컷이 있어서, 그 안에서 아홉 번을 뽑아 쓰는 바람에
    #   «같은 장면이 계속 나온다» 는 지적을 받았다. 촬영본 단위로 막는다.
    # ★촬영본 중복 금지는 **나레 컷끼리만** 이다.
    #   대사는 그 장면에서 나야 하므로 원음 블록끼리는 같은 촬영본을 써도 된다
    #   (4편 식당 장면은 76초짜리 한 컷 안에서 세 사람이 다 말한다).
    if any(abs(shot_of(s) - shot_of(x)) < 0.01 for x, y in taken):
        return False
    return all(not (s < y and e > x) for x, y in busy + taken)


# ★이웃 블록과 **같은 촬영본**에 앉으면 화면이 안 바뀐다.
#   계획상으로는 28컷인데 완성본을 재면 19컷(23.3컷/분)밖에 안 나왔다 —
#   나레 컷이 앞뒤 원음 블록과 같은 촬영본에 있어서 «시간만 건너뛴 같은 그림»
#   이 되기 때문이다. 검수기는 그걸 컷으로 세지 않고, 눈에도 컷으로 안 보인다.
#   그래서 나레 컷은 **앞 블록·뒤 블록과 다른 촬영본**이어야 한다.
def blk_shot(b):
    """그 블록이 쓰는 촬영본의 시작 (N 은 첫 컷, D 는 첫 구간 기준)."""
    return shot_of(b[2][0][0] if b[0] == 'N' else b[1][0][0])


taken, moved, kept = [], 0, 0
for bi, b in enumerate(A['BLOCKS']):
    if b[0] != 'N':
        continue
    이웃 = set()
    for j in (bi - 1, bi + 1):
        if 0 <= j < len(A['BLOCKS']) and A['BLOCKS'][j][0] == 'D':
            이웃.add(shot_of(A['BLOCKS'][j][1][0][0]))
    n = len(b[2])
    each = len(b[1]) / RATE / SPEED / n
    new = []
    for k, c in enumerate(b[2]):
        s = c[0]
        lo = max([x for x in SC if x <= s], default=0.0)
        hi = min([x for x in SC if x > s], default=SRC_END)
        ok = (s >= lo + GUARD and s + each <= hi - GUARD
              and shot_of(s) not in 이웃 and free(s, s + each, taken))
        if ok:
            new.append([round(s, 2), c[1]])
            taken.append((s, s + each))
            kept += 1
            continue
        # 이웃과 다른 촬영본 중 가장 가까운 곳으로 옮긴다
        cand = []
        for a, z in shots:
            if z - a < each or shot_of(a + 0.001) in 이웃:
                continue
            t = a
            while t + each <= z:
                if free(t, t + each, taken):
                    cand.append(t)
                    break
                t += 0.25
        if not cand:
            print(f"  ★b{bi:02d} 컷{k+1} 자리를 못 찾음 — 그대로 둔다 ({each:.2f}초)")
            new.append([round(s, 2), c[1]])
            continue
        t = min(cand, key=lambda x: abs(x - s))
        new.append([round(t, 2), c[1]])
        taken.append((t, t + each))
        moved += 1
        print(f"  b{bi:02d} 컷{k+1}  {s:.2f} → {t:.2f}  ({each:.2f}초, 이웃과 다른 촬영본으로)")
    b[2] = new

json.dump(A, open('authored.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"\n나레 컷 {kept + moved}개 · 그대로 {kept} · 옮김 {moved}")
