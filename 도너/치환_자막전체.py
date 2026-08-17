#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보관 — 되돌아갈 지점 (2026-08-17 계단 4). 이 치환 체인은 서버/runner/조립_prproj.py 로 합쳤다.
   정상 경로는 export 단계가 조립기를 부르는 것이다. 이 파일은 조립기가 깨졌을 때 단계별로 되짚어
   어디서 어긋났는지 보기 위한 실험용 체인으로만 남긴다 (계단 3-a~d 산출물도 도너/ 에 그대로 둔다)."""
"""도너/치환_자막전체.py — 계단 3-d 완결: 자막 194개 전부 우리 것으로. (사실상 최종 조립본)

  입력 = 3-c 산출 `_치환_나레.prproj`(컷·원본소리·덕킹·나레는 이미 우리 것).
  V2 = 대사 큐 120 · V3 = 나레 큐 74 · V4 = 비움(도너 강조 23 + Cross Dissolve 제거).
  자막 견본(규격 조립.도너.견본.자막_대사 3293 / 자막_나레 4211)의 서브트리 27블록을 큐마다 복제 →
  ObjectID 재발급 → Start/End(프레임 스냅)·In/Out(Graphic 3600s 기준)·ClipID·SubClip Name·InstanceName →
  Source Text 블롭 텍스트만 tail relocation 치환(런 분할 = **B안 단어 경계**, prproj_lib.split_runs_words).
  서식(폰트·크기·색·그림자)·Position 은 견본 그대로. 공유 오브젝트(Graphic 미디어 541/542/543/544/623·마스터클립)는 건드리지 않는다.
