# -*- coding: utf-8 -*-
r"""프리미어 프로젝트 안의 **자막 서식**을 원본.ass 대로 입힌다.

무슨 문제를 푸는가
  프리미어 안에서 자막 그래픽을 만들면 글자와 자리는 들어가지만 **글꼴·크기·색은
  기본값(LucidaConsole 48px 검정)으로 남는다.** 사람이 트랙마다 손으로 잡아 줘야 했다.
  그걸 대신한다 — 굽는 데 쓴 원본.ass 가 이미 정답을 들고 있으므로 거기서 읽어 온다.

어디를 건드리는가 (도구/소스텍스트.py 의 자리 지도)
    글꼴      플랫버퍼 문자열      ← 길이가 달라지므로 «뒤에 붙이고 uoffset 만 돌린다»
    run/1     글자 크기 (실수)     ← 제자리 덮어쓰기
    run/6     외곽선 굵기 (실수)   ← 제자리 덮어쓰기
    run/4     외곽선 색 (uint8 셋) ← 제자리 덮어쓰기
    root/10   채움색   (uint8 셋) ← 제자리 덮어쓰기
  상자 크기(root/2·/3)는 **손대지 않는다.** 사장님 프로젝트를 재 보니 글자 너비보다
  좁은 값도 있어서 무엇을 뜻하는지 확실하지 않다. 모르는 자리는 안 건드린다.

무엇을 못 하는가
  한 그래픽 안에서 **줄마다 색을 달리하지 못한다.** 그러려면 글줄 서식(run)을 하나 더
  만들어 넣어야 하는데 그건 vtable 을 새로 짜는 일이라 위험하다. 제목은 1줄 색(노랑)으로
  통일된다 — 2줄 빨강이 필요하면 프리미어에서 그 줄만 잡아 바꾸면 된다.

쓰는 법
  python <키트>/서식입히기.py <프로젝트.prproj> <원본.ass>
  python <키트>/서식입히기.py <프로젝트.prproj> <원본.ass> --보기만
"""
import argparse

칠건드리지마 = False
둘레지우기 = False
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
import 줄나누기 as J        # noqa: E402
import 글꼴표             # noqa: E402

# ★글꼴 이름과 크기 환산비는 **글꼴 파일에서 직접 읽는다**(도구/글꼴표.py).
#   · 프리미어는 PostScript 이름으로 글꼴을 찾는다. ASS 는 집안 이름을 쓴다.
#   · ASS 크기 → 프리미어 크기 환산비 = upm/(winAscent+winDescent) 이고
#     **글꼴마다 다르다** — Gmarket 0.870 · Paperlogy 0.849 · 강원교육모두 0.873.
#     예전엔 0.857 한 값으로 박아 뒀는데, 다른 글꼴을 쓰는 순간 어긋난다.

# ★외곽선은 넣는다. 다만 «둘레 부풀리기»(root/14)는 반드시 0 으로 둔다.
#   앞서 외곽선을 검정으로 넣었는데 흰 테로 보였다. 원인은 외곽선이 아니었다 —
#   root/14 = 3 이 글자 둘레를 흰색으로 부풀리고 있었고, 검정 외곽선은 그 **밑에**
#   깔려 안 보였던 것이다. 굵기 0 인 제목에도 테가 보인 것이 그 증거다.
#   root/14 를 0 으로 두면 사장님 완성본과 같은 «검정 외곽선» 이 드러난다.
외곽선넣기 = True

# ★줄마다 색을 달리하는 것은 **안 된다.**
#   제목 둘째 줄을 빨강으로 넣어 봤더니 «빨강 칠» 이 아니라 «빨강 테두리» 로 나왔다.
#   칠 색은 root/10 하나뿐이고 그것은 **그래픽 하나에 하나**다. 글줄 서식(run)에
#   있는 색 자리(/2·/4)는 둘 다 선 쪽이다. 그래서 제목은 한 색으로 간다.
#   그래서 이번엔 **안전한 꼴로만** 시도한다 —
#     · root/10(그래픽 칠) 은 첫 줄 색 그대로 둔다        → 실패해도 첫 줄은 안 변한다
#     · 줄마다 run/2 에 그 줄 색을 넣는다                 → /2 가 칠이면 둘째 줄이 빨개진다
#     · run/4(선 색) 는 **그래픽 칠 색**으로 맞춘다        → 선이 그려져도 안 보인다
#   /2 가 선 쪽이면 굵기 0 이라 아무 일도 안 일어난다. 잃을 것이 없다.
줄나누기쓰기 = True


