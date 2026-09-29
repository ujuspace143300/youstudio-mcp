#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파악받기.py <슬러그>… [--out 폴더] — plan 이 쓰는 JSON 파악 답(s2pipe.plan.파악질문)을 편마다 agy 로 받는다(동시 5).
  plan 을 다시 돌리지 않고 파악 답만 받아 plan 관문(셋업·결말 대사)을 재 보려는 도구 — 2026-09-29 plan 관문 재실측.
  --out 을 안 주면 work/<슬러그>.파악.json(plan 이 캐시로 쓰는 자리)에 쓴다. 이미 있으면 건너뛴다.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)
from s2pipe import plan, gem       # noqa: E402
from s2pipe.cfg import CFG         # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
if out:
    args = [a for a in args if a != out]
    os.makedirs(out, exist_ok=True)
work, pdir = CFG["paths"]["work"], CFG["paths"]["projects"]


def 하나(slug):
    p = json.load(open(os.path.join(pdir, f"{slug}.json"), encoding="utf-8"))
    sid = p["source"]["id"]
    dst = os.path.join(out, f"{slug}.json") if out else os.path.join(work, f"{slug}.파악.json")
    if os.path.exists(dst):
        return slug, "있음", 0
    t0 = time.time()
    mp4 = gem.shrink_for_inline(os.path.join(work, f"{sid}.mp4"))
    try:
        j = json.loads(plan._agy(plan._본문(mp4, plan.파악질문(float(p["source"]["dur"])), plan.파악SCHEMA), limit_min=10))
    except BaseException as e:                           # noqa: BLE001 — 판정멈춤(SystemExit)도 편 하나의 실패로
        return slug, f"실패 {str(e)[:120]}", time.time() - t0
    json.dump(j, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return slug, "받음", time.time() - t0


with ThreadPoolExecutor(max_workers=5) as ex:
    for slug, 결과, sec in ex.map(하나, args):
        print(f"{slug}: {결과} ({sec:.0f}초)", flush=True)
