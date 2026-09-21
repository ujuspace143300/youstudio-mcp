#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경계게이트모의.py <슬러그> <원본 t0> — 준비의 «경계 겹침 감시»(컷 시작+0.10s 의 0.5s 창을 원본 -0.65~+1.35s 에서 상관)를
원본 소리만으로 흉내 낸다(완성본 컷 소리 = 원본 소리임을 컷소리재기로 확인한 뒤에만 의미가 있다).
t0 를 -0.5~+0.5s 로 옮겨 가며 게이트가 낼 값을 찍는다. 읽기 전용."""
import os, subprocess, sys
import numpy as np
slug, t0 = sys.argv[1], float(sys.argv[2])
src = os.path.expanduser(f"~/Desktop/스케치코미디/work/{slug}.mp4")
def snd(a, d):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(a,0):.3f}", "-i", src, "-t", f"{d:.3f}",
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(float)
for k in range(-10, 11):
    t = round(t0 + k * 0.05, 2)
    a2, bb2 = snd(t + 0.10, 0.5), snd(t - 0.65, 2.0)
    if len(a2) < 4000 or a2.std() < 50: print(f"  t0={t:7.2f} 무음(판정 불가=통과)"); continue
    c2 = np.correlate(bb2 - bb2.mean(), a2 - a2.mean(), "valid"); i2 = int(np.argmax(c2))
    off = i2 / 16000 - 0.75
    verdict = "판정불가" if i2 in (0, len(c2) - 1) else ("★실패" if 0.08 < abs(off) <= 0.5 else "통과")
    print(f"  t0={t:7.2f} 게이트값 {off:+.3f}s {verdict}")
