# -*- coding: utf-8 -*-
r"""화면이 난사되는 대사 구간을 **다른 안정된 컷으로 덮는다.** 소리는 그대로 둔다.

무엇을 푸는가
  대사가 장면보다 먼저다. 그런데 어떤 대사 구간은 영화가 0.1~0.3초 간격으로 컷한다
  (「누나 이거 내가 세볼게」 뒤가 그렇다). 대사를 지키면 화면이 난사되고,
  화면을 지키면 대사가 잘린다 — 둘 다 안 되는 자리다.

  그래서 **소리는 그 대사 그대로 두고, 그림만 다른 컷으로 바꿔 끼운다.**
  회상 인서트처럼 보이고, 대사는 한 글자도 안 잘린다.

고르는 기준
  · 길이가 그 블록을 통째로 덮을 만큼 긴 **한 촬영본**
  · 원음·나레가 이미 쓰고 있지 않은 자리
  · 그 대사에서 **가장 가까운** 시각 — 맥락이 튀지 않는다
  · 대본에 `ALT_SHOTS = {블록번호: 소스시각}` 을 적어 두면 그것을 먼저 쓴다

언제 도는가
  서버가 블록을 구운 **뒤**, 배속·정렬 **앞**. 블록의 길이는 건드리지 않는다.
"""
import json
import os
import subprocess

MIN_SHOT = 0.80
GUARD = 0.12

A = json.load(open('authored.json', encoding='utf-8'))
P = json.load(open('state_payload.json', encoding='utf-8'))
cs = {int(k): float(v) for k, v in P['clip_secs'].items()}
SC = sorted(float(x) for x in open('scene_cuts.txt'))
SRC = '구간_인물.mp4'
SRC_END = float(subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', SRC],
    capture_output=True, text=True, encoding='utf-8', errors='replace').stdout.strip())

edges = [0.0] + SC + [SRC_END]
shots = [(edges[i] + GUARD, edges[i + 1] - GUARD) for i in range(len(edges) - 1)
         if edges[i + 1] - edges[i] > 2 * GUARD + 0.5]

busy = []
for b in A['BLOCKS']:
    if b[0] == 'D':
        busy += [(x[0] - 0.05, x[1] + 0.05) for x in b[1]]
    else:
        n = len(b[2])
        each = len(b[1]) / 7.9 / 1.2 / n
        busy += [(c[0] - 0.05, c[0] + each + 0.05) for c in b[2]]

def _블록프레임률(경로, 기본='30000/1001'):
    """갈아 끼울 블록과 **같은 프레임률**로 굽는다 (2026-08-26).

    ★전에는 `-r 30` 이 박혀 있었다. 소재가 29.97 이라 나머지 블록은 30000/1001 로
      구워지는데 이 도구만 30 으로 구워, 이어 붙일 때 타임베이스가 섞여
      **완성본이 60fps 로 튀어나왔다.** 갈아 끼우는 쪽이 원래 값을 따라가야 한다.
    """
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=r_frame_rate', '-of', 'csv=p=0', 경로],
                       capture_output=True, text=True).stdout.strip()
    return r if '/' in r else 기본


MANUAL = A.get('ALT_SHOTS') or {}
# 렌더를 재 보고 «여기가 튄다» 고 짚어 준 블록은 강제로 덮는다
import sys
FORCE = set()
for arg in sys.argv[1:]:
    if arg.startswith('--블록='):
        FORCE = {int(x) for x in arg.split('=', 1)[1].split(',') if x.strip()}


def fragments(s, e):
    ins = [c for c in SC if s + 0.02 < c < e - 0.02]
    if not ins:
        return []
    return ([ins[0] - s] + [ins[k + 1] - ins[k] for k in range(len(ins) - 1)]
            + [e - ins[-1]])


def pick(dur, want_at, taken):
    """dur 초를 통째로 담을 수 있는, want_at 에서 가장 가까운 촬영본."""
    cand = []
    for a, z in shots:
        if z - a < dur:
            continue
        t = a
        while t + dur <= z:
            if all(not (t < y and t + dur > x) for x, y in busy + taken):
                cand.append(t)
                break
            t += 0.25
    return min(cand, key=lambda x: abs(x - want_at)) if cand else None


