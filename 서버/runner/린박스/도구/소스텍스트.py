# -*- coding: utf-8 -*-
r"""프리미어 **텍스트 그래픽의 글자를 바꿔 쓴다.**

무엇을 알아냈나 (사장님 프로젝트 「미안해형.prproj」를 뜯어서)
  프리미어 자막은 캡션이 아니라 **텍스트 그래픽**이다. 글자와 서식은
  `ArbVideoComponentParam` 중 이름이 «소스 텍스트» 인 것의 base64 덩어리에 들어 있다.

  그 덩어리의 짜임 —
    [0:8]   본체 길이 (uint64)
    [8:12]  매직 44 33 22 11
    [12:]   **플랫버퍼(FlatBuffers)**  ← 글꼴·크기·색·글자가 여기 다 있다

  글자는 플랫버퍼 안의 문자열이다: [길이 4바이트][utf-8 바이트][널]. 그리고 그
  문자열을 가리키는 **uoffset** 이 한 자리 있다(위치 P 에 적힌 값 v 는 P+v 를 가리킨다).

왜 통째로 다시 짜지 않는가
  글자 길이가 바뀌면 뒤따르는 오프셋이 전부 어긋난다. 실제로 같은 무리의 두
  덩어리를 견줘 보니 글자 뒤 80군데가 달랐다 — 통짜 복사는 못 쓴다.

  대신 **뒤에 새 문자열을 덧붙이고 그 uoffset 만 새 자리로 돌린다.** 플랫버퍼의
  오프셋은 «자기 위치 기준» 이라, 버퍼 **끝에** 붙이는 것은 기존 자리를 하나도
  안 건드린다. 옛 문자열은 죽은 공간으로 남을 뿐이다.
"""
import struct

MAGIC = b'\x44\x33\x22\x11'


def unwrap(raw):
    """덩어리 → (플랫버퍼 본체, 머리)"""
    if raw[8:12] != MAGIC:
        raise ValueError('매직이 다르다 — 소스 텍스트 덩어리가 아니다')
    n = struct.unpack_from('<Q', raw, 0)[0]
    # ★덩어리 **뒤에 여분이 붙는다** (2026-08-26).
    #   프리미어가 FCP7 텍스트 제너레이터를 가져와 만든 자막은 머리에 적힌 길이보다
    #   실제 덩어리가 길다(머리 396 · 실제 701). 전에는 그걸 «길이가 안 맞는다» 로
    #   막아서 서식입히기·자리잡기·본떠서만들기가 **통째로 못 돌았다.**
    #   머리가 더 길면 진짜 탈이지만, **덩어리가 더 긴 것은 여분일 뿐**이라 잘라 쓴다.
    if n + 12 > len(raw):
        raise ValueError('길이가 안 맞는다: 머리 %d · 실제 %d' % (n, len(raw) - 12))
    # ★뒤에 **0 으로 채운 꼬리**가 붙어 있을 수 있다 (2026-08-25 실측).
    #   FCP7 XML 의 <generatoritem> 으로 들어온 자막이 그렇다 — 본체 376바이트 뒤에
    #   0 만 305바이트가 더 붙어 있었다. 머리에 적힌 길이가 참이니 그만큼만 쓴다.
    #   («!= 로 막아 두었더니 그 자막을 통째로 못 읽었다.»)
    꼬리 = raw[12 + n:]
    if 꼬리 and any(꼬리):
        raise ValueError('꼬리에 0 아닌 것이 %d바이트 있다 — 모르는 꼴이다' % sum(1 for b in 꼬리 if b))
    return bytearray(raw[12:12 + n]), raw[:12]


def wrap(buf):
    return struct.pack('<Q', len(buf)) + MAGIC + bytes(buf)


