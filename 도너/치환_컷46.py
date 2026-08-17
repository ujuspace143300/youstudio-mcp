#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보관 — 되돌아갈 지점 (2026-08-17 계단 4). 이 치환 체인은 서버/runner/조립_prproj.py 로 합쳤다.
   정상 경로는 export 단계가 조립기를 부르는 것이다. 이 파일은 조립기가 깨졌을 때 단계별로 되짚어
   어디서 어긋났는지 보기 위한 실험용 체인으로만 남긴다 (계단 3-a~d 산출물도 도너/ 에 그대로 둔다)."""
"""도너/치환_컷46.py — 계단 3-b: 도너 V1/A1/A3 를 우리 timeline.json 의 컷 전체로 갈아끼운다.

  V1 = picture 46 · A1 = audio keep 36 · A3 = audio duck 10 (규격 조립.덕킹_방식 = 별도트랙) · Link 46(V↔A1|A3).
  견본 사슬(규격 조립.도너.견본: 컷_비디오 647 · 컷_오디오_덕킹 1186)을 컷마다 복제 → ObjectID/UID 재발급 →
  프레임 스냅 틱(소스 Out = In + 타임라인 길이) → 트랙 목록 교체. Level = 유니티(keep) / 도너 덕킹 문자열(duck, −15 dB — 규격 −12 와의 차이는 보류 결정, 기록만).
  도너의 옛 V1/A1 컷·A1 페이드·Link 와 **A3 효과음 12 + 페이드 24 도 제거**(A3 자리를 덕킹 컷이 쓰므로 — 효과음은 다음 계단 대상이었으나 자리 충돌로 여기서 뺀다).
  A2 나레·V2~V5 자막은 도너 그대로. 시퀀스 길이 = 우리 총장. mp4 경로 = 우리 소재.
