# -*- coding: utf-8 -*-
r"""프리미어 프로젝트의 **자막 자리**를 원본.ass 대로 옮긴다.

무슨 문제를 푸는가
  프리미어 안에서 만든 자막 그래픽은 **55장이 전부 같은 자리**에 얹혀 있었다.
  제목도 나레이션도 크레딧도 한 곳에 포개져 보인다. 자리 정보가 아예 없었던 것이다.

좌표계 — 사장님 화면으로 확인한 사실
    글자 상자 왼쪽 = 위치.x × 1080      (0.125 → 135)
    글자 상자  위  = 위치.y × 1920      (0.65  → 1248)
    상자 가로/세로 = 덩어리의 root/2, root/3   (810 × 576)
    글자는 상자 안에서 **가로 가운데 · 세로 아래** 로 붙는다.

  그래서 **상자를 글자에 딱 맞게** 만들면 세로 정렬이 무엇이든 결과가 같아진다.
  줄 높이는 글꼴 hhea (800/-200/gap 0) 대로 1.0em — libass 가 쓰는 것과 같다.

  ASS 쪽 자리
    \an8 = 글자 덩이의 **위·가운데**가 \pos 자리        → 상자 위 = y
    \an5 = 글자 덩이의 **가운데**가 \pos 자리           → 상자 위 = y − 높이/2
    \move(x1,y1,x2,y2,…) 는 끝나는 자리를 쓴다
    \frz 는 회전이라 클립의 «회전» 값으로 넣는다

쓰는 법
  python <키트>/자리잡기.py <프로젝트.prproj> <원본.ass> [--보기만]
"""
import argparse
import base64
import gzip
import os
import re
import shutil
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '도구'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import 소스텍스트 as S      # noqa: E402
import 플랫버퍼 as F        # noqa: E402
import 글꼴표             # noqa: E402

BS = chr(92)
가로, 세로 = 1080.0, 1920.0
상자폭 = 1040.0            # 좌우 20px 만 남긴다 — 줄이 접히지 않게 넉넉히
줄높이배수 = 1.0           # 글꼴 hhea 기준 (Gmarket Sans: 800 − (−200) + 0 = 1000/1000)
# ASS 크기 → 프리미어 크기 환산비는 글꼴마다 다르다 (도구/글꼴표.py 가 파일에서 읽는다)


def 시각(s):
    h, m, rest = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest)


def 태그읽기(본문):
    """{\an8\pos(540,214)…} 들을 훑어 자리·회전·크기배율을 뽑는다."""
    잡 = {'an': 2, 'x': None, 'y': None, 'frz': 0.0, 'fscy': 100.0}
    for 덩이 in re.findall(r'\{([^}]*)\}', 본문):
        for 조각 in 덩이.split(BS):
            if not 조각:
                continue
            m = re.match(r'^an(\d)$', 조각)
            if m:
                잡['an'] = int(m.group(1)); continue
            m = re.match(r'^pos\(([-\d.]+),([-\d.]+)\)$', 조각)
            if m:
                잡['x'], 잡['y'] = float(m.group(1)), float(m.group(2)); continue
            m = re.match(r'^move\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)', 조각)
            if m:   # 움직이는 동안의 «가운데» 를 쓴다 — 그게 화면에 오래 보이는 자리다
                잡['x'] = (float(m.group(1)) + float(m.group(3))) / 2
                잡['y'] = (float(m.group(2)) + float(m.group(4))) / 2
                continue
            m = re.match(r'^frz([-\d.]+)$', 조각)
            if m:
                잡['frz'] = float(m.group(1)); continue
            m = re.match(r'^fscy([-\d.]+)\)?$', 조각)   # \t(...) 안의 목표값도 잡는다
            if m:
                잡['fscy'] = float(m.group(1)); continue
    return 잡