def find_string(buf, text):
    """buf 안에서 text 문자열의 (길이머리 위치, 그것을 가리키는 uoffset 위치)."""
    b = text.encode('utf-8')
    at = -1
    while True:
        at = buf.find(b, at + 1)
        if at < 0:
            raise KeyError('글자를 못 찾았다: %r' % text)
        if at >= 4 and struct.unpack_from('<I', buf, at - 4)[0] == len(b):
            break
    sp = at - 4
    ptrs = [i for i in range(0, len(buf) - 4)
            if struct.unpack_from('<I', buf, i)[0] == sp - i and i < sp]
    if not ptrs:
        raise ValueError('가리키는 자리가 없다: %r' % text)
    # ★가리키는 자리가 여럿일 수 있다 (2026-08-26).
    #   한 자막에 글줄이 둘이면 **같은 글꼴 이름을 두 run 이 함께 가리킨다.**
    #   전에는 «1곳이어야 한다» 며 멈춰서 서식입히기·자리잡기가 통째로 실패했다.
    #   여럿이면 **전부** 새 자리로 돌려야 한다 — 하나만 바꾸면 나머지가 옛 글자를 가리킨다.
    return sp, ptrs


def replace_text(raw, old, new):
    """소스 텍스트 덩어리의 글자를 old → new 로 바꾼 새 덩어리를 돌려준다."""
    buf, _ = unwrap(raw)
    sp, ptrs = find_string(buf, old)
    nb = new.encode('utf-8')
    # 4바이트 맞춤으로 끝에 새 문자열을 붙인다
    while len(buf) % 4:
        buf.append(0)
    at = len(buf)
    buf += struct.pack('<I', len(nb)) + nb + b'\x00'
    while len(buf) % 4:
        buf.append(0)
    for _p in ptrs:                                # ★가리키는 자리를 **전부** 돌린다
        struct.pack_into('<I', buf, _p, at - _p)   # uoffset 을 새 자리로
    return wrap(buf)


def read_text(raw, hint=None):
    """덩어리 안의 «지금 살아 있는» 글자를 읽는다 (uoffset 을 따라간다)."""
    buf, _ = unwrap(raw)
    out = []
    for i in range(0, len(buf) - 4):
        v = struct.unpack_from('<I', buf, i)[0]
        p = i + v
        if not (i < p <= len(buf) - 5):
            continue
        n = struct.unpack_from('<I', buf, p)[0]
        if not (1 <= n <= 400 and p + 4 + n < len(buf)):
            continue
        if buf[p + 4 + n] != 0:
            continue
        try:
            t = buf[p + 4:p + 4 + n].decode('utf-8')
        except UnicodeDecodeError:
            continue
        if any('가' <= c <= '힣' for c in t) or (hint and hint in t):
            out.append((i, t))
    return out


# ── 서식 자리 지도 (사장님 프로젝트 52장을 뜯어 확인) ────────────────
#
#   r/0                     그래픽 한 장
#     /0        글줄 벡터
#       [n]/0   **글자**            문자열
#       [n]/1   글줄 서식
#            /1  **글자 크기**       실수 — 실측 48 · 49.892 · 92.2973 · 41.4783
#            /6  **외곽선 굵기**     실수 — 실측 0 · 2.5 · 4 · 10
#            /2, /4  색 테이블 (uint8 넷)
#     /2, /3    상자 가로·세로       실수 — 810 · 576
#     /10, /17  색 테이블           uint8 넷 — #FFA800 · #D557DA · #E04FB2 등
#     /32       이름 벡터           "AnimationType"
#     /40       효과 목록 (그림자 등)
#
#   글꼴 이름은 **테이블 필드가 아니라 벡터 원소**로 들어 있다.
#   그래서 이름을 바꿀 때도 문자열 바꿔쓰기(덧붙이고 uoffset 돌리기)를 쓴다.
import struct as _s


def _root0(buf):
    """r/0 테이블 위치."""
    root = _s.unpack_from('<I', buf, 0)[0]
    vt = root - _s.unpack_from('<i', buf, root)[0]
    off = _s.unpack_from('<H', buf, vt + 4)[0]
    p = root + off
    return p + _s.unpack_from('<I', buf, p)[0]