def ass색(s):
    """&HAABBGGRR → (R, G, B)"""
    h = s.strip().lstrip('&').lstrip('Hh').rstrip('&')
    h = h.rjust(8, '0')
    return (int(h[6:8], 16), int(h[4:6], 16), int(h[2:4], 16))


def ass읽기(경로):
    """원본.ass → (스타일표, 글자→스타일)"""
    스타일 = {}
    차림 = None
    글자 = {}
    for 줄 in open(경로, encoding='utf-8'):
        줄 = 줄.rstrip('\n')
        if 줄.startswith('Format:') and 차림 is None and 스타일 == {}:
            차림 = [t.strip() for t in 줄[7:].split(',')]
        if 줄.startswith('Style:'):
            v = [t.strip() for t in 줄[6:].split(',')]
            d = dict(zip(차림, v))
            글 = 글꼴표.찾기(d['Fontname'])
            if 글 is None:
                raise SystemExit(f"이 컴퓨터에 없는 글꼴이다: {d['Fontname']}")
            스타일[d['Name']] = {
                '글꼴': 글['프리미어이름'],
                '크기': float(d['Fontsize']) * 글['환산비'],
                '채움': ass색(d['PrimaryColour']),
                '외곽선색': ass색(d['OutlineColour']),
                '외곽선': float(d['Outline']),
            }
        if 줄.startswith('Dialogue:'):
            f = 줄.split(',', 9)
            이름, 본문 = f[3].strip(), f[9]
            덮개 = re.findall(r'\\c&H([0-9A-Fa-f]{6})&', 본문)   # 줄 안에서 색을 갈아입힌 것
            글 = re.sub(r'\{[^}]*\}', '', 본문).replace('\\N', chr(10)).replace('\\n', chr(10)).strip()
            if not 글:
                continue
            잡 = dict(스타일.get(이름, {}))
            if 덮개:
                b, g, r = (int(덮개[-1][i:i + 2], 16) for i in (0, 2, 4))
                잡['채움'] = (r, g, b)
            잡['스타일'] = 이름
            글자.setdefault(글, 잡)
    return 스타일, 글자


def 색쓰기(buf, 표위치, rgb):
    g = F.fields(buf, 표위치)
    for k, v in zip((0, 1, 2), rgb):
        if k in g:
            buf[g[k]] = int(v) & 0xFF


def 색읽기(buf, 표위치):
    g = F.fields(buf, 표위치)
    return tuple(buf[g[k]] for k in (0, 1, 2) if k in g)


def 글꼴찾기(buf):
    """살아 있는(가리켜지고 있는) 영문 문자열 = 글꼴 이름."""
    for i in range(0, len(buf) - 4):
        v = struct.unpack_from('<I', buf, i)[0]
        q = i + v
        if not (i < q <= len(buf) - 5):
            continue
        n = struct.unpack_from('<I', buf, q)[0]
        if not (3 <= n <= 40 and q + 4 + n < len(buf)) or buf[q + 4 + n] != 0:
            continue
        try:
            t = bytes(buf[q + 4:q + 4 + n]).decode('ascii')
        except UnicodeDecodeError:
            continue
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9 \-]{2,39}', t) and t != 'AnimationType':
            return t
    return None


