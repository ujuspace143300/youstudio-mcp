#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan점검.py <슬러그> — plan 결과를 사람이 고칠 자리 중심으로 한 화면에 보인다.

  2026-09-26~27 싱글285~280 실측: plan 은 편마다 한 번 이상 틀렸다 — 결말(원본 마지막 펀치) 누락 5편,
  대사 한가운데 절단, 훅·본문 겹침, Climax 60% 미만, 나레 3초 초과. make ① 검사는 반려만 알려 주고
  «원본 끝에 무슨 대사가 있는지» 는 안 보여 줘서 사람이 전사를 따로 뒤졌다. 이 도구가 한 번에 보인다:
   · 조각 표(역할·원본 구간·길이·완성본 시작초) · 합계 · Climax 자리(%) · 나레 글자 수
   · 원본 끝 20초의 전사 줄(결말 후보) — 마지막 조각이 그 줄들을 담는지 ✓/✗
   · 조각 사이에서 빠진 긴 대사 구간(8초 이상)
"""
import json, os, re, sys

slug = sys.argv[1]
W = os.path.expanduser("~/Desktop/스케치코미디")
p = json.load(open(f"{W}/projects/{slug}.json", encoding="utf-8"))
L = [(int(a) * 3600 + int(b) * 60 + float(c), int(d) * 3600 + int(e) * 60 + float(f), x.strip())
     for a, b, c, d, e, f, x in re.findall(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)\n(.+)",
                                         open(f"{W}/work/{p['source']['id']}.ko.vtt", encoding="utf-8").read())]
segs = [s for s in p["segments"] if s.get("keep", True)]
tot = sum(s["t1"] - s["t0"] for s in segs)
at, c_at = 0.0, None
print(f"== {slug} · 원제 «{(p.get('credit') or {}).get('title', '')}» · 합계 {tot:.1f}초")
for s in segs:
    if s["phase"] == 4 and c_at is None:
        c_at = at
    nar = s.get("narration") or ""
    print(f"  P{s['phase']} {s['t0']:6.1f}~{s['t1']:6.1f} ({s['t1']-s['t0']:4.1f}s) @{at:5.1f}"
          f"{'  [나레 ' + str(len(nar)) + '자] ' + nar if nar else ''}  {s.get('what', '')[:40]}")
    at += s["t1"] - s["t0"]
print(f"  Climax {c_at / tot * 100:.0f}%" if c_at is not None else "  ★Climax 없음")
끝 = max((e for _t, e, _x in L), default=0)
last = segs[-1] if segs else None
print(f"  원본 끝 20초 전사 (마지막 조각 {last['t0']:.1f}~{last['t1']:.1f}):")
for t, e, x in L:
    if t >= 끝 - 20:
        담김 = any(s["t0"] - 0.3 <= t and e <= s["t1"] + 0.3 for s in segs)
        print(f"    {'✓' if 담김 else '✗'} {t:6.1f}~{e:6.1f} {x[:34]}")
빈 = []
원순 = sorted(segs, key=lambda s: s["t0"])
for a, b in zip(원순, 원순[1:]):
    if b["t0"] - a["t1"] >= 8:
        줄 = [x for t, e, x in L if a["t1"] <= t < b["t0"]]
        if 줄:
            빈.append((a["t1"], b["t0"], len(줄), 줄[0][:16], 줄[-1][:16]))
for a, b, n, f_, l_ in 빈:
    print(f"  (뺀 구간 {a:.1f}~{b:.1f} · {n}줄 · «{f_}» … «{l_}»)")
cands = [t if isinstance(t, list) else [t] for t in p.get("title_candidates", [])]
print("  제목 후보:", " | ".join(" / ".join(t) for t in cands))
