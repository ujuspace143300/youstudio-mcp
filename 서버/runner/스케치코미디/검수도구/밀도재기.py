# -*- coding: utf-8 -*-
"""밀도 관문(s2pipe/밀도.계산)을 스위치 끔·켬으로 나란히 잰다 — 돈 안 듦, 파일을 고치지 않는다.

    python 검수도구/밀도재기.py                 projects/ 전부: 스위치 끔 vs 켬(훅·광고·도입 15초) 값이 바뀐 것만
    python 검수도구/밀도재기.py 점심이네28 …     그 편만 자세히(뺀 것·도입점프 인정 여부)
    python 검수도구/밀도재기.py --도입 20        도입점프 한도를 바꿔 잰다
    python 검수도구/밀도재기.py --가짜시험       원본 전체에 조각을 흩뿌린 합성 안(편마다 20벌)을 «거짓 선언» 까지 붙여
                                                  새 관문이 통과시키는지 — 통과한 것이 «앞 블록만 빼면 예전 관문 통과» 인지도 센다

2026-09-29 점심이네 배치(먼 도입 셋업을 밀도 관문이 막음) 수리 때 만든 재기 도구. 설정은 S2_CONFIG.
"""
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG          # noqa: E402
from s2pipe import 밀도             # noqa: E402

args = [a for a in sys.argv[1:]]
L = 15.0
if "--도입" in args:
    i = args.index("--도입")
    L = float(args[i + 1])
    del args[i:i + 2]
가짜 = "--가짜시험" in args
names = [a for a in args if not a.startswith("--")]

E_OFF = dict(CFG["edit"], 훅_밀도제외=False, 광고_밀도제외=False, 도입점프_최대_s=0)
E_ON = dict(CFG["edit"], 훅_밀도제외=True, 광고_밀도제외=True, 도입점프_최대_s=L)
lo = CFG["edit"]["density"][0]
P = CFG["paths"]["projects"]


def 조각(p):
    segs = [s for s in p.get("segments", []) if s.get("keep", True)]
    return segs if segs and any("phase" in s for s in segs) else None


def 판(r):
    return "통과" if r["dens"] >= lo and not r["반려"] else "반려"


if 가짜:
    random.seed(20260929)
    n = 0
    거짓통과 = []          # 거짓 선언으로 통과한 안마다 «앞 블록 빼면 예전 관문 통과» 여부
    선언없이 = 0
    for f in sorted(glob.glob(os.path.join(P, "*.json"))):
        try:
            dur = float(json.load(open(f, encoding="utf-8"))["source"]["dur"])
        except Exception:
            continue
        if dur < 120:
            continue
        for _ in range(20):
            w = (dur - 60) / 5
            st = [k * w + random.uniform(0, max(0.0, w - 15)) for k in range(5)]
            body = [dict(t0=a, t1=a + random.uniform(9, 14), phase=ph, keep=True) for a, ph in zip(st, [2, 3, 3, 4, 4])]
            h = random.choice(body[1:])
            hook = dict(t0=h["t0"], t1=h["t0"] + 3, phase=1, keep=True)
            h["t0"] += 3.05
            segs = [hook] + body + [dict(t0=dur - 12, t1=dur - 4, phase=5, keep=True)]
            if 밀도.계산(segs, E_OFF)["dens"] >= lo:
                continue
            n += 1
            q = {"source": {"dur": dur}, "도입점프": {"근거": "시험 — 거짓 선언", "짝": [dur - 8]}}
            r = 밀도.계산(segs, E_ON, q)
            if 판(r) == "통과":
                front = [s for s in body if any(f"{s['t0']:.1f}~" in x and "도입 점프" in x for x in r["뺀것"])]
                rest = [s for s in segs if s not in front]
                거짓통과.append(밀도.계산(rest, E_OFF)["dens"] >= lo)
            if 판(밀도.계산(segs, E_ON, {"source": {"dur": dur}})) == "통과":
                선언없이 += 1
    print(f"합성 흩뿌림 안(예전 반려) {n}개 · 선언 없이 통과 {선언없이}개 · 거짓 선언으로 통과 {len(거짓통과)}개"
          f"(그중 앞 블록만 빼면 예전 관문 통과 {sum(거짓통과)}개)")
    sys.exit(0)

files = [os.path.join(P, x) if os.path.exists(os.path.join(P, x)) else os.path.join(P, f"{x}.json") for x in names] or \
    sorted(glob.glob(os.path.join(P, "*")))
바뀜 = 뒤집힘 = 0
for f in files:
    try:
        p = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    segs = 조각(p) if isinstance(p, dict) else None
    if not segs:
        continue
    a = 밀도.계산(segs, E_OFF, p)
    b = 밀도.계산(segs, E_ON, p)
    if names or abs(a["dens"] - b["dens"]) > 1e-9 or b["반려"]:
        바뀜 += 1
        뒤집힘 += 판(a) != 판(b)
        print(f"{os.path.basename(f):28} 끔 {a['dens']*100:5.1f}% {판(a)} → 켬 {b['dens']*100:5.1f}% {판(b)}")
        if names:
            for x in b["뺀것"] + b["주의"] + b["반려"]:
                print(f"      {x}")
if not names:
    print(f"\n값이 바뀐 파일 {바뀜}개 · 통과↔반려 뒤집힘 {뒤집힘}개 (도입점프 {L:.0f}초 · 파일에 적힌 선언만 씀)")