def 외곽선켜기(buf):
    """글줄 서식에 «외곽선 색을 쓴다» 표시(/5 = 1)를 넣는다.

    사장님 프로젝트 52장을 견줘 보니 규칙이 딱 떨어졌다 —
    **/5 가 있는 것만 /4 색이 먹는다.** /5 가 없으면 프리미어는 /4 를 무시하고
    기본 흰색으로 외곽선을 그린다. 우리 덩어리에는 /5 가 아예 없었다.

    플랫버퍼 테이블은 자리를 늘릴 수 없으므로 **버퍼 끝에 다시 짜서 붙이고**
    가리키는 곳만 새 자리로 돌린다. 기존 자리는 하나도 안 건드린다.
    """
    f = S._fields(buf, S._root0(buf))
    if 0 not in f:
        return
    p = f[0]
    v = p + F.u32(buf, p)
    n = F.u32(buf, v)
    for i in range(n):
        ep = v + 4 + 4 * i
        e = ep + F.u32(buf, ep)
        g = S._fields(buf, e)
        if 1 not in g:
            continue
        q = g[1]
        run = q + F.u32(buf, q)
        vt = run - F.i32(buf, run)
        vt크기 = F.u16(buf, vt)
        표크기 = F.u16(buf, vt + 2)
        if vt크기 < 4 + 2 * 6:
            continue
        있음 = F.u16(buf, vt + 4 + 2 * 5)
        if 있음:
            buf[run + 있음] = 1
            continue
        옛vt = bytes(buf[vt:vt + vt크기])
        옛표 = bytes(buf[run:run + 표크기])
        while len(buf) % 4:
            buf.append(0)
        새vt = len(buf)
        buf += 옛vt
        struct.pack_into('<H', buf, 새vt + 2, 표크기 + 1)
        struct.pack_into('<H', buf, 새vt + 4 + 2 * 5, 표크기)
        while len(buf) % 4:
            buf.append(0)
        새표 = len(buf)
        buf += 옛표
        buf.append(1)
        while len(buf) % 4:
            buf.append(0)
        struct.pack_into('<i', buf, 새표, 새표 - 새vt)
        # 표 안의 «가리키는 값»(색 테이블) 손보기.
        #   플랫버퍼의 uoffset 은 **앞으로만** 갈 수 있다. 새 표가 버퍼 끝으로
        #   갔으니 색 테이블도 그 뒤로 옮겨야 가리킬 수 있다. 테이블의 vtable 은
        #   제자리에 둬도 된다 — soffset(뒤로 가는 거리)만 다시 재면 된다.
        for k in (2, 4):
            o = F.u16(buf, vt + 4 + 2 * k) if vt크기 >= 4 + 2 * (k + 1) else 0
            if not o:
                continue
            옛자리 = run + o
            대상 = 옛자리 + F.u32(buf, 옛자리)
            vt2 = 대상 - F.i32(buf, 대상)
            크기2 = F.u16(buf, vt2 + 2)
            덩이 = bytes(buf[대상:대상 + 크기2])
            while len(buf) % 4:
                buf.append(0)
            새대상 = len(buf)
            buf += 덩이
            struct.pack_into('<i', buf, 새대상, 새대상 - vt2)
            새자리 = 새표 + o
            struct.pack_into('<I', buf, 새자리, 새대상 - 새자리)
        struct.pack_into('<I', buf, q, 새표 - q)


def 채움색넣기(buf, rgb):
    """글줄 서식에 **칠 색(run/2)** 을 넣는다.

    왜 두 군데에 넣나
      프리미어가 «칠» 로 쓰는 자리가 root/10 인지 run/2 인지 밖에서 가릴 수 없다.
      사장님 자막을 보면 이름이 «노란색 자막» 인 것은 run/2 가 노랑이고,
      «초록 특별» 인 것은 root/10 이 초록이다 — 두 꼴이 다 있다.
      그래서 **양쪽에 같은 색을 넣는다.** 외곽선 굵기가 0 이므로, 둘 중 하나가
      선 색이더라도 그려지지 않아 해가 없다. 어느 쪽이 칠이든 색은 맞는다.

    어떻게
      플랫버퍼 테이블은 자리를 못 늘리니 버퍼 끝에 다시 짜 붙인다.
      새 색 테이블은 이미 있는 run/4 색 테이블을 **본떠서** 만든다(그래야 vtable 을
      새로 짤 필요가 없다). uoffset 은 앞으로만 가므로 색 테이블은 표보다 뒤에 둔다.
    """
    f = S._fields(buf, S._root0(buf))
    if 0 not in f:
        return
    p = f[0]
    v = p + F.u32(buf, p)
    n = F.u32(buf, v)
    for i in range(n):
        ep = v + 4 + 4 * i
        e = ep + F.u32(buf, ep)
        g = S._fields(buf, e)
        if 1 not in g:
            continue
        q = g[1]
        run = q + F.u32(buf, q)
        vt = run - F.i32(buf, run)
        vt크기 = F.u16(buf, vt)
        표크기 = F.u16(buf, vt + 2)
        if vt크기 < 4 + 2 * 5:
            continue
        있2 = F.u16(buf, vt + 4 + 2 * 2)
        if 있2:
            자리 = run + 있2
            색쓰기(buf, 자리 + F.u32(buf, 자리), rgb)
            continue
        있4 = F.u16(buf, vt + 4 + 2 * 4)
        if not 있4:
            continue
        본자리 = run + 있4
        본 = 본자리 + F.u32(buf, 본자리)
        본vt = 본 - F.i32(buf, 본)
        본크기 = F.u16(buf, 본vt + 2)
        옛vt = bytes(buf[vt:vt + vt크기])
        옛표 = bytes(buf[run:run + 표크기])
        옛색 = bytes(buf[본:본 + 본크기])

        o2 = (표크기 + 3) // 4 * 4          # 새 자리는 4의 배수라야 한다
        while len(buf) % 4:
            buf.append(0)
        새vt = len(buf)
        buf += 옛vt
        struct.pack_into('<H', buf, 새vt + 2, o2 + 4)
        struct.pack_into('<H', buf, 새vt + 4 + 2 * 2, o2)
        while len(buf) % 4:
            buf.append(0)
        새표 = len(buf)
        buf += 옛표
        while len(buf) - 새표 < o2 + 4:
            buf.append(0)
        while len(buf) % 4:
            buf.append(0)
        struct.pack_into('<i', buf, 새표, 새표 - 새vt)

        # 선 색(/4) 은 자리가 옮겨졌으니 색표도 뒤로 옮겨 다시 가리킨다
        while len(buf) % 4:
            buf.append(0)
        새선 = len(buf)
        buf += 옛색
        struct.pack_into('<i', buf, 새선, 새선 - 본vt)
        struct.pack_into('<I', buf, 새표 + 있4, 새선 - (새표 + 있4))

        # 칠 색(/2) — 같은 본을 떠서 색만 새로
        while len(buf) % 4:
            buf.append(0)
        새칠 = len(buf)
        buf += 옛색
        struct.pack_into('<i', buf, 새칠, 새칠 - 본vt)
        색쓰기(buf, 새칠, rgb)
        struct.pack_into('<I', buf, 새표 + o2, 새칠 - (새표 + o2))

        struct.pack_into('<I', buf, q, 새표 - q)


