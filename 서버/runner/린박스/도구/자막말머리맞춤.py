# -*- coding: utf-8 -*-
r"""자막 카드가 **말보다 먼저 뜨는 것**을 소리로 재서 늦춘다.

왜 (2026-09-03 · 사장님 「싱크가 안 맞는다 — 자막이 말보다 먼저 뜬다」)
  D 블록 시작 시각은 SRT·ASR 에서 온다. 그런데 방송 SRT 는 말보다 0.3~0.6초
  **미리** 띄우는 일이 흔하고, 그 블록의 첫 카드는 블록 시작(0초)에 붙는다.
  그래서 아직 아무 말도 안 나오는데 글자가 먼저 뜬다 — 122편 중 82편이 그랬다.

무엇을 하나
  블록마다 **구운 bNN.mp4 의 소리**로 말머리를 찾고, 그 블록의 첫 카드가
  말머리보다 이르면 말머리(−0.06초 여유)까지 **늦춘다.**
  · 반대로 **늦게 뜨는** 카드는 말머리까지 당긴다 (앞 카드와 안 겹치는 만큼만).
  · 카드 끝은 건드리지 않는다 (말이 끝나는 자리는 이미 소리로 닫혀 있다).
  · 늦춰서 카드가 0.5초보다 짧아지면 그만큼만 늦춘다.
  · 나레(band_narr)·제목·크레딧은 손대지 않는다.

쓰는 법
  편 폴더에서:  python 자막말머리맞춤.py            재기만 한다
                python 자막말머리맞춤.py --쓰기      captions_fx.ass 를 고친다
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = argparse.ArgumentParser()
P.add_argument('--쓰기', action='store_true', dest='쓰기')
P.add_argument('--여유', type=float, default=0.06)
A = P.parse_args()

시각꼴 = re.compile(r'^(Dialogue:\s*\d+,)(\d):(\d\d):(\d\d)\.(\d\d),(\d):(\d\d):(\d\d)\.(\d\d),([^,]*),')


def 초(h, m, s, cs):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0


def 글꼴(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return '%d:%02d:%05.2f' % (h, m, s)


def dur(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', p], capture_output=True, text=True)
    try:
        return float((r.stdout or '').strip())
    except ValueError:
        return 0.0


def 포락(p):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-ac', '1', '-ar', '8000',
                        '-f', 's16le', '-'], capture_output=True)
    a = np.frombuffer(r.stdout, np.int16).astype(np.float32)
    if len(a) < 400:
        return None
    n = len(a) // 80
    return np.sqrt((a[:n * 80].reshape(n, 80) ** 2).mean(1))


ass = 'captions_fx.ass' if os.path.exists('captions_fx.ass') else 'captions.ass'
if not os.path.exists(ass) or not os.path.exists('authored.json'):
    raise SystemExit('편 폴더에서 돌려라 (captions·authored.json 이 있어야 한다)')

B = json.load(io.open('authored.json', encoding='utf-8'))['BLOCKS']
경계, t = [], 0.0
for i in range(len(B)):
    L = dur(os.path.join('blocks', 'b%02d.mp4' % i))
    경계.append((t, t + L, B[i][0], i))
    t += L

# 블록마다 말머리 (블록 안 상대 초)
말머리 = {}
for s0, e0, 종, i in 경계:
    if 종 != 'D':
        continue
    p = os.path.join('blocks', 'b%02d.mp4' % i)
    if not os.path.exists(p):
        continue
    env = 포락(p)
    if env is None:
        continue
    바닥 = float(np.percentile(env, 10)) + 1.0
    문턱 = max(바닥 * 4.0, env.max() * 0.18)
    위 = np.where(env > 문턱)[0]
    if len(위):
        말머리[i] = 위[0] / 100.0

줄들 = io.open(ass, encoding='utf-8', errors='replace').read().splitlines()
카드자리 = []          # (줄번호, 시작, 끝)
for n, l in enumerate(줄들):
    m = 시각꼴.match(l.strip())
    if not m:
        continue
    g = m.groups()
    if 'band_dlg' not in g[9]:
        continue
    카드자리.append((n, 초(*g[1:5]), 초(*g[5:9])))

고칠 = []
for s0, e0, 종, i in 경계:
    if 종 != 'D' or i not in 말머리:
        continue
    안 = sorted([c for c in 카드자리 if s0 - 0.03 <= c[1] < e0 - 0.03], key=lambda c: c[1])
    if not 안:
        continue
    n, s, e = 안[0]
    목표 = s0 + 말머리[i] - A.여유
    if 목표 > s + 0.10:
        # 자막이 이르다 → 말머리까지 늦춘다 (카드가 0.5초보다 짧아지지 않게)
        새s = min(목표, e - 0.50)
        if 새s > s + 0.05:
            고칠.append((n, s, 새s, e, i))
    elif 목표 < s - 0.20:
        # 자막이 늦다 → 말머리까지 당긴다. 앞 카드와 겹치지 않게 막는다
        앞끝 = max([c[2] for c in 카드자리 if c[2] <= s + 0.001] or [0.0])
        새s = max(목표, 앞끝 + 0.04, s0)
        if 새s < s - 0.05:
            고칠.append((n, s, 새s, e, i))

print('■ 자막 말머리 맞춤 — 원음 카드 %d장 · D 블록 %d개' % (len(카드자리), len(말머리)))
if not 고칠:
    print('  말과 어긋난 카드 없음 ✓')
    raise SystemExit(0)
# ★재기만 할 때는 ✗ 로 찍고 종료코드 1 (2026-09-04 맥2 · 볼트 승격 때 EP19 실측).
#   전에는 17장이 어긋나도 「b19 30.93 → 31.10」 만 찍고 0 으로 끝났다. render.py 관문은
#   «✗ 로 시작하는 줄» 만 모으므로 이 도구는 관문에 있어도 **한 번도 막지 못했다.**
#   작업규칙 완성검사 14 「종료코드 0 이어야 한다(재기만 할 때 어긋난 카드 없음)」 를 실제로 그렇게 만든다.
표 = '  ' if A.쓰기 else '  ✗ '
for n, s, 새s, e, i in 고칠:
    print('%sb%02d  %.2f → %.2f (%+.2f초 %s)' % (표, i, s, 새s, 새s - s, '늦춤' if 새s > s else '당김'))
print('  %d장을 옮긴다' % len(고칠))

if not A.쓰기:
    print('  ✗ 말과 어긋난 카드 %d장 — python 자막말머리맞춤.py --쓰기 로 맞추고 add_sfx → 라우드니스 → render 를 다시 돌린다 (규격 §93)' % len(고칠))
    raise SystemExit(1)

바꿈 = {n: 새s for n, s, 새s, e, i in 고칠}
새줄 = []
for n, l in enumerate(줄들):
    if n in 바꿈:
        m = 시각꼴.match(l.strip())
        머리 = m.group(1)
        끝 = 초(*m.groups()[5:9])
        새줄.append(l.replace(m.group(0), '%s%s,%s,%s,' % (머리, 글꼴(바꿈[n]), 글꼴(끝), m.group(10)), 1))
    else:
        새줄.append(l)
io.open(ass, 'w', encoding='utf-8').write('\n'.join(새줄) + '\n')
print('  %s 를 고쳤다 — render 를 다시 돌려라' % ass)
