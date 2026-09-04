# -*- coding: utf-8 -*-
r"""깔려 있는 글꼴을 훑어 **이름 ↔ 파일 ↔ 프리미어용 이름 ↔ 크기 환산비** 표를 만든다.

왜 필요한가
  · 프리미어는 글꼴을 **PostScript 이름**(name6) 으로 찾는다. ASS 는 **집안 이름**(name1)
    을 쓴다. 둘이 다르다 — 'Gmarket Sans TTF Medium' ↔ 'GmarketSansTTFMedium'.
  · ASS 의 글자 크기와 프리미어의 글자 크기는 **뜻이 다르다.** ASS(libass)는 «올림+내림»
    이 그 크기가 되게 잡고, 프리미어는 em 을 그 크기로 잡는다. 그래서
        프리미어 크기 = ASS 크기 × upm / (winAscent + winDescent)
    이 값은 **글꼴마다 다르다** — Gmarket 0.870 · Paperlogy 0.849 · 강원교육모두 0.873.
    한 값으로 고정해 두면 다른 글꼴을 쓰는 순간 크기가 어긋난다.
"""
import glob
import os
import struct

# ★맥 자리도 본다 (2026-08-26). 전에는 윈도우 두 곳만 훑어, 맥에서는 글꼴이 멀쩡히
#   깔려 있어도 «이 컴퓨터에 없는 글꼴이다» 로 서식입히기가 멈췄다.
자리 = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts'),
        os.path.expanduser('~/Library/Fonts'),
        '/Library/Fonts', '/System/Library/Fonts', '/System/Library/Fonts/Supplemental']

# ★산돌구름 글꼴은 **숨은 곳간**에 해시 이름으로 깔린다 (2026-08-27 맥2).
#   Paperlogy·강원교육모두처럼 산돌구름으로 받은 글꼴은 위 자리 어디에도 파일이 없어서
#   «이 컴퓨터에 없는 글꼴이다» 로 서식입히기.py 가 멈췄다. 실제 파일은 여기 있다:
#     ~/Library/Application Support/kr.co.sandoll.SandollCloud/.System.psp2Data/c69/32d/…/<해시>.ttf
#   폴더가 세 겹으로 갈라져 있어 glob 로는 안 걸린다 — 이 자리만 걸어서 훑는다.
_산돌 = os.path.expanduser(
    '~/Library/Application Support/kr.co.sandoll.SandollCloud/.System.psp2Data')
if os.path.isdir(_산돌):
    for _뿌리, _방들, _ in os.walk(_산돌):
        if _뿌리 != _산돌:
            자리.append(_뿌리)
_표 = None


def _읽기(fp):
    d = open(fp, 'rb').read()
    if d[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
        return None
    n = struct.unpack_from('>H', d, 4)[0]
    T = {}
    for i in range(n):
        o = 12 + 16 * i
        T[d[o:o + 4].decode('latin1', 'replace')] = struct.unpack_from('>II', d, o + 8)
    if 'name' not in T or 'head' not in T or 'OS/2' not in T:
        return None
    off, _ = T['name']
    cnt, so = struct.unpack_from('>HH', d, off + 2)
    이름 = {}
    for i in range(cnt):
        p = off + 6 + 12 * i
        pid, eid, lid, nid, ln, o2 = struct.unpack_from('>HHHHHH', d, p)
        s = d[off + so + o2:off + so + o2 + ln]
        try:
            t = s.decode('utf-16-be') if pid == 3 else s.decode('latin1')
        except Exception:
            continue
        if nid in (1, 4, 6) and nid not in 이름:
            이름[nid] = t
    ho, _ = T['head']
    upm = struct.unpack_from('>H', d, ho + 18)[0]
    o2, _ = T['OS/2']
    wA, wD = struct.unpack_from('>HH', d, o2 + 74)
    if not (upm and wA + wD):
        return None
    return 이름, upm, wA, wD


def 표():
    """{집안이름/전체이름: {'파일','프리미어이름','환산비'}}"""
    global _표
    if _표 is not None:
        return _표
    _표 = {}
    for d in 자리:
        for fp in glob.glob(os.path.join(d, '*.ttf')) + glob.glob(os.path.join(d, '*.otf')):
            try:
                r = _읽기(fp)
            except Exception:
                continue
            if not r:
                continue
            이름, upm, wA, wD = r
            항 = {'파일': fp, '프리미어이름': 이름.get(6) or 이름.get(4),
                  '환산비': upm / (wA + wD)}
            for k in (1, 4, 6):
                if 이름.get(k):
                    _표.setdefault(이름[k], 항)
                    _표.setdefault(이름[k].replace(' ', ''), 항)
    return _표


def 찾기(이름):
    t = 표()
    return t.get(이름) or t.get(이름.replace(' ', ''))
