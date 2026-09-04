# -*- coding: utf-8 -*-
r"""**화면에서 말은 나오는데 자막이 없는 자리**를 잡는다.

왜 있나 (2026-08-27 · 사장님 지적 「대사가 안 나오는 장면이 있는데」)
  D 블록의 **그림 구간**과 **자막 글자**는 따로 논다.
    · 블록 시작을 앞 대사 자리로 잡아 놓고 자막은 뒤 대사만 적거나
    · 컷다듬기·번쩍임정리가 블록을 **늘리면서** 다음 대사까지 삼키거나
  그러면 그 몇 초 동안 **말소리는 나는데 자막이 없다.**
  실제로 포헨즈 1-7편에서 여섯 자리가 그랬다 (가장 긴 것 2.0초).

  ★그리고 더 큰 물음 — **공식 SRT 가 있는데 왜 안 읽나?**
    안 읽는다. `author.py` 의 BLOCKS 는 **손으로 적는다.** 그래서 빠진다.
    이 검사가 그 손질을 대신 봐 준다. (SRT 에서 바로 뽑고 싶으면 `SRT블록.py`)

무엇을 재나
  D 블록마다 [시작,끝] 안에 들어오는 **공식 SRT 줄**을 찾아,
  그 줄의 말이 그 블록 자막에 **글자로 들어 있는지** 본다. 없으면 탈이다.

쓰기
  python 도구\대사빠짐검사.py                     (편 폴더에서 · SRT 자리를 스스로 찾는다)
  python 도구\대사빠짐검사.py --srt <파일> --밀기 -3560.70 --구간시작 3790
"""
import argparse
import glob
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

겹침한계 = 0.25       # 이보다 짧게 겹치면 스친 것이라 안 본다
막힘한계 = 0.60       # 이보다 길게 «말은 나는데 자막이 없으면» 막힘


def 초(t):
    h, m, s = t.split(':')
    s, ms = s.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def 씻기(x):
    return re.sub(r'[^0-9A-Za-z가-힣]', '', x)


def srt읽기(길, 밀기, 구간시작):
    본 = io.open(길, encoding='utf-8', errors='replace').read()
    난것 = []
    for m in re.finditer(r'(\d+)\s*\n([\d:,]+) --> ([\d:,]+)\s*\n(.*?)(?=\n\s*\n|\Z)',
                         본, re.S):
        a = 초(m.group(2)) + 밀기 - 구간시작
        b = 초(m.group(3)) + 밀기 - 구간시작
        난것.append((a, b, m.group(4).strip().replace(chr(10), ' ')))
    return 난것


def _srt인가(p):
    try:
        return '-->' in io.open(p, encoding='utf-8', errors='replace').read(4000)
    except OSError:
        return False


def 못박힌srt():
    """편 폴더 `srt원본` 에 못박아 둔 SRT 를 읽는다 → (경로, 밀기) 또는 None.

    ★2026-09-04 사장님 지적 「전사가 완벽할 수 없다 — SRT 로 맞춰라」로 들어왔다.
      아래 `srt찾기()` 는 위로 5층 올라가며 **옆 폴더를 알파벳순으로 훑어 «첫 .srt»**
      를 집었다. 그래서 약한영웅 6편이 `20260901-린박스-포핸즈-3화/3화.srt`
      (**남의 드라마**)와 대조됐고, 「3화.srt」라는 이름이 그럴듯해 보고서도
      정상처럼 읽혔다 — **조용히 틀렸다.**
      경로로 짐작하면 언제든 옆 드라마를 문다. 그래서 `도구/srt고르기.py` 가
      **내용으로** 골라 편 폴더에 못박고, 검사는 그 못만 본다.
    """
    if not os.path.exists('srt원본'):
        return None
    줄 = [l.strip() for l in io.open('srt원본', encoding='utf-8', errors='replace')]
    줄 = [l for l in 줄 if l]
    if not 줄:
        return None
    길 = 줄[0]
    밀기 = 0.0
    for l in 줄[1:]:
        m = re.match(r'밀기\s*=\s*(-?[\d.]+)', l)
        if m:
            밀기 = float(m.group(1))
    if not os.path.exists(길):
        print('  ★srt원본 이 가리키는 파일이 없다: %s' % 길)
        return None
    return 길, 밀기