def 입히기(raw, 잡, 줄잡=None):
    """덩어리 하나에 서식을 입힌 새 덩어리. 줄잡 을 주면 **줄마다** 색·크기를 달리한다."""
    buf, _ = S.unwrap(raw)

    # ① 글꼴 — 문자열이라 길이가 바뀐다. 지금 쓰고 있는 이름을 먼저 찾는다.
    #   ★소스텍스트.read_text 는 «한글이 든 것» 만 돌려준다. 글꼴 이름은 영문이라
    #     거기 안 걸린다 — 그래서 따로 훑는다.
    지금글꼴 = 글꼴찾기(buf)
    if 지금글꼴 and 지금글꼴 != 잡['글꼴']:
        raw = S.replace_text(raw, 지금글꼴, 잡['글꼴'])
        buf, _ = S.unwrap(raw)

    # ② 크기·외곽선 굵기·외곽선 색 — 제자리
    굵기 = 잡['외곽선'] if 외곽선넣기 else 0.0
    # ★굵기 0 이라도 프리미어가 선을 그리는 일이 있다(제목·크레딧에 검은 테가 생겼다).
    #   그래서 선이 없어야 하는 자막은 **선 색을 칠 색과 같게** 둔다 — 그려져도 안 보인다.
    선색 = 잡['외곽선색'] if 굵기 > 0 else 잡['채움']
    for r in S.runs(buf):
        g = S._fields(buf, r)
        if 1 in g:
            struct.pack_into('<f', buf, g[1], 잡['크기'])
        if 6 in g:
            struct.pack_into('<f', buf, g[6], 굵기)
        if 4 in g:
            색쓰기(buf, g[4] + F.u32(buf, g[4]), 선색)
        # ★칠(채움) 색은 **run/2** 다 (2026-08-26 실측).
        #   여태 root/10 에 써 왔는데 그 자리는 (0,0,0) 인 딴 값이라, 무슨 색을 넣어도
        #   화면은 곳간 본의 색 그대로 나왔다 — 포핸즈 1-1 에서 나레·모션자막이
        #   전부 흰색으로 나온 것이 이것이다. run/2 에 쓰면 그 색이 화면에 나온다.
        if 2 in g and not 칠건드리지마:
            색쓰기(buf, g[2] + F.u32(buf, g[2]), 잡['채움'])

    # ③ 외곽선을 «쓴다» 는 표시 — 이게 없으면 run/4 색을 무시하고 흰색으로 그린다
    외곽선켜기(buf)      # /5 가 있어야 run/4 색이 먹는다 — 굵기 0 일 때도 넣는다
    if not 칠건드리지마:
        채움색넣기(buf, 잡['채움'])

    # ③-2 줄마다 색이 다르면 (제목 1줄 노랑 · 2줄 빨강) 글줄을 나눈다
    if 줄나누기쓰기 and 줄잡 and len(줄잡) > 1 and len({j['채움'] for j in 줄잡}) > 1:
        if J.줄나누기(buf, [j['채움'] for j in 줄잡]):
            for r, j in zip(S.runs(buf), 줄잡):
                gg = S._fields(buf, r)
                굵 = j['외곽선'] if 외곽선넣기 else 0.0
                if 1 in gg:
                    struct.pack_into('<f', buf, gg[1], j['크기'])
                if 6 in gg:
                    struct.pack_into('<f', buf, gg[6], 굵)
                if 4 in gg:
                    # ★선 색은 **그 줄 자신의 칠 색**과 같게 둔다.
                    #   그래픽 칠 색(첫 줄 색)을 쓰면 둘째 줄에 흰/노란 테가 보인다.
                    색쓰기(buf, gg[4] + F.u32(buf, gg[4]),
                          j['외곽선색'] if 굵 > 0 else j['채움'])
                if 2 in gg:
                    색쓰기(buf, gg[2] + F.u32(buf, gg[2]), j['채움'])

    # ④ 채움색 — 그래픽 전체 (root/10). /11 은 «이 색을 쓴다» 는 표시라 건드리지 않는다
    f = S._fields(buf, S._root0(buf))
    if 10 in f and not 칠건드리지마:
        색쓰기(buf, f[10] + F.u32(buf, f[10]), 잡['채움'])

    # ④-2 그림자 색(root/17) — **곳간 색이 딸려 온다.** 반드시 선색(검정)으로 덮어라.
    #   2026-08-26: 곳간 「쓰인05」가 마젠타(#E04FB2) 그림자를 들고 있어서, 나레자막
    #   다섯 장에 분홍 그림자가 깔렸다. 사장님은 «배경색이 들어갔다» 고 보셨다.
    #   root/14·15·16·17·19·20 은 둘레가 아니라 **그림자 한 벌**이다
    #   (크기 3 · 흐림 6 · 16 · 색 · 각 · 거리 10). 색만 검정이면 사장님 판과 같다.
    if 17 in f:
        색쓰기(buf, f[17] + F.u32(buf, f[17]), 잡['외곽선색'])

    # ⑤ 글자 둘레 그룹(root/14 크기 · /15 흐림 · /16 · /20 거리) — **건드리지 않는다.**
    #   2026-08-26 프리미어에서 실제로 내보내 화소로 재고서야 알았다. 둘레는
    #   **채움색(root/10)으로 그려진다.** 그래서 root/10 을 안 넣고 두면(--칠은그대로)
    #   둘레가 흰/검정으로 남아 「흰 테두리」로 보인다. 원인은 둘레가 아니라 칠이었다.
    #   사장님이 손수 고쳐 확정한 판은 14=3 · 15=6 · 16=12 · 20=10 을 그대로 두고도
    #   멀쩡하다 — root/10 에 같은 색이 들어가 있어 둘레가 글자에 묻히기 때문이다.
    #   그러니 0 으로 밀지 말고 **칠을 제대로 넣어라.**
    if 둘레지우기:
        for k in (14, 15, 16, 20):
            if k in f:
                struct.pack_into('<f', buf, f[k], 0.0)

    # ⑥ run/20 — 이 표가 1 이면 run/2 색이 **칠이 아니라 선**으로 간다.
    #   모션자막 본(쓰인02)에만 붙어 있어서, 같은 자리에 같은 색을 넣어도 모션자막만
    #   글자 속이 비고 테두리만 물들었다. 내보낸 화면을 확대해서 잡았다(2026-08-26).
    for r in S.runs(buf):
        g20 = F.fields(buf, r)
        if 20 in g20:
            buf[g20[20]] = 0

    return S.wrap(buf), 지금글꼴


