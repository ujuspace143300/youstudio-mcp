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
                        blob_set_fonts, blob_set_colors, param_blob, param_set_blob,
                        is_source_text, GRAPHIC_IN, 빈블롭_RE, TPS)

# ★자막 글꼴(2026-09-01 사장님: 페이퍼로지) — 도너 서체(강원교육모두체)를 이걸로 갈아 끼운다.
#   PS 명은 fontTools 실측. 웨이트는 신병4 납품이 실제로 쓰던 9Black.
자막폰트 = "Paperlogy-9Black"

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


def media_uids(doc, key):
    """key 를 경로에 품은 Media **전부** — 키트 도너는 같은 파일에 미디어 객체를 컷마다 만든다(실측 17개).
       하나만 바꾸면 마스터클립이 다른 객체를 물어 오프라인이 난다 (2026-09-01 실측)."""
    out = []
    for m in re.finditer(r'<Media ObjectUID="([0-9a-f-]+)"', doc.xml):
        b = doc.get_uid(m.group(1))
        p = re.search(r"<ActualMediaFilePath>([^<]*)</ActualMediaFilePath>", b)
        if p and key in p.group(1):
            out.append(m.group(1))
    if not out:
        raise KeyError(key)
    return out


def set_param_value(b, value):
    b = re.sub(r"(<StartKeyframe>-91445760000000000,)[^,<]+(,)", rf"\g<1>{value}\g<2>", b, count=1)
    if "<CurrentValue>" in b:
        b = set_child(b, "CurrentValue", str(value))
    return b


