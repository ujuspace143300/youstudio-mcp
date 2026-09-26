#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계획고침.py <슬러그> <고침.json> — projects/<슬러그>.json 의 계획 값(조각·제목·훅·결말)을 고침 파일대로 바꾼다.
고침 파일의 키만 덮는다. 조각은 (phase, t0) 로 정렬하고 _est_sec 을 다시 센다. 끝나면 되읽어 표로 찍는다."""
import json, sys, os

slug, patch_path = sys.argv[1], sys.argv[2]
pj = os.path.expanduser(f"~/Desktop/스케치코미디/projects/{slug}.json")
proj = json.load(open(pj, encoding="utf-8"))

# ★체인이 도는 중이면 고치지 않는다 (2026-09-26 — 도는 체인이 옛 내용을 덮어써 고친 값이 사라진 사건)
def _체인중인가(pj):
    import os as _o
    lk = pj + ".체인중"
    if _o.path.exists(lk):
        try:
            _o.kill(int(open(lk).read().strip()), 0)
            return True
        except (ValueError, OSError):
            return False
    return False
if _체인중인가(pj):
    sys.exit(f"★{os.path.basename(pj)} 체인이 도는 중이다 — 끝난 뒤 고친다(고쳐도 체인이 덮어쓴다)")
patch = json.load(open(patch_path, encoding="utf-8"))
if not os.path.exists(pj + ".plan원본"):
    json.dump(proj, open(pj + ".plan원본", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
for k, v in patch.items():
    proj[k] = v
proj["segments"].sort(key=lambda s: (s.get("phase", 9), s["t0"]))
proj["_est_sec"] = round(sum(s["t1"] - s["t0"] for s in proj["segments"]), 1)
json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

back = json.load(open(pj, encoding="utf-8"))
print(back["title"], "|", back.get("_제목_출처", ""))
for s in back["segments"]:
    print(f"  P{s['phase']} {s['t0']:7.1f}~{s['t1']:7.1f} ({s['t1']-s['t0']:4.1f}s) punch {s['punch']:2d} "
          f"{s['what'][:40]}" + (f"  [나레] {s['narration']}" if s.get("narration") else ""))
print("합계", back["_est_sec"], "초 · 결말:", back.get("ending"))
