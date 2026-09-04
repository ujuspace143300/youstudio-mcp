# -*- coding: utf-8 -*-
r"""공식 SRT(글자) + 전사 밀기(시각)로 **원음 대사의 정본**을 만든다.

왜 있나 (2026-09-04 사장님 「전사가 완벽할 수 없다 — SRT 와 맞춰 대사 실수를 없애라」)
  전사(ASR)는 반드시 틀린다 — 「박후민 정학 풀렸을 때 네가 시마이 탁 쳐 주면은」을
  「박주민 정확히 풀렸을 때 너가 희망이 탁 쳐주면」으로 적었다. 그 전사표를 보고
  사람이 author.py 의 BLOCKS 를 손으로 적으니, 앞문장이 통째로 빠졌다 (약한영웅 1화).
  반대로 SRT 시각은 방송본 앞 리캡·로고 탓에 클립보다 앞설 수 있다 (포핸즈 4화 +39.35초).

  → **글자는 SRT, 시각은 전사.** `srt고르기.py` 가 못박은 `srt원본`(경로·밀기)에서
    ① `srt대사.txt` 를 다시 쓴다 — SRT 글자 · 클립 시각(SRT초 + 밀기 − 구간시작)
    ② `_대본초안_D블록.txt` 를 낸다 — author.py BLOCKS 에 **그대로 붙일 수 있는** D 블록 줄
       (말 사이가 1.0초 넘게 벌어지면 블록을 가른다 · 시작 = 첫 말 −0.10 · 끝 = 마지막 말 +0.25)

  사람은 이 초안에서 **뺄 블록을 고르고 자막을 줄일 뿐** — 없는 말을 지어내거나 있는 말을
  잃을 일이 없다. 줄인 자막이 원문을 얼마나 담았는지는 `대사빠짐검사.py` 가 관문에서 잰다.

쓰는 법
  편 폴더에서:  python 도구/SRT블록.py            srt대사.txt 를 다시 쓰고 초안을 낸다
                python 도구/SRT블록.py --보기만    초안만 화면에 보인다 (파일은 안 건드린다)
                python 도구/SRT블록.py --틈 1.0    블록을 가르는 말 사이 틈(초)
"""
import argparse
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = argparse.ArgumentParser()
P.add_argument('--보기만', action='store_true', dest='보기만')
P.add_argument('--틈', type=float, default=1.0)
P.add_argument('--앞여유', type=float, default=0.10)
P.add_argument('--뒤여유', type=float, default=0.25)
P.add_argument('--줄글자', type=int, default=10)     # 자막 한 줄 글자 수 (이보다 길면 | 로 가른다)
P.add_argument('--구간시작', type=float, default=None, dest='구간시작')   # ★유스튜디오 사본: EPnn 폴더는 이름에 ep_시작-끝 이 없다 — lb_transcript 가 넘긴다
P.add_argument('--구간끝', type=float, default=None, dest='구간끝')
A = P.parse_args()

if not os.path.exists('srt원본'):
    raise SystemExit('★srt원본 이 없다 — 먼저  python 도구/srt고르기.py  로 이 편의 SRT 를 못박아라')

줄 = [l.strip() for l in io.open('srt원본', encoding='utf-8', errors='replace') if l.strip()]
srt길 = 줄[0]
밀기 = 0.0
for l in 줄[1:]:
    m = re.match(r'밀기\s*=\s*(-?[\d.]+)', l)
    if m:
        밀기 = float(m.group(1))
if not os.path.exists(srt길):
    raise SystemExit('★srt원본 이 가리키는 파일이 없다: %s' % srt길)

m = re.search(r'ep_(\d+)-(\d+)', os.path.basename(os.path.abspath('.')))
구간시작 = A.구간시작 if A.구간시작 is not None else (float(m.group(1)) if m else 0.0)
구간끝 = A.구간끝 if A.구간끝 is not None else (float(m.group(2)) if m else 1e9)
길이 = 구간끝 - 구간시작


def srt읽기(p):
    txt = io.open(p, encoding='utf-8-sig', errors='replace').read()
    out = []
    for blk in re.split(r'\n\s*\n', txt):
        mm = re.search(r'(\d\d):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d+)', blk)
        if not mm:
            continue
        g = mm.groups()
        s = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000.0
        e = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000.0
        글 = ' '.join(l.strip() for l in blk.split('\n')[2:] if l.strip())
        글 = re.sub(r'<[^>]+>', '', 글).strip()
        # ★srt대사.txt 엔 **원문 그대로** 넣는다 — d_sync 가 글자로 카드를 맞추므로 한 글자도 바꾸면 안 된다.
        #   (「- 연시은 - 빨리 치워」 꼴은 초안에서만 « / » 로 다듬는다 · 2026-09-04)
        if 글:
            out.append((s, e, 글))
    return out


