#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전사보기.py <슬러그> <시작초> [끝초] — 원본 전사(vtt)의 그 구간을 「시작~끝 글」 로 찍는다. 쉼이 2초 넘으면 빈 줄."""
import re, sys, os
slug, a0 = sys.argv[1], float(sys.argv[2])
b0 = float(sys.argv[3]) if len(sys.argv) > 3 else 1e9
t = open(os.path.expanduser(f"~/Desktop/스케치코미디/work/{slug}.ko.vtt"), encoding="utf-8").read()
prev = None
for m in re.finditer(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)\n(.*)", t):
    a = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]); b = int(m[4]) * 3600 + int(m[5]) * 60 + float(m[6])
    if a < a0 or a > b0: continue
    if prev is not None and a - prev > 2: print(f"        … 쉼 {a-prev:.1f}s")
    print(f"{a:6.1f}~{b:6.1f} {m[7]}"); prev = b
