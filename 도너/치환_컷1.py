#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도너/치환_컷1.py — 계단 3-a: 도너 V1/A1 을 우리 timeline.json 의 첫 컷 하나로 갈아끼운다.

  도너 컷 견본 사슬(규격 조립.도너.견본.컷_비디오 647 / 컷_오디오 1186)을 복제 → ObjectID/UID 재발급 →
  In/Out/Start/End 를 첫 컷(프레임 스냅) 으로 → V1/A1 트랙 아이템 목록 = [새 아이템] → Link 1개 →
  도너의 옛 V1/A1 아이템·사슬·A1 페이드·Link 는 제거 → mp4 미디어 경로 = 우리 소재 절대경로.
  다른 트랙(V2~V5·A2·A3)은 손대지 않는다(3-a 는 컷 사슬만 시험).
사용: python 도너/치환_컷1.py  →  도너/_치환_컷1.prproj + 자기검증 출력
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
pic = tl["picture"][0]
out_path = os.path.join(ROOT, "도너", "_치환_컷1.prproj")

doc = Doc(load(donor_path))
next_id = doc.max_id() + 1
def alloc():
    global next_id; next_id += 1; return next_id - 1

V1, A1 = DN["트랙_UID"]["V1"], DN["트랙_UID"]["A1"]
seq_uid = DN["시퀀스"]["UID"]
S = DN["견본"]

# ── 1) 새 컷 = 견본 복제 ───────────────────────────────────────────────────
t0, t1 = frame_ticks(pic["t0"]), frame_ticks(pic["t1"])
si, so = frame_ticks(pic["src_in"]), frame_ticks(pic["src_out"])
name = f'{pic["k"] + 1:02d} {pic["role"]} seg{pic.get("seg", "")}'.strip()

vid_old = {"item": S["컷_비디오"]["item"], "chain": S["컷_비디오"]["chain"], "subclip": S["컷_비디오"]["subclip"], "clip": S["컷_비디오"]["clip"]}
aud_old = {"item": S["컷_오디오_덕킹"]["item"], "chain": S["컷_오디오_덕킹"]["chain"], "subclip": S["컷_오디오_덕킹"]["subclip"], "clip": S["컷_오디오_덕킹"]["clip"], "filter": S["컷_오디오_덕킹"]["filter"]}
# 오디오 견본의 파라미터 2개(Mute/Level)와 SecondaryContent 는 블록에서 읽어 온다
filt_blk = doc.get(aud_old["filter"])
aud_params = [int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', filt_blk)]
clip_blk = doc.get(aud_old["clip"])
aud_secs = [int(x) for x in re.findall(r'<SecondaryContentItem Index="\d+" ObjectRef="(\d+)"/>', clip_blk)]

tmpl_ids = list(vid_old.values()) + list(aud_old.values()) + aud_params + aud_secs
idmap = {int(o): alloc() for o in tmpl_ids}
new_blocks = []
def clone(oid, edit=None):
    b = rewire(doc.get(oid), idmap)
    if edit: b = edit(b)
    new_blocks.append(b); return idmap[int(oid)]

def strip_node(b):  # ESP/오디오 분류 캐시(Node>Properties) 제거 — 견본 값은 도너 컷의 것
    return re.sub(r"\n\t+<Node Version=\"1\">.*?</Node>", "", b, count=1, flags=re.S)

def edit_vitem(b):
    b = re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>",
               f'<TrackItem Version="4">\n\t\t\t\t{"<Start>%d</Start>%s" % (t0, chr(10)+chr(9)*4) if t0 else ""}<End>{t1}</End>\n\t\t\t</TrackItem>', b, flags=re.S)
    return b
def edit_vclip(b):
    b = set_child(b, "ClipID", str(uuid.uuid4())); b = set_child(b, "InPoint", str(si)); b = set_child(b, "OutPoint", str(so)); return b
def edit_subclip(b): return set_child(b, "Name", esc(name))
def edit_aitem(b):
    b = strip_node(b)
    b = re.sub(r"\n\t\t\t<HeadTransition ObjectRef=\"\d+\"/>", "", b); b = re.sub(r"\n\t\t\t<TailTransition ObjectRef=\"\d+\"/>", "", b)
    b = re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>",
               f'<TrackItem Version="4">\n\t\t\t\t{"<Start>%d</Start>%s" % (t0, chr(10)+chr(9)*4) if t0 else ""}<End>{t1}</End>\n\t\t\t</TrackItem>', b, flags=re.S)
    b = set_child(b, "ID", str(uuid.uuid4())); return b
def edit_aclip(b):
    b = strip_node(b); b = re.sub(r"\n\t\t<Gain>[^<]*</Gain>", "", b)   # 도너 정규화 게인 제거(유니티)
    b = set_child(b, "ClipID", str(uuid.uuid4())); b = set_child(b, "InPoint", str(si)); b = set_child(b, "OutPoint", str(so)); return b