S = srt읽기(srt길)
안 = []
for s, e, 글 in S:
    a = s + 밀기 - 구간시작
    b = e + 밀기 - 구간시작
    if -1.0 < a < 길이 + 1.0:
        안.append((a, b, 글))
if not 안:
    raise SystemExit('★이 구간(%.0f~%.0f)에 드는 SRT 줄이 없다 — 밀기(%.2f)·구간을 확인하라' % (구간시작, 구간끝, 밀기))

print('■ SRT 블록 — %s · 밀기 %+.2f초 · 이 구간 %d줄' % (os.path.basename(srt길), 밀기, len(안)))


def 다듬기(글):
    """두 화자 줄 「- 연시은 - 빨리 치워」 → 「연시은 / 빨리 치워」 (초안 전용)."""
    t = re.sub(r'^\s*-\s*', '', 글)
    return re.sub(r'\s+-\s+', ' / ', t)


def 자막꼴(글):
    """10자 넘으면 가운데 띄어쓰기에서 | 로 가른다 (make_ass 가 | 를 줄바꿈으로 쓴다)."""
    t = 다듬기(글).replace(' / ', ' ')
    if len(t) <= A.줄글자 or ' ' not in t:
        return t
    k = len(t) // 2
    왼 = t.rfind(' ', 0, k + 1)
    오 = t.find(' ', k)
    자리 = 왼 if (왼 != -1 and (오 == -1 or k - 왼 <= 오 - k)) else 오
    if 자리 == -1:
        return t
    return t[:자리] + '|' + t[자리 + 1:]


# 블록 가르기 — 말 사이 틈이 --틈 넘으면 새 블록
블록 = []
현 = []
for a, b, 글 in 안:
    if 현 and a - 현[-1][1] > A.틈:
        블록.append(현)
        현 = []
    현.append((a, b, 글))
if 현:
    블록.append(현)

초안 = []
초안.append('# author.py BLOCKS 에 붙일 D 블록 초안 — %s · 밀기 %+.2f · %d블록 (틈 %.1f초)'
          % (os.path.basename(srt길), 밀기, len(블록), A.틈))
초안.append('# ★없는 말을 만들지 말고, 있는 말을 잃지 마라. 뺄 블록은 줄째 지우고, 자막은 줄여도 된다.')
초안.append('#   줄인 뒤엔 대사빠짐검사.py 가 원문을 얼마나 담았는지 잰다 (덮임 45% 미만이면 막힌다).')
for 카드들 in 블록:
    s0 = max(0.0, 카드들[0][0] - A.앞여유)
    e0 = 카드들[-1][1] + A.뒤여유
    안쪽 = []
    for a, b, 글 in 카드들:
        안쪽.append('[%.2f, %.2f, "%s", "quote", "%s"]' % (a, b, 자막꼴(글).replace('"', '\\"'), 다듬기(글).replace('"', '\\"')))
    if len(안쪽) == 1:
        초안.append("    ['D', [%s]],   # %.2f~%.2f" % (안쪽[0], s0, e0))
    else:
        초안.append("    ['D', [%s,\n           %s]],   # %.2f~%.2f"
                  % (안쪽[0], ',\n           '.join(안쪽[1:]), s0, e0))

for l in 초안[:12]:
    print('  ' + l)
if len(초안) > 12:
    print('  … %d줄 더' % (len(초안) - 12))

if A.보기만:
    raise SystemExit(0)

# ① srt대사.txt — SRT 글자 · 클립 시각
if os.path.exists('srt대사.txt'):
    옛 = io.open('srt대사.txt', encoding='utf-8', errors='replace').read()
    새 = '\n'.join('%6.2f~%6.2f  %s' % (a, b, 글) for a, b, 글 in 안)
    if 옛.strip() != 새.strip():
        n = 1
        while os.path.exists('srt대사.txt.%d전' % n):
            n += 1
        os.replace('srt대사.txt', 'srt대사.txt.%d전' % n)
        io.open('srt대사.txt', 'w', encoding='utf-8').write(새 + chr(10))
        print('  → srt대사.txt 를 다시 썼다 (옛 것은 srt대사.txt.%d전)' % n)
    else:
        print('  → srt대사.txt 는 이미 같다')
else:
    io.open('srt대사.txt', 'w', encoding='utf-8').write(
        '\n'.join('%6.2f~%6.2f  %s' % (a, b, 글) for a, b, 글 in 안))
    print('  → srt대사.txt 를 썼다')
io.open('srt경계', 'w', encoding='utf-8').write(' '.join('%.2f %.2f' % (a, b) for a, b, _ in 안))

# ② 초안
io.open('_대본초안_D블록.txt', 'w', encoding='utf-8').write('\n'.join(초안) + '\n')
print('  → _대본초안_D블록.txt 에 %d블록 초안을 냈다 — author.py BLOCKS 에 붙이고 뺄 것만 빼라' % len(블록))
