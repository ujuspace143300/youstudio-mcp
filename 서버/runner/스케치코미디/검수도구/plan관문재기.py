#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan관문재기.py <시리즈접두> [번호…] — plan 초안과 사람이 고친 최종 조각을 plan 관문(s2pipe/plan관문.py)에 같이 넣어 잰다.

  초안 = projects/<슬러그>.json.plan원본(에이전트가 고치기 전 백업) · 없으면 배치로그/<슬러그>_2plan.txt 의 조각 표를 읽는다.
  최종 = projects/<슬러그>.json(납품본 — 읽기만).  파악 답 = 배치로그/agy파악_<시리즈>/<슬러그>.md (싱글벙글은 agy파악/).
  잡아야 할 것: 초안에서 반려가 나는가(결함 검출) · 최종은 통과하는가(가짜 반려 0).
  예) S2_CONFIG=~/Desktop/스케치코미디/config_누룽지독.json python 검수도구/plan관문재기.py 점심이네
  2026-09-29 점심이네 64편 배치 뒤 plan 관문 수리의 재실측 도구.
"""
import json, os, re, sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)
from s2pipe import plan관문 as G   # noqa: E402
from s2pipe import build           # noqa: E402
from s2pipe import plan            # noqa: E402

W = os.path.expanduser("~/Desktop/스케치코미디")
접두 = sys.argv[1]
번호 = [int(x) for x in sys.argv[2:] if x.isdigit()]
행표시 = "--파악json" in sys.argv
파악폴더 = os.path.join(W, "배치로그", "agy파악" if 접두 == "싱글" else f"agy파악_{접두}")
카드캐시 = os.path.join(W, "배치로그", f"_plan관문_카드_{접두}.json")
캐시 = json.load(open(카드캐시, encoding="utf-8")) if os.path.exists(카드캐시) else {}


def 초안(slug, 최종):
    p = os.path.join(W, "projects", f"{slug}.json.plan원본")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")), "plan원본"
    t = os.path.join(W, "배치로그", f"{slug}_2plan.txt")
    if not os.path.exists(t):
        return None, "없음"
    segs = []
    for 줄 in open(t, encoding="utf-8"):
        m = re.match(r"^\s+P(\d)\s+\S+\s+[\d.]+초\s+원본\s+([\d.]+)~\s*([\d.]+)\s+punch\s+(\d+)\s+(.*)$", 줄)
        if m:
            segs.append({"phase": int(m[1]), "t0": float(m[2]), "t1": float(m[3]), "punch": int(m[4]),
                         "what": m[5], "keep": True, "narration": ""})
            continue
        m = re.match(r"^\s+나레: (.*)$", 줄)
        if m and segs:
            segs[-1]["narration"] = m[1].strip()
    if not segs:
        return None, "없음"
    d = {k: 최종[k] for k in ("slug", "source", "title", "title_candidates", "credit", "hashtag") if k in 최종}
    d.update({"segments": segs, "hooks": [], "subs": []})
    return d, "2plan로그"


줄들 = []
n목록 = 번호 or sorted(int(f[len(접두):-5]) for f in os.listdir(os.path.join(W, "projects"))
                      if f.startswith(접두) and f.endswith(".json") and f[len(접두):-5].isdigit())
for n in n목록:
    slug = f"{접두}{n}"
    fp = os.path.join(W, "projects", f"{slug}.json")
    최종 = json.load(open(fp, encoding="utf-8"))
    sid = 최종["source"]["id"]
    큐 = G.큐읽기(os.path.join(W, "work", f"{sid}.ko.vtt"))
    # --파악json <폴더>: plan 이 쓰는 JSON 파악 답(검수도구/파악받기.py)이 있으면 그것(셋업·결말까지 잰다), 없으면 배치 .md
    jp = os.path.join(sys.argv[sys.argv.index("--파악json") + 1], f"{slug}.json") if "--파악json" in sys.argv else ""
    파악 = plan.파악정리(json.load(open(jp, encoding="utf-8"))) if jp and os.path.exists(jp) \
        else G.파악읽기(os.path.join(파악폴더, f"{slug}.md"))
    if sid not in 캐시:
        try:
            캐시[sid] = build.엔드카드시작(os.path.join(W, "work", f"{sid}.mp4"), float(최종["source"]["dur"]))
        except Exception as e:                           # noqa: BLE001
            캐시[sid] = None
        json.dump(캐시, open(카드캐시, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    카드 = 캐시[sid]
    카드줄 = G.카드줄읽기(os.path.join(W, "work", f"{sid}.mp4"), 만들기=False)   # ⑦ 설명시각 시계(2026-10-03) — 캐시만 읽는다
    초, 출처 = 초안(slug, 최종)
    행 = {"slug": slug, "초안출처": 출처, "카드": 카드, "파악로고": (파악 or {}).get("로고"), "파악": "json" if jp and os.path.exists(jp) else "md",
         "꼭남길수": len((파악 or {}).get("꼭남길", []))}
    for 이름, pj in (("초안", 초), ("최종", 최종)):
        if pj is None:
            행[이름] = None
            continue
        bad, warn, 값 = G.검사(pj, 큐, 파악, 카드, fp, 카드줄=카드줄)
        행[이름] = {"반려": [[d, g] for d, g in bad], "값": 값}
    줄들.append(행)
    f = lambda x: "-" if x is None else ",".join(sorted({d for d, _g in x["반려"]})) or "통과"
    print(f"{slug:10s} 초안({출처:7s}) {f(행['초안']):40s} | 최종 {f(행['최종'])}", flush=True)

out = os.path.join(W, "배치로그", f"_plan관문재기_{접두}{'_파악json' if 행표시 else ''}.json")
json.dump(줄들, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("저장:", out)