level = S["컷_오디오_유니티"]["level"] if pic["audio"] == "keep" else S["컷_오디오_덕킹"]["level"]
def edit_level(b):
    b = re.sub(r"<StartKeyframe>-91445760000000000,[0-9.eE+-]+,", f"<StartKeyframe>-91445760000000000,{level},", b)
    b = set_child(b, "CurrentValue", level); return b

new_vitem = clone(vid_old["item"], edit_vitem); clone(vid_old["chain"]); clone(vid_old["subclip"], edit_subclip); clone(vid_old["clip"], edit_vclip)
new_aitem = clone(aud_old["item"], edit_aitem); clone(aud_old["chain"]); clone(aud_old["subclip"], edit_subclip); clone(aud_old["clip"], edit_aclip)
clone(aud_old["filter"])
for p in aud_params:
    clone(p, edit_level if "<Name>Level</Name>" in doc.get(p) else None)
for s_ in aud_secs: clone(s_)
new_link = alloc()
new_blocks.append(f'\t<Link ObjectID="{new_link}" ClassID="149d4ea5-a7d4-4b34-9bb7-16d783904bf2" Version="1">\n\t\t<TrackItemGroup Version="1">\n\t\t\t<TrackItems Version="1">\n\t\t\t\t<TrackItem Index="0" ObjectRef="{new_vitem}"/>\n\t\t\t\t<TrackItem Index="1" ObjectRef="{new_aitem}"/>\n\t\t\t</TrackItems>\n\t\t</TrackItemGroup>\n\t</Link>')

# ── 2) 도너의 옛 V1/A1 아이템·사슬·페이드·Link 제거 ─────────────────────────
v_clips, _ = track_items(doc, V1); a_clips, a_trans = track_items(doc, A1)
seq = doc.get_uid(seq_uid)
old_links = [int(x) for x in re.findall(r'<Link Index="\d+" ObjectRef="(\d+)"/>', seq)]
to_remove = set(old_links) | set(a_trans)
for it in v_clips:
    b = doc.get(it); ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1)); sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
    cl = int(re.search(r'<Clip ObjectRef="(\d+)"', doc.get(sc)).group(1))
    chb = doc.get(ch); comps = [int(x) for x in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', chb)]
    to_remove |= {it, ch, sc, cl} | set(comps)
    for c in comps: to_remove |= {int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(c))}
for it in a_clips:
    b = doc.get(it); ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1)); sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
    cl = int(re.search(r'<Clip ObjectRef="(\d+)"', doc.get(sc)).group(1))
    chb = doc.get(ch); comps = [int(x) for x in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', chb)]
    secs = [int(x) for x in re.findall(r'<SecondaryContentItem Index="\d+" ObjectRef="(\d+)"/>', doc.get(cl))]
    to_remove |= {it, ch, sc, cl} | set(comps) | set(secs)
    for c in comps: to_remove |= {int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(c))}
removed = doc.remove_many(to_remove)

# ── 3) 배선: 트랙 아이템 목록 · LinkContainer · 새 블록 append ─────────────
doc.append(new_blocks)
track_set_items(doc, V1, [new_vitem])
track_set_items(doc, A1, [new_aitem], transitions=[])
seq = doc.get_uid(seq_uid)
seq = re.sub(r'<LinkContainer Version="1">.*?</LinkContainer>',
             f'<LinkContainer Version="1">\n\t\t\t\t<Links Version="1">\n\t\t\t\t\t<Link Index="0" ObjectRef="{new_link}"/>\n\t\t\t\t</Links>\n\t\t\t</LinkContainer>', seq, count=1, flags=re.S)
seq = set_child(seq, "Name", esc(f'{tl["title"]} 리캡 — 3a 컷1'))
doc.replace_uid(seq_uid, seq)

# ── 4) mp4 미디어 경로 = 우리 소재 (Media 블록: FilePath·ActualMediaFilePath·FileKey) ──
mb = doc.get_uid(DN["원본_mp4"]["Media_UID"])
mb = set_child(mb, "FilePath", esc(SRC)); mb = set_child(mb, "ActualMediaFilePath", esc(SRC)); mb = set_child(mb, "FileKey", str(uuid.uuid4()))
doc.replace_uid(DN["원본_mp4"]["Media_UID"], mb)

save(out_path, doc.xml)
print(f"저장 {out_path}  (제거 블록 {removed} · 추가 {len(new_blocks)} · 새 컷 {name}: t {pic['t0']}~{pic['t1']}s = 틱 {t0}~{t1}, src {si}~{so}, level {level})")

# ── 5) 자기검증 ────────────────────────────────────────────────────────────
res = verify(out_path, {"V1": (V1, 1), "A1": (A1, 1), "V2": (DN["트랙_UID"]["V2"], 79), "V3": (DN["트랙_UID"]["V3"], 34), "A2": (DN["트랙_UID"]["A2"], 39), "A3": (DN["트랙_UID"]["A3"], 12)})
for c in res["checks"]:
    print(("  ✓ " if c["pass"] else "  ✗ ") + c["check"] + "  " + c["detail"])
print("전체:", "통과" if res["pass"] else "실패")
sys.exit(0 if res["pass"] else 1)
