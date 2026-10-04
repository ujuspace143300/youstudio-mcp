#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""컷소리재기.py <슬러그> <컷번호(1부터)> — cut.mp4 의 그 컷 안 여러 지점 소리를 원본과 상관으로 맞춰 어긋남(초)을 잰다.
컷 시작은 build 로그(work/<슬러그>/build_log.json)가 없으면 계획 길이 누적으로 잡는다. 읽기 전용."""
import json, os, subprocess, sys
import numpy as np
# ffmpeg·ffprobe 스레드 상한은 s2pipe/ff.py 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
import os as _ff_os, sys as _ff_sys  # noqa: E402
_ff_d = _ff_os.path.dirname(_ff_os.path.abspath(__file__))
_ff_d = _ff_os.path.dirname(_ff_d)
if _ff_d not in _ff_sys.path:
    _ff_sys.path.append(_ff_d)
from s2pipe import ff  # noqa: E402
slug, k = sys.argv[1], int(sys.argv[2])
W = os.path.expanduser("~/Desktop/스케치코미디/work")
proj = json.load(open(os.path.expanduser(f"~/Desktop/스케치코미디/projects/{slug}.json"), encoding="utf-8"))
cut = os.path.join(W, slug, "cut.mp4"); src = os.path.join(W, f"{slug}.mp4")
fps = proj["source"]["fps"]
at = 0.0
for i, s in enumerate(proj["segments"], 1):
    d = round((s["t1"] - s["t0"]) * fps) / fps
    if i == k: break
    at += d
def snd(path, t0, d):
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{max(t0,0):.3f}", "-i", path, "-t", f"{d:.3f}",
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]), capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(float)
print(f"{slug} 컷{k}: 완성본 {at:.3f}s ← 원본 {s['t0']}s (길이 {d:.2f}s)")
for off in (0.10, 0.6, 1.2, 2.5, 4.0, d * 0.5, d - 1.5):
    a = snd(cut, at + off, 0.8); b = snd(src, s["t0"] + off - 1.0, 2.8)
    if len(a) < 6000 or a.std() < 50: print(f"  +{off:4.1f}s 무음"); continue
    c = np.correlate(b - b.mean(), a - a.mean(), "valid"); i = int(np.argmax(c))
    peak = c[i] / (np.linalg.norm(a - a.mean()) * np.linalg.norm(b[i:i + len(a)] - b[i:i + len(a)].mean()) + 1e-9)
    print(f"  +{off:4.1f}s 어긋남 {i/16000-1.0:+.3f}s (상관 {peak:.2f})")