def srt찾기():
    """편 폴더 → 위로 → **옆 폴더까지** «SRT 같은 것» 을 찾는다.

    ★위로만 올라가면 못 찾는다 (2026-08-27). 소재와 공식 SRT 는 흔히
      «작품 폴더» 에 따로 모여 있다 —
          볼케이노 mcp/포헨즈/EP01.txt        ← 여기
          볼케이노 mcp/20260825-린박스-포헨즈-1화/ep_.../   ← 일하는 곳
      둘은 **형제**라 위로만 봐서는 안 보인다.
    """
    본것 = set()
    길 = os.path.abspath('.')
    층 = []
    for _ in range(5):
        층.append(길)
        위 = os.path.dirname(길)
        if 위 == 길:
            break
        길 = 위
    볼곳 = list(층)
    for 층길 in 층[1:]:                       # 각 층의 **옆 폴더**도 본다
        try:
            for d in sorted(os.listdir(층길)):
                p2 = os.path.join(층길, d)
                if os.path.isdir(p2) and p2 not in 볼곳:
                    볼곳.append(p2)
        except OSError:
            pass
    for 곳 in 볼곳:
        if 곳 in 본것:
            continue
        본것.add(곳)
        try:
            것들 = sorted(os.listdir(곳))
        except OSError:
            continue
        for f in 것들:
            p2 = os.path.join(곳, f)
            if not os.path.isfile(p2):
                continue
            if f.lower().endswith('.srt') or re.match(r'^EP\d+\.txt$', f, re.I):
                if _srt인가(p2):
                    return p2
    return None


