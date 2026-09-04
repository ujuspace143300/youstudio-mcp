# -*- coding: utf-8 -*-
import struct
import 소스텍스트 as S
import 플랫버퍼 as F


def 색쓰기(buf, 표, rgb):
    g = F.fields(buf, 표)
    for k, v in zip((0, 1, 2), rgb):
        if k in g:
            buf[g[k]] = int(v) & 0xFF


def 맞춤(buf):
    while len(buf) % 4:
        buf.append(0)


def 줄나누기(buf, 색목록):
    """한 그래픽의 글줄을 나눠 줄마다 색을 달리한다. 성공하면 True."""
    f = S._fields(buf, S._root0(buf))
    if 0 not in f:
        return False
    p = f[0]
    v = p + F.u32(buf, p)
    if F.u32(buf, v) != 1:
        return False
    ep = v + 4
    e = ep + F.u32(buf, ep)
    g = S._fields(buf, e)
    if 0 not in g or 1 not in g:
        return False

    ts = g[0] + F.u32(buf, g[0])
    본문 = bytes(buf[ts + 4:ts + 4 + F.u32(buf, ts)]).decode('utf-8')
    사이 = chr(13) if chr(13) in 본문 else chr(10)
    줄 = 본문.split(사이)
    if len(줄) != len(색목록):
        return False

    run = g[1] + F.u32(buf, g[1])
    evt = e - F.i32(buf, e)
    rvt = run - F.i32(buf, run)
    옛e = bytes(buf[e:e + F.u16(buf, evt + 2)])
    옛r = bytes(buf[run:run + F.u16(buf, rvt + 2)])

    색본 = {}
    for k in (2, 4):
        o = F.u16(buf, rvt + 4 + 2 * k) if F.u16(buf, rvt) >= 4 + 2 * (k + 1) else 0
        if not o:
            continue
        대상 = (run + o) + F.u32(buf, run + o)
        vt2 = 대상 - F.i32(buf, 대상)
        색본[k] = (o, bytes(buf[대상:대상 + F.u16(buf, vt2 + 2)]), vt2)

    n = len(줄)
    맞춤(buf); V = len(buf)
    buf += struct.pack('<I', n) + b'\x00' * (4 * n)

    줄자리 = []
    for i in range(n):
        맞춤(buf); L = len(buf); buf += 옛e
        struct.pack_into('<i', buf, L, L - evt)
        줄자리.append(L)
        struct.pack_into('<I', buf, V + 4 + 4 * i, L - (V + 4 + 4 * i))

    run자리 = []
    for i in range(n):
        맞춤(buf); R = len(buf); buf += 옛r
        struct.pack_into('<i', buf, R, R - rvt)
        run자리.append(R)
        struct.pack_into('<I', buf, 줄자리[i] + F.u16(buf, evt + 4 + 2 * 1),
                         R - (줄자리[i] + F.u16(buf, evt + 4 + 2 * 1)))

    for i, 글 in enumerate(줄):
        맞춤(buf); T = len(buf)
        # ★줄바꿈 문자를 살려야 한다. 안 그러면 두 줄이 한 줄로 붙어 흘러가
        #   상자 폭에서 엉뚱한 자리에 접힌다 (「소년이웃으며」 사고)
        b = (글 + (사이 if i < n - 1 else '')).encode('utf-8')
        buf += struct.pack('<I', len(b)) + b + b'\x00'
        o0 = F.u16(buf, evt + 4 + 2 * 0)
        struct.pack_into('<I', buf, 줄자리[i] + o0, T - (줄자리[i] + o0))

    for i in range(n):
        for k, (o, 덩이, vt2) in 색본.items():
            맞춤(buf); C = len(buf); buf += 덩이
            struct.pack_into('<i', buf, C, C - vt2)
            if k == 2:
                색쓰기(buf, C, 색목록[i])
            struct.pack_into('<I', buf, run자리[i] + o, C - (run자리[i] + o))

    struct.pack_into('<I', buf, p, V - p)
    return True
