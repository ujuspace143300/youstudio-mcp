#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/스케치코미디/조립_prproj_sk.py — 스케치코미디 편.json → 완성 .prproj (도너 방식).

  도너  : 신병4 EP1 완성 prproj (세로 1080×1920 · 60fps · 컷=가로 원본 하나를 in/out 으로 묾)
  전략  : **삭제 최소화** — 트랙 아이템 계보만 갈아 끼우고, 마스터클립·미디어는
          프로젝트 자산으로 남긴다(미사용 자산은 무해 · 댕글링 위험 제거).
          복제는 전 계보(collect_lineage) + 마스터클립 URef 에서 멈춤 — 확정사실 §1 자립형 원칙.
          블롭은 blob_set_texts(tail relocation)만. 서식·StyleTable 은 안 건드린다.
  트랙  : V1 컷(원본 in/out — 핸들 살아 있음)+A1 원음(Link) · V2 껍데기 mov ·
          V3 제목 · V4 나레 자막 · V5 대사 자막 · A2 나레 wav · A3 비움
  검증  : prproj_lib.verify 7종 + 블롭 재파싱 대조. 프리미어로 여는 것은 사람 몫.

사용: python 조립_prproj_sk.py --timeline <timeline_sk.json> --donor <도너.prproj> --out <완성.prproj>
"""
import argparse, json, os, re, sys, uuid, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, "도너"))
from prproj_lib import (Doc, load, save, esc, rewire, set_child, child, collect_lineage,
                        track_set_items, track_items, verify, parse_blob, blob_set_texts,
                        param_blob, param_set_blob, is_source_text, GRAPHIC_IN, 빈블롭_RE, TPS)

DONOR = {
    "트랙": {"V1": "8cc1efd9-3aa0-49be-88c6-70447b6a0d65", "V2": "e3e60490-5a16-4e51-8152-587962bb9260",
             "V3": "ffd682c9-5d83-4631-971b-05617160dbff", "V4": "e02aa9b4-902f-4c19-8f2f-3c3f4641cc39",
             "V5": "12b91a7e-57e9-4d20-bc47-d71176d6e733", "A1": "ef3342f0-dcb7-4d31-88f0-7d17541ba09e",
             "A2": "391fadd0-3fd0-489a-bd03-bb54b05af6ca", "A3": "45501eac-bc31-4519-a4eb-c05b0aa1e815"},
    "FRAME": 4233600000,          # 60fps 시퀀스 (실측)
    "미디어키": {"원본": "구간_원본_가로", "템플릿": "그래픽_템플릿"},
}
FRAME = DONOR["FRAME"]


def frame_ticks(sec):
    return int(round(float(sec) * TPS / FRAME)) * FRAME


def strip_node(b):
    return re.sub(r"\n\t+<Node Version=\"1\">.*?</Node>", "", b, count=1, flags=re.S)


def set_span(b, t0, t1):
    inner = (f"<Start>{t0}</Start>\n\t\t\t\t" if t0 else "") + f"<End>{t1}</End>"
    return re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>",
                  f'<TrackItem Version="4">\n\t\t\t\t{inner}\n\t\t\t</TrackItem>', b, flags=re.S)


def kind(b):
    return re.match(r"\s*<(\w+)", b).group(1)


class Alloc:
    def __init__(self, doc):
        self.n = doc.max_id() + 1

    def __call__(self):
        self.n += 1
        return self.n - 1


def mc_of(doc, item):
    sub = int(re.search(r'<SubClip ObjectRef="(\d+)"', doc.get(item)).group(1))
    return re.search(r'<MasterClip ObjectURef="([^"]+)"', doc.get(sub)).group(1)


def media_uid(doc, key):
    for m in re.finditer(r'<Media ObjectUID="([0-9a-f-]+)"', doc.xml):
        b = doc.get_uid(m.group(1))
        p = re.search(r"<ActualMediaFilePath>([^<]*)</ActualMediaFilePath>", b)
        if p and key in p.group(1):
            return m.group(1)
    raise KeyError(key)


def set_param_value(b, value):
    b = re.sub(r"(<StartKeyframe>-91445760000000000,)[^,<]+(,)", rf"\g<1>{value}\g<2>", b, count=1)
    if "<CurrentValue>" in b:
        b = set_child(b, "CurrentValue", str(value))
    return b


def swap_media(doc, uid, new_path, dur_s, vrect=None, v_rate=None, a_rate=None):
    """미디어 파일 교체 — 어긋나도 프리미어 「미디어 다시 연결」로 복구 가능한 층."""
    b = doc.get_uid(uid)
    fname = os.path.basename(new_path)
    for tag, val in (("FilePath", new_path), ("ActualMediaFilePath", new_path),
                     ("Title", fname), ("RelativePath", fname), ("MediaFileHistory0", fname),
                     ("FileKey", str(uuid.uuid4()))):
        if f"<{tag}>" in b:
            b = set_child(b, tag, esc(val))
    doc.replace_uid(uid, b)
    b = doc.get_uid(uid)
    for tag in ("VideoStream", "AudioStream"):
        for r in re.findall(rf'<{tag} ObjectRef="(\d+)"/>', b):
            sb = doc.get(int(r))
            rate_m = re.search(r"<FrameRate>(\d+)</FrameRate>", sb)
            rate = int(rate_m.group(1)) if rate_m else TPS
            if tag == "VideoStream" and v_rate:
                sb = set_child(sb, "FrameRate", str(v_rate))
                rate = v_rate
            if tag == "AudioStream" and a_rate:
                sb = set_child(sb, "FrameRate", str(a_rate))
                rate = a_rate
            dur = (int(dur_s * TPS) // rate) * rate
            sb = set_child(sb, "Duration", str(dur))
            if vrect and tag == "VideoStream":
                sb = re.sub(r"<FrameRect>0,0,\d+,\d+</FrameRect>", f"<FrameRect>0,0,{vrect[0]},{vrect[1]}</FrameRect>", sb)
            doc.replace(int(r), sb)
    for m in re.finditer(r'^\t<(\w+MediaSource) ObjectID="(\d+)"', doc.xml, re.M):
        blk = doc.get(int(m.group(2)))
        if f'<Media ObjectURef="{uid}"/>' not in blk:
            continue
        if "<OriginalDuration>" in blk:
            blk = set_child(blk, "OriginalDuration", str(int(dur_s * TPS)))
        if vrect:
            blk = re.sub(r"<FrameRect>0,0,\d+,\d+</FrameRect>", f"<FrameRect>0,0,{vrect[0]},{vrect[1]}</FrameRect>", blk)
        doc.replace(int(m.group(2)), blk)


def lineage_stopped(doc, item):
    """아이템의 복제/삭제 대상 계보 — 마스터클립(URef)에서 멈춘다. (ids, uids, stop)"""
    stop = set()
    try:
        stop = {mc_of(doc, item)}
    except Exception:
        pass
    ids, uids = collect_lineage(doc, [item], stop=stop)
    return ids - stop, uids - stop, stop


def clone_item(doc, item, alloc, new_blocks, span=None, inout=None, name=None,
               params=None, texts=None):
    """아이템 전 계보 복제 (마스터클립은 공유). texts 를 주면 소스 텍스트 블롭도 바꾼다."""
    ids, uids, _stop = lineage_stopped(doc, item)
    ids = sorted(ids, key=int)
    idmap = {int(k): alloc() for k in ids}
    uidmap = {u: str(uuid.uuid4()) for u in uids}
    blob_got = None
    for k in ids:
        b = rewire(doc.get(k), idmap, uidmap)
        kd = kind(b)
        if kd.endswith("ClipTrackItem"):
            b = strip_node(b)
            b = re.sub(r"\n\t\t\t<(Head|Tail)Transition ObjectRef=\"\d+\"/>", "", b)
            if span:
                b = set_span(b, span[0], span[1])
            if kd == "AudioClipTrackItem":
                b = set_child(b, "ID", str(uuid.uuid4()))
        elif kd in ("VideoClip", "AudioClip"):
            b = strip_node(b)
            b = set_child(b, "ClipID", str(uuid.uuid4()))
            if inout and child(b, "InPoint") is not None:
                b = set_child(set_child(b, "InPoint", str(inout[0])), "OutPoint", str(inout[1]))
        elif kd == "SubClip" and name:
            b = set_child(b, "Name", esc(name))
        elif kd == "VideoFilterComponent" and name:
            b = re.sub(r"<InstanceName>.*?</InstanceName>", "<InstanceName>" + esc(name) + "</InstanceName>", b, flags=re.S)
        elif texts is not None and is_source_text(b):
            if 빈블롭_RE.search(b):
                채움 = param_blob(doc.get(k), doc.xml)
                b = 빈블롭_RE.sub(lambda m: f'<StartKeyframeValue Encoding="base64" BinaryHash="{m.group(1)}">{채움}</StartKeyframeValue>', b, count=1)
            b64, binhash, info = blob_set_texts(param_blob(b), texts)
            b = param_set_blob(b, b64, binhash)
            blob_got = "".join(r["text"] for r in info["runs"])
        elif params:
            nm = re.search(r"<Name>([^<]*)</Name>", b)
            if nm and nm.group(1) in params and "<StartKeyframe>" in b:
                b = set_param_value(b, params[nm.group(1)])
        new_blocks.append(b)
    for u in uids:
        new_blocks.append(rewire(doc.get_uid(u), idmap, uidmap))
    return idmap[int(item)], blob_got, uidmap


def remove_old_items(doc, uid):
    """트랙의 옛 아이템 계보를 지운다 — 마스터클립·미디어는 자산으로 남긴다."""
    rm_i, rm_u = set(), set()
    clips, trans = track_items(doc, uid)
    for it in list(clips) + list(trans):
        ids, uids, _ = lineage_stopped(doc, it)
        rm_i |= ids
        rm_u |= uids
    return rm_i, rm_u


def text_runs(doc, item):
    """견본 텍스트 아이템의 런 수"""
    ids, _u, _s = lineage_stopped(doc, item)
    st = [i for i in ids if is_source_text(doc.get(i))][0]
    return len(parse_blob(param_blob(doc.get(st), doc.xml))["runs"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--donor", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tl = json.load(open(a.timeline, encoding="utf-8"))
    out_path = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    doc = Doc(load(a.donor))
    alloc = Alloc(doc)
    T = DONOR["트랙"]
    seq_uid = re.search(r'<Sequence ObjectUID="([0-9a-f-]+)"', doc.xml).group(1)
    total = frame_ticks(tl["total_s"])
    box = tl["box"]

    # 견본 (각 트랙 첫 아이템)
    tpl_v1 = track_items(doc, T["V1"])[0][0]
    tpl_a1 = track_items(doc, T["A1"])[0][0]
    tpl_a2 = track_items(doc, T["A2"])[0][0]
    tpl_v3 = track_items(doc, T["V3"])[0][0]
    tpl_v4 = track_items(doc, T["V4"])[0][0]
    tpl_v5 = track_items(doc, T["V5"])[0][0]
    runs = {"title": text_runs(doc, tpl_v3), "narr": text_runs(doc, tpl_v4), "dlg": text_runs(doc, tpl_v5)}
    print(f"견본 런 수: {runs}", file=sys.stderr)

    new_blocks, links, v_refs, a_refs = [], [], [], []

    # ── ① 컷 (V1+A1+Link) — 원본 하나를 in/out 으로 문다 (핸들 생존) ─────────
    cut_params = {"위치": box["pos"], "비율 조정": box["scale"], "폭 비율 조정": box["scale"]}
    for cut in tl["picture"]:
        t0, t1 = frame_ticks(cut["t0"]), frame_ticks(cut["t1"])
        si = int(cut["src_in"] * TPS)
        so = si + (t1 - t0)
        vi, _b, _u = clone_item(doc, tpl_v1, alloc, new_blocks, span=(t0, t1), inout=(si, so),
                                name=cut["name"], params=cut_params)
        ai, _b, _u = clone_item(doc, tpl_a1, alloc, new_blocks, span=(t0, t1), inout=(si, so), name=cut["name"])
        lid = alloc()
        new_blocks.append(f'\t<Link ObjectID="{lid}" ClassID="149d4ea5-a7d4-4b34-9bb7-16d783904bf2" Version="1">\n\t\t<TrackItemGroup Version="1">\n\t\t\t<TrackItems Version="1">\n\t\t\t\t<TrackItem Index="0" ObjectRef="{vi}"/>\n\t\t\t\t<TrackItem Index="1" ObjectRef="{ai}"/>\n\t\t\t</TrackItems>\n\t\t</TrackItemGroup>\n\t</Link>')
        links.append(lid)
        v_refs.append(vi)
        a_refs.append(ai)

    # ── ② 나레 (A2) — 계보 복제 + 우리 wav (미디어까지 새로) ────────────────
    a2_refs, new_cpis = [], []
    mc_nar = mc_of(doc, tpl_a2)
    cpi_nar = None
    for m in re.finditer(r'^\t<ClipProjectItem ObjectUID="([^"]+)"', doc.xml, re.M):
        if f'<MasterClip ObjectURef="{mc_nar}"/>' in doc.get_uid(m.group(1)):
            cpi_nar = m.group(1)
            break
    for nar in tl["narration"]:
        wav = os.path.normpath(nar["wav"])
        fname = os.path.basename(wav)
        w = wave.open(wav)
        rate, ch_, sw, nframes = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        w.close()
        assert ch_ == 1 and sw == 2 and TPS % rate == 0, (fname, rate, ch_, sw)
        tick_rate = TPS // rate
        dur_ticks = nframes * tick_rate
        t0 = frame_ticks(nar["t0"])
        length = min(frame_ticks(nar["t1"]) - t0, (dur_ticks // FRAME) * FRAME)
        t1 = t0 + length
        # 나레는 마스터클립·미디어까지 통째 복제해야 파일을 갈아 끼울 수 있다 — stop 없이 전부
        ids, uids = collect_lineage(doc, [tpl_a2, cpi_nar])
        ids = sorted({i for i in ids if "AudioTransitionTrackItem" not in doc.get(i)}, key=int)
        idmap = {int(k): alloc() for k in ids}
        uidmap = {u: str(uuid.uuid4()) for u in uids}

        def emit(b):
            k = kind(b)
            if k == "AudioClipTrackItem":
                b = set_child(set_span(strip_node(b), t0, t1), "ID", str(uuid.uuid4()))
                b = re.sub(r"\n\t\t\t<(Head|Tail)Transition ObjectRef=\"\d+\"/>", "", b)
            elif k == "AudioClip":
                b = strip_node(b)
                b = set_child(b, "ClipID", str(uuid.uuid4()))
                if child(b, "InPoint") is not None:
                    b = set_child(set_child(b, "InPoint", "0"), "OutPoint", str(length))
            elif k == "SubClip":
                b = set_child(b, "Name", esc("나레 " + nar["text"][:20]))
            elif k == "AudioStream":
                b = set_child(set_child(b, "FrameRate", str(tick_rate)), "Duration", str(dur_ticks))
            elif k == "AudioMediaSource":
                b = set_child(b, "OriginalDuration", str(dur_ticks))
            elif k == "ClipLoggingInfo":
                b = set_child(set_child(b, "ClipName", esc(fname)), "MediaOutPoint", str(dur_ticks))
            elif k == "Markers":
                b = set_child(b, "LastContentState", str(uuid.uuid4()))
            elif k == "Media":
                for tag, val in (("FilePath", wav), ("ActualMediaFilePath", wav), ("Title", fname),
                                 ("RelativePath", fname), ("MediaFileHistory0", fname),
                                 ("FileKey", str(uuid.uuid4())), ("ConformedAudioRate", str(tick_rate))):
                    if f"<{tag}>" in b:
                        b = set_child(b, tag, esc(val))
            elif k in ("MasterClip", "ClipProjectItem"):
                b = set_child(b, "Name", esc(fname))
            return b

        for k in ids:
            new_blocks.append(emit(rewire(doc.get(k), idmap, uidmap)))
        for u in uids:
            new_blocks.append(emit(rewire(doc.get_uid(u), idmap, uidmap)))
        a2_refs.append(idmap[int(tpl_a2)])
        new_cpis.append(uidmap[cpi_nar])

    # ── ③ 텍스트 — 제목(V3)·나레 자막(V4)·대사(V5) ──────────────────────────
    refs = {"title": [], "narr": [], "dlg": []}
    tpl_map = {"title": tpl_v3, "narr": tpl_v4, "dlg": tpl_v5}
    blob_bad = []
    for cue in tl["cues"]:
        lane = cue["lane"]
        t0, t1 = frame_ticks(cue["t0"]), max(frame_ticks(cue["t1"]), frame_ticks(cue["t0"]) + FRAME)
        texts = [cue["text"]] + [""] * (runs[lane] - 1)
        gi = GRAPHIC_IN
        ref, got, _u = clone_item(doc, tpl_map[lane], alloc, new_blocks, span=(t0, t1),
                                  inout=(gi, gi + (t1 - t0)),
                                  name=cue["text"].replace("\r", " ")[:40], texts=texts)
        refs[lane].append(ref)
        if got != cue["text"]:
            blob_bad.append({"lane": lane, "want": cue["text"], "got": got})

    # ── ④ 템플릿(V2) — 아이템 span·클립 out 연장 (미디어는 아래서 교체) ───────
    b = doc.get(track_items(doc, T["V2"])[0][0])
    doc.replace(track_items(doc, T["V2"])[0][0], set_span(b, 0, total))
    v2_item = track_items(doc, T["V2"])[0][0]
    sub2 = int(re.search(r'<SubClip ObjectRef="(\d+)"', doc.get(v2_item)).group(1))
    clip2 = int(re.search(r'<Clip ObjectRef="(\d+)"', doc.get(sub2)).group(1))
    doc.replace(clip2, set_child(set_child(doc.get(clip2), "InPoint", "0"), "OutPoint", str(total)))

    # ── ⑤a 삭제 후보 수집 (배선 전에 — 배선하면 track_items 가 새 것을 돌려준다) ──
    rm_ids, rm_uids = set(), set()
    for uid in (T["V1"], T["A1"], T["A2"], T["A3"], T["V3"], T["V4"], T["V5"]):
        i_, u_ = remove_old_items(doc, uid)
        rm_ids |= i_
        rm_uids |= u_
    # 옛 Link 오브젝트 — 시퀀스 LinkContainer 를 갈아 끼우면 고아가 되므로 후보에 넣는다
    rm_ids |= {x for x in re.findall(r'<Link Index="\d+" ObjectRef="(\d+)"/>', doc.get_uid(seq_uid))}
    new_set = {str(r) for r in v_refs + a_refs + a2_refs + refs["title"] + refs["narr"] + refs["dlg"]}
    assert not ({str(x) for x in rm_ids} & new_set), "새 아이템이 제거 목록에 들어감"

    # ── ⑥ 배선 ────────────────────────────────────────────────────────────────
    doc.append(new_blocks)
    track_set_items(doc, T["V1"], v_refs)
    track_set_items(doc, T["A1"], a_refs, transitions=[])
    track_set_items(doc, T["A2"], a2_refs, transitions=[])
    track_set_items(doc, T["A3"], [], transitions=[])
    track_set_items(doc, T["V3"], refs["title"], transitions=[])
    track_set_items(doc, T["V4"], refs["narr"], transitions=[])
    track_set_items(doc, T["V5"], refs["dlg"], transitions=[])

    seq = doc.get_uid(seq_uid)
    links_inner = "".join(f'\n\t\t\t\t\t<Link Index="{i}" ObjectRef="{l}"/>' for i, l in enumerate(links))
    seq = re.sub(r'<LinkContainer Version="1">.*?</LinkContainer>',
                 f'<LinkContainer Version="1">\n\t\t\t\t<Links Version="1">{links_inner}\n\t\t\t\t</Links>\n\t\t\t</LinkContainer>', seq, count=1, flags=re.S)
    for tag in ("MZ.WorkOutPoint", "MZ.OutPoint"):
        if f"<{tag}>" in seq:
            seq = set_child(seq, tag, str(total))
    seq = set_child(seq, "Name", esc(tl["title"]))
    doc.replace_uid(seq_uid, seq)

    # ── ⑤b 참조 GC + 삭제 — 살아남는 블록이 아직 참조하는 후보는 남긴다 ───────
    #   (트랙 아이템 계보와 마스터클립 계보가 Markers 등을 공유한다 — 실측 2026-09-01)
    rm_all = {str(x) for x in rm_ids} | set(rm_uids)
    referrers = {}
    for bm in re.finditer(r'^\t<(\w+) (?:ObjectU?ID)="([^"]+)"[^>]*>(.*?)^\t</\1>', doc.xml, re.M | re.S):
        owner = bm.group(2)
        for t in re.findall(r'Object(?:Ref|URef)="([^"]+)"', bm.group(3)):
            referrers.setdefault(t, set()).add(owner)
    changed = True
    while changed:
        changed = False
        for cand in list(rm_all):
            if any(r not in rm_all for r in referrers.get(cand, ())):
                rm_all.discard(cand)
                changed = True
    print(f"참조 GC — 후보 {len(rm_ids) + len(rm_uids)} 중 공유돼 남긴 블록 "
          f"{len(rm_ids) + len(rm_uids) - len(rm_all)}개", file=sys.stderr)
    removed = doc.remove_many(rm_all)
    rm_uids = {u for u in rm_uids if u in rm_all}

    root_m = re.search(r'^\t<RootProjectItem ObjectUID="([^"]+)"', doc.xml, re.M)
    root = doc.get_uid(root_m.group(1))
    im = re.search(r'(<Items Version="\d+">)(.*?)(</Items>)', root, re.S)
    kept = [u for u in re.findall(r'<Item Index="\d+" ObjectURef="([^"]+)"/>', im.group(2)) if u not in rm_uids]
    items = "".join(f'\n\t\t\t\t<Item Index="{i}" ObjectURef="{u}"/>' for i, u in enumerate(kept + new_cpis))
    doc.replace_uid(root_m.group(1), root[:im.start()] + im.group(1) + items + "\n\t\t\t" + im.group(3) + root[im.end():])

    # ── ⑦ 미디어 교체 — 원본(1920×1080 23.976)·템플릿(길이만) ────────────────
    swap_media(doc, media_uid(doc, DONOR["미디어키"]["원본"]), tl["source"], tl["source_dur_s"],
               vrect=(1920, 1080), v_rate=10594584000, a_rate=tl.get("src_audio_tickrate"))
    swap_media(doc, media_uid(doc, DONOR["미디어키"]["템플릿"]), tl["template"], tl["total_s"] + 1)

    save(out_path, doc.xml)

    want = {"V1": (T["V1"], len(v_refs)), "A1": (T["A1"], len(a_refs)), "A2": (T["A2"], len(a2_refs)),
            "A3": (T["A3"], 0), "V2": (T["V2"], 1), "V3": (T["V3"], len(refs["title"])),
            "V4": (T["V4"], len(refs["narr"])), "V5": (T["V5"], len(refs["dlg"]))}
    res = verify(out_path, want)
    res["checks"].append({"check": "블롭 재파싱 = 넣은 텍스트", "pass": not blob_bad, "detail": f"불일치 {len(blob_bad)}"})
    ok = res["pass"] and not blob_bad
    for c in res["checks"]:
        print(("  [OK] " if c["pass"] else "  [X] ") + str(c["check"]) + "  " + str(c.get("detail", "")))
    print(f"저장 {out_path}: 컷 {len(v_refs)} · 나레 {len(a2_refs)} · 제목 {len(refs['title'])} · "
          f"나레자막 {len(refs['narr'])} · 대사 {len(refs['dlg'])} · 제거 {removed}블록 · 추가 {len(new_blocks)}블록")
    print("전체: " + ("통과" if ok else "실패"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
