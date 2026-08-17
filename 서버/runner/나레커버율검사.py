#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""나레 발성 중인데 나레 자막이 없는 구간 전수 측정 (진단용 — 수리는 승인 후).

  축 = voice.json blocks[].speech(실측 발성 덩어리, 블록 안 초) → 타임라인 시각으로 옮긴 구간.
  덮개 = timeline.json 의 나레 큐(lane=nar). 겹치지 않는 시간이 「소리는 나는데 자막이 없는」 구간이다.
"""
import io, json, sys, collections

W = "C:/Users/user/Desktop/youstudio_work/fulltime"
tl = json.load(io.open(W + "/subtitle/timeline.json", encoding="utf-8"))
vo = json.load(io.open(W + "/voice/voice.json", encoding="utf-8"))
vmap = {b["n"]: b for b in vo["blocks"]}
nars = sorted(tl["narration"], key=lambda n: n["t0"])
cues = collections.defaultdict(list)
for c in tl["cues"]:
    if c["lane"] == "nar":
        cues[c["ref"]].append(c)
for k in cues:
    cues[k].sort(key=lambda c: c["t0"])

CASE = float(sys.argv[1]) if len(sys.argv) > 1 else 144.1

def runs_of(n):
    b = vmap[n["n"]]
    sp = b.get("speech") or [[0, b["dur_s"]]]
    return [(n["t0"] + u, n["t0"] + v) for u, v in sp]

# ── ① 사례 추적 ─────────────────────────────────────────────────────────────
print(f"── 사례 {CASE}s ──")
for n in nars:
    if not (n["t0"] - 1.0 <= CASE <= n["t1"] + 1.0):
        continue
    b = vmap[n["n"]]
    print(f"나레 n{n['n']} 타임라인 {n['t0']}~{n['t1']} (wav {b['dur_s']}s) 「{n['text']}」")
    print(f"  집필 줄: {b.get('lines')}")
    print("  발성 덩어리(타임라인 시각):")
    for u, v in runs_of(n):
        print(f"    {u:8.3f} ~ {v:8.3f}  ({v-u:.3f}s)" + ("   ← 사례 시각 포함" if u <= CASE <= v else ""))
    print("  줄 큐:")
    for c in cues[f"n{n['n']}"]:
        print(f"    {c['t0']:8.3f} ~ {c['t1']:8.3f}  ({c['t1']-c['t0']:.3f}s) 「{c['text']}」" + ("   ← 사례 시각 포함" if c["t0"] <= CASE <= c["t1"] else ""))
    # 이 블록 안에서 소리는 있는데 자막이 없는 구간
    holes = []
    for u, v in runs_of(n):
        cur = u
        for c in sorted(cues[f"n{n['n']}"], key=lambda c: c["t0"]):
            a, b2 = max(cur, c["t0"]), min(v, c["t1"])
            if b2 > a:
                if a - cur > 0.001:
                    holes.append((cur, a))
                cur = max(cur, c["t1"])
        if v - cur > 0.001:
            holes.append((cur, v))
    print("  구멍(소리 있고 자막 없음):", [f"{a:.3f}~{b2:.3f}({b2-a:.3f}s)" for a, b2 in holes if b2 - a > 0.05] or "없음")
    print()

# ── ② 전수 ──────────────────────────────────────────────────────────────────
tot_speech = 0.0
tot_cov = 0.0
holes = []
for n in nars:
    cs = cues[f"n{n['n']}"]
    for u, v in runs_of(n):
        tot_speech += v - u
        cur = u
        for c in cs:
            a, b2 = max(cur, c["t0"]), min(v, c["t1"])
            if b2 > a:
                if a - cur > 0.001:
                    holes.append((cur, a, n["n"]))
                tot_cov += b2 - a
                cur = max(cur, c["t1"])
        if v - cur > 0.001:
            holes.append((cur, v, n["n"]))
big = [h for h in holes if h[1] - h[0] >= 0.3]
print("── 전수 ──")
print(f"나레 발성 총 {tot_speech:.3f}s · 자막이 덮은 {tot_cov:.3f}s → 나레 커버율 {tot_cov/tot_speech:.3f}")
print(f"구멍 총 {sum(b-a for a,b,_ in holes):.3f}s · 0.3s 이상 {len(big)}곳 (전체 구멍 {len(holes)}곳)")
for a, b2, n in sorted(big, key=lambda h: -(h[1] - h[0])):
    print(f"   n{n:<3} {a:8.3f} ~ {b2:8.3f}  {b2-a:.3f}s")
if len(sys.argv) > 2:
    json.dump({"speech_s": tot_speech, "covered_s": tot_cov, "coverage": tot_cov / tot_speech,
               "holes": [{"n": n, "t0": round(a, 3), "t1": round(b2, 3), "len": round(b2 - a, 3)} for a, b2, n in holes]},
              io.open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
