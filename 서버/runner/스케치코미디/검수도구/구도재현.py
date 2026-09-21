#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구도재현.py <슬러그> <조각번호(0부터)> — 굽기와 같은 입력으로 framing.plan_beats 를 돌려 비트별 crop·확대·얼굴을 찍는다(읽기 전용)."""
import json, os, sys, tempfile
RUN = os.path.expanduser("~/Desktop/youstudio-mcp/서버/runner/스케치코미디")
sys.path.insert(0, RUN); os.chdir(RUN)
os.environ.setdefault("S2_CONFIG", os.path.expanduser("~/Desktop/스케치코미디/config.json"))
from s2pipe import framing
from s2pipe.cfg import CFG
slug, k = sys.argv[1], int(sys.argv[2])
proj = json.load(open(os.path.expanduser(f"~/Desktop/스케치코미디/projects/{slug}.json"), encoding="utf-8"))
src = os.path.expanduser(f"~/Desktop/스케치코미디/work/{slug}.mp4")
b = CFG["layout"]["video_box"]
W, H = 1920, 1080
usable_h = int(sys.argv[3]) if len(sys.argv) > 3 else 930
work = tempfile.mkdtemp(prefix="_구도_")
seg = proj["segments"][k]
for a, e, vf, info in framing.plan_beats(src, seg, k, W, H, usable_h, b, work, (), None):
    bw, bh, x, y = info["crop"]
    print(f"{a:7.2f}~{e:7.2f} zoom {info['zoom']:.2f} face {info['face']!s:5} crop {bw}x{bh}@{x},{y}  (아랫변 {y+bh})")