사용: python 도너/치환_자막전체.py → 도너/_치환_자막전체.prproj + .report.json + 자기검증
"""
import json, os, re, sys, uuid
sys.path.insert(0, os.path.dirname(__file__))
from prproj_lib import (Doc, load, save, esc, frame_ticks, rewire, set_child, child, collect_lineage,
                        track_set_items, track_items, verify, parse_blob, blob_set_texts, param_blob,
                        param_set_blob, split_runs_words, GRAPHIC_IN, FRAME_TICKS, TPS)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))
DN = SPEC["조립"]["도너"]; T = DN["트랙_UID"]; S = DN["견본"]
in_path = os.path.join(ROOT, "도너", "_치환_나레.prproj")
out_path = os.path.join(ROOT, "도너", "_치환_자막전체.prproj")
tl = json.load(open("C:/Users/user/Desktop/youstudio_work/fulltime/subtitle/timeline.json", encoding="utf-8"))

doc = Doc(load(in_path))
next_id = doc.max_id() + 1
def alloc():
    global next_id; next_id += 1; return next_id - 1

SHARED = {"541", "542", "543", "544", "623",           # Graphic 미디어 계보 — 공유, 복제·삭제 금지
          "ebfb8f8d-03b7-48bc-a7a8-3a00c6414625",      # Graphic MasterClip (모든 자막 SubClip 이 가리킨다)
          "1b62cdc4-0c16-4be3-a9f4-9cbf7a26236f"}      # Graphic Media
def template(item_id):
    ids, uids = collect_lineage(doc, [item_id], stop=SHARED)
    tmpl_ids = sorted(ids - SHARED, key=int)
    blocks = {i: doc.get(i) for i in tmpl_ids}
    st = [i for i in tmpl_ids if "<Name>Source Text</Name>" in blocks[i]][0]
    vfc = [i for i in tmpl_ids if blocks[i].lstrip().startswith("<VideoFilterComponent")][0]
    sub = [i for i in tmpl_ids if blocks[i].lstrip().startswith("<SubClip")][0]
    vclip = [i for i in tmpl_ids if blocks[i].lstrip().startswith("<VideoClip")][0]
    runs = len(parse_blob(param_blob(blocks[st]))["runs"])
    return {"ids": tmpl_ids, "blocks": blocks, "item": str(item_id), "st": st, "vfc": vfc, "sub": sub, "clip": vclip, "runs": runs}

TPL = {"dlg": template(S["자막_대사"]["item"]), "nar": template(S["자막_나레"]["item"])}
print(f'견본: 대사 {len(TPL["dlg"]["ids"])}블록/런 {TPL["dlg"]["runs"]} · 나레 {len(TPL["nar"]["ids"])}블록/런 {TPL["nar"]["runs"]}')

def set_span(b, t0, t1):
    inner = (f"<Start>{t0}</Start>\n\t\t\t\t" if t0 else "") + f"<End>{t1}</End>"
    return re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>", f'<TrackItem Version="4">\n\t\t\t\t{inner}\n\t\t\t</TrackItem>', b, flags=re.S)

new_blocks, refs = [], {"dlg": [], "nar": []}
rows = []
for cue in sorted(tl["cues"], key=lambda c: (c["t0"], c["lane"])):
    lane = cue["lane"]; tpl = TPL[lane]
    t0 = frame_ticks(cue["t0"]); t1 = max(frame_ticks(cue["t1"]), t0 + FRAME_TICKS)
    texts = split_runs_words(cue["text"], tpl["runs"])
    idmap = {int(i): alloc() for i in tpl["ids"]}
    blob_info = None
    for i in tpl["ids"]:
        b = rewire(tpl["blocks"][i], idmap)
        if i == tpl["item"]:
            b = set_span(b, t0, t1)
        elif i == tpl["clip"]:
            b = set_child(set_child(set_child(b, "ClipID", str(uuid.uuid4())), "InPoint", str(GRAPHIC_IN)), "OutPoint", str(GRAPHIC_IN + (t1 - t0)))
        elif i == tpl["sub"]:
            b = set_child(b, "Name", esc(cue["text"]))
        elif i == tpl["vfc"]:
            b = re.sub(r"<InstanceName>.*?</InstanceName>", f"<InstanceName>{esc(cue['text'])}</InstanceName>", b, flags=re.S)
        elif i == tpl["st"]:
            b64, binhash, blob_info = blob_set_texts(param_blob(b), texts)   # tail relocation + 재파싱
            b = param_set_blob(b, b64, binhash)
        new_blocks.append(b)
    refs[lane].append(idmap[int(tpl["item"])])
    rows.append({"lane": lane, "t0_s": cue["t0"], "t1_s": cue["t1"], "text": cue["text"], "runs": texts,
                 "item": idmap[int(tpl["item"])], "blob_len": blob_info["len"], "font": blob_info["fonts"],
                 "size": [r["size"] for r in blob_info["runs"]], "reparsed": "".join(r["text"] for r in blob_info["runs"])})

# ── 도너 자막 전부 제거 (V2 79 · V3 34 · V4 23 + Cross Dissolve) ─────────────
rm_ids, rm_uids = set(), set()
for uid in (T["V2"], T["V3"], T["V4"]):
    clips, trans = track_items(doc, uid)
    for tr in trans:
        i_, u_ = collect_lineage(doc, [tr], stop=SHARED); rm_ids |= i_; rm_uids |= u_
    for it in clips:
        i_, u_ = collect_lineage(doc, [it], stop=SHARED); rm_ids |= i_; rm_uids |= u_
rm_ids -= SHARED; rm_uids -= SHARED
assert not (rm_ids & {str(i) for i in refs["dlg"] + refs["nar"]}), "새 자막이 제거 목록에 들어감"
removed = doc.remove_many(rm_ids | rm_uids)

doc.append(new_blocks)
track_set_items(doc, T["V2"], refs["dlg"], transitions=[])
track_set_items(doc, T["V3"], refs["nar"], transitions=[])
track_set_items(doc, T["V4"], [], transitions=[])
seq = doc.get_uid(DN["시퀀스"]["UID"])
doc.replace_uid(DN["시퀀스"]["UID"], set_child(seq, "Name", esc(f'{tl["title"]} 리캡')))
save(out_path, doc.xml)

# ── 검증 ───────────────────────────────────────────────────────────────────
bad_blob = [r for r in rows if r["reparsed"] != r["text"]]
by_lane = {"dlg": [c for c in tl["cues"] if c["lane"] == "dlg"], "nar": [c for c in tl["cues"] if c["lane"] == "nar"]}
doc2 = Doc(load(out_path))
mismatch_tl = []
for lane, uid in (("dlg", T["V2"]), ("nar", T["V3"])):
    items, _ = track_items(doc2, uid)
    want = sorted(by_lane[lane], key=lambda c: c["t0"])
    if len(items) != len(want):
        mismatch_tl.append({"lane": lane, "count": [len(items), len(want)]}); continue
    for it, cue in zip(items, want):
        b = doc2.get(it); ti = re.search(r"<TrackItem Version=\"4\">(.*?)</TrackItem>", b, re.S).group(1)
        st_, en_ = int(child(ti, "Start") or 0), int(child(ti, "End"))
        sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
        ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1))
        vfc = int(re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', doc2.get(ch))[0])
        stp = [p for p in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc2.get(vfc)) if "<Name>Source Text</Name>" in doc2.get(p)][0]
        txt = "".join(r["text"] for r in parse_blob(param_blob(doc2.get(stp)))["runs"])
        if txt != cue["text"] or child(doc2.get(sc), "Name") != esc(cue["text"]) or st_ != frame_ticks(cue["t0"]):
            mismatch_tl.append({"lane": lane, "t0": cue["t0"], "want": cue["text"], "got": txt})
report = {"stage": "3-d 자막전체(최종 조립본)", "input": os.path.basename(in_path),
          "counts": {"V2_대사": len(refs["dlg"]), "V3_나레": len(refs["nar"]), "V4": 0, "removed_blocks": removed, "added_blocks": len(new_blocks)},
          "run_split": "B안 — 단어 경계에서만 분할(단어 < 런이면 첫 런에 전부 + 빈 런). 강조 서식 방침은 설계/분석단계_강조학습.md",
          "template": {k: {"blocks": len(v["ids"]), "runs": v["runs"]} for k, v in TPL.items()},
          "blob_mismatch": bad_blob, "timeline_mismatch": mismatch_tl, "cues": rows}
json.dump(report, open(out_path.replace(".prproj", ".report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"저장 {out_path}: V2 {len(refs['dlg'])} · V3 {len(refs['nar'])} · V4 0 · 제거 {removed} · 추가 {len(new_blocks)}")
_cnt = lambda uid: len(track_items(doc2, uid)[0])
res = verify(out_path, {"V1": (T["V1"], _cnt(T["V1"])), "A1": (T["A1"], _cnt(T["A1"])), "A3": (T["A3"], _cnt(T["A3"])), "A2": (T["A2"], _cnt(T["A2"])),
                        "V2": (T["V2"], len(refs["dlg"])), "V3": (T["V3"], len(refs["nar"])), "V4": (T["V4"], 0)})
res["checks"].append({"check": "치환 블롭 재파싱 = 넣은 텍스트", "pass": not bad_blob, "detail": f"{len(rows)}개 중 불일치 {len(bad_blob)}"})
res["checks"].append({"check": "timeline.json 문구·시각 대조", "pass": not mismatch_tl, "detail": f"불일치 {len(mismatch_tl)}"})
for c in res["checks"]:
    print(("  ✓ " if c["pass"] else "  ✗ ") + c["check"] + "  " + c["detail"])
ok = res["pass"] and not bad_blob and not mismatch_tl
print("전체:", "통과" if ok else "실패")
sys.exit(0 if ok else 1)