def main():
    P = argparse.ArgumentParser()
    P.add_argument('--srt', default=None)
    P.add_argument('--밀기', type=float, default=None, dest='밀기')
    P.add_argument('--구간시작', type=float, default=None, dest='구간시작')
    P.add_argument('--짐작', action='store_true', dest='짐작',
                   help='(진단용) srt원본 도 --srt 도 없을 때 옛 방식대로 경로를 훑어 SRT 를 짐작한다')
    A = P.parse_args()

    # ★차례 — ①사람이 준 것(--srt) ②편 폴더에 못박힌 것(srt원본). 그게 다다.
    #   경로 짐작(srt찾기)은 **기본에서 뺐다** (2026-09-04 맥2 · 볼트 승격 때 EP19 실측):
    #   신병 EP19 에서 돌리니 `신병/작업/EP1/신병4_EP1_자막.srt`(우리가 만든 **다른 편** 자막)를 물고
    #   「막힘 4건」(종료코드 2)을 냈다 — render.py 관문에 걸리면 **남의 SRT 로 편을 막는다.**
    #   작업규칙 완성검사 13 「경로로 SRT 를 짐작하지 않는다」 그대로. 진단하고 싶을 때만 --짐작.
    못 = 못박힌srt()
    srt길 = A.srt or (못[0] if 못 else None)
    if srt길 and A.srt is None and 못 and A.밀기 is None:
        A.밀기 = 못[1]
    짐작 = False
    if not srt길 and A.짐작:
        srt길 = srt찾기()
        짐작 = bool(srt길)
    if not srt길:
        print('※못박힌 SRT(srt원본)가 없다 — 이 검사는 건너뛴다. 경로로 짐작하지 않는다(완성검사 13).')
        print('  (`python 도구/srt고르기.py` 로 이 편에 맞는 SRT 를 내용 대조로 못박아라)')
        return 0
    if 짐작:
        print('  ★SRT 를 «경로 짐작» 으로 골랐다(--짐작) — 남의 드라마일 수 있다: %s' % srt길)
        print('    이 결과로 판정하지 마라. `python 도구/srt고르기.py` 로 내용을 대조해 못박아라.')

    # 밀기·구간시작을 안 주면 편 폴더 이름(ep_3790-3892)과 제작지시에서 짐작한다
    밀기 = A.밀기
    구간시작 = A.구간시작
    if 구간시작 is None:
        m = re.search(r'ep_(\d+)-', os.path.basename(os.path.abspath('.')))
        구간시작 = float(m.group(1)) if m else 0.0
    if 밀기 is None:
        밀기 = 0.0
        for 지시 in glob.glob(os.path.join('..', '*.md')) + glob.glob('*.md'):
            try:
                본 = io.open(지시, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            m = re.search(r'SRT초\s*[−-]\s*([\d.]+)', 본)
            if m:
                밀기 = -float(m.group(1))
                break

    srt = [x for x in srt읽기(srt길, 밀기, 구간시작)]
    A2 = json.load(io.open('authored.json', encoding='utf-8'))
    BL = A2['BLOCKS']
    끝 = 0.0
    for b in BL:
        if b[0] == 'D':
            끝 = max(끝, b[1][-1][1])
    안 = [x for x in srt if -2 <= x[0] <= 끝 + 3]
    print('■ 대사 빠짐 — 말은 나는데 자막이 없는 자리')
    print('  SRT %s · 밀기 %.2f · 구간시작 %.0f → 이 구간에 %d줄'
          % (os.path.basename(srt길), 밀기, 구간시작, len(안)))
    if not 안:
        print('  ★SRT 시각이 이 구간과 안 맞는다 — --밀기/--구간시작 을 줘라. 건너뛴다.')
        return 0

    # ★판정을 «글자 포함» 에서 «덮임 비율» 로 바꿨다 (2026-09-04 사장님 지적
    #   「전사가 완벽할 수 없다 — SRT 로 맞춰라」).
    #   전에는 SRT 줄의 **앞 6글자**가 자막에 그대로 들어 있는지만 봤다. 그래서
    #     · 줄여 적은 자막 (「나 화장실 갔다 올게」 → 「화장실 갔다 올게」)
    #     · 복자 처리 (「새끼」 → 「새X」)
    #   이 전부 «빠졌다» 로 걸렸다. 헛경보가 쏟아지니 **진짜 빠진 말이 그 속에 묻혔다** —
    #   약한영웅 6편에서 9~15건씩 떴는데 대부분 헛것이었다.
    #   거꾸로, 앞 6글자만 맞으면 **뒤를 통째로 잃어도 통과**했다 — 진짜 구멍은 이쪽이다.
    #   이제 그 SRT 줄의 글자가 «시간이 겹치는 자막들» 에 얼마나 담겼는지를 잰다.
    def 잇기(a, b):
        """a(SRT)의 글자가 b(자막)에 **차례대로** 얼마나 들어 있나 — 0~1.
        복자(X·○·*)는 아무 글자에나 맞는 것으로 친다."""
        if not a:
            return 1.0
        마스크 = set('Xx○*')
        앞 = [0] * (len(b) + 1)
        for ca in a:
            새 = [0] * (len(b) + 1)
            for j, cb in enumerate(b):
                if ca == cb or cb in 마스크:
                    새[j + 1] = 앞[j] + 1
                else:
                    새[j + 1] = max(새[j], 앞[j + 1])
            앞 = 새
        return 앞[len(b)] / float(len(a))

    막힘, 알림 = [], []
    본줄 = set()
    for i, b in enumerate(BL):
        if b[0] != 'D':
            continue
        블록시작, 블록끝 = b[1][0][0], b[1][-1][1]
        for a2, b2, t in 안:
            겹 = min(블록끝, b2) - max(블록시작, a2)
            if 겹 <= 겹침한계:
                continue
            키 = (i, round(a2, 2), t[:12])
            if 키 in 본줄:
                continue
            본줄.add(키)
            # 이 블록 자막 + **이웃 블록** 자막까지 본다 — 한 SRT 줄을 두 블록으로
            # 갈라 적는 일이 있다 (2026-08-27).
            덩이 = ''.join(씻기(x[2]) for x in b[1])
            for j in (i - 1, i + 1):
                if 0 <= j < len(BL) and BL[j][0] == 'D':
                    덩이 += ''.join(씻기(x[2]) for x in BL[j][1])
            덮임 = 잇기(씻기(t), 덩이)
            if 덮임 >= 0.75:
                continue
            보임 = '%s  (덮임 %.0f%%)' % (' '.join(x[2] for x in b[1])[:40], 100 * 덮임)
            (막힘 if (덮임 < 0.45 and 겹 >= 막힘한계) else 알림).append(
                (i, 블록시작, 블록끝, 보임, 겹, t))
    for i, s, e, 글, 겹, t in 알림:
        print('  ! b%02d %.2f~%.2f  %.2f초 「%s」 (자막: %s)'
              % (i, s, e, 겹, t[:28], 글[:22]))
    for i, s, e, 글, 겹, t in 막힘:
        print('  ✗ b%02d %.2f~%.2f  **%.2f초 동안 말은 나는데 자막이 없다** 「%s」'
              % (i, s, e, 겹, t[:34]))
        print('       지금 자막: 「%s」' % 글[:40])
    print()
    if 막힘:
        print('★막힘 %d건 — 그 말을 자막에 넣거나, 블록 구간을 그 말 뒤에서 열어라' % len(막힘))
        return 2
    print('  말과 자막이 어긋난 자리 없음 ✓')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
