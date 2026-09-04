# -*- coding: utf-8 -*-
r"""블록 경계가 옮겨진 뒤에도 **자막이 블록 안에서 나는 말만** 담게 한다.

왜 있나 (2026-09-04 · 약한영웅 실측)
  `컷다듬기.py`·`번쩍임정리.py`·`fix_cuts.py` 는 authored.json 의 D 블록 **경계**를 줄이거나 옮긴다.
  그런데 자막 글자는 안 따라간다. 그래서
    · 3화 b04  끝 23.48 → 22.80 으로 줄었는데 자막은 「젓가락으로|찌른다며」 — 「찌른다며」는 22.94~ 다
    · 2화 b10  자막 「전학 오자마자|시비 붙었잖아」 — 「시비 붙었잖아」는 109.32~, 블록은 108.94 에 끝난다
  **안 들리는 말이 화면에 떠 있었다.** 자막대조·대본검사는 «완성본 ass ↔ 프로젝트» 만 맞춰서 못 잡는다.

판정 근거는 SRT 다 — 전사가 아니다 (2026-09-04 v2)
  v1 은 전사(ASR) 낱말에 없으면 지웠다. 그래서 진짜 말 「잘못 없어」·「발릴 거 같다」·「교복을」·
  「아이큐 검사」·「있어?」를 지웠다 — **전사는 낱말을 흔히 빠뜨린다.** 「없다」가 아니라 「못 들었다」다.
  이제 `srt대사.txt`(SRT 글자 · 클립 시각)로 «블록 안에서 나는 말» 을 정한다.
    · 블록에 **온전히 드는** SRT 줄의 낱말 → 안에서 나는 말
    · 블록에 **온전히 밖인** SRT 줄(±2.5초)의 낱말 → 밖 말
    · **경계에 걸친** SRT 줄의 낱말만 전사 시각으로 안/밖을 가른다 (전사에 없으면 «모름» → 둔다)
  자막 토막은 «안에서 안 나고 밖에서만 난다» 고 **확실할 때만** 지운다. 모르면 둔다.
  · 복자(X·○·*)가 든 토막은 둔다 · 카드 시각은 손대지 않는다 (경계 도구의 몫)

쓰는 법
  편 폴더에서:  python 도구/자막경계맞춤.py            재기만 한다 (고칠 것 있으면 종료코드 1)
                python 도구/자막경계맞춤.py --쓰기      authored.json 을 고친다 (옛 것은 옆에 둔다)
                python 도구/자막경계맞춤.py --파일 X    다른 authored.json 을 잰다 (시험용)
"""
import argparse
import io
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = argparse.ArgumentParser()
P.add_argument('--쓰기', action='store_true', dest='쓰기')
P.add_argument('--파일', default='authored.json')
P.add_argument('--밖여유', type=float, default=2.5)
P.add_argument('--안여유', type=float, default=0.10)
P.add_argument('--걸침한계', type=float, default=0.5)    # 이보다 조금 걸친 SRT 줄은 통째로 «안» 으로 친다
A = P.parse_args()


def 씻기(s):
    return re.sub(r'[^0-9A-Za-z가-힣]', '', s)


def 같은말(k, w):
    """자막 토막 k 가 낱말 w 와 같은 말인가 — 같거나, 3글자 넘게 서로 품는 경우만."""
    if not k or not w:
        return False
    if k == w:
        return True
    if len(k) >= 3 and (k in w or w in k):
        return True
    return False


def srt대사():
    out = []
    if not os.path.exists('srt대사.txt'):
        return out
    for ln in io.open('srt대사.txt', encoding='utf-8', errors='replace'):
        m = re.match(r'\s*(-?[\d.]+)~\s*(-?[\d.]+)\s+(.*)', ln)
        if m:
            글 = re.sub(r'^\s*-\s*', '', m.group(3)).replace(' - ', ' ')
            out.append((float(m.group(1)), float(m.group(2)), [씻기(t) for t in 글.split() if 씻기(t)]))
    return out


def 전사낱말():
    for f in ('대사.json', 'src_words.json', 'seg_asr.json'):
        if not os.path.exists(f):
            continue
        try:
            d = json.load(io.open(f, encoding='utf-8'))
        except Exception:
            continue
        raw = d.get('words') if isinstance(d, dict) else d
        if not isinstance(raw, list):
            continue
        out = []
        for x in raw:
            if not isinstance(x, dict):
                continue
            s = x.get('s', x.get('start')); e = x.get('e', x.get('end'))
            t = x.get('t', x.get('word', x.get('text')))
            if s is None or t is None:
                continue
            out.append((float(s), float(e if e is not None else s), 씻기(str(t))))
        if out:
            return out
    return []


if not os.path.exists(A.파일):
    raise SystemExit('편 폴더에서 돌려라 (%s 가 있어야 한다)' % A.파일)