def swap_media(doc, uid, new_path, dur_s, vrect=None, v_rate=None, a_rate=None, old_key=None):
    """미디어 파일 교체 — 어긋나도 프리미어 「미디어 다시 연결」로 복구 가능한 층."""
    b = doc.get_uid(uid)
    fname = os.path.basename(new_path)
    for tag, val in (("FilePath", new_path), ("ActualMediaFilePath", new_path),
                     ("Title", fname), ("RelativePath", fname), ("MediaFileHistory0", fname),
                     ("FileKey", str(uuid.uuid4())),
                     ("ConformedAudioPath", ""), ("PeakFilePath", "")):   # 캐시 경로는 비우면 재생성된다
        if f"<{tag}>" in b:
            b = set_child(b, tag, esc(val))
    if old_key:   # RelativePath 등이 블록 안에 여러 번(히스토리) — 옛 이름이 든 텍스트 노드 전부 치환
        b = re.sub(r">([^<]*" + re.escape(old_key) + r"[^<]*)<", ">" + esc(fname) + "<", b)
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
            if old_key:
                sb = re.sub(r">([^<]*" + re.escape(old_key) + r"[^<]*)<", ">" + esc(fname) + "<", sb)
            doc.replace(int(r), sb)
    if a_rate and "<ConformedAudioRate>" in doc.get_uid(uid):
        doc.replace_uid(uid, set_child(doc.get_uid(uid), "ConformedAudioRate", str(a_rate)))
    for m in re.finditer(r'^\t<(\w+MediaSource) ObjectID="(\d+)"', doc.xml, re.M):
        blk = doc.get(int(m.group(2)))
        if f'<Media ObjectURef="{uid}"/>' not in blk:
            continue
        if "<OriginalDuration>" in blk:
            blk = set_child(blk, "OriginalDuration", str(int(dur_s * TPS)))
        if vrect:
            blk = re.sub(r"<FrameRect>0,0,\d+,\d+</FrameRect>", f"<FrameRect>0,0,{vrect[0]},{vrect[1]}</FrameRect>", blk)
        if v_rate and m.group(1).startswith("Video") and "<FrameRate>" in blk:
            blk = set_child(blk, "FrameRate", str(v_rate))
        if a_rate and m.group(1).startswith("Audio") and "<FrameRate>" in blk:
            blk = set_child(blk, "FrameRate", str(a_rate))
        if old_key:
            blk = re.sub(r">([^<]*" + re.escape(old_key) + r"[^<]*)<", ">" + esc(fname) + "<", blk)
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
               params=None, texts=None, color=None):
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
            b64, binhash, info = blob_set_fonts(b64, 자막폰트)     # 페이퍼로지(2026-09-01)
            if color:                                              # 화자별 색(2026-09-02)
                b64, binhash, info = blob_set_colors(b64, [list(color)] * len(info["runs"]))
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

    # ── ① 컷 (V1+A1+Link) — 원본 하나를 in/out 으로 문다 (핸들 생존).
    #    모션은 컷별(box) — 번인 자막 잘라내기 + 얼굴 중심 (2026-09-01)
    #    ★나레이션 덕킹(2026-09-01 사장님: TTS 가 원음에 묻힌다) — 나레 창과 겹치는 컷의
    #    원음(A1)을 조각내 가운데 조각의 «레벨»을 -15dB(도너·원조 조립기 실측값)로 내린다.
    LEVEL_DUCK = "0.031653400511"        # -15dB (볼케이노 규격 컷_오디오_덕킹 실측 문자열)
    nar_pad = 0.2
    nar_wins = [(frame_ticks(n["t0"] - nar_pad), frame_ticks(n["t1"] + nar_pad)) for n in tl["narration"]]
    duck_cnt = 0
    for cut in tl["picture"]:
        cbox = cut.get("box", box)
        cut_params = {"위치": cbox["pos"], "비율 조정": cbox["scale"], "폭 비율 조정": cbox["scale"]}
        t0, t1 = frame_ticks(cut["t0"]), frame_ticks(cut["t1"])
        si = int(cut["src_in"] * TPS)
        so = si + (t1 - t0)
        vi, _b, _u = clone_item(doc, tpl_v1, alloc, new_blocks, span=(t0, t1), inout=(si, so),
                                name=cut["name"], params=cut_params)
        # A1 — 나레 창 경계로 조각낸다 (겹침 없으면 1조각)
        pieces = [(t0, t1, False)]
        for n0, n1 in nar_wins:
            nxt = []
            for p0, p1, dk in pieces:
                if dk or p1 <= n0 or p0 >= n1:
                    nxt.append((p0, p1, dk))
                    continue
                if p0 < n0:
                    nxt.append((p0, n0, False))
                nxt.append((max(p0, n0), min(p1, n1), True))
                if p1 > n1:
                    nxt.append((n1, p1, False))
            pieces = nxt
        first_ai = None
        for p0, p1, dk in pieces:
            if p1 - p0 < FRAME:
                continue
            ai, _b2, _u2 = clone_item(doc, tpl_a1, alloc, new_blocks, span=(p0, p1),
                                      inout=(si + (p0 - t0), si + (p1 - t0)),
                                      name=cut["name"] + (" (덕킹)" if dk else ""),
                                      params=({"레벨": LEVEL_DUCK} if dk else None))
            a_refs.append(ai)
            duck_cnt += 1 if dk else 0
            if first_ai is None:
                first_ai = ai
        lid = alloc()
        new_blocks.append(f'\t<Link ObjectID="{lid}" ClassID="149d4ea5-a7d4-4b34-9bb7-16d783904bf2" Version="1">\n\t\t<TrackItemGroup Version="1">\n\t\t\t<TrackItems Version="1">\n\t\t\t\t<TrackItem Index="0" ObjectRef="{vi}"/>\n\t\t\t\t<TrackItem Index="1" ObjectRef="{first_ai}"/>\n\t\t\t</TrackItems>\n\t\t</TrackItemGroup>\n\t</Link>')
        links.append(lid)
        v_refs.append(vi)
    if duck_cnt:
        print(f"나레 덕킹 조각 {duck_cnt}개 (-15dB)", file=sys.stderr)

    # ── ② 나레 (A2) — 계보 복제 + 우리 wav (미디어까지 새로) ────────────────
    a2_refs, a3_sfx, new_cpis = [], [], []
    mc_nar = mc_of(doc, tpl_a2)
    cpi_nar = None
    for m in re.finditer(r'^\t<ClipProjectItem ObjectUID="([^"]+)"', doc.xml, re.M):
        if f'<MasterClip ObjectURef="{mc_nar}"/>' in doc.get_uid(m.group(1)):
            cpi_nar = m.group(1)
            break
    # 나레(A2) + 효과음(A3, 2026-09-02 사장님 승인) — 둘 다 wav 클립이라 같은 복제 경로를 쓴다
    소리들 = [(n, "A2") for n in tl["narration"]] + [(s, "A3") for s in tl.get("sfx", [])]
    for nar, 소리트랙 in 소리들:
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
                라벨 = nar["text"][:24] if 소리트랙 == "A3" else "나레 " + nar["text"][:20]
                b = set_child(b, "Name", esc(라벨))
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
        (a2_refs if 소리트랙 == "A2" else a3_sfx).append(idmap[int(tpl_a2)])
        new_cpis.append(uidmap[cpi_nar])

    # ── ③ 텍스트 — 제목(V3)·나레 자막(V4)·대사(V5) ──────────────────────────
    refs = {"title": [], "narr": [], "dlg": []}
    tpl_map = {"title": tpl_v3, "narr": tpl_v4, "dlg": tpl_v5}
    blob_bad = []
    dlg_colors = []                     # refs["dlg"] 와 나란히 — 층 분리(⑥b)에 쓴다
    # 제목 클론은 화면 밖(y 1.8)으로 — 보이는 제목은 껍데기가 담당한다 (2026-09-01)
    lane_params = {"title": {"위치": tl.get("title_pos", "0.5:1.8")}, "narr": None, "dlg": None}
    for cue in tl["cues"]:
        lane = cue["lane"]
        t0, t1 = frame_ticks(cue["t0"]), max(frame_ticks(cue["t1"]), frame_ticks(cue["t0"]) + FRAME)
        texts = [cue["text"]] + [""] * (runs[lane] - 1)
        gi = GRAPHIC_IN
        ref, got, _u = clone_item(doc, tpl_map[lane], alloc, new_blocks, span=(t0, t1),
                                  inout=(gi, gi + (t1 - t0)),
                                  name=cue["text"].replace("\r", " ")[:40], texts=texts,
                                  params=lane_params[lane], color=cue.get("color"))
        refs[lane].append(ref)
        if lane == "dlg":
            dlg_colors.append(tuple(cue["color"]) if cue.get("color") else None)
        if got != cue["text"]:
            blob_bad.append({"lane": lane, "want": cue["text"], "got": got})
    assert refs["title"], "제목 클론이 없다 — V3 를 비우면 프리미어가 거부한다(2026-09-01 실측). 준비 스크립트가 title 큐를 내야 한다"

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
    track_set_items(doc, T["A3"], a3_sfx, transitions=[])
    track_set_items(doc, T["V3"], refs["title"], transitions=[])
    track_set_items(doc, T["V4"], refs["narr"], transitions=[])

    # ── ⑥b 화자별 층 분리 (2026-09-02 사장님: 색깔별로 트랙을 나눠라) ─────────
    #    V5 = 기본색(화자1). 다른 색은 V5 블록을 본떠 만든 새 트랙 V6·V7·… 에 얹는다.
    #    실측 구조: 트랙 = VideoClipTrack 블록(ObjectUID·<ID>·<Index>×3) +
    #    VideoTrackGroup 의 Track 목록·NextTrackID 등록이 전부다.
    색순서 = []
    for c in dlg_colors:
        if c is not None and c not in 색순서:
            색순서.append(c)
    v5_refs = [r for r, c in zip(refs["dlg"], dlg_colors) if c is None]
    분리 = [(c, [r for r, c2 in zip(refs["dlg"], dlg_colors) if c2 == c]) for c in 색순서]
    if not v5_refs and 분리:            # 기본색 줄이 없으면 첫 그룹이 V5 를 지킨다(빈 트랙 방지)
        v5_refs = 분리.pop(0)[1]
    새트랙 = []                          # (라벨, uid, refs, color)
    if 분리:
        tg_m = re.search(r'^\t<VideoTrackGroup ObjectID="(\d+)"', doc.xml, re.M)
        tg_id = int(tg_m.group(1))
        tg = doc.get(tg_id)
        assert T["V5"] in tg, "비디오 트랙 그룹에 V5 가 없다"
        base_blk = doc.get_uid(T["V5"])
        기존트랙 = re.findall(r'<Track Index="\d+" ObjectURef="([^"]+)"/>', tg)
        next_tid = int(child(tg, "NextTrackID"))
        for k, (color, grp) in enumerate(분리):
            nu = str(uuid.uuid4())
            nb = base_blk.replace(f'ObjectUID="{T["V5"]}"', f'ObjectUID="{nu}"', 1)
            nb = re.sub(r"<ID>\d+</ID>", f"<ID>{next_tid + k}</ID>", nb, count=1)
            nb = re.sub(r"<Index>\d+</Index>", f"<Index>{len(기존트랙) + k}</Index>", nb)
            doc.append([nb])
            track_set_items(doc, nu, grp)
            새트랙.append((f"V{6 + k}", nu, grp, color))
        rows = "".join(f'\n\t\t\t\t<Track Index="{i}" ObjectURef="{u}"/>'
                       for i, u in enumerate(기존트랙 + [t[1] for t in 새트랙]))
        tg = re.sub(r'(<Tracks Version="1">).*?(</Tracks>)',
                    lambda m: m.group(1) + rows + "\n\t\t\t" + m.group(2), tg, count=1, flags=re.S)
        tg = set_child(tg, "NextTrackID", str(next_tid + len(새트랙)))
        doc.replace(tg_id, tg)
        print("화자별 층 분리 — V5(기본색) " + str(len(v5_refs)) + "장 · " +
              " · ".join(f"{lb} {len(g)}장 RGB{tuple(c)}" for lb, _u, g, c in 새트랙), file=sys.stderr)
    track_set_items(doc, T["V5"], v5_refs)

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

    # ── ⑦ 미디어 교체 — 스트림 메타를 실제 파일 물성과 **전부** 일치시킨다.
    #    (실측 2026-09-01: 템플릿·나레는 메타=실물이라 정상, 원본은 도너 29.97fps·960 잔재로 오프라인.
    #     길이만 바꾼 판도 오프라인 — 프리미어는 비디오 메타 불일치에 엄격하다)
    src_uids = media_uids(doc, DONOR["미디어키"]["원본"])
    print(f"원본 미디어 객체 {len(src_uids)}개 전부 교체", file=sys.stderr)
    for mu in src_uids:
        swap_media(doc, mu, tl["source"], tl["source_dur_s"], old_key=DONOR["미디어키"]["원본"],
                   vrect=(1920, 1080), v_rate=10594584000, a_rate=tl.get("src_audio_tickrate"))
    for mu in media_uids(doc, DONOR["미디어키"]["템플릿"]):
        swap_media(doc, mu, tl["template"], tl["total_s"] + 1)   # old_key 스크럽은 안 쓴다(자기 경로를 뭉갠다)
        blk = doc.get_uid(mu)
        if "<RelativePath>" in blk:                              # 지문 이름 도입 후 옛 상대경로 잔재 제거(2026-09-03)
            doc.replace_uid(mu, set_child(blk, "RelativePath",
                                          esc("./소스/" + os.path.basename(tl["template"]))))
    # 로깅 블록(ClipLoggingInfo)의 옛 파일명·캐시 경로도 갈아 준다 — 잔재 46개가 전부 여기 있었다(실측)
    for m in re.finditer(r'^\t<ClipLoggingInfo ObjectID="(\d+)"', doc.xml, re.M):
        blk = doc.get(int(m.group(1)))
        # 원본·템플릿 각각의 로깅 잔재를 그 쪽 새 파일명으로 간다 (2026-09-03 템플릿도 추가 —
        # 지문 이름 도입 후 옛 «그래픽_템플릿.mov» RelativePath 가 남아 재연결 위험)
        if DONOR["미디어키"]["원본"] in blk:
            새이름 = os.path.basename(tl["source"])
        elif DONOR["미디어키"]["템플릿"] in blk:
            새이름 = os.path.basename(tl["template"])
        else:
            continue
        for tag, val in (("ClipName", 새이름), ("RelativePath", 새이름), ("Title", 새이름),
                         ("ConformedAudioPath", ""), ("PeakFilePath", "")):
            if f"<{tag}>" in blk:
                blk = set_child(blk, tag, esc(val))
        doc.replace(int(m.group(1)), blk)
    # 옛 템플릿 이름 최종 스크럽(2026-09-03 지문 이름 도입) — 어느 블록에 남았든 전량 치환
    _옛tpl, _새tpl = "그래픽_템플릿.mov", os.path.basename(tl["template"])
    if _새tpl != _옛tpl and _옛tpl in doc.xml:
        n = doc.xml.count(_옛tpl)
        doc.xml = doc.xml.replace(_옛tpl, _새tpl)
        print(f"  옛 템플릿 이름 잔재 {n}건 → {_새tpl} 로 전량 치환", file=sys.stderr)

    # 되읽기 게이트 ① — 파일 전체에 도너 원본 경로·물성 잔재가 없어야 한다
    잔재 = [tok for tok in (DONOR["미디어키"]["원본"], "8475667200", "0,0,1920,960") if tok in doc.xml]
    print(("  [OK] " if not 잔재 else "  [X] ") + f"도너 원본 잔재 0  남음 {잔재}")
    for tok in 잔재:
        for m in list(re.finditer(re.escape(tok), doc.xml))[:3]:
            s = doc.xml.rfind("\n\t<", 0, m.start())
            tag = re.search(r"<(\w+)>[^<]*$", doc.xml[max(0, m.start() - 80):m.start()])
            print(f"    잔재 「{tok}」 in {doc.xml[s:s+80].strip().splitlines()[0][:70]} · 태그 {tag and tag.group(1)}", file=sys.stderr)
    # 되읽기 게이트 ② — V1 첫 컷의 마스터클립 사슬을 따라간 실제 미디어 경로 = 우리 원본
    it0 = track_items(doc, T["V1"])[0][0]
    mc0 = mc_of(doc, it0)
    ids0, uids0 = collect_lineage(doc, [mc0])
    got_paths = set()
    for u in uids0 | {mc0}:
        try:
            p = re.search(r"<ActualMediaFilePath>([^<]*)</ActualMediaFilePath>", doc.get_uid(u))
            if p:
                got_paths.add(p.group(1))
        except KeyError:
            pass
    ok_path = got_paths == {tl["source"]}
    print(("  [OK] " if ok_path else "  [X] ") + f"컷 마스터클립 → 미디어 경로 = 원본.mp4  실제 {sorted(got_paths)}")
    assert not 잔재 and ok_path, "미디어 교체 불완전 — 위 게이트 참조"
    # 패널 표시 이름 — 컷 마스터클립·해당 프로젝트 항목의 도너 이름을 우리 원본으로
    src_name = os.path.basename(tl["source"])
    doc.replace_uid(mc0, set_child(doc.get_uid(mc0), "Name", esc(src_name)))
    for m in re.finditer(r'^\t<ClipProjectItem ObjectUID="([^"]+)"', doc.xml, re.M):
        blk = doc.get_uid(m.group(1))
        if f'<MasterClip ObjectURef="{mc0}"/>' in blk:
            doc.replace_uid(m.group(1), set_child(blk, "Name", esc(src_name)))

    # ── ⑧ 도너 잔여 자산 청소 — 트랙이 안 쓰는 마스터클립(신병 원음·나레·효과음·옛 그래픽)을
    #    프로젝트 패널에서 걷어낸다. 참조 GC 가 공유물(원본 Media 등)은 지키므로 안전하다.
    used_mcs = set()
    for uid in T.values():
        for it in track_items(doc, uid)[0]:
            try:
                used_mcs.add(mc_of(doc, it))
            except Exception:
                pass
    # 시퀀스 계보 전체 = 살아있는 집합. 시퀀스 자신의 마스터클립도 여기 포함된다(실측 — 빠뜨리면
    # 시퀀스가 통째로 쓸려나간다). 후보에서 무조건 뺀다.
    alive_i, alive_u = collect_lineage(doc, [seq_uid])
    alive = {str(x) for x in alive_i} | alive_u | {seq_uid}
    used_mcs |= {u for u in alive_u if u in {m.group(1) for m in re.finditer(r'^\t<MasterClip ObjectUID="([0-9a-f-]+)"', doc.xml, re.M)}}
    root_m = re.search(r'^\t<RootProjectItem ObjectUID="([^"]+)"', doc.xml, re.M)
    root = doc.get_uid(root_m.group(1))
    im = re.search(r'(<Items Version="\d+">)(.*?)(</Items>)', root, re.S)
    kept2, pruned = [], []
    for u in re.findall(r'<Item Index="\d+" ObjectURef="([^"]+)"/>', im.group(2)):
        try:
            blk = doc.get_uid(u)
        except KeyError:
            kept2.append(u)          # 블록을 못 읽으면 건드리지 않는다
            continue
        tag = re.match(r"\s*<(\w+)", blk).group(1)
        mc = re.search(r'<MasterClip ObjectURef="([^"]+)"', blk)
        # ★시퀀스도 ClipProjectItem 로 루트에 산다(마스터클립→SequenceSource→시퀀스 사슬, 실측).
        #   계보가 시퀀스에 닿는 항목은 무조건 남긴다 — 지우면 패널에서 시퀀스가 사라진다.
        is_seq_item = False
        if mc:
            try:
                li, lu = collect_lineage(doc, [mc.group(1)])
                is_seq_item = seq_uid in lu or any("SequenceSource" in doc.get(i)[:120] for i in li)
            except KeyError:
                is_seq_item = True          # 못 읽으면 건드리지 않는다
        if tag == "ClipProjectItem" and mc and not is_seq_item and mc.group(1) not in used_mcs:
            pruned.append(u)
        else:
            if is_seq_item:          # 시퀀스 항목 이름도 우리 제목으로 (도너 이름이 남는다 — 실측)
                doc.replace_uid(u, set_child(blk, "Name", esc(tl["title"])))
            kept2.append(u)
    items2 = "".join(f'\n\t\t\t\t<Item Index="{i}" ObjectURef="{u}"/>' for i, u in enumerate(kept2))
    doc.replace_uid(root_m.group(1), root[:im.start()] + im.group(1) + items2 + "\n\t\t\t" + im.group(3) + root[im.end():])
    cand_i, cand_u = set(), set(pruned)
    for u in pruned:
        try:
            i_, u_ = collect_lineage(doc, [u])
            cand_i |= i_
            cand_u |= u_
        except KeyError:
            pass
    for m in re.finditer(r'^\t<MasterClip ObjectUID="([0-9a-f-]+)"', doc.xml, re.M):
        if m.group(1) in used_mcs:
            continue
        try:
            i_, u_ = collect_lineage(doc, [m.group(1)])
            cand_i |= i_
            cand_u |= u_ | {m.group(1)}
        except KeyError:
            pass
    rm2 = ({str(x) for x in cand_i} | cand_u) - alive
    referrers2 = {}
    for bm in re.finditer(r'^\t<(\w+) (?:ObjectU?ID)="([^"]+)"[^>]*>(.*?)^\t</\1>', doc.xml, re.M | re.S):
        for t in re.findall(r'Object(?:Ref|URef)="([^"]+)"', bm.group(3)):
            referrers2.setdefault(t, set()).add(bm.group(2))
    changed = True
    while changed:
        changed = False
        for cand in list(rm2):
            if any(r not in rm2 for r in referrers2.get(cand, ())):
                rm2.discard(cand)
                changed = True
    cleaned = doc.remove_many(rm2)
    print(f"도너 잔여 자산 청소 — 프로젝트 항목 {len(pruned)}개 정리 · 블록 {cleaned}개 제거", file=sys.stderr)

    # ── ⑨ 도너 표시 이름 최종 청소 + 게이트 — 「신병」 이 한 글자라도 남으면 실패다 ──
    a1_mc = mc_of(doc, track_items(doc, T["A1"])[0][0])
    try:
        doc.replace_uid(a1_mc, set_child(doc.get_uid(a1_mc), "Name", esc("원본 소리")))
        for m in re.finditer(r'^\t<ClipProjectItem ObjectUID="([^"]+)"', doc.xml, re.M):
            blk = doc.get_uid(m.group(1))
            if f'<MasterClip ObjectURef="{a1_mc}"/>' in blk:
                doc.replace_uid(m.group(1), set_child(blk, "Name", esc("원본 소리")))
    except KeyError:
        pass
    for tag in ("Name", "ClipName", "InstanceName", "Title"):
        doc.xml = re.sub(rf"<{tag}>[^<]*신병[^<]*</{tag}>", f"<{tag}>{esc(tl['title'])}</{tag}>", doc.xml)
        doc.xml = re.sub(rf"<{tag}>원음 b\d+</{tag}>", f"<{tag}>원본 소리</{tag}>", doc.xml)
    잔명 = doc.xml.count("신병") + len(re.findall(r"원음 b\d", doc.xml))
    print(("  [OK] " if not 잔명 else "  [X] ") + f"도너 이름 흔적 0  남음 {잔명}")
    assert not 잔명, "도너 이름 흔적이 남았다"

    save(out_path, doc.xml)

    # ── ⑩ 마스터 트랙 오디오 이펙트 — 작업규칙 11번(2026-08-28 사장님 중요 규칙):
    #    멀티밴드 압축기 «브로드캐스트» + 선택적 제한 −3dB. 프리셋은 코드로 못 걸므로
    #    사장님이 손으로 걸어 저장한 도너(2026-09-01, 도너/마스터이펙트_도너_스케치.prproj)에서
    #    볼트 키트의 마스터효과심기 로 통째 복제한다. 없으면 이 prproj 는 미완이다.
    심기 = os.path.expanduser("~/Desktop/유스튜디오-규격서/스크립트/린박스/키트/도구/마스터효과심기.py")
    이펙트도너 = os.path.join(ROOT, "도너", "마스터이펙트_도너_스케치.prproj")
    import subprocess as _sp
    _sp.run([sys.executable, 심기, out_path, "--도너", 이펙트도너], check=True, capture_output=True)
    chk = _sp.run([sys.executable, 심기, out_path, "--확인만"], capture_output=True)
    마스터ok = chk.returncode == 0 and b"\xeb\xa9\x80\xed\x8b\xb0\xeb\xb0\xb4\xeb\x93\x9c" in chk.stdout  # «멀티밴드»
    print(("  [OK] " if 마스터ok else "  [X] ") + "마스터 트랙 이펙트(브로드캐스트·−3dB 제한) 주입")
    assert 마스터ok, "마스터 이펙트 주입 실패 — 작업규칙 11번"

    # ── ⑪ 자막 꾸미기 — 그림자 + 아모르 등장 팝 (2026-09-01 사장님: 아모르팝업 프리셋).
    #    볼트 키트 꾸미기.py — 부품을 새로 만들지 않고 텍스트 «비율 조정» 키프레임만 넣는
    #    검증된 방식(신병4 납품). 키트 모듈은 평면 복사로 스테이징(볼트 한글 경로 import 함정 회피).
    import shutil as _sh, tempfile as _tf, unicodedata as _ud
    kit_src = os.path.expanduser("~/Desktop/유스튜디오-규격서/스크립트/린박스/키트")
    stage = _tf.mkdtemp(prefix="_kit_")
    # ★파일명 NFC 정규화 — 볼트 파일명은 NFD 라 import 소스텍스트 가 파일을 못 찾는다(실측)
    _sh.copy2(os.path.join(kit_src, "꾸미기.py"), os.path.join(stage, "꾸미기.py"))
    for f in os.listdir(os.path.join(kit_src, "도구")):
        if f.endswith(".py"):
            _sh.copy2(os.path.join(kit_src, "도구", f), os.path.join(stage, _ud.normalize("NFC", f)))
    r = _sp.run([sys.executable, os.path.join(stage, "꾸미기.py"), out_path, "--팝없이"], capture_output=True)
    꾸밈ok = r.returncode == 0 and ("넣었다".encode() in r.stdout)
    print(("  [OK] " if 꾸밈ok else "  [X] ") + "자막 꾸미기(그림자) — " +
          (r.stdout.decode(errors="replace").strip().splitlines()[0] if r.stdout else r.stderr.decode(errors="replace")[:80]))
    assert 꾸밈ok, "자막 꾸미기 실패"

    # ── ⑪c 진짜 아모르 팝 — 사장님 프리셋 «팝업자막_아모르» 의 벡터 모션 부품을 단다.
    #    (꾸미기의 텍스트 팝은 기준점이 달라 «이상하게 튄다» — 2026-09-02 사장님 반려.
    #     아모르입히기 = 신병4 납품 검증 도구. 팝 곡선은 아모르 사전설정 150→175/0.182s,
    #     도구가 끝값 100% 로 정규화해 글자 중심에서 되튀게 단다.)
    아모르도구 = os.path.expanduser("~/Desktop/볼케이노 MCP/23. 신병4/ep_0212-0352/아모르입히기.py")
    아모르본 = os.path.expanduser("~/Desktop/유스튜디오-규격서/스크립트/린박스/키트/스타일/아모르_부품.prproj")
    # ★스테이징 사본에 «상자 없음 폴백» 패치 — 우리 블롭은 점 텍스트라 상자 필드(2·3)가 없다.
    #   위치 x = 글자 가로 중심(실측), 세로는 글꼴 크기 절반. 볼트/원본 도구는 건드리지 않는다.
    아모르src = open(아모르도구, encoding="utf-8").read()
    _OLD = ("            상자w = _st.unpack_from('<f', buf, FF[2])[0]\n"
            "            상자h = _st.unpack_from('<f', buf, FF[3])[0]")
    _NEW = """            if 2 in FF and 3 in FF:
                상자w = _st.unpack_from('<f', buf, FF[2])[0]
                상자h = _st.unpack_from('<f', buf, FF[3])[0]
            else:
                상자w = 0.0
                상자h = 65.0
                try:
                    _vt2 = t2 - i32(t2)
                    _r0 = t2 + u16(_vt2 + 4)
                    _vec = _r0 + u32(_r0)
                    _el = _vec + 4
                    _rt = _el + u32(_el)
                    _vt3 = _rt - i32(_rt)
                    _sto = u16(_vt3 + 4 + 2)
                    if _sto:
                        _st4 = _rt + _sto
                        _stt = _st4 + u32(_st4)
                        _vt4 = _stt - i32(_stt)
                        _szo = u16(_vt4 + 4 + 2)
                        if _szo:
                            상자h = _st.unpack_from('<f', buf, _stt + _szo)[0]
                except Exception:
                    pass"""
    assert _OLD in 아모르src, "아모르입히기 패치 지점을 못 찾았다 — 도구가 바뀌었나"
    아모르src = 아모르src.replace(_OLD, _NEW)
    # ★패치 2 — 볼트 아모르_부품의 파라미터 이름은 «위치 (Position)» 처럼 영문 꼬리가 붙는다.
    #   도구의 정확 일치 비교가 전부 스킵돼 붙박이 값·원본 키프레임이 그대로 복제됐다(2026-09-02
    #   실측: 자막이 위로 솟고 175% 로 커짐 — 문서가 경고한 바로 그 사고). 접두 일치로 바꾼다.
    _fixes = [("if 이름 in ('위치', '기준점'):", "if 이름.startswith(('위치', '기준점')):"),
              ("elif 이름 == '비율 조정':", "elif 이름.startswith('비율 조정'):"),
              ("elif 이름 in ('폭 비율 조정', '회전'):", "elif 이름.startswith(('폭 비율 조정', '회전')):"),
              # ★패치 3 — 되튐 보간 보존(2026-09-02 사장님 «원래대로 안 튄다»).
              #   도구의 줄 재작성은 보간 필드를 평평하게 갈아 밋밋해진다. 부품 원본 키프레임
              #   (베지어 오버슈트 5·-134.31·137.03)을 그대로 두고 **값만 끝=100 으로 정규화**한다.
              ("            줄 = ''.join('%d,%g.,0,0,0,0.16666666666666666,0,0.16666666666666666;'\n"
               "                         % (int(round(t3 * TICK)), v * 100.0 / 끝값) for t3, v in 점)",
               "            _kf0 = re.search(r'<Keyframes>([^<]*)</Keyframes>', 도막)\n"
               "            _entries = [e for e in (_kf0.group(1) if _kf0 else '').split(';') if e.strip()]\n"
               "            _끝 = float(_entries[-1].split(',')[1]) if _entries else 100.0\n"
               "            줄 = ''.join(','.join([p[0], '%.6f' % (float(p[1]) * 100.0 / _끝)] + p[2:]) + ';'\n"
               "                         for p in (e.split(',') for e in _entries))")]
    # ★패치 4(2026-09-03 Deep06) — 도구는 1장만 못 찾아도 통째로 중단해 나머지 50장까지
    #   안 달린다. 1장까지는 계속 달고 나가게 완화(2장부터는 원래대로 중단).
    _fixes.append(("if 못:\n    raise SystemExit", "if len(못) > 1:\n    raise SystemExit"))
    # ★패치 5(2026-09-04 Deep08 «3»·«2») — 한글 없는 자막(숫자·부호뿐)은 도구가 블롭에서
    #   글자를 못 읽어 짝을 못 짓는다(2026-08-27 «?!» 제안과 같은 클래스의 잔여 구멍).
    #   위치(한가운데)는 쟀으므로 공통 팝으로 단다 — 글자는 이후 안 쓰인다(그 줄뿐).
    _fixes.append((
        "    if 글자 and 글자 in 팝표 and 가운데:\n"
        "        짝.append((c, 글자, 팝표[글자][0], 가운데))\n"
        "    else:\n",
        "    if 글자 and 글자 in 팝표 and 가운데:\n"
        "        짝.append((c, 글자, 팝표[글자][0], 가운데))\n"
        "    elif 글자 is None and 가운데 and 팝표:\n"
        "        print('  ★글자 못 읽은 장(한글 없는 자막) — 위치는 쟀으므로 공통 팝으로 단다')\n"
        "        짝.append((c, '(글자없음)', next(iter(팝표.values()))[0], 가운데))\n"
        "    else:\n"))
    for _o, _n in _fixes:
        assert _o in 아모르src, "아모르입히기 패치 2 지점을 못 찾았다: " + _o
        아모르src = 아모르src.replace(_o, _n)
    open(os.path.join(stage, "아모르입히기.py"), "w", encoding="utf-8").write(아모르src)
    ass_p = os.path.join(os.path.dirname(out_path), "_아모르팝.ass")
    with open(ass_p, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for cue in tl["cues"]:
            층 = {"dlg": "band_dlg", "narr": "band_narr"}.get(cue["lane"], "title")
            팝 = "{\\fscx150\\t(0,182,\\fscx175)}" if 층 != "title" else ""
            텍 = cue["text"].replace("\r", " ")
            f.write(f"Dialogue: 0,0:00:00.00,0:00:05.00,{층},,0,0,0,,{팝}{텍}\n")
    # ★묵은 기준 사본 제거(2026-09-04 Deep08 재조립 실측) — 도구는 .아모르전 이 «없을 때만»
    #   만든다. 재조립 때 옛 판 기준이 남으면 주입검사 기준 대조가 어긋나 가짜 «탈»이 뜨고,
    #   수가 우연히 맞으면 진짜 탈을 가린다. 이번 판의 직전 상태로 늘 갱신한다.
    _bak = out_path + ".아모르전"
    if os.path.exists(_bak):
        os.remove(_bak)
    r = _sp.run([sys.executable, os.path.join(stage, "아모르입히기.py"), out_path, ass_p,
                 "--본", 아모르본], capture_output=True)
    아모르ok = r.returncode == 0
    tail_out = (r.stdout.decode(errors="replace").strip().splitlines() or [""])[-1]
    print(("  [OK] " if 아모르ok else "  [X] ") + "아모르 팝 부품 — " +
          (tail_out if 아모르ok else r.stderr.decode(errors="replace")[-200:]))
    if not 아모르ok:                       # 실패 진단용 — 어느 장을 못 찾았는지 전체 출력
        전체출력 = r.stdout.decode(errors="replace")
        print(전체출력[-1500:], file=sys.stderr)
        m못 = re.search(r"못 찾은 것 (\d+)장", 전체출력)
        # ★1장까지는 경고로 통과(2026-09-03 Deep06 — 도구가 글자를 못 읽는 장 1개로 편
        #   전체가 막히는 것 방지). 2장부터는 실패. 명단은 위 출력에 있다.
        if m못 and int(m못.group(1)) <= 1:
            print("  ★아모르 미부착 1장 — 경고로 통과 (프리미어에서 눈 확인 필요)")
            아모르ok = True
    assert 아모르ok, "아모르 팝 부품 달기 실패"
    # 꾸미기가 옆에 남기는 «꾸미기전» 백업은 납품 폴더를 어지럽히므로 걷는다
    for f in os.listdir(os.path.dirname(out_path)):
        if "꾸미기전" in f:
            os.remove(os.path.join(os.path.dirname(out_path), f))

    # ── ⑪b 팝 키프레임 시각 보정 — 키트 자막은 소재 0초에서 시작하지만 우리 그래픽 클립은
    #    GRAPHIC_IN(3600초)에서 시작한다. 0초대 키프레임은 재생 구간 밖이라 팝이 안 보인다
    #    (2026-09-01 사장님 «아모르팝업 적용 안 됨» 실측 원인). 시각에 GRAPHIC_IN 을 더한다.
    #   ★블록이 줄바꿈 없이 붙어 나오기도 해서(아모르 도구 출력 실측) 줄 앵커 없이 전수 훑고,
    #   컨테이너 첫 키프레임을 기준으로 GRAPHIC_IN 에 «리베이스»한다 — 꾸미기(0초대)든
    #   부품 원본 시각(10초대)이든 클립 소재 구간 안으로 들어온다.
    xml2 = load(out_path)
    shifted = 0

    def _param_fix(pm):
        nonlocal shifted
        blk = pm.group(0)
        nm = re.search(r"<Name>([^<]*)</Name>", blk)
        if not nm or not any(nm.group(1).startswith(k) for k in ("비율 조정", "폭 비율 조정", "위치", "불투명도", "기준점")):
            return blk
        if "<Keyframes>" not in blk:
            return blk

        def _rebase(mm):
            nonlocal shifted
            entries = [seg for seg in mm.group(1).split(";") if seg.strip()]
            if not entries:
                return mm.group(0)
            base = int(float(entries[0].split(",")[0]))
            if base >= GRAPHIC_IN:
                return mm.group(0)               # 이미 소재 구간 안
            segs = []
            for seg in entries:
                parts = seg.split(",")
                parts[0] = str(int(float(parts[0])) - base + GRAPHIC_IN)
                segs.append(",".join(parts))
            shifted += 1
            return "<Keyframes>" + ";".join(segs) + ";</Keyframes>"

        nb = re.sub(r"<Keyframes>(.*?)</Keyframes>", _rebase, blk, flags=re.S)
        # ★스톱워치 — IsTimeVarying=true 없으면 프리미어가 키프레임을 통째로 무시한다(실측)
        if "<IsTimeVarying>" in nb:
            nb = re.sub(r"<IsTimeVarying>[^<]*</IsTimeVarying>", "<IsTimeVarying>true</IsTimeVarying>", nb)
        else:
            nb = nb.replace("<StartKeyframe>", "<IsTimeVarying>true</IsTimeVarying>\n\t\t<StartKeyframe>", 1)
        return nb

    xml2 = re.sub(r"<(\w+ComponentParam) ObjectID=\"\d+\"[^>]*>(?:(?!</\1>).)*?</\1>", _param_fix, xml2, flags=re.S)
    save(out_path, xml2)
    print(f"  [OK] 팝 키프레임 보정 — 컨테이너 {shifted}개를 소재 구간으로 리베이스 + 스톱워치 켬")

    want = {"V1": (T["V1"], len(v_refs)), "A1": (T["A1"], len(a_refs)), "A2": (T["A2"], len(a2_refs)),
            "A3": (T["A3"], len(a3_sfx)), "V2": (T["V2"], 1), "V3": (T["V3"], len(refs["title"])),
            "V4": (T["V4"], len(refs["narr"])), "V5": (T["V5"], len(v5_refs))}
    for lb, nu, grp, _c in 새트랙:
        want[lb] = (nu, len(grp))
    res = verify(out_path, want)
    res["checks"].append({"check": "블롭 재파싱 = 넣은 텍스트", "pass": not blob_bad, "detail": f"불일치 {len(blob_bad)}"})
    # 되읽기 게이트(2026-09-02) — 층 = 색. 트랙마다 자막 채움색이 그 트랙 색과 전부 같아야 한다.
    doc2 = Doc(load(out_path))
    층색오류 = []
    분리색들 = {tuple(t[3]) for t in 새트랙}
    for lb, uid, _grp, color in [("V5", T["V5"], v5_refs, None)] + [(t[0], t[1], t[2], t[3]) for t in 새트랙]:
        for it in track_items(doc2, uid)[0]:
            ids_, _u, _s = lineage_stopped(doc2, it)
            st = [i for i in ids_ if is_source_text(doc2.get(i))]
            if not st:
                층색오류.append((lb, it, "소스텍스트 없음")); continue
            got = parse_blob(param_blob(doc2.get(st[0]), doc2.xml))["runs"][0].get("color")
            if color is not None and got != list(color):
                층색오류.append((lb, it, got))
            if color is None and got and tuple(got) in 분리색들:
                층색오류.append((lb, it, got))          # 기본색 트랙에 다른 화자 색이 섞임
    res["checks"].append({"check": "트랙별 자막 색 단일(층=색)", "pass": not 층색오류,
                          "detail": f"트랙 {1 + len(새트랙)}개 · 오류 {len(층색오류)} {층색오류[:3]}"})
    # 게이트(2026-09-02 사장님 «템플릿 빠짐») — 템플릿 실물 길이가 시퀀스 총길이 이상이어야 한다
    import subprocess as _sp
    tpl_dur = float(_sp.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", tl["template"]], check=True, capture_output=True).stdout)
    tpl_ok = tpl_dur + 1e-3 >= tl["total_s"]
    res["checks"].append({"check": "템플릿 길이 ≥ 시퀀스 총길이", "pass": tpl_ok,
                          "detail": f"템플릿 {tpl_dur:.2f}s vs 총 {tl['total_s']:.2f}s"})
    ok = res["pass"] and not blob_bad and not 층색오류 and tpl_ok
    for c in res["checks"]:
        print(("  [OK] " if c["pass"] else "  [X] ") + str(c["check"]) + "  " + str(c.get("detail", "")))
    print(f"저장 {out_path}: 컷 {len(v_refs)} · 나레 {len(a2_refs)} · 제목 {len(refs['title'])} · "
          f"나레자막 {len(refs['narr'])} · 대사 {len(refs['dlg'])} · 제거 {removed}블록 · 추가 {len(new_blocks)}블록")
    # ★프리미어 묵은 세션 경고(2026-09-04 Deep08 실측) — 재조립은 템플릿·나레를 내용 해시의
    #   «새 이름»으로 갈고 옛 파일을 지운다. 옛 판을 연 채인 프리미어 세션은 그 순간
    #   미디어 오프라인이 된다(새 prproj 는 멀쩡). 물고 있으면 «저장 없이 닫고 재열기»를 알린다.
    try:
        r_lsof = _sp.run(["lsof", "+D", os.path.dirname(out_path)], capture_output=True, text=True, timeout=20)
        if any("Adobe" in ln or "Premiere" in ln for ln in r_lsof.stdout.splitlines()):
            print("★프리미어가 이 편 폴더를 열고 있다 — 옛 판 세션은 미디어 오프라인이 된다."
                  " 프리미어를 «저장하지 않고» 완전히 닫은 뒤 새 prproj 를 다시 열어라.")
    except Exception:
        pass
    print("전체: " + ("통과" if ok else "실패"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
