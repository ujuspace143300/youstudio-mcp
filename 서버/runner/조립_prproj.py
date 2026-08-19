#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/조립_prproj.py — 도너 사본 → **완성 prproj** 를 한 번에 만든다 (계단 4).

  입력  : timeline.json(subtitle 산출) · voice.json(voice 산출) · 규격 「조립.도너」
  출력  : 완성 prproj + report.json (자기검증 결과 포함)
  단계  : ① 컷(V1/A1/A3 + Link) ② 나레(A2) ③ 자막(V2/V3, V4 비움) — 도너 사본 한 장을 메모리에서 세 번 고친다.
          계단 3-a~d 의 치환 체인(도너/치환_*.py)을 그대로 합친 것이다. 체인은 되돌아갈 지점으로 보관한다.
  검증  : prproj_lib.verify 7규칙 + 나레 길이 대조 + 블롭 재파싱 + timeline 문구·시각 대조. 하나라도 어긋나면 종료코드 1.

사용: python 서버/runner/조립_prproj.py --timeline <timeline.json> --voice <voice.json> --out <완성.prproj> [--report <report.json>]
"""
import argparse, json, os, re, sys, uuid, wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "도너"))          # prproj_lib 는 도너 폴더에 한 벌만 둔다
from prproj_lib import (Doc, load, save, esc, frame_ticks, rewire, set_child, child, collect_lineage,
                        track_set_items, track_items, verify, parse_blob, blob_set_texts, param_blob,
                        param_set_blob, split_runs_words, is_source_text, 이름인가, 빈블롭_RE, GRAPHIC_IN, FRAME_TICKS, TPS)

SPEC = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))
DN = SPEC["조립"]["도너"]
T = DN["트랙_UID"]
S = DN["견본"]


# ── 견본 찾기 — ObjectID 를 못박지 않는다 (2026-08-19) ────────────────────────
#   도너를 프리미어에서 다시 저장하면 ObjectID 가 다시 매겨질 수 있다. 그때도 안 깨지도록
#   **속성으로 찾고**(자막=트랙+폰트 · 컷/나레=트랙의 첫 아이템), 딸린 ID(사슬·서브클립·클립·필터)는
#   아이템에서 **따라가 얻는다**. 못 찾으면 규격에 적힌 값으로 물러선다.
SHARED_규격 = {"541", "542", "543", "544", "623",       # 옛 도너의 번호 — 못 찾을 때의 폴백
               "ebfb8f8d-03b7-48bc-a7a8-3a00c6414625",  # Graphic MasterClip (모든 자막 SubClip 이 가리킨다)
               "1b62cdc4-0c16-4be3-a9f4-9cbf7a26236f"}  # Graphic Media
_공유캐시 = {}


def 공유계보(doc):
    """Graphic 미디어 계보 = 모든 자막이 함께 쓰는 것. 복제도 삭제도 하지 않는다.
       UID 둘은 왕복해도 안 변하므로 못박고, **번호는 거기서 따라가 얻는다**."""
    키 = id(doc)
    if 키 in _공유캐시:
        return _공유캐시[키]
    mc, md = "ebfb8f8d-03b7-48bc-a7a8-3a00c6414625", "1b62cdc4-0c16-4be3-a9f4-9cbf7a26236f"
    공유 = {mc, md}
    try:
        for uid in (mc, md):                                  # MasterClip → 로깅·채널그룹 · Media → 스트림
            공유 |= {o for _t, o in re.findall(r'<(\w+) ObjectRef="(\d+)"/>', doc.get_uid(uid))}
        for m in re.finditer(r'^	<\w+ ObjectID="(\d+)"', doc.xml, re.M):   # Graphic Media 를 가리키는 MediaSource
            if f'<Media ObjectURef="{md}"/>' in doc.get(int(m.group(1))):
                공유.add(m.group(1))
        assert len(공유) >= 5, 공유
    except Exception:
        공유 = set(SHARED_규격)
    _공유캐시[키] = 공유
    return 공유


def 딸린ID(doc, item, 오디오=False):
    """트랙 아이템 하나에서 사슬·서브클립·클립(·레벨 필터)을 따라가 얻는다"""
    b = doc.get(item)
    chain = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1))
    sub = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
    clip = int(re.search(r'<Clip ObjectRef="(\d+)"', doc.get(sub)).group(1))
    out = {"item": item, "chain": chain, "subclip": sub, "clip": clip}
    if 오디오:
        for comp in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', doc.get(chain)):
            cb = doc.get(int(comp))
            if any(이름인가(doc.get(int(p)), "Level") for p in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', cb)):
                out["filter"] = int(comp); break
    return out


def 보호계보(doc):
    """원본 mp4 미디어 계보 = 지우면 안 되는 것. UID 는 규격에서(왕복해도 안 변한다),
       번호(ObjectID)는 도너에서 **따라가 얻는다**(프리미어가 다시 저장하면 번호가 바뀐다)."""
    M = DN["원본_mp4"]
    보호 = {M["Media_UID"], M["MasterClip_UID"]}
    try:
        b = doc.get_uid(M["Media_UID"])
        for _t, oid in re.findall(r'<(\w+) ObjectRef="(\d+)"/>', b):
            보호.add(oid)
            for _t2, o2 in re.findall(r'<(\w+) ObjectRef="(\d+)"/>', doc.get(int(oid))):
                보호.add(o2)
    except Exception:
        보호 |= {str(M[k]) for k in ("VideoStream", "AudioStream", "VideoMediaSource", "AudioMediaSource", "Markers") if k in M}
    return 보호


def 견본찾기(doc, 말하기=None):
    """규격 「조립.도너.견본」 대신 실제 도너에서 견본을 찾아 돌려준다"""
    from prproj_lib import parse_blob, param_blob, collect_lineage
    말 = 말하기 or (lambda *x: None)
    폰트 = {"자막_나레": SPEC["자막"]["폰트"]["나레"]["PS명"], "자막_대사": SPEC["자막"]["폰트"]["대사"]["PS명"]}
    찾은 = {}
    for 이름, 트랙 in (("자막_나레", "V3"), ("자막_대사", "V2")):
        items, _ = track_items(doc, T[트랙])
        고름 = None
        for it in items:
            try:
                ids, _u = collect_lineage(doc, [it], stop=공유계보(doc))
                st = [i for i in sorted(ids - 공유계보(doc), key=int) if is_source_text(doc.get(i))]
                if not st: continue
                if 폰트[이름] in (parse_blob(param_blob(doc.get(st[0]), doc.xml)).get("fonts") or []):
                    고름 = it; break
            except Exception:
                continue
        찾은[이름] = 딸린ID(doc, 고름) if 고름 else 딸린ID(doc, int(S[이름]["item"]))
        if 고름 and str(고름) != str(S[이름]["item"]):
            말(f"  · 견본 {이름}: 규격 {S[이름]['item']} → 실제 {고름}(폰트 {폰트[이름]} 로 찾음)")
    for 이름, 트랙, 오디오 in (("컷_비디오", "V1", False), ("컷_오디오_덕킹", "A3", True), ("나레", "A2", True)):
        items, _ = track_items(doc, T[트랙])
        고름 = items[0] if items else int(S[이름]["item"])
        찾은[이름] = 딸린ID(doc, 고름, 오디오)
        if str(고름) != str(S[이름]["item"]):
            말(f"  · 견본 {이름}: 규격 {S[이름]['item']} → 실제 {고름}({트랙} 첫 아이템)")
    return 찾은


# ── 공통 도구 ──────────────────────────────────────────────────────────────
def strip_node(b):
    return re.sub(r"\n\t+<Node Version=\"1\">.*?</Node>", "", b, count=1, flags=re.S)


def set_span(b, t0, t1):
    inner = (f"<Start>{t0}</Start>\n\t\t\t\t" if t0 else "") + f"<End>{t1}</End>"
    return re.sub(r"<TrackItem Version=\"4\">.*?</TrackItem>", f'<TrackItem Version="4">\n\t\t\t\t{inner}\n\t\t\t</TrackItem>', b, flags=re.S)


def kind(b):
    return re.match(r'\s*<(\w+)', b).group(1)


class Alloc:
    """ObjectID 발급기 — 세 단계가 하나의 번호대를 나눠 쓴다"""

    def __init__(self, doc):
        self.n = doc.max_id() + 1

    def __call__(self):
        self.n += 1
        return self.n - 1


# ── ① 컷 (계단 3-b) ────────────────────────────────────────────────────────
def 컷치환(doc, tl, alloc, src_path, 견본):
    V1, A1, A3 = T["V1"], T["A1"], T["A3"]
    seq_uid = DN["시퀀스"]["UID"]
    LEVEL_KEEP = S["컷_오디오_유니티"]["level"]
    LEVEL_DUCK = S["컷_오디오_덕킹"]["level"]
    vid_t = 견본["컷_비디오"]
    aud_t = 견본["컷_오디오_덕킹"]
    aud_params = [int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(aud_t["filter"]))]
    aud_secs = [int(x) for x in re.findall(r'<SecondaryContentItem Index="\d+" ObjectRef="(\d+)"/>', doc.get(aud_t["clip"]))]
    tmpl = {oid: doc.get(oid) for oid in list(vid_t.values()) + list(aud_t.values()) + aud_params + aud_secs}
    level_param = [p for p in aud_params if 이름인가(tmpl[p], "Level")][0]

    new_blocks, links = [], []
    v_refs, a1_refs, a3_refs, report_cuts = [], [], [], []
    for pic in tl["picture"]:
        t0, t1 = frame_ticks(pic["t0"]), frame_ticks(pic["t1"])
        si = frame_ticks(pic["src_in"])
        so = si + (t1 - t0)                       # 소스 길이 = 타임라인 길이 (배속 없음)
        assert t1 > t0, pic
        name = f'{pic["k"] + 1:02d} {pic["role"]}' + (f' seg{pic["seg"]}' if pic.get("seg") is not None else "")
        duck = pic["audio"] == "duck"
        level = LEVEL_DUCK if duck else LEVEL_KEEP
        idmap = {oid: alloc() for oid in tmpl}

        def cl(oid, edit=None):
            b = rewire(tmpl[oid], idmap)
            if edit:
                b = edit(b)
            new_blocks.append(b)
            return idmap[oid]

        vi = cl(vid_t["item"], lambda b: set_span(b, t0, t1))
        cl(vid_t["chain"])
        cl(vid_t["subclip"], lambda b: set_child(b, "Name", esc(name)))
        cl(vid_t["clip"], lambda b: set_child(set_child(set_child(b, "ClipID", str(uuid.uuid4())), "InPoint", str(si)), "OutPoint", str(so)))

        def ed_aitem(b):
            b = strip_node(b)
            b = re.sub(r"\n\t\t\t<(Head|Tail)Transition ObjectRef=\"\d+\"/>", "", b)
            return set_child(set_span(b, t0, t1), "ID", str(uuid.uuid4()))

        ai = cl(aud_t["item"], ed_aitem)
        cl(aud_t["chain"])
        cl(aud_t["subclip"], lambda b: set_child(b, "Name", esc(name)))

        def ed_aclip(b):
            b = strip_node(b)
            b = re.sub(r"\n\t\t<Gain>[^<]*</Gain>", "", b)
            return set_child(set_child(set_child(b, "ClipID", str(uuid.uuid4())), "InPoint", str(si)), "OutPoint", str(so))

        cl(aud_t["clip"], ed_aclip)
        cl(aud_t["filter"])
        for p in aud_params:
            if p == level_param:
                cl(p, lambda b: set_child(re.sub(r"<StartKeyframe>-91445760000000000,[0-9.eE+-]+,", f"<StartKeyframe>-91445760000000000,{level},", b), "CurrentValue", level))
            else:
                cl(p)
        for s_ in aud_secs:
            cl(s_)
        lid = alloc()
        new_blocks.append(f'\t<Link ObjectID="{lid}" ClassID="149d4ea5-a7d4-4b34-9bb7-16d783904bf2" Version="1">\n\t\t<TrackItemGroup Version="1">\n\t\t\t<TrackItems Version="1">\n\t\t\t\t<TrackItem Index="0" ObjectRef="{vi}"/>\n\t\t\t\t<TrackItem Index="1" ObjectRef="{ai}"/>\n\t\t\t</TrackItems>\n\t\t</TrackItemGroup>\n\t</Link>')
        links.append(lid)
        v_refs.append(vi)
        (a3_refs if duck else a1_refs).append(ai)
        report_cuts.append({"k": pic["k"], "name": name, "t0_s": pic["t0"], "t1_s": pic["t1"], "src_in_ticks": si, "src_out_ticks": so,
                            "track": "A3" if duck else "A1", "level": level, "v_item": vi, "a_item": ai, "link": lid})

    # ── 도너 옛 것 제거: V1/A1/A3 아이템 + 사슬 + 페이드 + Link ─────────────
    def chain_ids(item):
        b = doc.get(item)
        ids = {item}
        ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1))
        sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
        cl_ = int(re.search(r'<Clip ObjectRef="(\d+)"', doc.get(sc)).group(1))
        ids |= {ch, sc, cl_}
        comps = [int(x) for x in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', doc.get(ch))]
        ids |= set(comps)
        for c in comps:
            ids |= {int(x) for x in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc.get(c))}
        ids |= {int(x) for x in re.findall(r'<SecondaryContentItem Index="\d+" ObjectRef="(\d+)"/>', doc.get(cl_))}
        return ids

    to_remove = set()
    for uid in (V1, A1, A3):
        clips, trans = track_items(doc, uid)
        to_remove |= set(trans)
        for it in clips:
            to_remove |= chain_ids(it)
    seq = doc.get_uid(seq_uid)
    to_remove |= {int(x) for x in re.findall(r'<Link Index="\d+" ObjectRef="(\d+)"/>', seq)}
    removed = doc.remove_many(to_remove)

    # ── 배선 ───────────────────────────────────────────────────────────────
    doc.append(new_blocks)
    track_set_items(doc, V1, v_refs)
    track_set_items(doc, A1, a1_refs, transitions=[])
    track_set_items(doc, A3, a3_refs, transitions=[])
    total_ticks = frame_ticks(tl["total_s"])
    seq = doc.get_uid(seq_uid)
    links_inner = "".join(f'\n\t\t\t\t\t<Link Index="{i}" ObjectRef="{l}"/>' for i, l in enumerate(links))
    seq = re.sub(r'<LinkContainer Version="1">.*?</LinkContainer>', f'<LinkContainer Version="1">\n\t\t\t\t<Links Version="1">{links_inner}\n\t\t\t\t</Links>\n\t\t\t</LinkContainer>', seq, count=1, flags=re.S)
    for tag in ("MZ.WorkOutPoint", "MZ.OutPoint"):
        if f"<{tag}>" in seq:
            seq = set_child(seq, tag, str(total_ticks))
    doc.replace_uid(seq_uid, seq)
    mb = doc.get_uid(DN["원본_mp4"]["Media_UID"])
    mb = set_child(set_child(set_child(mb, "FilePath", esc(src_path)), "ActualMediaFilePath", esc(src_path)), "FileKey", str(uuid.uuid4()))
    doc.replace_uid(DN["원본_mp4"]["Media_UID"], mb)
    return {"V1": len(v_refs), "A1": len(a1_refs), "A3": len(a3_refs), "links": len(links), "removed": removed, "added": len(new_blocks),
            "levels": {"keep": LEVEL_KEEP, "duck": LEVEL_DUCK, "_note": "덕킹 = 도너 견본 문자열(−15 dB). 규격 조립.덕킹_레벨(−12 dB)과 다름 — 보류 결정"},
            "total_ticks": total_ticks, "cuts": report_cuts}


# ── ② 나레 (계단 3-c) ──────────────────────────────────────────────────────
def 나레치환(doc, tl, voice, alloc, 견본):
    A2 = T["A2"]
    N = {**S["나레"], **견본["나레"]}      # UID(계보 GUID)는 규격 값, 아이템·사슬은 찾은 값
    root_uid = N["RootProjectItem_UID"]
    vdur = {b["n"]: b["dur_s"] for b in voice["blocks"]}
    ids, uids = collect_lineage(doc, [N["item"], N["ClipProjectItem_UID"]])
    tmpl_ids = [i for i in ids if "AudioTransitionTrackItem" not in doc.get(i)]
    tmpl_uids = list(uids)
    tmpl = {k: doc.get(k) for k in tmpl_ids}
    tmpl_u = {k: doc.get_uid(k) for k in tmpl_uids}

    new_blocks, a2_refs, new_cpis, report_nars = [], [], [], []
    for nar in sorted(tl["narration"], key=lambda n: n["t0"]):
        wav = os.path.normpath(nar["wav"])
        fname = os.path.basename(wav)
        w = wave.open(wav)
        rate, ch, sw, nframes = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        w.close()
        assert ch == 1 and sw == 2 and TPS % rate == 0, (fname, rate, ch, sw)
        tick_rate = TPS // rate                        # 24000Hz → 10584000
        dur_ticks = nframes * tick_rate                # 미디어 길이(샘플 정확)
        t0 = frame_ticks(nar["t0"])
        t1 = frame_ticks(nar["t1"])
        length = min(t1 - t0, (dur_ticks // FRAME_TICKS) * FRAME_TICKS)   # 클립 길이 ≤ 미디어 길이(프레임 내림)
        assert length > 0, nar
        t1 = t0 + length
        idmap = {int(k): alloc() for k in tmpl_ids}
        uidmap = {k: str(uuid.uuid4()) for k in tmpl_uids}
        label = f'나레 {nar["n"]:02d} {nar["text"][:20]}'

        def emit(b):
            k = kind(b)
            if k == "AudioClipTrackItem":
                b = strip_node(b)
                b = re.sub(r"\n\t\t\t<(Head|Tail)Transition ObjectRef=\"\d+\"/>", "", b)
                b = set_child(set_span(b, t0, t1), "ID", str(uuid.uuid4()))
            elif k == "AudioClip":
                b = strip_node(b)
                b = re.sub(r"\n\t\t<Gain>[^<]*</Gain>", "", b)
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
        a2_refs.append(idmap[N["item"]])
        new_cpis.append(uidmap[N["ClipProjectItem_UID"]])
        report_nars.append({"n": nar["n"], "wav": fname, "t0_s": nar["t0"], "t1_s": nar["t1"], "clip_len_s": round(length / TPS, 4),
                            "media_dur_s": round(dur_ticks / TPS, 4), "voice_dur_s": vdur.get(nar["n"]), "rate": rate, "item": a2_refs[-1]})

    # ── 도너 나레 계보 + A2 페이드 제거, RootProjectItem Items 갱신 ─────────
    old_items, old_trans = track_items(doc, A2)
    rm_ids, rm_uids = set(old_trans), set()
    for it in old_items:
        i_, u_ = collect_lineage(doc, [it])
        rm_ids |= i_
        rm_uids |= u_
        mc = re.search(r'<MasterClip ObjectURef="([^"]+)"', doc.get(int(re.search(r'<SubClip ObjectRef="(\d+)"', doc.get(it)).group(1)))).group(1)
        for m in re.finditer(r'^\t<ClipProjectItem ObjectUID="([^"]+)"', doc.xml, re.M):
            if f'<MasterClip ObjectURef="{mc}"/>' in doc.get_uid(m.group(1)):
                rm_uids.add(m.group(1))
    protect = 보호계보(doc)
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
    mism = [r for r in report_nars if r["voice_dur_s"] is None or abs(r["clip_len_s"] - r["voice_dur_s"]) > 1.0 / 23.976 + 1e-6]
    return {"A2": len(a2_refs), "removed": removed, "added": len(new_blocks), "root_items": len(kept) + len(new_cpis),
            "length_mismatch": mism, "nars": report_nars}


# ── ③ 자막 (계단 3-d) ──────────────────────────────────────────────────────


def 자막치환(doc, tl, alloc, 견본):
    def template(item_id):
        ids, uids = collect_lineage(doc, [item_id], stop=공유계보(doc))
        tmpl_ids = sorted(ids - 공유계보(doc), key=int)
        blocks = {i: doc.get(i) for i in tmpl_ids}
        st = [i for i in tmpl_ids if is_source_text(blocks[i])][0]
        vfc = [i for i in tmpl_ids if blocks[i].lstrip().startswith("<VideoFilterComponent")][0]
        sub = [i for i in tmpl_ids if blocks[i].lstrip().startswith("<SubClip")][0]
        vclip = [i for i in tmpl_ids if blocks[i].lstrip().startswith("<VideoClip")][0]
        if 빈블롭_RE.search(blocks[st]):        # 해시로 남의 본문을 가리키는 블롭 — 견본으로 쓰려면 본문을 채워 둔다
            채움 = param_blob(blocks[st], doc.xml)
            blocks[st] = 빈블롭_RE.sub(lambda m: f'<StartKeyframeValue Encoding="base64" BinaryHash="{m.group(1)}">{채움}</StartKeyframeValue>', blocks[st], count=1)
        runs = len(parse_blob(param_blob(blocks[st], doc.xml))["runs"])
        return {"ids": tmpl_ids, "blocks": blocks, "item": str(item_id), "st": st, "vfc": vfc, "sub": sub, "clip": vclip, "runs": runs}

    TPL = {"dlg": template(견본["자막_대사"]["item"]), "nar": template(견본["자막_나레"]["item"])}
    new_blocks, refs = [], {"dlg": [], "nar": []}
    rows = []
    for cue in sorted(tl["cues"], key=lambda c: (c["t0"], c["lane"])):
        lane = cue["lane"]
        tpl = TPL[lane]
        t0 = frame_ticks(cue["t0"])
        t1 = max(frame_ticks(cue["t1"]), t0 + FRAME_TICKS)
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
                b = re.sub(r"<InstanceName>.*?</InstanceName>", "<InstanceName>" + esc(cue["text"]) + "</InstanceName>", b, flags=re.S)
            elif i == tpl["st"]:
                b64, binhash, blob_info = blob_set_texts(param_blob(b), texts)   # tail relocation + 재파싱
                b = param_set_blob(b, b64, binhash)
            new_blocks.append(b)
        refs[lane].append(idmap[int(tpl["item"])])
        rows.append({"lane": lane, "t0_s": cue["t0"], "t1_s": cue["t1"], "text": cue["text"], "runs": texts,
                     "item": idmap[int(tpl["item"])], "blob_len": blob_info["len"], "font": blob_info["fonts"],
                     "size": [r["size"] for r in blob_info["runs"]], "reparsed": "".join(r["text"] for r in blob_info["runs"])})

    # ── 도너 자막 전부 제거 (V2 · V3 · V4 + Cross Dissolve) ─────────────────
    rm_ids, rm_uids = set(), set()
    for uid in (T["V2"], T["V3"], T["V4"]):
        clips, trans = track_items(doc, uid)
        for tr in trans:
            i_, u_ = collect_lineage(doc, [tr], stop=공유계보(doc))
            rm_ids |= i_
            rm_uids |= u_
        for it in clips:
            i_, u_ = collect_lineage(doc, [it], stop=공유계보(doc))
            rm_ids |= i_
            rm_uids |= u_
    rm_ids -= 공유계보(doc)
    rm_uids -= 공유계보(doc)
    assert not (rm_ids & {str(i) for i in refs["dlg"] + refs["nar"]}), "새 자막이 제거 목록에 들어감"
    removed = doc.remove_many(rm_ids | rm_uids)

    doc.append(new_blocks)
    track_set_items(doc, T["V2"], refs["dlg"], transitions=[])
    track_set_items(doc, T["V3"], refs["nar"], transitions=[])
    track_set_items(doc, T["V4"], [], transitions=[])
    bad_blob = [r for r in rows if r["reparsed"] != r["text"]]
    return {"V2_대사": len(refs["dlg"]), "V3_나레": len(refs["nar"]), "V4": 0, "removed": removed, "added": len(new_blocks),
            "template": {k: {"blocks": len(v["ids"]), "runs": v["runs"]} for k, v in TPL.items()},
            "blob_mismatch": bad_blob, "cues": rows}


# ── 자기검증: 완성본을 다시 읽어 timeline 과 대조한다 ───────────────────────
def timeline_대조(out_path, tl):
    doc2 = Doc(load(out_path))
    bad = []
    by_lane = {"dlg": [c for c in tl["cues"] if c["lane"] == "dlg"], "nar": [c for c in tl["cues"] if c["lane"] == "nar"]}
    for lane, uid in (("dlg", T["V2"]), ("nar", T["V3"])):
        items, _ = track_items(doc2, uid)
        want = sorted(by_lane[lane], key=lambda c: c["t0"])
        if len(items) != len(want):
            bad.append({"lane": lane, "count": [len(items), len(want)]})
            continue
        for it, cue in zip(items, want):
            b = doc2.get(it)
            ti = re.search(r"<TrackItem Version=\"4\">(.*?)</TrackItem>", b, re.S).group(1)
            st_ = int(child(ti, "Start") or 0)
            sc = int(re.search(r'<SubClip ObjectRef="(\d+)"', b).group(1))
            ch = int(re.search(r'<Components ObjectRef="(\d+)"', b).group(1))
            vfc = int(re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', doc2.get(ch))[0])
            stp = [p for p in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', doc2.get(vfc)) if is_source_text(doc2.get(p))][0]
            txt = "".join(r["text"] for r in parse_blob(param_blob(doc2.get(stp), doc2.xml))["runs"])
            if txt != cue["text"] or child(doc2.get(sc), "Name") != esc(cue["text"]) or st_ != frame_ticks(cue["t0"]):
                bad.append({"lane": lane, "t0": cue["t0"], "want": cue["text"], "got": txt})
    # 컷·나레 시각도 대조한다 (자막만 보던 계단 3-d 에서 넓힌 것 — 계단 4)
    for uid, key, want_list in ((T["V1"], "picture", sorted(tl["picture"], key=lambda p: p["t0"])),
                                (T["A2"], "narration", sorted(tl["narration"], key=lambda n: n["t0"]))):
        items, _ = track_items(doc2, uid)
        if len(items) != len(want_list):
            bad.append({"track": key, "count": [len(items), len(want_list)]})
            continue
        for it, w in zip(items, want_list):
            ti = re.search(r"<TrackItem Version=\"4\">(.*?)</TrackItem>", doc2.get(it), re.S).group(1)
            if int(child(ti, "Start") or 0) != frame_ticks(w["t0"]):
                bad.append({"track": key, "t0": w["t0"], "start_ticks": child(ti, "Start")})
    return bad


# ── 본체 ───────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--도너", default=None, help="규격 「조립.도너.파일」 대신 쓸 도너(시험용)")
    ap.add_argument("--json", action="store_true", help="요약(JSON)만 표준출력으로 — 사람이 읽는 줄은 표준오류로. export 가 게이트로 읽는다")
    a = ap.parse_args()
    out_path = os.path.abspath(a.out)
    report_path = a.report or out_path.replace(".prproj", ".report.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    tl = json.load(open(a.timeline, encoding="utf-8"))
    voice = json.load(open(a.voice, encoding="utf-8"))
    src = os.path.normpath(tl["source"]["path"] if isinstance(tl.get("source"), dict) else tl["source"])
    assert os.path.exists(src), "원본 영상 없음: " + src
    donor = getattr(a, "도너", None) or os.path.join(ROOT, DN["파일"])
    assert os.path.exists(donor), "도너 없음: " + donor

    doc = Doc(load(donor))
    alloc = Alloc(doc)
    say = (lambda *x: print(*x, file=sys.stderr)) if a.json else print
    견본 = 견본찾기(doc, say)
    r_cut = 컷치환(doc, tl, alloc, src, 견본)
    r_nar = 나레치환(doc, tl, voice, alloc, 견본)
    r_sub = 자막치환(doc, tl, alloc, 견본)
    seq = doc.get_uid(DN["시퀀스"]["UID"])
    doc.replace_uid(DN["시퀀스"]["UID"], set_child(seq, "Name", esc(tl["title"] + " 리캡")))
    save(out_path, doc.xml)

    tl_bad = timeline_대조(out_path, tl)
    res = verify(out_path, {"V1": (T["V1"], r_cut["V1"]), "A1": (T["A1"], r_cut["A1"]), "A3": (T["A3"], r_cut["A3"]),
                            "A2": (T["A2"], r_nar["A2"]), "V2": (T["V2"], r_sub["V2_대사"]), "V3": (T["V3"], r_sub["V3_나레"]), "V4": (T["V4"], 0)})
    res["checks"].append({"check": "나레 클립 길이 = voice.json 실측(±1프레임)", "pass": not r_nar["length_mismatch"], "detail": str(r_nar["A2"]) + "개 중 불일치 " + str(len(r_nar["length_mismatch"]))})
    res["checks"].append({"check": "자막 블롭 재파싱 = 넣은 텍스트", "pass": not r_sub["blob_mismatch"], "detail": str(len(r_sub["cues"])) + "개 중 불일치 " + str(len(r_sub["blob_mismatch"]))})
    res["checks"].append({"check": "timeline.json 대조(자막 문구·시각 · 컷/나레 시각)", "pass": not tl_bad, "detail": "불일치 " + str(len(tl_bad))})
    ok = res["pass"] and not r_nar["length_mismatch"] and not r_sub["blob_mismatch"] and not tl_bad

    report = {"stage": "계단 4 — 조립 통합", "donor": DN["파일"], "source": src, "out": out_path,
              "title": tl["title"], "total_s": tl["total_s"],
              "counts": {"V1": r_cut["V1"], "A1": r_cut["A1"], "A3": r_cut["A3"], "A2": r_nar["A2"],
                         "V2": r_sub["V2_대사"], "V3": r_sub["V3_나레"], "V4": 0, "links": r_cut["links"],
                         "removed_blocks": r_cut["removed"] + r_nar["removed"] + r_sub["removed"],
                         "added_blocks": r_cut["added"] + r_nar["added"] + r_sub["added"]},
              "levels": r_cut["levels"], "pass": ok, "checks": res["checks"],
              "cuts": r_cut["cuts"], "nars": r_nar["nars"], "cues": r_sub["cues"], "timeline_mismatch": tl_bad}
    json.dump(report, open(report_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    say("저장 " + out_path + ": 컷 " + str(r_cut["V1"]) + " · A1 " + str(r_cut["A1"]) + " · A3 " + str(r_cut["A3"]) +
        " · 나레 " + str(r_nar["A2"]) + " · 자막 " + str(r_sub["V2_대사"] + r_sub["V3_나레"]) +
        "(대사 " + str(r_sub["V2_대사"]) + " · 나레 " + str(r_sub["V3_나레"]) + ")")
    for c in res["checks"]:
        say(("  [OK] " if c["pass"] else "  [X] ") + c["check"] + "  " + c["detail"])
    say("전체: " + ("통과" if ok else "실패"))
    if a.json:   # export 가 게이트로 읽는 요약 — 큐 목록 같은 큰 배열은 빼고 숫자와 판정만
        print(json.dumps({"pass": ok, "out": out_path, "report": report_path, "donor": DN["파일"],
                          "total_s": tl["total_s"], "counts": report["counts"],
                          "checks": [{"check": c["check"], "pass": c["pass"], "detail": c["detail"]} for c in res["checks"]],
                          "failed": [c["check"] for c in res["checks"] if not c["pass"]]}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