SRT = srt대사()
if not SRT:
    print('※srt대사.txt 가 없다 — 이 검사는 건너뛴다 (도구/SRT블록.py 로 만들어라).')
    raise SystemExit(0)
W = 전사낱말()

J = json.load(io.open(A.파일, encoding='utf-8'))
B = J['BLOCKS']

고칠 = []
for i, b in enumerate(B):
    if b[0] != 'D':
        continue
    for j, c in enumerate(b[1]):
        s, e, 글 = float(c[0]), float(c[1]), str(c[2])
        안, 밖, 걸침 = [], [], []
        for a2, b2, 낱말 in SRT:
            if b2 <= s - A.안여유 or a2 >= e + A.안여유:
                if (e <= a2 < e + A.밖여유) or (s - A.밖여유 < b2 <= s):
                    밖 += 낱말
                continue
            if a2 >= s - A.안여유 and b2 <= e + A.안여유:
                안 += 낱말
            elif max(0.0, s - a2) + max(0.0, b2 - e) < A.걸침한계:
                # ★조금(0.5초 미만) 걸친 줄은 통째로 «안» 으로 친다 — 전사 시각으로 갈라 봐야
                #   낱말 하나둘이라 오판이 크다. 「내가 걔한테|발릴 거 같다」(0.22초 걸침)를
                #   「내가 걔한테|거」로 만든 것이 그 예다 (2026-09-04).
                안 += 낱말
            else:
                걸침 += 낱말
        if not (안 or 걸침):
            continue                    # 이 카드 자리에 SRT 줄이 없다 — 판정 못 한다
        # 걸친 줄의 낱말은 전사 시각으로 안/밖을 가른다. 전사에 없으면 «모름».
        걸침안, 걸침밖 = [], []
        for w in 걸침:
            안쪽 = [1 for ws, we, t in W if 같은말(w, t) and ws < e + A.안여유 and we > s - A.안여유]
            바깥 = [1 for ws, we, t in W if 같은말(w, t)
                    and ((e + A.안여유 <= ws < e + A.밖여유) or (s - A.밖여유 < we <= s - A.안여유))]
            if 안쪽:
                걸침안.append(w)
            elif 바깥:
                걸침밖.append(w)
            else:
                걸침안.append(w)        # 모르면 «안» 으로 친다 — 지우지 않는다
        안에 = 안 + 걸침안
        밖에 = 밖 + 걸침밖
        새줄, 지운 = [], []
        for 줄 in 글.split('|'):
            남 = []
            for tok in 줄.split(' '):
                if not tok:
                    continue
                k = 씻기(tok)
                if not k or any(ch in tok for ch in 'Xx○*'):
                    남.append(tok); continue
                if any(같은말(k, w) for w in 안에):
                    남.append(tok)
                elif any(같은말(k, w) for w in 밖에):
                    지운.append(tok)     # 안에서는 안 나고 밖에서만 난다 — 확실할 때만 지운다
                else:
                    남.append(tok)       # 어디에도 없으면(줄임·다른 표기) 둔다
            if 남:
                새줄.append(' '.join(남))
        새글 = '|'.join(새줄)
        if 지운 and 새글 != 글:
            고칠.append((i, j, s, e, 글, 새글, 지운))

print('■ 자막 경계 맞춤 — SRT %d줄 · 전사 %s · D 카드 %d장'
      % (len(SRT), '%d낱말' % len(W) if W else '없음', sum(len(b[1]) for b in B if b[0] == 'D')))
if not 고칠:
    print('  블록 밖 말이 자막에 남은 카드 없음 ✓')
    raise SystemExit(0)
for i, j, s, e, 글, 새글, 지운 in 고칠:
    print('  ✗ b%02d 카드%d %.2f~%.2f  「%s」 → 「%s」  (블록 밖 말: %s)'
          % (i, j, s, e, 글, 새글 or '(비게 됨)', ' '.join(지운)))
if not A.쓰기:
    print('  고치는 길: python 도구/자막경계맞춤.py --쓰기 → d_sync → make_ass → render')
    raise SystemExit(1)

n = 1
while os.path.exists('%s.경계맞춤%d전' % (A.파일, n)):
    n += 1
shutil.copy2(A.파일, '%s.경계맞춤%d전' % (A.파일, n))
for i, j, s, e, 글, 새글, 지운 in 고칠:
    if 새글:
        B[i][1][j][2] = 새글
    else:
        print('  ★b%02d 카드%d 는 자막이 비게 된다 — 지우지 않고 둔다. 사람이 블록 경계를 보라' % (i, j))
json.dump(J, io.open(A.파일, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('  → %s 를 고쳤다 (옛 것: %s.경계맞춤%d전). author.py 도 맞추려면 python 도구/대본되메우기.py' % (A.파일, A.파일, n))