사용: python 도너/치환_컷46.py → 도너/_치환_컷46.prproj + _치환_컷46.report.json + 자기검증
"""
import json, os, re, sys, uuid
sys.path.insert(0, os.path.dirname(__file__))
from prproj_lib import (Doc, load, save, esc, frame_ticks, rewire, set_child, child,
                        track_set_items, track_items, verify)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))
DN = SPEC["조립"]["도너"]
donor_path = os.path.join(ROOT, DN["파일"])
WORK = "C:/Users/user/Desktop/youstudio_work/fulltime"
tl = json.load(open(f"{WORK}/subtitle/timeline.json", encoding="utf-8"))
SRC = os.path.normpath(tl["source"]["path"] if isinstance(tl.get("source"), dict) else tl["source"])
assert os.path.exists(SRC), SRC
out_path = os.path.join(ROOT, "도너", "_치환_컷46.prproj")

doc = Doc(load(donor_path))
next_id = doc.max_id() + 1
def alloc():
    global next_id; next_id += 1; return next_id - 1

T = DN["트랙_UID"]; V1, A1, A3 = T["V1"], T["A1"], T["A3"]
seq_uid = DN["시퀀스"]["UID"]; S = DN["견본"]
LEVEL_KEEP = S["컷_오디오_유니티"]["level"]; LEVEL_DUCK = S["컷_오디오_덕킹"]["level"]

# ── 견본 블록 읽기 (제거 전에) ─────────────────────────────────────────────
vid_t = {"item": S["컷_비디오"]["item"], "chain": S["컷_비디오"]["chain"], "subclip": S["컷_비디오"]["subclip"], "clip": S["컷_비디오"]["clip"]}
aud_t = {"item": S["컷_오디오_덕킹"]["item"], "chain": S["컷_오디오_덕킹"]["chain"], "subclip": S["컷_오디오_덕킹"]["subclip"], "clip": S["컷_오디오_덕킹"]["clip"], "filter": S["컷_오디오_덕킹"]["filter"]}
aud_params = [int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(aud_t["filter"]))]
aud_secs = [int(x) for x in re.findall(r'<SecondaryContentItem Index="\d+" ObjectRef="(\d+)"/>', doc.get(aud_t["clip"]))]
tmpl = {oid: doc.get(oid) for oid in list(vid_t.values()) + list(aud_t.values()) + aud_params + aud_secs}
level_param = [p for p in aud_params if "<Name>Level</Name>" in tmpl[p]][0]

def strip_node(b):
    return re.sub(r"\n\t+<Node Version=\"1\">.*?</Node>", "", b, count=1, flags=re.S)
def set_span(b, t0, t1):
    inner = (f"<Start>{t0}</Start>\n\t\t\t\t" if t0 else "") + f"<End>{t1}</End>"
    return re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>", f'<TrackItem Version="4">\n\t\t\t\t{inner}\n\t\t\t</TrackItem>', b, flags=re.S)

new_blocks, links = [], []
v_refs, a1_refs, a3_refs, report_cuts = [], [], [], []
for pic in tl["picture"]:
    t0, t1 = frame_ticks(pic["t0"]), frame_ticks(pic["t1"])
    si = frame_ticks(pic["src_in"]); so = si + (t1 - t0)   # 소스 길이 = 타임라인 길이 (FCP XML export 와 같은 규칙 — 배속 없음)
    assert t1 > t0, pic
    name = f'{pic["k"] + 1:02d} {pic["role"]}' + (f' seg{pic["seg"]}' if pic.get("seg") is not None else "")
    duck = pic["audio"] == "duck"; level = LEVEL_DUCK if duck else LEVEL_KEEP
    idmap = {oid: alloc() for oid in tmpl}
    def cl(oid, edit=None):
        b = rewire(tmpl[oid], idmap)
        if edit: b = edit(b)
        new_blocks.append(b); return idmap[oid]
    vi = cl(vid_t["item"], lambda b: set_span(b, t0, t1)); cl(vid_t["chain"])
    cl(vid_t["subclip"], lambda b: set_child(b, "Name", esc(name)))
    cl(vid_t["clip"], lambda b: set_child(set_child(set_child(b, "ClipID", str(uuid.uuid4())), "InPoint", str(si)), "OutPoint", str(so)))
    def ed_aitem(b):
        b = strip_node(b); b = re.sub(r"\n\t\t\t<(Head|Tail)Transition ObjectRef=\"\d+\"/>", "", b)
        return set_child(set_span(b, t0, t1), "ID", str(uuid.uuid4()))
    ai = cl(aud_t["item"], ed_aitem); cl(aud_t["chain"])
    cl(aud_t["subclip"], lambda b: set_child(b, "Name", esc(name)))
    def ed_aclip(b):
        b = strip_node(b); b = re.sub(r"\n\t\t<Gain>[^<]*</Gain>", "", b)
        return set_child(set_child(set_child(b, "ClipID", str(uuid.uuid4())), "InPoint", str(si)), "OutPoint", str(so))
    cl(aud_t["clip"], ed_aclip); cl(aud_t["filter"])
    for p in aud_params:
        if p == level_param:
            cl(p, lambda b: set_child(re.sub(r"<StartKeyframe>-91445760000000000,[0-9.eE+-]+,", f"<StartKeyframe>-91445760000000000,{level},", b), "CurrentValue", level))
        else:
            cl(p)
    for s_ in aud_secs: cl(s_)
    lid = alloc()
    new_blocks.append(f'\t<Link ObjectID="{lid}" ClassID="149d4ea5-a7d4-4b34-9bb7-16d783904bf2" Version="1">\n\t\t<TrackItemGroup Version="1">\n\t\t\t<TrackItems Version="1">\n\t\t\t\t<TrackItem Index="0" ObjectRef="{vi}"/>\n\t\t\t\t<TrackItem Index="1" ObjectRef="{ai}"/>\n\t\t\t</TrackItems>\n\t\t</TrackItemGroup>\n\t</Link>')
    links.append(lid); v_refs.append(vi); (a3_refs if duck else a1_refs).append(ai)
    report_cuts.append({"k": pic["k"], "name": name, "t0_s": pic["t0"], "t1_s": pic["t1"], "t0_ticks": t0, "t1_ticks": t1, "src_in_ticks": si, "src_out_ticks": so, "track": "A3" if duck else "A1", "level": level, "v_item": vi, "a_item": ai, "link": lid})

# ── 도너 옛 것 제거: V1/A1/A3 아이템 + 사슬 + 페이드 + Link ─────────────────
def chain_ids(item):
    b = doc.get(item); ids = {item}
    ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1)); sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
    cl_ = int(re.search(r'<Clip ObjectRef="(\d+)"', doc.get(sc)).group(1)); ids |= {ch, sc, cl_}
    comps = [int(x) for x in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', doc.get(ch))]; ids |= set(comps)
    for c in comps: ids |= {int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(c))}
    ids |= {int(x) for x in re.findall(r'<SecondaryContentItem Index="\d+" ObjectRef="(\d+)"/>', doc.get(cl_))}
    return ids
to_remove = set()
for uid in (V1, A1, A3):
    clips, trans = track_items(doc, uid); to_remove |= set(trans)
    for it in clips: to_remove |= chain_ids(it)
seq = doc.get_uid(seq_uid)
old_links = [int(x) for x in re.findall(r'<Link Index="\d+" ObjectRef="(\d+)"/>', seq)]
to_remove |= set(old_links)
removed = doc.remove_many(to_remove)

# ── 배선 ───────────────────────────────────────────────────────────────────
doc.append(new_blocks)
track_set_items(doc, V1, v_refs)
track_set_items(doc, A1, a1_refs, transitions=[])
track_set_items(doc, A3, a3_refs, transitions=[])
total_ticks = frame_ticks(tl["total_s"])
seq = doc.get_uid(seq_uid)
links_inner = "".join(f'\n\t\t\t\t\t<Link Index="{i}" ObjectRef="{l}"/>' for i, l in enumerate(links))
seq = re.sub(r'<LinkContainer Version="1">.*?</LinkContainer>', f'<LinkContainer Version="1">\n\t\t\t\t<Links Version="1">{links_inner}\n\t\t\t\t</Links>\n\t\t\t</LinkContainer>', seq, count=1, flags=re.S)
seq = set_child(seq, "Name", esc(f'{tl["title"]} 리캡 — 3b 컷46'))
for tag in ("MZ.WorkOutPoint", "MZ.OutPoint"):
    if f"<{tag}>" in seq: seq = set_child(seq, tag, str(total_ticks))
doc.replace_uid(seq_uid, seq)
mb = doc.get_uid(DN["원본_mp4"]["Media_UID"])
mb = set_child(set_child(set_child(mb, "FilePath", esc(SRC)), "ActualMediaFilePath", esc(SRC)), "FileKey", str(uuid.uuid4()))
doc.replace_uid(DN["원본_mp4"]["Media_UID"], mb)
save(out_path, doc.xml)

report = {"stage": "3-b 컷46", "donor": DN["파일"], "source": SRC, "total_s": tl["total_s"], "total_ticks": total_ticks,
          "counts": {"V1": len(v_refs), "A1": len(a1_refs), "A3": len(a3_refs), "links": len(links), "removed_blocks": removed, "added_blocks": len(new_blocks)},
          "levels": {"keep": LEVEL_KEEP, "duck": LEVEL_DUCK, "_note": "덕킹 = 도너 견본 문자열(−15 dB). 규격 조립.덕킹_레벨(−12 dB)과 다름 — 보류 결정, 여기 기록만"},
          "kept_from_donor": ["A2 나레 39", "V2/V3/V4 자막 136", "V5·캡션 트랙(빈)"], "removed_from_donor": ["V1/A1 컷 134+134 + 사슬", "A1 페이드 130", "Link 134", "A3 효과음 12 + 페이드 24 (덕킹 컷 자리 충돌)"],
          "cuts": report_cuts}
json.dump(report, open(out_path.replace(".prproj", ".report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"저장 {out_path}: V1 {len(v_refs)} · A1 {len(a1_refs)} · A3 {len(a3_refs)} · Link {len(links)} · 제거 {removed} · 추가 {len(new_blocks)} · 총장 {tl['total_s']}s")
from prproj_lib import Doc as _D
_doc2 = _D(load(out_path))
res = verify(out_path, {"V1": (V1, len(v_refs)), "A1": (A1, len(a1_refs)), "A3": (A3, len(a3_refs)),
                        "V2": (T["V2"], len(track_items(_doc2, T["V2"])[0])), "V3": (T["V3"], len(track_items(_doc2, T["V3"])[0])),
                        "V4": (T["V4"], len(track_items(_doc2, T["V4"])[0])), "A2": (T["A2"], len(track_items(_doc2, T["A2"])[0]))})
for c in res["checks"]:
    print(("  ✓ " if c["pass"] else "  ✗ ") + c["check"] + "  " + c["detail"])
print("전체:", "통과" if res["pass"] else "실패")
sys.exit(0 if res["pass"] else 1)
