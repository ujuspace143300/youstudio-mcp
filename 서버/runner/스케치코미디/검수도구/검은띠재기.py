#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검은띠재기.py <완성본.mp4> — 영상 상자(y540~1448) 윗변·아랫변에 «순흑 줄»(줄 최대 밝기<20)이 몇 줄 붙어 있는지 1초마다 잰다.
8줄 넘는 시각만 찍는다. 어두운 장면 오탐을 줄이려고 상자 한가운데가 밝은(평균>30) 프레임만 센다."""
import subprocess, sys
mp4 = sys.argv[1]
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                           capture_output=True).stdout)
W, Y0, H = 900, 540, 908
hits = []
t = 0.5
while t < dur - 0.3:
    b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", mp4, "-frames:v", "1",
                        "-vf", f"crop={W}:{H}:90:{Y0},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    if len(b) == W * H:
        rows = [max(b[r * W:(r + 1) * W]) for r in range(H)]
        mid = sum(b[(H // 2) * W:(H // 2 + 1) * W]) / W
        top = next((i for i, x in enumerate(rows) if x >= 20), H)
        bot = next((i for i, x in enumerate(reversed(rows)) if x >= 20), H)
        if mid > 30 and (top > 8 or bot > 8):
            hits.append((t, top, bot))
    t += 1.0
print(f"{mp4.split('/')[-1]}: 길이 {dur:.1f}s · 검은 띠 의심 {len(hits)}곳")
for t, a, c in hits:
    print(f"  {t:5.1f}s  위 {a}px · 아래 {c}px")
