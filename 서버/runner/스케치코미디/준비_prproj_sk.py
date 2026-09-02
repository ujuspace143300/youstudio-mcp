#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""준비_prproj_sk.py — 조립_prproj_sk 의 입력 한 벌을 만든다.

  ① 납품 폴더(<workdir>/프리미어_<슬러그>/소스/)에 미디어 복사
     원본.mp4(그대로) · 나레_00.wav(모노 48k s16 변환) · 그래픽_템플릿.mov(껍데기, qtrle argb 30fps)
  ② 껍데기 = build.draw_frame(제목 비움) → 영상 상자(y0~y1)에 알파 구멍 → mov
     제목은 굽지 않는다 — V3 텍스트 그래픽으로 들어가 프리미어에서 수정 가능해야 하므로.
  ③ timeline_sk.json — 컷·나레·자막 큐·상자 배치(모션 값)

사용: python 준비_prproj_sk.py <편.json> --config <config.json>
"""
import argparse, json, os, subprocess, sys, wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG  # noqa: E402  (--config 인자를 걷어간다)
from s2pipe import build    # noqa: E402
from prproj_lib_probe import ffprobe_info  # noqa: E402


def run(argv):
    subprocess.run(argv, check=True, capture_output=True)


def 텍스트검출(rgb, row_min=15, tot_min=40, top=False):   # tot 60 은 짧은 대사 자막을 놓쳤다(컷05 실측) → 40
    """외곽선 자막 검출 — 밝은 픽셀(≥200)에 맞닿은 어두운 픽셀(≤70)을 센다. 색 무관.
       top=True 면 (검출여부, 검출 최상단 행) 을 돌려준다 — 자막 윗변 실측용."""
    import numpy as np
    g = np.asarray(rgb).astype(int)
    if g.ndim == 3:
        g = g.mean(axis=2)
    bright = g >= 200
    dark = g <= 70
    bd = np.zeros_like(bright)
    bd[1:, :] |= bright[:-1, :]
    bd[:-1, :] |= bright[1:, :]
    bd[:, 1:] |= bright[:, :-1]
    bd[:, :-1] |= bright[:, 1:]
    c = bd & dark
    rows = c.sum(axis=1)
    hit = int(rows.max()) >= row_min and int(c.sum()) >= tot_min
    if not top:
        return hit
    strong = np.where(rows >= max(6, row_min // 2))[0]
    return hit, (int(strong[0]) if hit and len(strong) else None)


def 배경맞춤(img, bg):
    """카드·로고의 순백 배경을 껍데기 배경색으로 — 흰 카드 경계가 티 나지 않게 (2026-09-01 사장님)."""
    import numpy as np
    a = np.asarray(img.convert("RGBA")).copy()
    m = (a[:, :, 0] >= 250) & (a[:, :, 1] >= 250) & (a[:, :, 2] >= 250)
    a[m, 0], a[m, 1], a[m, 2] = bg[0], bg[1], bg[2]
    from PIL import Image as _I
    return _I.fromarray(a, "RGBA")


def 화자판정(lines, cut_mp4, logline, times=None, 예상화자수=None, 회수=3):
    """대사 줄마다 화자 번호(1·2·3…) 또는 «효과»를 배정한다 (EvoLink 무료 경로).

    ★2026-09-02 사장님 지시(같은 화자 색 바뀜 재발 금지)로 전면 개편 —
      한 번 판정을 그대로 믿다가 같은 사람이 두 색으로 갈렸다. 원인 셋:
      ① 줄에 시각이 없어 모델이 자막↔영상 정렬을 혼자 맞춰야 했다 → 시각을 준다.
      ② 인물 정체를 고정하는 장치가 없어 장면이 바뀌면 같은 사람에 새 번호가 붙었다
         → 겉모습(cast) 목록을 먼저 쓰게 강제하고, 사람이 아는 화자 수를 힌트로 준다.
      ③ 검증 없이 1회 판정 → 독립 3회 판정 후 번호를 정렬해 다수결. 과반 미달 줄은
         «불안정»으로 보고한다(게이트).

    반환 (who, 불안정줄번호목록, cast설명). 전부 실패하면 ([None]*n, [], {})."""
    import base64
    from collections import Counter
    from s2pipe import gem
    from s2pipe.cfg import CFG as _C
    models = _C.get("gemini", {}).get("models", ["gemini-3.5-flash"])
    if times:
        목록 = "\n".join(f"{i}. [{t:.1f}초] {s}" for i, (t, s) in enumerate(zip(times, lines)))
    else:
        목록 = "\n".join(f"{i}. {s}" for i, s in enumerate(lines))
    힌트 = (f"- 이 영상의 화자는 {예상화자수}명으로 알려져 있다(효과 제외). "
            f"그보다 많게 나누려거든 정말 다른 사람인지 겉모습을 다시 확인하라.\n") if 예상화자수 else ""
    vid = base64.b64encode(open(gem.shrink_for_inline(cut_mp4), "rb").read()).decode()
    prompt = (f"숏폼({logline})의 자막 줄 목록이다. 줄 앞 [초]는 그 자막이 영상에 뜨는 시각이다.\n"
              f"영상을 보고 줄마다 **말하는 사람**을 배정하라.\n"
              f"- 먼저 등장인물 목록(cast)을 만들어라 — 번호마다 겉모습(성별·옷·자리)을 한 줄로.\n"
              f"  같은 사람은 장면이 바뀌어도 **반드시 같은 번호**다. 목소리도 근거로 써라.\n"
              f"{힌트}"
              f"- 시각을 이용해 그 순간 말하는 사람을 확인하라.\n"
              f"- ★화면에 보이는 사람이 곧 말하는 사람이라고 단정하지 마라 — 대화 장면은 듣는\n"
              f"  사람을 비추는 컷(리버스샷)이 많다. 입 움직임·목소리·대화 맥락(질문과 대답은\n"
              f"  보통 화자가 교대한다)으로 판정하라.\n"
              f"- 사람이 말하는 대사가 아닌 줄(상황 설명·괄호·효과)은 \"효과\" 로.\n"
              f"JSON 만, 공백 없이 한 줄로. ★who 를 먼저: {{\"who\":[줄별 값,...],"
              f"\"cast\":{{\"1\":\"겉모습\",...}}}} — who 는 줄 수 {len(lines)}개와 같아야 한다.\n\n{목록}")
    표, cast = [], {}
    import re as _re2
    for n회 in range(회수):
        try:
            payload = {"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "video/mp4", "data": vid}},
                {"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 6000, "responseMimeType": "application/json"}}
            txt, _r, _m = gem.ask(payload, models, timeout=600)
            try:
                j = json.loads(txt)
                who = [str(w) for w in j["who"]]
                c = {str(k): str(v) for k, v in (j.get("cast") or {}).items()}
            except Exception:
                # ★응답이 뒤에서 잘려도(2026-09-03 3회 연속 실측) who 배열만 온전하면 살린다
                #   — 그래서 프롬프트가 who 를 앞에 쓰게 한다.
                m = _re2.search(r'"who"\s*:\s*\[(.*?)\]', txt or "", _re2.S)
                if not m:
                    raise
                who = [w.strip().strip('"') for w in m.group(1).split(",")]
                c = {}
            assert len(who) == len(lines), f"who {len(who)}개 ≠ 줄 {len(lines)}개"
            표.append(who)
            if not cast and c:
                cast = c
        except Exception as e:
            print(f"화자 판정 {n회 + 1}회차 실패:", str(e)[:60])
    if not 표:
        print("화자 판정 전부 실패 — 색 구분 없이 간다")
        return [None] * len(lines), [], {}
    # 회차마다 번호 체계가 다를 수 있다 — 1회차 기준으로 겹침 최대 매칭(그리디)으로 재명명
    기준 = 표[0]
    맞춘 = [기준]
    for run in 표[1:]:
        쌍 = Counter((a, b) for a, b in zip(run, 기준) if a != "효과" and b != "효과")
        사상, 씀 = {}, set()
        for (a, b), _n in 쌍.most_common():
            if a not in 사상 and b not in 씀:
                사상[a] = b
                씀.add(b)
        맞춘.append(["효과" if w == "효과" else 사상.get(w, w) for w in run])
    who, 불안정 = [], []
    for i in range(len(lines)):
        표결 = Counter(r[i] for r in 맞춘)
        값, 표수 = 표결.most_common(1)[0]
        who.append(값)
        if 표수 * 2 <= len(맞춘):                      # 과반 미달 = 회차끼리 갈렸다
            불안정.append(i)
    print(f"화자 판정 {len(맞춘)}회 표결 — 과반 일치 {len(lines) - len(불안정)}/{len(lines)}줄")
    return who, 불안정, cast


def 화자교정적용(dlg_cues, 교정, 팔레트):
    """★사장님 교정(2026-09-02: «저 사람 두고 말한 거야?» 색 뒤바뀜) — 사장님이 확정한
       줄별 화자({"시각": "1|2|3|효과"})를 색에 강제 적용한다. 판정이 몇 번을 다시 돌아도
       교정이 이긴다. 시각은 ±0.3s 로 맞춘다. "1" = 기본색(흰)."""
    n = 0
    for k, v in (교정 or {}).items():
        t = float(k)
        cand = min(dlg_cues, key=lambda c: abs(c["t0"] - t))
        if abs(cand["t0"] - t) > 0.3:
            print(f"★화자교정 {k}s — 맞는 자막을 못 찾았다(가장 가까운 {cand['t0']:.1f}s). 건너뜀")
            continue
        v = str(v)
        cand["color"] = list(팔레트[v]) if v in 팔레트 else None
        n += 1
    return n


def 댓글선별(pngs, logline, want=(10, 15)):
    """댓글 카드 PNG 중 편 내용과 어울리는 것을 모델이 고른다 (EvoLink 무료 한도).
       ★최소 10장(2026-09-01 사장님). 판정이 실패하면 앞에서 12장을 그대로 쓴다."""
    import base64
    from s2pipe import gem
    from s2pipe.cfg import CFG as _C
    models = _C.get("gemini", {}).get("models", ["gemini-3.5-flash"])
    parts = [{"text": (f"숏폼 내용: {logline}\n아래 번호 붙은 유튜브 댓글 카드 중 이 내용과 어울리는 것을 "
                       f"{want[0]}~{want[1]}개, 어울리는 순서대로 골라라. JSON 만: {{\"picks\":[번호,...]}} (0부터)")}]
    for i, p in enumerate(pngs):
        parts.append({"text": f"[{i}]"})
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(open(p, "rb").read()).decode()}})
    payload = {"contents": [{"role": "user", "parts": parts}],
               "generationConfig": {"maxOutputTokens": 1000, "responseMimeType": "application/json"}}
    import re as _re
    for 시도 in range(2):                      # ★빈 응답이 잦다(2026-09-03 실측) — 한 번 더 준다
        try:
            txt, _r, _m = gem.ask(payload, models, timeout=300)
            m = _re.search(r"\[[\d,\s]+\]", txt or "")
            picks = [i for i in json.loads(m.group(0) if m else "x") if 0 <= int(i) < len(pngs)]
            picks = list(dict.fromkeys(int(i) for i in picks))
            assert len(picks) >= want[0]
            return [pngs[i] for i in picks[:want[1]]]
        except Exception as e:
            print(f"댓글 선별 {시도 + 1}차 실패:", str(e)[:60])
    print("댓글 선별 실패 — 앞 12장 사용")
    return pngs[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    a = ap.parse_args()
    proj = json.load(open(a.project, encoding="utf-8"))
    slug = proj["slug"]
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(a.project)))
    wdir = os.path.join(workdir, "work", slug)
    src_orig = os.path.join(workdir, "work", proj["source"]["id"] + ".mp4")
    out_root = os.path.join(workdir, f"프리미어_{slug}")
    sdir = os.path.join(out_root, "소스")
    os.makedirs(sdir, exist_ok=True)

    segs = [s for s in proj["segments"] if s.get("keep")]
    total = sum(s["t1"] - s["t0"] for s in segs)
    # ★끝맺음 여운(2026-09-01 사장님: 하드컷이 너무 급하다) — 마지막 컷을 원본에서 연장.
    #   ★반드시 템플릿 굽기·댓글 슬롯 계산 «앞»에서 늘린다 — 뒤에서 늘렸다가 템플릿 mov 가
    #   여운만큼 짧아 끝 0.8초에 껍데기가 통째로 비었다(2026-09-02 사장님 실측 «템플릿 빠짐»).
    여운 = 1.8
    ext = max(0.0, min(여운, proj["source"]["dur"] - 0.3 - segs[-1]["t1"]))
    if ext:
        segs[-1] = dict(segs[-1], t1=segs[-1]["t1"] + ext)
        total = round(total + ext, 4)
        print(f"끝맺음 여운 +{ext:.1f}s → 총 {total:.1f}s")

    # ① 미디어 — ★프리미어가 읽는 코덱만 넣는다 (2026-09-01 실측: 유튜브 AV1 원본 → 비디오만
    #   미디어 오프라인, 소리(AAC)는 정상. 경로·메타가 아니라 코덱이 원인이었다)
    지원코덱 = {"h264", "hevc", "prores", "qtrle", "mpeg4", "mjpeg", "dnxhd"}

    def vcodec(path):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                             check=True, capture_output=True)
        return out.stdout.decode().strip()

    dst_src = os.path.join(sdir, "원본.mp4")
    if os.path.exists(dst_src) and vcodec(dst_src) not in 지원코덱:
        os.remove(dst_src)                     # 이전에 복사된 미지원 코덱본 폐기
    if not os.path.exists(dst_src):
        if vcodec(src_orig) in 지원코덱:
            import shutil
            shutil.copy2(src_orig, dst_src)
        else:
            print(f"원본 코덱 {vcodec(src_orig)} — 프리미어 미지원 → H.264 변환 (수 분)")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src_orig,
                            "-vf", "fps=24000/1001", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "16", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst_src], check=True)
    assert vcodec(dst_src) in 지원코덱, "원본 변환 실패 — 코덱 " + vcodec(dst_src)
    dst_nar = os.path.join(sdir, "나레_00.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(wdir, "narr01.wav"),
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", dst_nar])

    # ② 껍데기 — 제목 포함 frame → 알파 구멍 → mov
    #   ★제목은 껍데기에 굽는다(2026-09-01 사장님 — 정위치·검은색 보장). 도너 텍스트 견본으로
    #   넣으면 신병 헤드라인 서식(노랑·상단)이 따라온다. 수정 가능해야 하는 것은 대사다.
    #   ★Deep 흐름(work/<슬러그>_로고.png 존재): 헤더는 사장님 지정 로고 이미지로 갈고
    #   (배치는 최하연님 작업 prproj 실측 — 위치 0.1993:0.0699 · 비율 16.45%),
    #   댓글 카드 PNG 를 선별해 슬롯 순환으로 굽는다(위치 0.5:0.8126 · 폭 1020 = 실측).
    from PIL import Image
    import copy as _copy
    import re as _re
    p_draw = _copy.deepcopy(proj)
    cr = p_draw.get("credit") or {}
    if cr.get("title"):
        import unicodedata as _ud
        # ★NFD(맥 파일명 자모 분해)·이모지는 폰트가 못 그린다 — 출처 줄이 «#띱 Deep -» 에서 끊긴 실측
        cr["title"] = _ud.normalize("NFC", cr["title"])
        cr["title"] = _re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]", "", cr["title"]).strip()
    frame_png = os.path.join(sdir, "_frame.png")
    build.draw_frame(p_draw, frame_png)
    im = Image.open(frame_png).convert("RGBA")
    b = CFG["layout"]["video_box"]
    L = CFG["layout"]
    bg = tuple(int(L["bg"][i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    logo_p = os.path.join(wdir, os.pardir, f"{slug}_로고.png")
    logo_p = os.path.normpath(logo_p)
    deep = os.path.exists(logo_p)
    if deep:
        hd = L["header"]
        im.paste(Image.new("RGBA", (1080, hd["y1"] - hd["y0"] + 40), bg), (0, hd["y0"] - 20))
        logo = 배경맞춤(Image.open(logo_p), bg)
        s_ = 0.16451612472534 * 1080 / 1080          # 최하연 실측 비율(시퀀스 1080 기준)
        w_, h_ = int(logo.width * s_), int(logo.height * s_)
        logo = logo.resize((w_, h_))
        cx, cy_ = 0.19928400218486786 * 1080, 0.069892480969429016 * 1920
        im.alpha_composite(logo, (int(cx - w_ / 2), int(cy_ - h_ / 2)))
        cm = L["comment"]
        im.paste(Image.new("RGBA", (1080, cm["y1"] - cm["y0"] + 40), bg), (0, cm["y0"] - 20))
    hole = Image.new("RGBA", (b["w"], b["y1"] - b["y0"]), (0, 0, 0, 0))
    im.paste(hole, (0, b["y0"]))
    rgba = os.path.join(sdir, "_frame_hole.png")
    im.save(rgba)
    dst_tpl = os.path.join(sdir, "그래픽_템플릿.mov")
    cmt_overlays = []
    if deep:
        import glob as _g
        pngs = sorted(_g.glob(os.path.join(wdir, os.pardir, f"{slug}_댓글", "**", "*.png"), recursive=True))
        picked = 댓글선별(pngs, proj.get("logline", ""))
        slots = max(len(picked), 1)
        each = total / slots
        # 댓글 자리 = 영상 상자 아래 ~ 출처 위 (침범 금지 · 좌우 꽉차게 — 2026-09-01 사장님)
        zone0, zone1 = b["y1"] + 8, L["credit"]["y0"] - 10
        zone_h = zone1 - zone0
        for i, p in enumerate(picked):
            c = 배경맞춤(Image.open(p), bg)
            w2, h2 = 1080, int(c.height * 1080 / c.width)
            if h2 > zone_h:                              # 긴 카드는 자리 높이에 맞춰 줄인다
                w2, h2 = int(c.width * zone_h / c.height), zone_h
            c = c.resize((w2, h2))
            cp = os.path.join(sdir, f"_cmt{i:02d}.png")
            c.save(cp)
            # ★상단 정렬(2026-09-01 사장님) — 영상 바로 아래 붙이되(침범 없음) 세로 중앙이 아니라 위로
            cmt_overlays.append((cp, i * each, (i + 1) * each, (1080 - w2) // 2, zone0))
        print(f"댓글 {len(picked)}장 → 슬롯 {each:.1f}초씩 · 자리 y{zone0}~{zone1}")
    if cmt_overlays:
        args = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", rgba]
        for cp, *_r in cmt_overlays:
            args += ["-loop", "1", "-i", cp]
        fc, cur = "", "[0]"
        for i, (_cp, a0, a1, x, y) in enumerate(cmt_overlays):
            nxt = f"[v{i}]"
            fc += f"{cur}[{i + 1}]overlay={x}:{y}:enable='between(t,{a0:.2f},{a1:.2f})'{nxt};"
            cur = nxt
        fc = fc[:-1]
        args += ["-filter_complex", fc, "-map", cur, "-t", f"{total + 1:.3f}",
                 "-r", "30", "-c:v", "qtrle", "-pix_fmt", "argb", dst_tpl]
        run(args)
    else:
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", rgba, "-t", f"{total + 1:.3f}",
             "-r", "30", "-c:v", "qtrle", "-pix_fmt", "argb", dst_tpl])
    # 되읽기 게이트(2026-09-02) — 템플릿이 총길이보다 짧으면 끝에서 껍데기가 빈다
    tpl_dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", dst_tpl], check=True, capture_output=True).stdout)
    assert tpl_dur >= total, f"템플릿 {tpl_dur:.2f}s < 총길이 {total:.2f}s — 껍데기가 끝에서 빈다"

    # ③ timeline
    picture, cum = [], 0.0
    for i, s in enumerate(segs):
        d = s["t1"] - s["t0"]
        picture.append({"t0": round(cum, 4), "t1": round(cum + d, 4), "src_in": s["t0"],
                        "name": f'{i + 1:02d} P{s["phase"]} {s["what"][:24]}'})
        cum += d
    # (끝맺음 여운은 위 — 템플릿 굽기 전 — 로 옮겼다. 2026-09-02)

    # ★게이트(2026-09-03 Deep02 사건 — 싱크 단계를 건너뛰어 자막이 통째로 어긋났다)
    #   자막은 완성본 재전사(s2pipe.asr)와 단어 정렬(s2pipe.sync)을 거쳐야 믿을 수 있다.
    assert proj.get("subs_before_sync"), (
        "★자막 싱크 단계를 안 거쳤다 — 먼저:\n"
        "  python -m s2pipe.asr projects/<슬러그>.json   (★유료 · 완성본 재전사)\n"
        "  python -m s2pipe.sync projects/<슬러그>.json")
    subs = sorted(proj["subs"], key=lambda x: x["t"])
    nar_seg = next(s for s in segs if s.get("narration"))
    nar_sub = next((x for x in subs if x.get("kind") == "narr"), None)
    w = wave.open(dst_nar)
    nar_dur = w.getnframes() / w.getframerate()
    w.close()
    nar_t0 = nar_sub["t"] if nar_sub else picture[segs.index(nar_seg)]["t0"] + 0.3
    narration = [{"t0": round(nar_t0, 3), "t1": round(nar_t0 + nar_dur, 3),
                  "wav": dst_nar, "text": nar_seg["narration"]}]

    # 제목 텍스트 클론은 유지하되 **화면 밖**에 둔다 — 보이는 제목은 껍데기에 굽는다.
    #   (구조를 열렸던 판과 동일하게 유지하기 위함. V3 를 비우거나 다른 견본을 넣은 판은
    #    프리미어가 「손상」으로 거부했다 — 2026-09-01 실측 2회)
    # 효과음 (2026-09-02 사장님 승인 — 최소 원칙 3개): 훅=dun · 절정(P4)=dudun · 반전(P5)=gaze.
    #   아모르 팩 mp3 → 모노 48k wav(끝 0.4s 페이드·-6dB). 위치는 이야기 구조(phase 경계)에서 자동.
    sfx_dir = os.path.expanduser("~/Desktop/볼케이노 MCP/린박스_배포키트/자산/sfx_amor")
    sfx = []
    if os.path.isdir(sfx_dir):
        i4 = next((i for i, s_ in enumerate(segs) if s_["phase"] == 4), None)
        i5 = next((i for i, s_ in enumerate(segs) if s_["phase"] == 5), None)
        for 이름, 라벨, pi in (("dun", "훅", 0), ("dudun", "절정", i4), ("gaze", "반전", i5)):
            if pi is None:
                continue
            srcm = os.path.join(sfx_dir, 이름 + ".mp3")
            if not os.path.exists(srcm):
                continue
            w = os.path.join(sdir, f"효과음_{라벨}.wav")
            dur0 = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", srcm], check=True, capture_output=True).stdout)
            run(["ffmpeg", "-y", "-v", "error", "-i", srcm, "-ac", "1", "-ar", "48000",
                 "-c:a", "pcm_s16le", "-af", f"afade=t=out:st={max(0, dur0-0.4):.2f}:d=0.4,volume=-6dB", w])
            t0_ = picture[pi]["t0"]
            sfx.append({"wav": w, "t0": round(t0_, 3), "t1": round(min(t0_ + dur0, total), 3),
                        "text": f"효과음 {라벨} {이름}"})
        print(f"효과음 {len(sfx)}개: " + " · ".join(s_['text'] for s_ in sfx))

    cues = [{"lane": "title", "t0": 0.0, "t1": round(total, 3), "text": proj["title"][0] + "\r" + proj["title"][1]}]
    cues.append({"lane": "narr", "t0": narration[0]["t0"], "t1": narration[0]["t1"], "text": nar_seg["narration"]})
    # 대사 큐 — 60fps 격자에서 끝 = min(시작+6초, 다음 시작) 로 겹침 0 을 보장한다.
    # ★나레이션이 뜨는 동안 대사 자막은 감춘다 (규격 narration.hide_line_subs — 2026-09-01 사장님 재확인:
    #   나레이션 중에는 본편 대사 자막이 안 나오는 게 맞다). 겹치면 자르고, 0.3초도 안 남으면 뺀다.
    F = 60
    pad = float(CFG["narration"].get("duck_pad_sec", 0.15))
    n0f, n1f = round((narration[0]["t0"] - pad) * F), round((narration[0]["t1"] + pad) * F)
    lines = [x for x in subs if x.get("kind") != "narr"]
    숨김 = 0
    for i, x in enumerate(lines):
        t0f = round(x["t"] * F)
        nxtf = round((lines[i + 1]["t"] if i + 1 < len(lines) else total) * F)
        t1f = min(t0f + 6 * F, nxtf, round(total * F))
        if t1f <= t0f:
            t1f = t0f + 1
        if t0f < n1f and t1f > n0f:                  # 나레이션 창과 겹침
            if t0f >= n0f:
                t0f = n1f                            # 나레 중 시작 → 나레 끝으로 민다
            else:
                t1f = n0f                            # 나레 전 시작 → 나레 앞에서 끊는다
            if t1f - t0f < round(0.3 * F):
                숨김 += 1
                continue
        cues.append({"lane": "dlg", "t0": round(t0f / F, 4), "t1": round(t1f / F, 4), "text": x["text"]})
    if 숨김:
        print(f"나레이션과 겹쳐 감춘 대사 자막 {숨김}줄")

    # ★화자별 자막 색 (2026-09-02 사장님) — 화자마다 색, 효과자막은 나레와 같은 노랑.
    #   화자1 은 기본색 유지(주인공), 파스텔 팔레트라 눈이 편하다. 나레(V4)는 건드리지 않는다.
    dlg_cues = [c for c in cues if c["lane"] == "dlg"]
    who, 불안정, cast = 화자판정([c["text"] for c in dlg_cues], os.path.join(wdir, "cut.mp4"),
                                proj.get("logline", ""), times=[c["t0"] for c in dlg_cues],
                                예상화자수=proj.get("화자수"))
    팔레트 = {"효과": (245, 244, 37), "2": (135, 206, 250), "3": (255, 182, 193),
              "4": (144, 238, 144), "5": (255, 200, 150)}          # 4·5는 예비(화자가 더 많을 때)
    from collections import Counter
    if any(w for w in who):
        # 가장 많이 말한 화자 = 1번(기본색) 로 정규화 — 모델이 번호를 어떤 순서로 매겨도 주인공은 기본색
        말수 = Counter(w for w in who if w and w != "효과")
        순위 = [w for w, _n in 말수.most_common()]
        재배 = {w: str(i + 1) for i, w in enumerate(순위)}
        for c, w in zip(dlg_cues, who):
            key = "효과" if w == "효과" else (재배.get(w) if w else None)
            c["color"] = list(팔레트[key]) if key in 팔레트 else None
        print("화자 분포:", dict(Counter(("효과" if w == "효과" else 재배.get(w, "?")) for w in who if w)))
        for 원, 겉 in cast.items():
            print(f"  화자{재배.get(원, 원)}: {겉}")
        # ★게이트(2026-09-02) — 회차끼리 갈린 줄은 색이 틀렸을 확률이 높다. 명단을 보고하고
        #   완성 보고에 «화자 검사» 항목으로 남긴다. 불안정 줄이 있으면 사람 눈 확인 필수.
        if 불안정:
            print(f"★화자 불안정 {len(불안정)}줄 — 눈으로 확인 필요:")
            for i in 불안정:
                print(f"   [{dlg_cues[i]['t0']:.1f}초] {dlg_cues[i]['text'][:30]}")
        if proj.get("화자수") and len(말수) != int(proj["화자수"]):
            print(f"★화자 수 불일치 — 판정 {len(말수)}명 vs 사장님 확인 {proj['화자수']}명. 보고 필요.")
    n교정 = 화자교정적용(dlg_cues, proj.get("화자교정"), 팔레트)
    if n교정:
        print(f"사장님 화자교정 {n교정}줄 강제 적용 — 판정보다 우선한다")

    # 상자 배치 — ★원본 번인 자막이 상자 밖으로 잘려나가게 확대하고, 컷마다 얼굴 중심을 맞춘다
    #   (2026-09-01 사장님: 원본 자막과 우리 자막이 겹친다 — 확대+인물 포커싱으로 가리지 말고 잘라내라)
    src_info = ffprobe_info(dst_src)
    box_h = b["y1"] - b["y0"]                       # 908
    from s2pipe import build as B
    from s2pipe import framing as FR
    sub_top = B.find_burned_subs(dst_src, 1920, 1080, src_info["dur"]) or int(1080 * b["sub_zone_top"])

    def grab(t, tag):
        """★frame_at 은 tag 로 캐시한다 — 같은 tag 면 다른 시각도 같은 프레임을 돌려준다(실측).
           캐시를 우회해 ffmpeg 로 직접 뽑는다."""
        import numpy as np
        from PIL import Image as _I
        p = os.path.join(wdir, f"_pv_{tag}.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", dst_src,
                        "-frames:v", "1", p], check=True, capture_output=True)
        return np.asarray(_I.open(p).convert("RGB"))

    def face_center(t0, t1, tag):
        """컷 구간에서 얼굴 중심 실측 (yunet, 3프레임 평균). 못 찾으면 화면 중상단."""
        pts = []
        for f in (0.3, 0.5, 0.7):
            try:
                rgb = grab(t0 + (t1 - t0) * f, f"f{tag}_{int(f*10)}")
                faces = FR._faces_yunet(rgb, score=b.get("face_score", 0.45))
                if faces is not None and len(faces):
                    best = max(faces, key=lambda r: r[4] if len(r) > 4 else 0)
                    x, y, w_, h_ = best[:4]
                    pts.append((x + w_ / 2, y + h_ / 2))
            except Exception:
                pass
        if not pts:
            return 960.0, 430.0
        xs = sorted(p[0] for p in pts)
        ys = sorted(p[1] for p in pts)
        # ★한 컷에 샷이 여러 개면(얼굴 위치 편차 큼) 평균이 아무도 안 맞춘다 — 중앙 크롭이 안전하다
        if len(xs) >= 2 and xs[-1] - xs[0] > 350:
            return 960.0, ys[len(ys) // 2]
        return xs[len(xs) // 2], ys[len(ys) // 2]

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    def seg_has_burned(t0, t1):
        """이 컷 구간의 하단 밴드에 **노란 번인 자막**이 있는가 (이 소재의 번인 자막은 노랑).
           밝기만 보면 하늘·흰 차가 오탐된다(실측 — 결말 컷이 확대돼 중앙 반전 자막이 잘렸다).
           ★없는 컷은 확대하지 않는다 — 중앙 화면 자막이 내용인 컷을 자르면 안 된다."""
        # ★색 하드코딩 금지 — 소재마다 자막 색이 다르다(노랑 소재 다음에 흰 소재가 와서 재발했다,
        #   2026-09-01 사장님 반려 2회). 번인 자막의 공통 속성 = 밝은 글자에 검은 외곽선.
        #   「밝은 픽셀(≥200)과 어두운 픽셀(≤70)이 맞닿은 자리」를 세면 색과 무관하게 잡힌다.
        #   실측: 자막 프레임 행최대 22~35·총 400+ vs 무자막 0~10·총 ≤65.
        #   ★한 순간이라도 검출되면 「있음」이다 — 자막이 드문드문한 컷(컷05 실측: 8샘플 중 1~2개만
        #   강검출)을 「없음」으로 놓치는 것이 오탐보다 치명적이다(사장님 절대 요구).
        #   자막 윗변도 함께 실측한다 — 전역 중앙값(find_burned_subs)만 믿었다가 여운 구간의
        #   더 높은 자막(전역 840 vs 실측 ~830)이 한계선을 뚫었다(잔존 게이트가 잡음, 2026-09-01).
        band0 = int(1080 * 0.70)
        tops = []
        found = False
        for j, f in enumerate((0.1, 0.2, 0.35, 0.5, 0.6, 0.7, 0.85, 0.95)):
            try:
                hit, top = 텍스트검출(grab(t0 + (t1 - t0) * f, f"b{t0:.0f}_{j}")[band0:, :, :], top=True)
                if hit:
                    found = True
                    if top is not None:
                        tops.append(band0 + top)
            except Exception:
                pass
        return found, (min(tops) if tops else None)

    # 1차 — 컷별 번인 유무·자막 윗변 실측
    burn, tops_all = [], []
    for seg in segs:
        f_, t_ = seg_has_burned(seg["t0"], seg["t1"])
        burn.append(f_)
        if t_ is not None:
            tops_all.append(t_)
    limit_y = min([sub_top] + tops_all) - 12          # 전역 + 컷 실측 중 최솟값 위 여유 12px
    s = min(1.25, max(box_h / (limit_y - 0), box_h / 1080) * 1.03)
    print(f"번인 자막 윗변 — 전역 {sub_top} · 컷 실측 최소 {min(tops_all) if tops_all else '없음'} → 한계 y={limit_y} · 확대 {s*100:.1f}%")
    cy_lo = b["y1"] - (limit_y - b["y0"]) * s
    cy_hi = b["y0"] + 540 * s
    px_lo, px_hi = 1080 - 960 * s, 960 * s

    for i, (seg, pic) in enumerate(zip(segs, picture)):
        if not burn[i]:
            pic["box"] = {"scale": round(box_h / 1080 * 100, 3),
                          "pos": f"0.5:{(b['y0'] + b['y1']) / 2 / CFG['video']['h']:.6f}"}
            print(f"  컷{i+1:02d}: 번인 자막 없음 → 풀샷 유지")
            continue
        xf, yf = face_center(seg["t0"], seg["t1"], i)
        cy = clamp(970 - (yf - 540) * s, cy_lo, cy_hi)
        px = clamp(540 - (xf - 960) * s, px_lo, px_hi)
        pic["box"] = {"scale": round(s * 100, 3), "pos": f"{px / 1080:.6f}:{cy / 1920:.6f}"}
        print(f"  컷{i+1:02d}: 번인 자막 있음 → 확대 {s*100:.0f}% · 얼굴 ({xf:.0f},{yf:.0f})")
    # 미리보기 — 상자에 담길 화면을 컷별 box 값 그대로 잘라 확인용으로 남긴다
    pvdir = os.path.join(out_root, "_미리보기")
    os.makedirs(pvdir, exist_ok=True)

    def 미리보기생성():
      for i, (seg, pic) in enumerate(zip(segs, picture)):
        try:
            sc = pic["box"]["scale"] / 100.0
            pxn, cyn = (float(v) for v in pic["box"]["pos"].split(":"))
            px_, cy_ = pxn * 1080, cyn * 1920
            x0 = clamp(960 + (0 - px_) / sc, 0, 1920 - 1080 / sc)
            y0 = clamp(540 + (b["y0"] - cy_) / sc, 0, 1080 - box_h / sc)
            mid = (seg["t0"] + seg["t1"]) / 2
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{mid:.2f}", "-i", dst_src,
                            "-frames:v", "1", "-vf",
                            f"crop={1080/sc:.0f}:{box_h/sc:.0f}:{x0:.0f}:{y0:.0f},scale=540:-2",
                            os.path.join(pvdir, f"컷{i+1:02d}.png")], check=True)
        except Exception as e:
            print("  미리보기 실패:", e)

    미리보기생성()

    # ★잔존 번인 게이트 (절대 재발 금지 — 2026-09-01 사장님 반려 2회) — 상자에 담길 화면의
    #   하단 40% 에서 외곽선 자막이 검출되면 실패다. 판정이 틀려도 여기서 걸린다.
    #   ★걸린 컷은 자동으로 확대로 승격해 다시 만들고 재검사한다 — 표본 추첨(드문드문한 자막)에
    #   판정이 흔들려도 게이트가 최종 판정자다.
    import numpy as np

    def 컷잔존(i):
        seg, pic = segs[i], picture[i]
        sc = pic["box"]["scale"] / 100.0
        pxn, cyn = (float(v) for v in pic["box"]["pos"].split(":"))
        px_, cy_ = pxn * 1080, cyn * 1920
        x0 = clamp(960 + (0 - px_) / sc, 0, 1920 - 1080 / sc)
        y0 = clamp(540 + (b["y0"] - cy_) / sc, 0, 1080 - box_h / sc)
        for f in (0.2, 0.4, 0.6, 0.8):
            t = seg["t0"] + (seg["t1"] - seg["t0"]) * f
            p = os.path.join(wdir, "_gatechk.png")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", dst_src,
                            "-frames:v", "1", "-vf",
                            f"crop={1080/sc:.0f}:{box_h/sc:.0f}:{x0:.0f}:{y0:.0f}", p],
                           check=True, capture_output=True)
            a = np.asarray(Image.open(p).convert("RGB"))
            if 텍스트검출(a[int(a.shape[0] * 0.60):, :, :]):
                return True
        return False

    for round_ in range(3):
        걸림 = [i for i in range(len(picture)) if 컷잔존(i)]
        if not 걸림:
            break
        print(f"  잔존 게이트 {round_+1}회차 — 컷 {[i+1 for i in 걸림]} 확대로 승격해 다시 잡는다")
        for i in 걸림:
            seg = segs[i]
            xf, yf = face_center(seg["t0"], seg["t1"], f"g{i}")
            cy = clamp(970 - (yf - 540) * s, cy_lo, cy_hi)
            px = clamp(540 - (xf - 960) * s, px_lo, px_hi)
            picture[i]["box"] = {"scale": round(s * 100, 3), "pos": f"{px / 1080:.6f}:{cy / 1920:.6f}"}
    잔존 = [i + 1 for i in range(len(picture)) if 컷잔존(i)]
    print(("  [OK] " if not 잔존 else "  [X] ") + f"컷 하단 잔존 번인 자막 0  걸린 컷 {잔존}")
    assert not 잔존, f"컷 {잔존} 하단에 번인 자막이 남아 있다 — 확대 후에도 남는다"
    미리보기생성()          # 승격된 컷의 미리보기 갱신
    scale = round(s * 100, 3)
    cy = round((b["y0"] + b["y1"]) / 2 / CFG["video"]["h"], 6)

    tl = {"title": f"스케치 {slug}", "total_s": round(total, 4),
          "source": dst_src, "source_dur_s": src_info["dur"],
          "src_audio_tickrate": src_info["audio_tickrate"],
          "template": dst_tpl,
          "box": {"scale": scale, "pos": f"0.5:{cy}"},
          "picture": picture, "narration": narration, "sfx": sfx, "cues": cues}
    out = os.path.join(out_root, "timeline_sk.json")
    json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("생성:", out)
    print(f"컷 {len(picture)} · 나레 {len(narration)} · 큐 {len(cues)} (나레1·대사 {len(lines)} — 제목은 껍데기에 굽는다) · 총 {total:.1f}s")
    print(f"상자: scale {scale}% · pos 0.5:{cy}")


if __name__ == "__main__":
    main()
