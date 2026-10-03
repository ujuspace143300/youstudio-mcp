#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초안자막쪼갬.py <슬러그> — plan 이 낸 초안 자막(subs) 중 14자 넘는 «대사» 줄을 띄어쓰기 자리에서 둘로 가른다.
초안은 굽기 뒤 s2pipe.sync 가 ASR 단어 실측으로 통째로 다시 짜므로(채널 카드 「대사 자막 규칙」) 여기서는 검사 통과용 분할만 한다.

★나레 줄(kind=narr)은 가르지 않는다 (2026-10-03 루키치165 — 줄 종류를 안 가리고 14자로 갈라 나레 줄이 둘이 됐고 손으로 지웠다.
  나레 자막은 노란 한 줄·최대 26자로 대사 14자 규칙과 다르다). 나레 줄은 조각(narration·조각 머리)에서 다시 만든다 —
  조각을 다시 짠 뒤 옛 자리에 남은 나레 줄 시각도 여기서 같이 맞는다(루키치204). 규칙은 s2pipe/화자색.py 나레줄()."""
import json, sys, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ.setdefault("S2_CONFIG", os.path.expanduser("~/Desktop/스케치코미디/config.json"))
from s2pipe import 화자색 as HS          # noqa: E402
from s2pipe.cfg import CFG              # noqa: E402

slug = sys.argv[1]
pj = os.path.expanduser(f"~/Desktop/스케치코미디/projects/{slug}.json")
proj = json.load(open(pj, encoding="utf-8"))
out, n = [], 0
subs = proj.get("subs", [])
for i, x in enumerate(subs):
    txt = x["text"]
    if x.get("kind") == "narr" or len(txt) <= 14 or " " not in txt:
        out.append(x); continue
    cuts = [k for k, c in enumerate(txt) if c == " "]
    k = min(cuts, key=lambda k: abs(k - len(txt) / 2))
    a, b = txt[:k], txt[k + 1:]
    nxt = subs[i + 1]["t"] if i + 1 < len(subs) else x["t"] + 2.0
    span = min(nxt - x["t"], 4.0)
    y = dict(x); y["text"] = a
    z = dict(x); z["text"] = b; z["t"] = round(x["t"] + span * len(a) / (len(a) + len(b)), 2)
    out += [y, z]; n += 1
proj["subs"] = out
바뀜 = HS.나레줄맞춤(proj, os.path.join(HERE, CFG["paths"]["work"], slug))
json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
되읽음 = json.load(open(pj, encoding="utf-8"))
left = [x["text"] for x in 되읽음["subs"] if x.get("kind") != "narr" and len(x["text"]) > 14]
print(f"{slug}: 대사 {n}줄 가름 · 아직 14자 넘는 대사 줄 {len(left)}개 {left}")
for m in 바뀜:
    print(f"  나레 줄을 조각에서 다시 맞춤 — {m}")
남은 = HS.나레줄검사(되읽음, os.path.join(HERE, CFG["paths"]["work"], slug))
print("  나레 줄 = 나레 조각 " + ("OK" if not 남은 else f"★어긋남 {남은}"))