def _fields(buf, tbl):
    vt = tbl - _s.unpack_from('<i', buf, tbl)[0]
    n = (_s.unpack_from('<H', buf, vt)[0] - 4) // 2
    out = {}
    for k in range(n):
        o = _s.unpack_from('<H', buf, vt + 4 + k * 2)[0]
        if o:
            out[k] = tbl + o
    return out


def runs(buf):
    """글줄 서식 테이블들의 위치."""
    f = _fields(buf, _root0(buf))
    if 0 not in f:
        return []
    p = f[0]
    v = p + _s.unpack_from('<I', buf, p)[0]
    n = _s.unpack_from('<I', buf, v)[0]
    out = []
    for i in range(n):
        ep = v + 4 + 4 * i
        e = ep + _s.unpack_from('<I', buf, ep)[0]
        g = _fields(buf, e)
        if 1 in g:
            q = g[1]
            out.append(q + _s.unpack_from('<I', buf, q)[0])
    return out


def 글줄들(raw):
    """글줄 벡터를 **구조로 걸어서** 글자를 읽는다 → [(자리, 글자), …]

    ★`read_text()` 와 무엇이 다른가 — read_text 는 버퍼를 통째로 훑어 «문자열처럼 생긴 것»
      을 다 줍기 때문에 글꼴 이름(LucidaConsole·GangwonEduAllBold)·«AnimationType» 까지
      딸려 온다. 그래서 그걸 걸러내려고 **«한글이 든 것만»** 남겼는데, 그 필터가
      「?!」·숫자·영문 자막까지 함께 버렸다. 그런 자막은 서식·자리를 못 받고
      **조용히 건너뛰어져** 화면 밖으로 나갔다 (2026-08-27 사장님 지적).

      이 함수는 r/0 → 글줄 벡터 → 각 글줄의 /0 만 읽으므로 **글자만 정확히** 나온다.
      한글이 없어도 된다. 새 코드는 이것을 쓰고, read_text 는 옛 호출자를 위해 남겨 둔다.
    """
    buf, _ = unwrap(raw)
    f = _fields(buf, _root0(buf))
    if 0 not in f:
        return []
    p = f[0]
    v = p + _s.unpack_from('<I', buf, p)[0]
    n = _s.unpack_from('<I', buf, v)[0]
    out = []
    for i in range(n):
        ep = v + 4 + 4 * i
        e = ep + _s.unpack_from('<I', buf, ep)[0]
        g = _fields(buf, e)
        if 0 not in g:
            continue
        q = g[0]
        t = q + _s.unpack_from('<I', buf, q)[0]
        ln = _s.unpack_from('<I', buf, t)[0]
        out.append((q, bytes(buf[t + 4:t + 4 + ln]).decode('utf-8', 'replace')))
    return out


def 글자만(raw):
    """글줄들() 의 글자만. 못 읽으면 read_text 로 물러난다."""
    try:
        옛 = [t for _, t in 글줄들(raw) if t.strip()]
        if 옛:
            return 옛
    except Exception:
        pass
    return [t for _, t in read_text(raw) if t.strip()]


def set_style(raw, size=None, outline=None):
    """글자 크기·외곽선 굵기를 바꾼다 (자리를 안 옮기므로 안전하다)."""
    buf, _ = unwrap(raw)
    n = 0
    for r in runs(buf):
        g = _fields(buf, r)
        if size is not None and 1 in g:
            _s.pack_into('<f', buf, g[1], float(size)); n += 1
        if outline is not None and 6 in g:
            _s.pack_into('<f', buf, g[6], float(outline)); n += 1
    return wrap(buf), n


def read_style(raw):
    buf, _ = unwrap(raw)
    out = []
    for r in runs(buf):
        g = _fields(buf, r)
        out.append({'크기': _s.unpack_from('<f', buf, g[1])[0] if 1 in g else None,
                    '외곽선': _s.unpack_from('<f', buf, g[6])[0] if 6 in g else None})
    return out
