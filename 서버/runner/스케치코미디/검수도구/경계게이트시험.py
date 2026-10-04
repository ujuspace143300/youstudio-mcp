#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경계게이트시험.py — 준비의 «경계» 게이트 공식(옛: 맨 상관 / 새: 정규화 상관)을 원본 소리로 시험한다.
① 오탐 네 건(실측 0ms 였던 컷 시작)에서 새 공식이 0 을 내는가  ② 일부러 밀어 놓은 소리(±0.1·0.2s)를 새 공식이 잡는가."""
import os, subprocess
import numpy as np
# ffmpeg·ffprobe 스레드 상한은 s2pipe/ff.py 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
import os as _ff_os, sys as _ff_sys  # noqa: E402
_ff_d = _ff_os.path.dirname(_ff_os.path.abspath(__file__))
_ff_d = _ff_os.path.dirname(_ff_d)
if _ff_d not in _ff_sys.path:
    _ff_sys.path.append(_ff_d)
from s2pipe import ff  # noqa: E402
W = os.path.expanduser("~/Desktop/스케치코미디/work")


def snd(path, t0, d):
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{max(t0,0):.3f}", "-i", path, "-t", f"{d:.3f}",
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]), capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(float)


def 옛(a2, bb2):
    c = np.correlate(bb2 - bb2.mean(), a2 - a2.mean(), "valid"); i = int(np.argmax(c))
    return None if i in (0, len(c) - 1) else i / 16000 - 0.75


def 새(a2, bb2):
    a0, b0 = a2 - a2.mean(), bb2 - bb2.mean()
    c = np.correlate(b0, a0, "valid"); n = len(a0)
    cs = np.concatenate([[0.0], np.cumsum(b0 * b0)])
    en = np.sqrt(np.maximum(cs[n:] - cs[:-n], 1e-9) * float((a0 * a0).sum()))
    c = c / en[:len(c)]; i = int(np.argmax(c))
    if c[i] < 0.5 or i in (0, len(c) - 1):
        return None
    return i / 16000 - 0.75


def 판정(v):
    return "판정불가" if v is None else (f"{v:+.3f}s " + ("★실패" if 0.08 < abs(v) <= 0.5 else "통과"))


print("① 오탐이 났던 컷 시작(실측 0ms) — 완성본 컷 소리 = 원본 소리")
for slug, t0 in (("Deep93", 366.8), ("Deep77", 272.6), ("Deep80", 244.4), ("Deep92", 271.0)):
    src = f"{W}/{slug}.mp4"
    a2, bb2 = snd(src, t0 + 0.10, 0.5), snd(src, t0 - 0.65, 2.0)
    print(f"  {slug} t0={t0}: 옛 {판정(옛(a2, bb2))} · 새 {판정(새(a2, bb2))}")
print("② 일부러 민 소리 — 말이 있는 자리에서 컷 소리를 원본보다 d 초 늦게 뜬 것으로 꾸밈")
for slug, t0 in (("Deep93", 345.0), ("Deep77", 300.0), ("Deep80", 250.0)):
    src = f"{W}/{slug}.mp4"
    for d in (0.0, 0.1, -0.2):
        a2, bb2 = snd(src, t0 + 0.10 + d, 0.5), snd(src, t0 - 0.65, 2.0)
        print(f"  {slug} t0={t0} 민 값 {d:+.1f}: 옛 {판정(옛(a2, bb2))} · 새 {판정(새(a2, bb2))}")
