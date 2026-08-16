#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도너/치환_나레.py — 계단 3-c: A2 나레 39개(도너 48k wav) → 우리 나레 27개(24000Hz 모노 wav).

  입력 = 계단 3-b 산출 `_치환_컷46.prproj` (V1/A1/A3 는 이미 우리 것). 나레 견본 계보(규격 조립.도너.견본.나레 —
  트랙 아이템 2268 + 마스터클립·미디어·ClipProjectItem 까지 20+3 블록)를 wav 마다 통째 복제 → ObjectID/UID 재발급 →
  경로·이름·레이트(10584000)·길이 치환 → Start/End = timeline.narration 실측(프레임 스냅), In 0 / Out = 클립 길이 →
  RootProjectItem Items 에 새 ClipProjectItem 등록 → 도너 나레 39 계보 + A2 페이드 78 제거. 레벨 = 견본값(유니티) 유지, 도너 Gain 은 제거.
  V2/V3/V4 자막은 도너 그대로(마지막 계단).
사용: python 도너/치환_나레.py → 도너/_치환_나레.prproj + .report.json + 자기검증(7규칙 + voice.json 길이 대조)
"""
import json, os, re, sys, uuid, wave
sys.path.insert(0, os.path.dirname(__file__))
from prproj_lib import (Doc, load, save, esc, frame_ticks, rewire, set_child, child, collect_lineage,
                        track_set_items, track_items, verify, TPS, FRAME_TICKS)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))
DN = SPEC["조립"]["도너"]
in_path = os.path.join(ROOT, "도너", "_치환_컷46.prproj")
out_path = os.path.join(ROOT, "도너", "_치환_나레.prproj")
WORK = "C:/Users/user/Desktop/youstudio_work/fulltime"
tl = json.load(open(f"{WORK}/subtitle/timeline.json", encoding="utf-8"))
voice = json.load(open(f"{WORK}/voice/voice.json", encoding="utf-8"))
vdur = {b["n"]: b["dur_s"] for b in voice["blocks"]}

doc = Doc(load(in_path))
next_id = doc.max_id() + 1
def alloc():
    global next_id; next_id += 1; return next_id - 1

T = DN["트랙_UID"]; A2 = T["A2"]; N = DN["견본"]["나레"]
root_uid = N["RootProjectItem_UID"]

# ── 견본 계보 (전환 참조 7149/7150 류는 제외) ─────────────────────────────────
ids, uids = collect_lineage(doc, [N["item"], N["ClipProjectItem_UID"]])
tmpl_ids = [i for i in ids if "AudioTransitionTrackItem" not in doc.get(i)]
tmpl_uids = list(uids)
tmpl = {k: doc.get(k) for k in tmpl_ids}
tmpl_u = {k: doc.get_uid(k) for k in tmpl_uids}
def kind(b): return re.match(r'\s*<(\w+)', b).group(1)

def strip_node(b):
    return re.sub(r"\n\t+<Node Version=\"1\">.*?</Node>", "", b, count=1, flags=re.S)
def set_span(b, t0, t1):
    inner = (f"<Start>{t0}</Start>\n\t\t\t\t" if t0 else "") + f"<End>{t1}</End>"
    return re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>", f'<TrackItem Version="4">\n\t\t\t\t{inner}\n\t\t\t</TrackItem>', b, flags=re.S)

new_blocks, a2_refs, new_cpis, report_nars = [], [], [], []
for nar in sorted(tl["narration"], key=lambda n: n["t0"]):
    wav = os.path.normpath(nar["wav"]); fname = os.path.basename(wav)
    w = wave.open(wav); rate, ch, sw, nframes = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes(); w.close()
    assert ch == 1 and sw == 2 and TPS % rate == 0, (fname, rate, ch, sw)
    tick_rate = TPS // rate                       # 24000Hz → 10584000
    dur_ticks = nframes * tick_rate                # 미디어 길이(샘플 정확)
    t0 = frame_ticks(nar["t0"]); t1 = frame_ticks(nar["t1"])
    length = min(t1 - t0, (dur_ticks // FRAME_TICKS) * FRAME_TICKS)   # 클립 길이 ≤ 미디어 길이(프레임 내림)
    assert length > 0, nar
    t1 = t0 + length
    idmap = {int(k): alloc() for k in tmpl_ids}
    uidmap = {k: str(uuid.uuid4()) for k in tmpl_uids}
    label = f'나레 {nar["n"]:02d} {nar["text"][:20]}'
    def emit(b):
        k = kind(b)
        if k == "AudioClipTrackItem":
            b = strip_node(b); b = re.sub(r"\n\t\t\t<(Head|Tail)Transition ObjectRef=\"\d+\"/>", "", b)
            b = set_child(set_span(b, t0, t1), "ID", str(uuid.uuid4()))
        elif k == "AudioClip":
            b = strip_node(b); b = re.sub(r"\n\t\t<Gain>[^<]*</Gain>", "", b)
            b = set_child(b, "ClipID", str(uuid.uuid4()))
            if child(b, "InPoint") is not None:            # 트랙 클립(마스터 AudioClip 엔 In/Out 없음)
                b = set_child(set_child(b, "InPoint", "0"), "OutPoint", str(length))
        elif k == "SubClip":
            b = set_child(b, "Name", esc(label))
        elif k == "AudioStream":
            b = set_child(set_child(b, "FrameRate", str(tick_rate)), "Duration", str(dur_ticks))
        elif k == "AudioMediaSource":
            b = set_child(b, "OriginalDuration", str(dur_ticks))
        elif k == "ClipLoggingInfo":
            b = set_child(set_child(b, "ClipName", esc(fname)), "MediaOutPoint", str(dur_ticks))
        elif k == "Markers":
            b = set_child(b, "LastContentState", str(uuid.uuid4()))
        elif k == "Media":
            for tag, val in (("FilePath", wav), ("ActualMediaFilePath", wav), ("Title", fname), ("RelativePath", fname), ("MediaFileHistory0", fname), ("FileKey", str(uuid.uuid4())), ("ConformedAudioRate", str(tick_rate))):
                b = set_child(b, tag, esc(val))
        elif k == "MasterClip":
            b = set_child(b, "Name", esc(fname))
        elif k == "ClipProjectItem":
            b = set_child(b, "Name", esc(fname))
        return b
    for k in tmpl_ids:
        new_blocks.append(emit(rewire(tmpl[k], idmap, uidmap)))
    for k in tmpl_uids:
        new_blocks.append(emit(rewire(tmpl_u[k], idmap, uidmap)))
    a2_refs.append(idmap[N["item"]]); new_cpis.append(uidmap[N["ClipProjectItem_UID"]])
    report_nars.append({"n": nar["n"], "wav": fname, "t0_s": nar["t0"], "t1_s": nar["t1"], "start_ticks": t0, "end_ticks": t1, "clip_len_s": round(length / TPS, 4),
                        "media_dur_s": round(dur_ticks / TPS, 4), "voice_dur_s": vdur.get(nar["n"]), "rate": rate, "item": a2_refs[-1], "media_uid": uidmap[N["Media_UID"]]})

# ── 도너 나레 39 계보 + A2 페이드 제거, RootProjectItem Items 갱신 ─────────────
old_items, old_trans = track_items(doc, A2)
rm_ids, rm_uids = set(old_trans), set()
for it in old_items:
    i_, u_ = collect_lineage(doc, [it]); rm_ids |= i_; rm_uids |= u_
    mc = re.search(r'<MasterClip ObjectURef="([^"]+)"', doc.get(int(re.search(r'<SubClip ObjectRef="(\d+)"', doc.get(it)).group(1)))).group(1)
    for m in re.finditer(r'^\t<ClipProjectItem ObjectUID="([^"]+)"', doc.xml, re.M):
        if f'<MasterClip ObjectURef="{mc}"/>' in doc.get_uid(m.group(1)): rm_uids.add(m.group(1))
# 원본 mp4 계보가 섞여 들어가면 안 된다 (나레 lineage 는 mp4 를 참조하지 않지만 안전장치)
protect = {DN["원본_mp4"]["Media_UID"], DN["원본_mp4"]["MasterClip_UID"], str(DN["원본_mp4"]["VideoMediaSource"]), str(DN["원본_mp4"]["AudioMediaSource"]), str(DN["원본_mp4"]["Markers"])}
assert not ((rm_ids | rm_uids) & protect), "원본 mp4 계보 보호 위반"
removed = doc.remove_many(rm_ids | rm_uids)

doc.append(new_blocks)
track_set_items(doc, A2, a2_refs, transitions=[])
root = doc.get_uid(root_uid)
m = re.search(r'(<Items Version="\d+">)(.*?)(</Items>)', root, re.S)
kept = [u for u in re.findall(r'<Item Index="\d+" ObjectURef="([^"]+)"/>', m.group(2)) if u not in rm_uids]
items = "".join(f'\n\t\t\t\t<Item Index="{i}" ObjectURef="{u}"/>' for i, u in enumerate(kept + new_cpis))
root = root[:m.start()] + m.group(1) + items + "\n\t\t\t" + m.group(3) + root[m.end():]
doc.replace_uid(root_uid, root)
seq = doc.get_uid(DN["시퀀스"]["UID"]); seq = set_child(seq, "Name", esc(f'{tl["title"]} 리캡 — 3c 나레')); doc.replace_uid(DN["시퀀스"]["UID"], seq)
save(out_path, doc.xml)

# ── 보고 + 검증 ────────────────────────────────────────────────────────────
mism = [r for r in report_nars if r["voice_dur_s"] is None or abs(r["clip_len_s"] - r["voice_dur_s"]) > 1.0 / 23.976 + 1e-6]
report = {"stage": "3-c 나레", "input": os.path.basename(in_path), "counts": {"A2": len(a2_refs), "removed_blocks": removed, "added_blocks": len(new_blocks), "root_items": len(kept) + len(new_cpis)},
          "level": "견본 유니티(0.177827998996) 유지 · 도너 Gain 제거", "rate": "24000Hz 모노 → AudioStream/ConformedAudioRate 10584000",
          "length_check": {"rule": "클립 길이 = 슬롯(t1−t0 프레임 스냅) 과 wav 실측(프레임 내림) 중 작은 것; voice.json dur_s 와 1프레임 이내", "mismatch": mism},
          "kept_from_donor": ["V2/V3/V4 자막 136", "V5·캡션 트랙(빈)"], "nars": report_nars}
json.dump(report, open(out_path.replace(".prproj", ".report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"저장 {out_path}: A2 {len(a2_refs)} · 제거 {removed} · 추가 {len(new_blocks)} · 루트 항목 {len(kept)}+{len(new_cpis)}")
res = verify(out_path, {"V1": (T["V1"], 46), "A1": (T["A1"], 36), "A3": (T["A3"], 10), "A2": (A2, len(a2_refs)), "V2": (T["V2"], 79), "V3": (T["V3"], 34), "V4": (T["V4"], 23)})
res["checks"].append({"check": "나레 클립 길이 = voice.json 실측(±1프레임)", "pass": not mism, "detail": f"27개 중 불일치 {len(mism)}"})
for c in res["checks"]:
    print(("  ✓ " if c["pass"] else "  ✗ ") + c["check"] + "  " + c["detail"])
ok = res["pass"] and not mism
print("전체:", "통과" if ok else "실패")
sys.exit(0 if ok else 1)
