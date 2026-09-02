#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화자재판정.py — 이미 만든 timeline_sk.json 의 대사 색만 다시 판정해 갱신한다.

  2026-09-02 사장님 지시(같은 화자 색 바뀜)로 만든 수리 도구.
  준비_prproj_sk.화자판정(3회 표결판)을 그대로 쓰고, 이전 색과의 차이를 표로 보고한다.
  갱신 뒤에는 조립_prproj_sk.py 를 다시 돌려 prproj 를 재조립해야 반영된다.

사용: python 화자재판정.py <timeline_sk.json> --cut <cut.mp4> [--화자수 3] [--logline "..."]
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from 준비_prproj_sk import 화자판정  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("--cut", required=True)
    ap.add_argument("--화자수", type=int, default=None)
    ap.add_argument("--logline", default="")
    a = ap.parse_args()

    tl = json.load(open(a.timeline, encoding="utf-8"))
    dlg = [c for c in tl["cues"] if c.get("lane") == "dlg"]
    assert dlg, "대사 큐가 없다"

    who, 불안정, cast = 화자판정([c["text"] for c in dlg], a.cut, a.logline,
                                times=[c["t0"] for c in dlg], 예상화자수=a.화자수)
    assert any(w for w in who), "판정 전부 실패 — 색을 바꾸지 않는다"

    팔레트 = {"효과": (245, 244, 37), "2": (135, 206, 250), "3": (255, 182, 193),
              "4": (144, 238, 144), "5": (255, 200, 150)}
    from collections import Counter
    말수 = Counter(w for w in who if w and w != "효과")
    순위 = [w for w, _n in 말수.most_common()]
    재배 = {w: str(i + 1) for i, w in enumerate(순위)}

    바뀜 = 0
    for i, (c, w) in enumerate(zip(dlg, who)):
        key = "효과" if w == "효과" else (재배.get(w) if w else None)
        새색 = list(팔레트[key]) if key in 팔레트 else None
        if 새색 != c.get("color"):
            바뀜 += 1
            표시 = "★불안정" if i in 불안정 else ""
            print(f"  [{c['t0']:6.1f}초] {c.get('color')} → {새색}  {c['text'][:24]} {표시}")
        c["color"] = 새색

    print(f"\n화자 {len(말수)}명 · 색 바뀐 줄 {바뀜}/{len(dlg)}")
    for 원, 겉 in cast.items():
        print(f"  화자{재배.get(원, 원)}: {겉}")
    if 불안정:
        print(f"★화자 불안정 {len(불안정)}줄 — 눈으로 확인 필요:")
        for i in 불안정:
            print(f"   [{dlg[i]['t0']:.1f}초] {dlg[i]['text'][:30]}")
    if a.화자수 and len(말수) != a.화자수:
        print(f"★화자 수 불일치 — 판정 {len(말수)}명 vs 지정 {a.화자수}명")

    json.dump(tl, open(a.timeline, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("저장:", a.timeline)


if __name__ == "__main__":
    main()