taken, done, _record = [], 0, []
for bi, b in enumerate(A['BLOCKS']):
    if b[0] == 'D':
        s, e = b[1][0][0], b[1][0][1]
        fr = fragments(s, e)
        label = b[1][0][2].split('|')[0][:16]
    else:
        # ★나레 블록도 본다. fix_cuts 는 **어림한 길이**로 자리를 잡아서, 실제 클립이
        #   길면 컷이 장면전환을 넘는다. 나레는 그림이 무엇이든 상관없으니 덮으면 된다.
        n = len(b[2])
        each = cs[bi] / n
        fr = []
        for c in b[2]:
            f2 = fragments(c[0], c[0] + each)
            fr += f2 if f2 else [each]
        s = b[2][0][0]
        label = b[1][:16]
    manual = MANUAL.get(str(bi))
    # ★원음(대사) 블록은 **그림을 바꾸지 않는다.**
    #   말하는 사람이 화면에 없는데 목소리만 나오면 눈에 대뜸 걸린다.
    #   영화가 그 구간에서 스스로 빠르게 컷하더라도 그건 원본 그대로다 — 봐줄 만하다.
    #   대본에 ALT_SHOTS 로 콕 집어 준 것만 예외로 바꾼다.
    # ★`--블록=` 강제는 이 관문보다 **앞**이라야 한다 (2026-08-26).
    #   전에는 여기서 원음 블록을 먼저 걸러 버려, 문서에 «강제로 덮는다» 고 적어 놓고도
    #   `--블록=5,11` 이 **아무 말 없이 아무것도 안 했다.** 사람이 짚어 준 자리는 덮는다.
    if b[0] == 'D' and manual is None and bi not in FORCE:
        continue
    if manual is None and bi not in FORCE and (not fr or min(fr) >= MIN_SHOT):
        continue                       # 화면이 멀쩡하다 — 그대로 둔다
    dur = cs[bi]
    # ★ALT_SHOTS 값이 [파일, 시각] 이면 다른 회차 파일에서 그림을 가져온다 (2026-09-01).
    if isinstance(manual, (list, tuple)):
        alt_src, alt = manual[0], float(manual[1])
    else:
        alt_src = SRC
        alt = manual if manual is not None else pick(dur + 0.1, s, taken)
    if alt is None:
        print(f"  ★b{bi:02d} 덮을 촬영본을 못 찾음 — 그대로 둔다")
        continue
    src_mp4 = f'blocks/b{bi:02d}.mp4'
    tmp = f'blocks/_alt{bi:02d}.mp4'
    r = subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-ss', f'{alt:.3f}', '-t', f'{dur:.3f}', '-i', alt_src,
         '-i', src_mp4, '-map', '0:v', '-map', '1:a',
         '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p',
         '-color_range', 'tv', '-colorspace', 'bt709',
         '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', _블록프레임률(src_mp4),
         '-video_track_timescale', '30000',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-shortest', tmp])
    if r.returncode:
        print(f"  ★b{bi:02d} 덮기 실패")
        continue
    os.replace(tmp, src_mp4)
    taken.append((alt, alt + dur))
    _record.append((bi, alt))
    done += 1
    why = ('지정' if manual is not None else
           '렌더에서 튐' if bi in FORCE else f'조각 {min(fr):.2f}초')
    print(f"  b{bi:02d} {b[0]} 「{label}」 화면을 {alt:.2f}초 컷으로 덮음 "
          f"({dur:.2f}초, {why}) — 소리는 그대로")

# ★갈아 끼운 자리를 **대본에 남긴다** (2026-08-26).
#   전에는 `_record` 를 모으기만 하고 **어디에도 안 썼다.** 그래서 두 가지가 터졌다.
#     ① `장면튐검사.py` 는 `ALT_SHOTS` 를 읽어 «이 블록은 소재 시각이 다르다» 를 안다.
#        기록이 없으니 갈아 끼운 뒤에도 **계속 «막힘» 으로 찍었다.**
#     ② 블록을 다시 구우면 갈아 끼운 그림이 **아무 흔적 없이 원래대로 돌아간다.**
#   ★이 도구는 굽기 **뒤**에 돈다. 다시 구웠으면 이 도구도 다시 돌려라.
if _record:
    A['ALT_SHOTS'] = dict(A.get('ALT_SHOTS') or {})
    for bi, alt in _record:
        A['ALT_SHOTS'][str(bi)] = round(alt, 3)
    json.dump(A, open('authored.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('  authored.json 의 ALT_SHOTS 에 %d곳 남겼다 (장면튐검사가 이걸 읽는다)'
          % len(_record))

print(f"\n화면만 바꾼 블록 {done}개 · 대사는 한 글자도 안 잘렸다")
