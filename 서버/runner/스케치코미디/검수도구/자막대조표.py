#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자막대조표.py <슬러그> — 완성본 자막 줄마다 «원본 그 시각의 하단 구운 자막 띠» 를 잘라 우리 문구와 나란히 놓는다.
완성본 시각 → 원본 시각은 segments 누적으로 환산한다. 결과: 작업폴더 work/<슬러그>/대조/표_NN.jpg (한 장 12줄).

★왜 있나 (2026-09-21 띱 7차): 완성본 재전사는 편당 1~15줄을 틀리는데(«볶음밥도 안 먹고!»→«진짜 다 먹어»)
  체인 게이트는 글자 수·시각만 본다. 원본에 구워진 자막이 정답이다 — 이 표를 보고 문구교정 핀을 박는다."""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
# ffmpeg·ffprobe 스레드 상한은 s2pipe/ff.py 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
import os as _ff_os, sys as _ff_sys  # noqa: E402
_ff_d = _ff_os.path.dirname(_ff_os.path.abspath(__file__))
_ff_d = _ff_os.path.dirname(_ff_d)
if _ff_d not in _ff_sys.path:
    _ff_sys.path.append(_ff_d)
from s2pipe import ff  # noqa: E402

slug = sys.argv[1]
proj = json.load(open(os.path.expanduser(f"~/Desktop/스케치코미디/projects/{slug}.json"), encoding="utf-8"))
src = os.path.expanduser(f"~/Desktop/스케치코미디/work/{slug}.mp4")
out = os.path.expanduser(f"~/Desktop/스케치코미디/work/{slug}/대조"); os.makedirs(out, exist_ok=True)
for f in os.listdir(out): os.remove(os.path.join(out, f))

segs, at = [], 0.0
for s in proj["segments"]:
    segs.append((at, at + s["t1"] - s["t0"], s["t0"])); at += s["t1"] - s["t0"]

def to_src(t):
    for a, b, t0 in segs:
        if a <= t < b: return t0 + (t - a)
    return None

font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 26)
rows = []
for x in proj["subs"]:
    if x.get("kind") == "narr": continue
    mid = (x["t"] + x.get("t1", x["t"] + 1.0)) / 2
    st = to_src(mid)
    if st is None: continue
    png = os.path.join(out, "_c.png")
    subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.2f}", "-i", src, "-frames:v", "1",
                    "-vf", "crop=iw:ih*0.2:0:ih*0.78,scale=600:-1", png]), check=True)
    band = Image.open(png).convert("RGB")
    row = Image.new("RGB", (1100, band.height), (250, 250, 250))
    row.paste(band, (500, 0))
    ImageDraw.Draw(row).text((8, band.height // 2 - 16), f"{x['t']:5.1f} {x['text']}", fill=(0, 0, 0), font=font)
    rows.append(row)
for k in range(0, len(rows), 12):
    part = rows[k:k + 12]
    sheet = Image.new("RGB", (1100, sum(r.height + 2 for r in part)), (180, 180, 180))
    y = 0
    for r in part: sheet.paste(r, (0, y)); y += r.height + 2
    sheet.save(os.path.join(out, f"표_{k//12+1:02d}.jpg"), quality=80)
if os.path.exists(os.path.join(out, "_c.png")): os.remove(os.path.join(out, "_c.png"))
print(f"{slug}: 자막 {len(rows)}줄 → {out} 표 {-(-len(rows)//12)}장")