def ass읽기(경로):
    차림, 크기, 글줄 = None, {}, {}
    for 줄 in open(경로, encoding='utf-8'):
        줄 = 줄.rstrip('\n')
        if 줄.startswith('Format:') and not 크기:
            차림 = [t.strip() for t in 줄[7:].split(',')]
        if 줄.startswith('Style:'):
            v = [t.strip() for t in 줄[6:].split(',')]
            d = dict(zip(차림, v))
            글 = 글꼴표.찾기(d['Fontname'])
            크기[d['Name']] = float(d['Fontsize']) * (글['환산비'] if 글 else 0.87)
        if 줄.startswith('Dialogue:'):
            f = 줄.split(',', 9)
            이름, 본문 = f[3].strip(), f[9]
            글 = re.sub(r'\{[^}]*\}', '', 본문).replace(BS + 'N', chr(10)).strip()
            if not 글:
                continue
            잡 = 태그읽기(본문)
            잡['스타일'] = 이름
            잡['크기'] = 크기.get(이름, 48.0)
            잡['때'] = 시각(f[1])
            # 같은 글자가 여러 번 나오면 (등장 애니메이션) **마지막 것**이 자리다
            앞 = 글줄.get(글)
            if 앞 is None or 잡['때'] >= 앞['때']:
                글줄[글] = 잡
    return 글줄


P = argparse.ArgumentParser()
P.add_argument('프로젝트')
P.add_argument('자막')
P.add_argument('--보기만', action='store_true', dest='보기만')
A = P.parse_args()

글줄 = ass읽기(A.자막)
쪽 = gzip.open(A.프로젝트, 'rb').read().decode('utf-8')

# 덩어리 ↔ 위치 ↔ 회전 은 «소스 텍스트» 뒤에 차례로 하나씩 나온다
표 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', 쪽)]
if not 표:
    raise SystemExit('자막 덩어리를 못 찾았다')
칸 = [(표[i], 표[i + 1] if i + 1 < len(표) else len(쪽)) for i in range(len(표))]

print('═' * 84)
print(f'  자막 자리잡기 — {os.path.basename(A.프로젝트)}')
print('═' * 84)
print(f'  자막 {len(칸)}장 · 원본.ass 글줄 {len(글줄)}가지')
print()