P = argparse.ArgumentParser()
P.add_argument('프로젝트')
P.add_argument('자막')
P.add_argument('--보기만', action='store_true', dest='보기만')
P.add_argument('--둘레지우기', action='store_true', dest='둘레지우기',
               help='글자 둘레(root/14·15·16·20)를 0 으로 민다. 보통은 필요 없다 — 칠을 제대로 넣으면 묻힌다')
# ★칠(채움) 색은 곳간 본에 그 자리가 없으면 **못 쓴다** — 써도 흰색으로 나온다.
#   그럴 때는 «그 색을 원래 가진 본» 을 가져다 쓰고, 칠은 건드리지 않는다.
#   글꼴·크기·외곽선(굵기·색)은 그대로 입힌다.
P.add_argument('--칠은그대로', action='store_true', dest='칠은그대로')
P.add_argument('--층', default=None, dest='층',
               help='이 스타일들만 입힌다 (쉼표) — 예: headline_l1,headline_l2. 나머지 클립은 안 건드린다')
A = P.parse_args()
칠건드리지마 = bool(getattr(A, '칠은그대로', False))
둘레지우기 = bool(getattr(A, '둘레지우기', False))

_, 글자표 = ass읽기(A.자막)
if A.층:
    _허용 = set(x.strip() for x in A.층.split(','))
    글자표 = {k: v for k, v in 글자표.items() if v.get('스타일') in _허용}
    print('  (--층 %s — 그 스타일만 입힌다)' % A.층)
