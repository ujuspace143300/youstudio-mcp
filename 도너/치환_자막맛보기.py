#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도너/치환_자막맛보기.py — 계단 3-d 첫 사다리: 자막 6개만 텍스트를 갈아끼운다.

  입력 = 3-c 산출 `_치환_나레.prproj`. 도너 V2(대사) 3개 · V3(나레, 본명조) 3개를 골라
  각각 **견본과 같은 길이 / 더 짧게 / 더 길게** 우리 자막 문구로 바꾼다(블롭 tail relocation).
  바꾸는 것: Source Text 블롭의 런 텍스트 + BinaryHash · VFC InstanceName · SubClip Name.
  건드리지 않는 것: 폰트·크기·색·그림자(StyleTable)·Position·Start/End·나머지 자막 클립.
사용: python 도너/치환_자막맛보기.py → 도너/_치환_자막맛보기.prproj + .report.json + 자기검증
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from prproj_lib import (Doc, load, save, esc, rewire, set_child, child, track_items, verify,
                        parse_blob, blob_set_texts, param_blob, param_set_blob, split_runs, TPS)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))
DN = SPEC["조립"]["도너"]; T = DN["트랙_UID"]
in_path = os.path.join(ROOT, "도너", "_치환_나레.prproj")
out_path = os.path.join(ROOT, "도너", "_치환_자막맛보기.prproj")
tl = json.load(open("C:/Users/user/Desktop/youstudio_work/fulltime/subtitle/timeline.json", encoding="utf-8"))
dlg_cues = [c["text"] for c in tl["cues"] if c["lane"] == "dlg"]
nar_cues = [c["text"] for c in tl["cues"] if c["lane"] == "nar"]

doc = Doc(load(in_path))

def title_parts(item):
    """텍스트 클립 한 벌에서 (VFC id, Source Text 파라미터 id, SubClip id, 블롭 정보, Start/End 초)."""
    b = doc.get(item)
    ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1))
    vfc = int(re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', doc.get(ch))[0])
    sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
    ti = re.search(r"<TrackItem Version=\"4\">(.*?)</TrackItem>", b, re.S).group(1)
    t0 = int(child(ti, "Start") or 0) / TPS; t1 = int(child(ti, "End")) / TPS
    st = None
    for pr in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(vfc)):
        pb = doc.get(pr)
        if "<Name>Source Text</Name>" in pb:
            st = pr; info = parse_blob(param_blob(pb))
    return vfc, st, sc, info, t0, t1

def pick(track_uid, want_font=None, n=3):
    """트랙에서 앞에서부터 조건에 맞는 클립 n개 (시간순)."""
    items, _ = track_items(doc, track_uid)
    rows = []
    for it in items:
        vfc, st, sc, info, t0, t1 = title_parts(it)
        if want_font and info["fonts"] != [want_font]:
            continue
        rows.append({"item": it, "vfc": vfc, "st": st, "sc": sc, "info": info, "t0": t0, "t1": t1,
                     "old": "".join(r["text"] for r in info["runs"]), "runs": len(info["runs"])})
        if len(rows) == n: break
    return rows

def choose(cues, old_len, mode, used):
    """길이 조건에 맞는 우리 문구 고르기 — same(같은 자수) / short(더 짧게) / long(더 길게)."""
    pool = [c for c in cues if c not in used]
    if mode == "same":
        exact = [c for c in pool if len(c) == old_len]
        return exact[0] if exact else min(pool, key=lambda c: abs(len(c) - old_len))
    if mode == "short":
        cand = [c for c in pool if len(c) < old_len]
        return min(cand, key=lambda c: len(c)) if cand else min(pool, key=len)
    cand = [c for c in pool if len(c) > old_len]
    return max(cand, key=lambda c: len(c)) if cand else max(pool, key=len)

targets = []
for row in pick(T["V2"], "SDGwanghwamun", 3):
    targets.append(("V2 대사", row))
for row in pick(T["V3"], DN["견본"]["자막_나레"]["폰트"], 3):
    targets.append(("V3 나레", row))
assert len(targets) == 6, [t[0] for t in targets]

used, report_rows = set(), []
for (lane, row), mode in zip(targets, ["same", "short", "long"] * 2):
    cues = dlg_cues if lane.startswith("V2") else nar_cues
    new_text = choose(cues, len(row["old"]), mode, used); used.add(new_text)
    texts = split_runs(new_text, row["runs"])
    pb = doc.get(row["st"])
    b64, binhash, info = blob_set_texts(param_blob(pb), texts)      # ← tail relocation + 재파싱 자가검증
    doc.replace(row["st"], param_set_blob(pb, b64, binhash))
    vb = doc.get(row["vfc"])
    doc.replace(row["vfc"], re.sub(r"<InstanceName>.*?</InstanceName>", f"<InstanceName>{esc(new_text)}</InstanceName>", vb, flags=re.S))
    doc.replace(row["sc"], set_child(doc.get(row["sc"]), "Name", esc(new_text)))
    report_rows.append({"track": lane, "mode": mode, "item": row["item"], "t0_s": round(row["t0"], 3), "t1_s": round(row["t1"], 3),
                        "old_text": row["old"], "old_len": len(row["old"]), "new_text": new_text, "new_len": len(new_text),
                        "runs": texts, "blob_len_old": row["info"]["len"], "blob_len_new": info["len"],
                        "font": info["fonts"], "size": [r["size"] for r in info["runs"]],
                        "reparsed": "".join(r["text"] for r in info["runs"])})

seq = doc.get_uid(DN["시퀀스"]["UID"])
doc.replace_uid(DN["시퀀스"]["UID"], set_child(seq, "Name", esc(f'{tl["title"]} 리캡 — 3d 자막맛보기')))
save(out_path, doc.xml)

bad = [r for r in report_rows if r["reparsed"] != r["new_text"]]
json.dump({"stage": "3-d 맛보기", "input": os.path.basename(in_path), "rows": report_rows,
           "rule": "블롭은 tail relocation 만(재조립·in-place 금지) · 서식/폰트/Position/Start/End 무변경 · BinaryHash = uuid28+hex8(len+12)",
           "mismatch": bad}, open(out_path.replace(".prproj", ".report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"저장 {out_path}")
for r in report_rows:
    print(f"  [{r['track']}/{r['mode']}] {r['t0_s']:.2f}~{r['t1_s']:.2f}s  '{r['old_text']}'({r['old_len']}) → '{r['new_text']}'({r['new_len']})  블롭 {r['blob_len_old']}→{r['blob_len_new']}B  {r['font']} {r['size']}")
res = verify(out_path, {"V1": (T["V1"], 46), "A1": (T["A1"], 36), "A3": (T["A3"], 10), "A2": (T["A2"], 27), "V2": (T["V2"], 79), "V3": (T["V3"], 34), "V4": (T["V4"], 23)})
res["checks"].append({"check": "치환 블롭 재파싱 = 넣은 텍스트", "pass": not bad, "detail": f"6개 중 불일치 {len(bad)}"})
for c in res["checks"]:
    print(("  ✓ " if c["pass"] else "  ✗ ") + c["check"] + "  " + c["detail"])
ok = res["pass"] and not bad
print("전체:", "통과" if ok else "실패")
sys.exit(0 if ok else 1)
