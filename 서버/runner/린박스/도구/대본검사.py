# -*- coding: utf-8 -*-
r"""**굽기 전에** 대본만으로 볼 수 있는 화면 튐을 판독한다. (2026-08-25)

왜 이 검사기가 있나
  `장면튐검사.py` 는 **구운 블록의 길이**로 잰다 — 나레(N) 블록의 화면 길이는
  TTS 음성이 정하므로 대본만으로는 못 재기 때문이다. 그래서 굽기 전에 돌리면
  아무것도 못 재고 **거짓 통과**가 나온다(그 검사기는 이제 거부한다).

  ★그런데 **원음(D) 블록은 대본만으로 다 잴 수 있다.** 시작·끝이 소재 시각으로
  적혀 있으니 장면전환과 견주면 된다. 포헨즈 1화에서 번쩍인 자리는 **거의 다** 여기다.

  서버도 `stitch_script` 에서 이미 ⚠ 로 알려 준다 — ep_2825-3005 은 29블록 중
  **18번** 경고했고 그중 b19 가 실제로 번쩍였다. **경고는 정확했고 아무도 안 막았다.**
  이 검사기는 그 경고를 **막힘으로 바꾼다.**

무엇을 보나 (전부 authored.json + scene_cuts.txt 만으로)
  ① D블록 **안**에서 장면이 바뀌면 그림이 둘로 쪼개진다 → 짧은 쪽이 조각이다
     ★단, 이웃 블록이 **같은 촬영본으로 이어지면** 조각이 아니다 — 그건 이어진 그림이다
  ② D블록 시작이 장면전환에서 멀면 «장면 중간에서 끊긴다» (서버의 ⚠ 와 같은 조건)

무엇을 **못** 보나 — 정직하게
  · 나레(N) 블록의 화면 길이 (TTS 음성 길이에 달렸다) → 굽고 나서 `장면튐검사.py`
  · 배율 순환 (구운 그림을 봐야 안다)                → 굽고 나서 `장면튐검사.py`
  **이 검사기가 통과해도 «굽고 나서» 를 건너뛰지 마라.**

쓰는 법
  편 폴더에서:  python 대본검사.py
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

번쩍임 = 1.00       # 이보다 짧은 그림이 뜨면 **막힘**
MIN_컷 = 1.30       # 이보다 짧으면 **알림** (§48)
멀다 = 0.40         # 블록 시작이 전환에서 이만큼 넘게 떨어지면 «장면 중간»

if not os.path.exists('authored.json'):
    raise SystemExit('authored.json 이 없다 — 편 폴더에서 돌려라')
A = json.load(io.open('authored.json', encoding='utf-8'))
SC = sorted(float(x) for x in io.open('scene_cuts.txt') if x.strip())
BL = A['BLOCKS']


def 촬영본(t):
    return sum(1 for c in SC if t >= c)


# ★대체화면(ALT_SHOTS)을 **반드시** 봐야 한다 (2026-08-26).
#   `대체화면.py` 로 그림을 갈아 끼운 블록은 **소재 시각이 authored.json 과 다르다.**
#   그 표를 모르면 «있지도 않은 전환»을 보고 막는다 — 실제로 포헨즈 2화 2-1 에서
#   b14 를 «앞조각 0.81초» 로 막았는데, 그 블록 그림은 65.6초에서 온 것이라
#   47.276 언저리의 전환과는 아무 상관이 없었다. **거짓 막힘이었고, 그 판정을 믿고
#   대사 한 줄을 지웠다.** 정식 검사기(장면튐검사.py)는 ALT 를 보고 «튐 없음» 이라 했다.
#   ★두 검사기가 어긋나면 **더 많이 아는 쪽**이 맞다. 어긋남 자체를 의심하라.
ALT = {int(k): float(v) for k, v in (A.get('ALT_SHOTS') or {}).items()}


def 앞뒤(b, i=None):
    if i is not None and i in ALT:
        return None, None          # 그림이 갈렸다 — 대본 시각으로는 못 잰다. 굽고 나서 본다
    칸 = b[1] if b[0] == 'D' else b[2]
    try:
        return float(칸[0][0]), float(칸[-1][1] if b[0] == 'D' else 칸[-1][0])
    except Exception:
        return None, None


막힘, 알림 = [], []
print('=' * 62)
print('  대본검사 — 굽기 전에 대본만으로 본다 (원음 블록만)')
print('=' * 62)

# ── ① 블록 안 장면전환이 만드는 조각 ────────────────────────────
print()
print('■ 원음 블록 안에서 장면이 바뀌는가')
앞끝, 앞촬 = None, None
샌것 = 0
for i, b in enumerate(BL):
    s, e = 앞뒤(b, i)
    if s is None:
        continue
    if b[0] == 'D':
        안 = [c for c in SC if s + 0.05 < c < e - 0.05]
        for c in 안:
            앞조각, 뒤조각 = c - s, e - c
            # 앞조각은 앞 블록이 같은 촬영본으로 이어지면 더 길어진다
            이어짐 = (앞끝 is not None and abs(s - 앞끝) < 0.05
                      and 앞촬 == 촬영본(s))
            # ★뒤조각은 **다음 블록으로 이어질 수 있다** (2026-08-26).
            #   b15 뒤조각 0.27초가 b16(같은 촬영본·틈 0초)으로 이어져 실제로는 1.22초인데
            #   «막힘» 으로 잡혔다. `번쩍임정리.py` 는 그 자리를 탈로 안 봤다 — 내 검사기가 틀렸다.
            뒤이어짐 = False
            if i + 1 < len(BL) and BL[i + 1][0] == 'D':
                s2, e2 = 앞뒤(BL[i + 1], i + 1)
                if s2 is not None and abs(s2 - e) < 0.05 and 촬영본(s2) == 촬영본(c):
                    안2 = [x for x in SC if s2 + 0.05 < x < e2 - 0.05]
                    뒤조각 += (안2[0] if 안2 else e2) - s2      # 다음 그림까지 이어 붙인다
                    뒤이어짐 = True
            짧은쪽 = min(앞조각, 뒤조각)
            누구 = 'b%02d 앞조각' % i if 앞조각 < 뒤조각 else 'b%02d 뒤조각' % i
            꼬리 = (' (앞 블록과 이어져 더 길다)' if (이어짐 and 앞조각 < 뒤조각)
                    else ' (다음 블록으로 이어져 더 길다)' if 뒤이어짐 else '')
            if 짧은쪽 < 번쩍임 and not (이어짐 and 앞조각 < 뒤조각):
                막힘.append('%s 가 %.2f초뿐이다 — 번쩍인다 (전환 %.3f)' % (누구, 짧은쪽, c))
                print('  ✗ b%02d  전환 %.3f → 앞 %.2f초 / 뒤 %.2f초%s' % (i, c, 앞조각, 뒤조각, 꼬리))
                샌것 += 1
            elif 짧은쪽 < MIN_컷:
                알림.append('%s %.2f초 — 조각 (1.30초 권장, §48)' % (누구, 짧은쪽))
                print('  ! b%02d  전환 %.3f → 앞 %.2f초 / 뒤 %.2f초%s' % (i, c, 앞조각, 뒤조각, 꼬리))
                샌것 += 1
    앞끝, 앞촬 = e, 촬영본(e)
if not 샌것:
    print('  없음 ✓')

# ── ② 블록 시작이 장면전환에서 먼가 (서버의 ⚠ 와 같은 조건) ────
print()
if ALT:
    print('  ※대체화면으로 그림을 갈아 끼운 블록 %s — 대본 시각으로는 못 재니 건너뛴다.'
          % sorted(ALT))
    print('    그 블록들은 **굽고 나서 `장면튐검사.py`** 로 봐야 한다.')
print('■ 원음 블록 시작이 장면전환에 붙어 있는가')
먼것 = []
for i, b in enumerate(BL):
    if b[0] != 'D':
        continue
    s, e = 앞뒤(b, i)
    if s is None:
        continue
    앞전환 = max([c for c in SC if c <= s] + [0.0])
    if s - 앞전환 > 멀다:
        먼것.append((i, round(s - 앞전환, 2)))
D수 = sum(1 for b in BL if b[0] == 'D')
if 먼것:
    print('  %d/%d 개가 전환에서 %.1f초 넘게 떨어져 있다' % (len(먼것), D수, 멀다))
    print('   ', ' · '.join('b%02d %.2f초' % x for x in 먼것[:10]),
          '…' if len(먼것) > 10 else '')
    if len(먼것) > D수 * 0.5:
        알림.append('원음 블록 %d/%d 개가 장면전환에 안 붙어 있다 — 대본을 전환에 맞춰 다시 짜면 '
                    '조각이 줄어든다' % (len(먼것), D수))
else:
    print('  전부 붙어 있다 ✓')

# ── 판정 ────────────────────────────────────────────────────────
print()
print('=' * 62)
if 막힘:
    print('  막힘 %d건 — 고치기 전에는 굽지 마라' % len(막힘))
    for x in 막힘:
        print('   ✗', x)
else:
    print('  대본에서 보이는 튐 없음 ✓')
if 알림:
    print('  알림 %d건 — 편의 취지를 보고 사람이 정한다' % len(알림))
    for x in 알림:
        print('   !', x)
print()
print('  ★이 검사는 **원음 블록만** 본다. 나레 화면 길이와 배율 순환은')
print('    굽고 나서 `장면튐검사.py` 로 다시 봐야 한다. 건너뛰지 마라.')
print('=' * 62)
sys.exit(1 if 막힘 else 0)