쪽 = gzip.open(A.프로젝트, 'rb').read().decode('utf-8')
덩어리 = re.findall(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', 쪽)

print('═' * 78)
print(f'  자막 서식 입히기 — {os.path.basename(A.프로젝트)}')
print('═' * 78)
print(f'  덩어리 {len(덩어리)}개 · 원본.ass 글줄 {len(글자표)}가지')
print()

바꿈 = {}
못찾음 = []
for i, b64 in enumerate(덩어리):
    raw = base64.b64decode(b64)
    # ★한글이 없는 자막도 글자다 (2026-08-27) — [[자리잡기.py]] 와 같은 까닭.
    글 = S.글자만(raw)
    if not 글:
        continue
    본문 = 글[0].replace('\r', '\n')
    잡 = 글자표.get(본문)
    if 잡 is None:                       # 두 줄이 한 장으로 합쳐진 것 — 첫 줄로 찾는다
        for 한줄 in 본문.split('\n'):
            잡 = 글자표.get(한줄.strip())
            if 잡:
                break
    if 잡 is None:
        못찾음.append((i, 본문))
        continue
    줄잡 = [글자표.get(q.strip()) for q in 본문.split(chr(10))]
    줄잡 = 줄잡 if all(줄잡) else None
    새raw, 옛글꼴 = 입히기(raw, 잡, 줄잡)
    바꿈[b64] = base64.b64encode(새raw).decode('ascii')
    r, g, bl = 잡['채움']
    print(f'  {i:2d} {잡["스타일"]:<14} {잡["글꼴"]:<18} {잡["크기"]:>5.0f}px  '
          f'#{r:02X}{g:02X}{bl:02X}  외곽선 {잡["외곽선"]:>3}  {본문.splitlines()[0][:20]}')

print()
if 못찾음:
    print('  ★원본.ass 에서 못 찾은 것:')
    for i, t in 못찾음:
        print(f'     {i:2d}  {t!r}')
    print()
print(f'  입힐 것 {len(바꿈)}장 · 못 찾은 것 {len(못찾음)}장')

if A.보기만:
    print('\n(--보기만 이라 파일은 안 건드린다)')
    raise SystemExit(0)

새쪽 = 쪽
for 옛, 새 in 바꿈.items():
    if 옛 not in 새쪽:
        raise SystemExit('덩어리를 다시 못 찾았다 — 멈춘다')
    새쪽 = 새쪽.replace(옛, 새, 1)

# ── 되읽어 확인한다. 여기서 안 맞으면 아무것도 안 쓴다 ──────────────
확인 = re.findall(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', 새쪽)
if len(확인) != len(덩어리):
    raise SystemExit(f'덩어리 수가 달라졌다 {len(덩어리)} → {len(확인)}')
탈 = 0
for b64 in 확인:
    raw = base64.b64decode(b64)
    try:
        buf, _ = S.unwrap(raw)
        S.runs(buf)
        S._fields(buf, S._root0(buf))
    except Exception as e:
        탈 += 1
        print('  ★다시 읽기 실패:', e)
if 탈:
    raise SystemExit('되읽기에서 탈이 났다 — 파일을 안 건드리고 멈춘다')
print('  되읽기 확인 — 55/55 정상')

백업 = A.프로젝트.replace('.prproj', f'_서식전_{time.strftime("%m%d_%H%M")}.prproj')
shutil.copy2(A.프로젝트, 백업)
with gzip.open(A.프로젝트, 'wb') as fh:
    fh.write(새쪽.encode('utf-8'))
print(f'  서식 전 판은 옆에 두었다: {os.path.basename(백업)}')
print(f'  다 됐다 → {A.프로젝트}')
