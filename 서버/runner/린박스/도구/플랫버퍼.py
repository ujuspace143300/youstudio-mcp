# -*- coding: utf-8 -*-
r"""스키마 없이 플랫버퍼(FlatBuffers)를 훑는다.

프리미어의 «소스 텍스트» 덩어리는 어도비가 스키마를 공개하지 않는다. 그래서
버퍼 자체가 들고 있는 **vtable** 을 읽어 «이 테이블에 몇 번 자리가 있고 값이
무엇인가» 를 알아낸다. 플랫버퍼는 자기를 설명하는 정보가 버퍼 안에 있다:

  · 테이블 맨 앞 4바이트 = vtable 까지의 **뒤로 가는** 거리(soffset)
  · vtable = [자기 크기 2][테이블 크기 2][필드0 위치 2][필드1 위치 2]...
    필드 위치가 0 이면 «그 필드는 없다»

값의 종류는 알 수 없으니 **가능한 해석을 모두** 보여 준다 — 정수·실수·문자열·
테이블. 사람이 보고 고른다.
"""
import struct


def u32(b, p):
    return struct.unpack_from('<I', b, p)[0]


def i32(b, p):
    return struct.unpack_from('<i', b, p)[0]


def u16(b, p):
    return struct.unpack_from('<H', b, p)[0]


def f32(b, p):
    return struct.unpack_from('<f', b, p)[0]


def fields(buf, tbl):
    """테이블의 {필드번호: 값위치} — vtable 을 읽어서."""
    vt = tbl - i32(buf, tbl)
    vt_size = u16(buf, vt)
    out = {}
    for k in range((vt_size - 4) // 2):
        off = u16(buf, vt + 4 + k * 2)
        if off:
            out[k] = tbl + off
    return out


def as_string(buf, p):
    """p 에 있는 uoffset 이 문자열을 가리키는가 — 그렇다면 그 글자."""
    try:
        q = p + u32(buf, p)
        n = u32(buf, q)
        if not (0 <= n <= 4096 and q + 4 + n < len(buf)):
            return None
        if buf[q + 4 + n] != 0:
            return None
        return buf[q + 4:q + 4 + n].decode('utf-8')
    except Exception:
        return None


def as_table(buf, p):
    """p 에 있는 uoffset 이 테이블을 가리키는가."""
    try:
        q = p + u32(buf, p)
        if not (0 < q < len(buf)):
            return None
        vt = q - i32(buf, q)
        if not (0 <= vt < len(buf) - 4):
            return None
        vs = u16(buf, vt)
        if not (4 <= vs <= 200 and vt + vs <= len(buf)):
            return None
        return q
    except Exception:
        return None


def walk(buf, tbl=None, depth=0, seen=None, out=None, path='root'):
    """테이블을 재귀로 훑어 [(길, 필드번호, 종류, 값)] 을 모은다."""
    if out is None:
        out = []
    if seen is None:
        seen = set()
    if tbl is None:
        tbl = u32(buf, 0)
    if tbl in seen or depth > 6:
        return out
    seen.add(tbl)
    for k, p in sorted(fields(buf, tbl).items()):
        s = as_string(buf, p)
        if s is not None and (s.isprintable() or s == ''):
            out.append((path, k, '글자', s))
            continue
        t = as_table(buf, p)
        if t is not None:
            out.append((path, k, '테이블', t))
            walk(buf, t, depth + 1, seen, out, '%s/%d' % (path, k))
            continue
        v_i = u32(buf, p) if p + 4 <= len(buf) else 0
        v_f = f32(buf, p) if p + 4 <= len(buf) else 0.0
        out.append((path, k, '값', (v_i, v_f, p)))
    return out