# ★껍데기(덩어리 없이 BinaryHash 로만 가리키는 장)도 **자리는 잡아야 한다.**
#   같은 문구를 여러 번 띄우는 층(모션자막)은 덩어리를 나눠 쓰지만 **자리는 제각각**이다.
#   글자는 그 무리의 «내용 담은 태그» 에서 빌려 오고, **상자는 안 건드린다**(무리가 함께 쓴다).
#   (2026-08-25 포헨즈: 껍데기 30장에서 m.group(1) 이 None 이라 터졌다)
무리글 = {}
for _a, _b in 칸:
    _도 = 쪽[_a:_b]
    _h = re.search(r'<StartKeyframeValue[^>]*BinaryHash="([^"]+)"', _도)
    _m = re.search(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', _도)
    if _h and _m and _h.group(1) not in 무리글:
        무리글[_h.group(1)] = base64.b64decode(_m.group(1))

고침 = []      # (자를곳, 붙일곳, 새글)
못찾음 = []
껍데기수 = 0
for k, (a, b) in enumerate(칸):
    도막 = 쪽[a:b]
    m = re.search(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', 도막)
    if m:
        raw = base64.b64decode(m.group(1))
    else:
        h = re.search(r'<StartKeyframeValue[^>]*BinaryHash="([^"]+)"', 도막)
        raw = 무리글.get(h.group(1)) if h else None
        if raw is None:
            못찾음.append((k, '(주인 없는 껍데기)')); continue
        껍데기수 += 1
    # ★한글이 없는 자막(「?!」·숫자·영문)도 글자다 — 옛 «한글 필터» 는 그런 줄을
    #   조용히 버려서 자리를 못 받게 했다. 그러면 그 자막은 프리미어에서
    #   엉뚱한 자리에 남아 **화면 밖으로 나간다** (2026-08-27 사장님 지적).
    #   글줄 구조를 직접 걸어 읽고, 그래도 못 읽으면 **소리 내어 알린다.**
    글자 = S.글자만(raw)
    if not 글자:
        못찾음.append((k, '(글자를 못 읽음)')); continue
    본문 = 글자[0].replace(chr(13), chr(10))
    잡 = 글줄.get(본문) or next((글줄[q] for q in (본문.split(chr(10))[0].strip(),) if q in 글줄), None)
    if 잡 is None or 잡['x'] is None:
        못찾음.append((k, 본문)); continue

    줄수 = 본문.count(chr(10)) + 1
    fs = 잡['크기']
    높이 = 줄수 * fs * 줄높이배수 * (잡['fscy'] / 100.0)
    위 = 잡['y'] if 잡['an'] in (7, 8, 9) else (잡['y'] - 높이 / 2 if 잡['an'] in (4, 5, 6) else 잡['y'] - 높이)
    왼 = 잡['x'] - 상자폭 / 2

    # ① 덩어리의 상자 크기 (root/2 = 가로, root/3 = 세로)
    #    ★껍데기는 건드리지 않는다 — 상자는 무리가 함께 쓰고, 그 무리의 주인이 이미 고친다
    if m:
        buf, _ = S.unwrap(raw)
        f = S._fields(buf, S._root0(buf))
        # ★본에 따라 상자 크기 자리(root/2·/3)가 **없다**. 「분홍 감정」이 그렇다.
        #   없으면 상자는 그대로 두고 클립 값(위치·회전)만 준다 — 없는 자리에 쓰면 죽는다.
        if 2 in f and 3 in f:
            struct.pack_into('<f', buf, f[2], 상자폭)
            struct.pack_into('<f', buf, f[3], 높이)
            새덩어리 = base64.b64encode(S.wrap(buf)).decode('ascii')
            도막 = 도막.replace(m.group(1), 새덩어리, 1)

    # ② 클립의 위치·회전
    def 값갈기(도막, 이름, 새값):
        패 = r'(<Name>' + 이름 + r'</Name>\s*<StartKeyframe>)(-?\d+),([^,]+)(,)'
        return re.sub(패, lambda z: z.group(1) + z.group(2) + ',' + 새값 + z.group(4), 도막, count=1)

    도막 = 값갈기(도막, '위치', f'{왼 / 가로:.9f}:{위 / 세로:.9f}')
    if abs(잡['frz']) > 0.01:
        도막 = 값갈기(도막, '회전', f'{-잡["frz"]:g}')   # ASS 는 반시계, 프리미어는 시계 방향

    고침.append((a, b, 도막))
    print(f'  {k:2d} {잡["스타일"]:<14} {줄수}줄 {fs:>5.0f}px  '
          f'상자 ({왼:6.1f}, {위:6.1f}) {상자폭:.0f}x{높이:.0f}  '
          f'회전 {잡["frz"]:>5}  {본문.splitlines()[0][:18]}')

print()
if 못찾음:
    print('  ★원본.ass 에서 자리를 못 찾은 것:')
    for k, t in 못찾음:
        print(f'     {k:2d}  {t!r}')
print(f'  옮길 것 {len(고침)}장 · 못 찾은 것 {len(못찾음)}장')

if A.보기만:
    print('\n(--보기만 이라 파일은 안 건드린다)')
    raise SystemExit(0)

새쪽 = []
끝 = 0
for a, b, 도막 in 고침:
    새쪽.append(쪽[끝:a]); 새쪽.append(도막); 끝 = b
새쪽.append(쪽[끝:])
새쪽 = ''.join(새쪽)

# ── 되읽어 확인 ───────────────────────────────────────────────────
확 = re.findall(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', 새쪽)
자리 = re.findall(r'<Name>위치</Name>\s*<StartKeyframe>[^,]+,([^,]+),', 새쪽)
# ★«내용 담은 덩어리» 수로 잰다 — 칸 수가 아니다. 같은 문구가 되풀이되는 편에서는
#   프리미어가 한 무리에 덩어리를 하나만 두고 나머지는 BinaryHash 로 가리킨다.
전 = re.findall(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', 쪽)
if len(확) != len(전):
    raise SystemExit(f'덩어리 수가 달라졌다 — 전 {len(전)} · 후 {len(확)}')
for b64 in 확:
    buf, _ = S.unwrap(base64.b64decode(b64))
    S.runs(buf); S._fields(buf, S._root0(buf))
print(f'  되읽기 확인 — 덩어리 {len(확)}/{len(전)} 정상 · 위치 값 {len(set(자리))}가지 (겹치지 않는다)')

백업 = A.프로젝트.replace('.prproj', f'_자리전_{time.strftime("%m%d_%H%M")}.prproj')
shutil.copy2(A.프로젝트, 백업)
with gzip.open(A.프로젝트, 'wb') as fh:
    fh.write(새쪽.encode('utf-8'))
print(f'  전 판은 옆에 두었다: {os.path.basename(백업)}')
print(f'  다 됐다 → {A.프로젝트}')
