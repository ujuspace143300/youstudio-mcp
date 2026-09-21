#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초안자막쪼갬.py <슬러그> — plan 이 낸 초안 자막(subs) 중 14자 넘는 줄을 띄어쓰기 자리에서 둘로 가른다.
초안은 굽기 뒤 s2pipe.sync 가 ASR 단어 실측으로 통째로 다시 짜므로(채널 카드 「대사 자막 규칙」) 여기서는 검사 통과용 분할만 한다."""
import json, sys, os

slug = sys.argv[1]
pj = os.path.expanduser(f"~/Desktop/스케치코미디/projects/{slug}.json")
proj = json.load(open(pj, encoding="utf-8"))
out, n = [], 0
subs = proj.get("subs", [])
for i, x in enumerate(subs):
    txt = x["text"]
    if len(txt) <= 14 or " " not in txt:
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
json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
left = [x["text"] for x in json.load(open(pj, encoding="utf-8"))["subs"] if len(x["text"]) > 14]
print(f"{slug}: {n}줄 가름 · 아직 14자 넘는 줄 {len(left)}개 {left}")
