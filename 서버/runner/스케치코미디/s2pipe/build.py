# -*- coding: utf-8 -*-
"""한 편을 굽는다. ★나레이션 TTS 요금이 나간다.

sketch 와 갈리는 지점은 **레이아웃**이다. 저쪽은 영상을 가운데 상자에 넣는 5층
구조인데, 여기는 **영상이 화면을 꽉 채우고 그 위에 타이틀바·자막·워터마크를 얹는다**
(지침서 1장). 그래서 crop 비율이 9:16 이고 인물이 훨씬 크게 잡힌다.

순서
    1) 구간을 잘라 붙인다 (framing.plan_beats — 자주·작게)
    2) 오버레이 한 장을 그린다 (타이틀바·해시태그·워터마크)
    3) 자막 ASS — 대사와 나레이션을 **색으로 가른다**
    4) 나레이션을 굽고 제자리에 얹는다 (★요금)
    5) 합성·렌더 + 라우드니스
"""
import json
import os
import random
import subprocess
import sys
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)
V, L = CFG["video"], CFG["layout"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run(argv, capture=False):
    p = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"실패: {' '.join(str(a) for a in argv[:6])}…\n"
                         f"{(p.stderr or '')[-700:]}")
    return p.stdout if capture else ""


def probe_wh(src):
    o = run(["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "default=nw=1", src], capture=True)
    d = dict(x.split("=") for x in o.strip().splitlines() if "=" in x)
    return int(d["width"]), int(d["height"])


def probe_dur(src):
    o = run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", src], capture=True)
    try:
        return float(o.strip())
    except ValueError:
        return 0.0


def find_burned_subs(src, W, H, dur, n=10):
    """원본에 박힌 자막의 윗변. 못 찾으면 None. 우리 자막과 두 겹이 되는 것을 막는다."""
    import numpy as np
    tops = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        p = os.path.join(__import__("tempfile").gettempdir(), f"_s2burn{i}.png")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss",
                            f"{t:.2f}", "-i", src, "-frames:v", "1", "-y", p],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(p):
            continue
        try:
            a = np.asarray(Image.open(p).convert("RGB")).astype(int)
        except Exception:                                # noqa: BLE001
            continue
        finally:
            pass
        band = a[int(H * 0.75):, :, :]
        g = band.mean(axis=2)
        # ★외곽선 없는 노란 예능자막도 같이 잡는다 (Deep03 실측 2026-09-03)
        노랑 = (band[:, :, 0] >= 200) & (band[:, :, 1] >= 170) & (band[:, :, 2] <= 140)
        y_ok = int(노랑.sum()) >= 1500
        rows = np.where(((g > 200).sum(axis=1) > W * 0.02) |
                        (y_ok & (노랑.sum(axis=1) > 15)))[0]
        if len(rows):
            tops.append(int(H * 0.75) + int(rows[0]))
        try:
            os.remove(p)
        except OSError:
            pass
    if len(tops) < 3:
        return None
    tops.sort()
    return tops[len(tops) // 2]


def cut_and_join(src, segs, dst, work, fps):
    """구간을 잘라 **여백 없이** 붙인다. crop 은 비트마다 조금씩 움직인다."""
    from . import framing
    from . import split as sp

    b = L["video_box"]                           # ★1080x908 상자 (sketch 껍데기)
    W, H = probe_wh(src)
    usable_h = H
    if b.get("avoid_burned_subs"):
        top = find_burned_subs(src, W, H, max(s["t1"] for s in segs))
        if top:
            usable_h = top - b.get("safe_pad_px", 8)
            print(f"    원본 자막 감지: y={top} ({top/H*100:.1f}%) →"
                  f" 세로 {usable_h}px 만 쓴다", flush=True)
        else:
            usable_h = int(H * b.get("sub_zone_top", 0.872)) - b.get("safe_pad_px", 8)
            print(f"    원본 자막 못 찾음 → 기본값으로 세로 {usable_h}px", flush=True)

    cuts = sp.scene_cuts(src) if b.get("follow_face") else []
    parts, log = [], {"segments": [], "beats": []}

    def bake_beats(a, bnd, plan):
        legs, tags = [], []
        for j, (bt0, bt1, vf, _) in enumerate(plan):
            cut = (f"trim=start={bt0-a:.3f}"
                   + ("" if j == len(plan) - 1 else f":end={bt1-a:.3f}"))
            legs.append(f"[0:v]{cut},setpts=PTS-STARTPTS,{vf},setsar=1[v{j}]")
            tags.append(f"[v{j}]")
        fc = ";".join(legs) + f";{''.join(tags)}concat=n={len(plan)}:v=1:a=0[vo]"
        p = os.path.join(work, f"seg{len(parts):03d}.mp4")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(a),
             "-to", str(bnd), "-i", src, "-filter_complex", fc,
             "-map", "[vo]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", str(CFG["ffmpeg"]["crf"]), "-c:a", "aac", "-b:a",
             CFG["ffmpeg"]["audio_bitrate"], "-avoid_negative_ts", "make_zero",
             "-y", p])
        parts.append(p)

    prev = None
    for i, s in enumerate(segs):
        plan = framing.plan_beats(src, s, i, W, H, usable_h, b, work, cuts, prev)
        if not plan:
            vf, info = framing.plan_frame(src, s, i, W, H, usable_h, b, work, prev=prev)
            p = os.path.join(work, f"seg{len(parts):03d}.mp4")
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(s["t0"]),
                 "-to", str(s["t1"]), "-i", src, "-vf", vf, "-c:v", "libx264",
                 "-preset", "veryfast", "-crf", str(CFG["ffmpeg"]["crf"]),
                 "-c:a", "aac", "-b:a", CFG["ffmpeg"]["audio_bitrate"],
                 "-avoid_negative_ts", "make_zero", "-y", p])
            parts.append(p)
            prev = info["crop"]
            log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                    "phase": s.get("phase"), "part": p, "beats": 0})
            continue
        bake_beats(s["t0"], s["t1"], plan)
        prev = plan[-1][3]["crop"]
        log["segments"].append({"i": i, "t0": s["t0"], "t1": s["t1"],
                                "phase": s.get("phase"), "part": parts[-1],
                                "beats": len(plan)})
        for a, e, _vf, info in plan:
            log["beats"].append({"seg": i, "t0": a, "t1": e,
                                 "crop": list(info["crop"]),
                                 "at_cut": bool(info["at_cut"])})
        zs = [x[3]["zoom"] for x in plan]
        nf = sum(1 for x in plan if x[3]["face"])
        # ★얼굴 수를 반드시 찍는다. **조용히 실패하는 코드를 만들지 마라** — 모델
        #   (assets/models/yunet.onnx)이 없으면 얼굴을 하나도 못 찾고 확대가 기본값
        #   1.24 로 굳는데, 안 찍으면 그냥 그렇게 구워진다(실제로 한 번 그렇게 나왔다).
        print(f"    P{s.get('phase')} 조각 {i} {s['t1']-s['t0']:5.1f}초 →"
              f" 비트 {len(plan):2d}개(얼굴 {nf}) · 확대 {min(zs):.2f}~{max(zs):.2f}배"
              + ("  ★얼굴을 하나도 못 찾았다" if nf == 0 else ""), flush=True)

    lst = os.path.join(work, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{p.replace(chr(92), '/')}'\n")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", "-y", dst])

    off = 0.0
    for e in log["segments"]:
        d = probe_dur(e["part"])
        e["out_t0"], e["out_dur"] = round(off, 3), round(d, 3)
        off += d
    log["out_dur"] = round(off, 3)
    json.dump(log, open(os.path.join(work, "beats.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return dst


# ★글꼴을 못 찾으면 **반드시 진짜 글꼴로 떨어져야 한다.** `load_default()` 는 고정 크기
#   비트맵이라 **size 가 통째로 무시된다** — 헤더 글자가 아무리 키워도 작게 나온 이유가
#   이것이었다. 사다리 끝까지 못 찾으면 조용히 굽지 말고 **멈춘다**(맥 이식 2026-08-28).
FALLBACK = [
    r"C:\Windows\Fonts\malgunbd.ttf", r"C:\Windows\Fonts\malgun.ttf",  # 윈도우
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",                      # 맥 — 맑은 고딕 대응
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
]


def _font(rel, px):
    # ★rel 이 빈 문자열이면 os.path.join 이 폴더를 돌려준다 — isfile 로 걸러야 한다.
    for p in ([os.path.join(HERE, rel)] if rel else []) + FALLBACK:
        if p and os.path.isfile(p):
            try:
                return ImageFont.truetype(p, px)
            except OSError:
                continue
    raise SystemExit(f"글꼴을 못 찾았다 (rel={rel!r}) — load_default 는 size 를 무시하므로 쓰지 않는다. FALLBACK 사다리를 확인하라.")


def draw_frame(proj, dst):
    """움직이지 않는 층을 한 장으로 — 헤더·제목·출처. 영상과 자막은 ffmpeg 가 얹는다.

    ★껍데기는 sketch 에서 가져왔다. 좌표·글꼴은 「먹기전에」 10편 실측이라 손대지 않는다.
    """
    im = Image.new("RGB", (V["w"], V["h"]), "#" + L["bg"])
    d = ImageDraw.Draw(im)

    h = L["header"]
    ch = CFG["channel"]
    icon = os.path.join(HERE, ch.get("icon", "") or "")
    if ch.get("icon") and os.path.isfile(icon):
        ic = Image.open(icon).convert("RGB").resize((h["icon_size"], h["icon_size"]))
        im.paste(ic, (h["icon_x"], h["y0"] + 8))
    else:
        d.ellipse([h["icon_x"], h["y0"] + 8,
                   h["icon_x"] + h["icon_size"], h["y0"] + 8 + h["icon_size"]],
                  outline="#E23B3B", width=8)
    tx = h["icon_x"] + h["icon_size"] + 26
    d.text((tx, h["y0"] + 10), ch.get("handle", ""),
           font=_font("", h["handle_size"]), fill="#111111")
    d.text((tx, h["y0"] + 10 + h["handle_size"] + 12), ch.get("name", ""),
           font=_font("", h["name_size"]), fill="#333333")

    # 제목 — ★항상 2줄, 가운데 정렬
    t = L["title"]
    tf = _font(t["font"], t["line_h"])
    title = proj.get("title")
    if isinstance(title, str):                           # 옛 형식이면 그대로 한 줄
        title = [title]
    for i, line in enumerate((title or [])[:t["lines"]]):
        y = t["line1_y"] if i == 0 else t["line2_y"]
        w = d.textlength(line, font=tf)
        d.text(((V["w"] - w) / 2, y), line, font=tf, fill="#" + t["color"])

    # 댓글 층 — 유튜브 댓글 UI 를 흉내 낸다(벤치 실측). 고정된 것만 여기 그리고
    # 본문과 좋아요 수는 장면 따라 바뀌므로 ASS 가 얹는다.
    if proj.get("comments"):
        cm = L["comment"]
        cy = cm["y0"] + 6
        d.ellipse([cm["icon_x"], cy,
                   cm["icon_x"] + cm["icon_size"], cy + cm["icon_size"]],
                  fill="#C9CDD4")
        # ★닉네임은 뭉갠다 — 원본 시청자 이름을 그대로 노출하지 않는다
        nx = cm["text_x"]
        d.rounded_rectangle([nx, cm["nick_y"], nx + cm["nick_w"],
                             cm["nick_y"] + cm["nick_h"]], radius=11, fill="#D6D9DE")
        df = _font("", cm["date_size"])
        d.text((nx + cm["nick_w"] + 16, cm["nick_y"] - 2), cm.get("date", ""),
               font=df, fill="#" + cm.get("date_color", "8A8F98"))
        # 좋아요 엄지와 답글 — 실제 댓글처럼 보이게 하는 것이 목적이다
        mf = _font("", cm["meta_size"])
        my = cm["meta_y"]
        d.rectangle([nx, my + 10, nx + 12, my + 26], fill="#8A8F98")
        d.rectangle([nx + 12, my + 4, nx + 26, my + 26], fill="#8A8F98")
        d.text((nx + 150, my), cm.get("reply", "답글"), font=mf,
               fill="#" + cm.get("meta_color", "8A8F98"))

    # 출처 — 설명란이 아니라 화면 안에 박는다
    c = L["credit"]
    cr = proj.get("credit") or {}
    if cr.get("channel") or cr.get("title"):
        txt = c["format"].format(channel=cr.get("channel", ""), title=cr.get("title", ""))
        cf = _font(t["font"], c["size"])
        w = d.textlength(txt, font=cf)
        d.text(((V["w"] - w) / 2, c["y0"]), txt, font=cf, fill="#" + c["color"])

    im.save(dst)
    return dst


def _ts(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(proj, dst, total, narrs=()):
    """대사와 나레이션을 **색으로 가른다**(지침서 3장).

    ★**나레이션 자막은 `subs` 가 아니라 `segments[].narration` 에서 만든다.**
      두 곳에 같은 문구를 두면 한쪽만 고쳤을 때 어긋난다 — 실제로 나레이션을 줄였는데
      화면에는 옛 문구가 그대로 나와 좌우로 넘쳤다. 실제로 **구운 음성의 길이**(narrs)를
      그대로 자막 길이로 쓴다.
    """
    s, ns = L["subtitle"], L["narration_sub"]
    size = int(s["cap_h"] / 0.72)
    nsize = int(ns["cap_h"] / 0.72)

    def bgr(h):
        return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}"

    c = L["comment"]
    # ★Format 줄은 sketch 와 **똑같이** 쓴다. 필드를 줄여 쓰면 libass 가 값을 어긋난
    #   자리에서 읽는다 — 댓글 글꼴·크기가 안 맞던 이유가 여기에도 있었다.
    # ★댓글은 얇은 시스템 글꼴이다 — 자막 글꼴을 쓰면 너무 굵어 댓글로 안 보인다.
    #   윈도우는 맑은 고딕, 맥은 Apple SD Gothic Neo (맥 이식 2026-08-28, 사람 눈 확인 대상).
    cmt_font = c.get("font_name") or ("Malgun Gothic" if os.name == "nt" else "Apple SD Gothic Neo")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {V['w']}
PlayResY: {V['h']}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: main,{s.get('font_name', 'Malgun Gothic')},{size},&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{s['outline_px']},0,2,60,60,{V['h'] - s['baseline_y']},1
Style: narr,{s.get('font_name', 'Malgun Gothic')},{nsize},{bgr(ns['color'])},{bgr(ns.get('outline', '000000'))},&H00000000,-1,0,0,0,100,100,0,0,1,{ns.get('outline_px', 7)},0,2,40,40,{V['h'] - ns['baseline_y']},1
Style: cmt,{cmt_font},{c['text_size']},{bgr(c['color'])},&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,1,0,0,7,{c['text_x']},40,{c['text_y']},1
Style: cmtlike,{cmt_font},{c['meta_size']},{bgr(c.get('meta_color','8A8F98'))},&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,1,0,0,7,{c['text_x'] + 36},40,{c['meta_y']},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    # 대사 — `subs` 에서. 나레이션 몫(kind=narr)은 여기서 빼고 아래에서 다시 만든다.
    subs = sorted([x for x in proj.get("subs", []) if x.get("kind") != "narr"],
                  key=lambda x: x["t"])
    body = []
    hi = s["max_chars"]
    for i, cur in enumerate(subs):
        end = subs[i + 1]["t"] if i + 1 < len(subs) else min(cur["t"] + 3.0, total)
        if end <= cur["t"]:
            continue
        txt = (cur.get("text") or "").replace("\n", " ")
        if len(txt) > hi:                                # 넘치면 화면 밖으로 나간다
            txt = txt[:hi - 1] + "…"
        body.append(f"Dialogue: 0,{_ts(cur['t'])},{_ts(end)},main,,0,0,0,,{txt}")

    # 나레이션 — 실제로 구운 음성과 **같은 문구·같은 길이**로 얹는다
    seg_narr = {}
    at = 0.0
    for sg in proj["segments"]:
        t = (sg.get("narration") or "").strip()
        if t:
            seg_narr[round(at, 3)] = t
        at += sg["t1"] - sg["t0"]
    spans = []
    for a, wav in narrs:
        t = seg_narr.get(round(a, 3))
        if not t:
            continue
        try:
            d = probe_dur(wav)
        except Exception:                                # noqa: BLE001
            d = 3.0
        spans.append((a, a + d))
        body.append(f"Dialogue: 0,{_ts(a)},{_ts(a + d)},narr,,0,0,0,,{t}")

    # ★★나레이션이 뜨는 동안 **대사 자막을 감춘다.** 둘이 겹쳐 자막이 2줄로 뭉쳐
    #   나왔다. 그 구간은 원음도 죽였으니 읽을 대사가 없다.
    if spans and CFG["narration"].get("hide_line_subs", True):
        def _sec(v):
            return sum(float(x) * m for x, m in zip(v.split(":"), (3600, 60, 1)))

        keep, cut_n = [], 0
        for ln in body:
            if ",main," not in ln:
                keep.append(ln)
                continue
            p = ln.split(",")
            st, en = _sec(p[1]), _sec(p[2])
            # ★★**구간이 겹치면 감춘다 — 시작 시각만 보면 안 된다.**
            #   나레이션 **전에 시작해서** 그 위로 흘러 들어오는 자막이 그대로
            #   남아 두 줄이 겹쳤다(실측 2026-08-19).
            if any(st < b + 0.2 and en > a - 0.2 for a, b in spans):
                cut_n += 1
                continue
            keep.append(ln)
        if cut_n:
            print(f"    나레이션과 겹쳐 감춘 대사 자막 {cut_n}줄", flush=True)
        body = keep

    # 댓글 — 편 전체에 균등 배치한다. **읽을 게 계속 바뀌어야 지루하지 않다**
    cmts = proj.get("comments", [])
    if cmts:
        cc = L["comment"]
        hi, per = cc["max_chars"], max(1, cc["max_chars"] // cc.get("lines", 2))
        # ★★**길이에 비례해 시간을 나눈다.** 균등하게 주면 51자짜리는 못 읽고
        #   14자짜리는 남아돈다(한국어 묵독은 초당 8~12자다). 짧은 것을 빨리
        #   넘기면 그만큼 긴 것에 줄 수 있어 **같은 시간에 더 많이 담긴다.**
        floor = cc.get("min_sec", 2.2)
        wts = [max(len((c.get("text") or "")), 12) for c in cmts]
        sw = sum(wts) or 1
        spans_c, at_c = [], 0.0
        for w in wts:
            d = max(floor, total * w / sw)
            spans_c.append((at_c, at_c + d))
            at_c += d
        if at_c > total:                             # 최소 시간 때문에 넘치면 줄인다
            k = total / at_c
            spans_c = [(a * k, b * k) for a, b in spans_c]

        def likes(v):
            """유튜브처럼 줄여 쓴다 — 4400 → 4.4천"""
            if v >= 10000:
                return f"{v/10000:.1f}만".replace(".0", "")
            if v >= 1000:
                return f"{v/1000:.1f}천".replace(".0", "")
            return str(v)

        for i, cm in enumerate(cmts):
            t = (cm.get("text") or "").replace("\n", " ")
            if len(t) > hi:                              # 넘치면 화면 밖으로 나간다
                t = t[:hi - 1] + "…"
            # ★두 줄로 나눠 넣는다(\\N). 벤치도 긴 댓글을 2줄로 보여 준다
            if len(t) > per:
                cutp = t.rfind(" ", 0, per + 4)
                cutp = cutp if cutp >= per * 0.5 else per
                t = t[:cutp].rstrip() + "\\N" + t[cutp:].lstrip()
            a, b = _ts(spans_c[i][0]), _ts(spans_c[i][1])
            body.append(f"Dialogue: 0,{a},{b},cmt,,0,0,0,,{t}")
            if cm.get("likes"):
                body.append(f"Dialogue: 0,{a},{b},cmtlike,,0,0,0,,{likes(cm['likes'])}")

    body.sort(key=lambda x: x.split(",")[1])
    open(dst, "w", encoding="utf-8").write(head + "\n".join(body) + "\n")
    return dst


def narrate(proj, work, total):
    """나레이션을 굽고 (시작초, wav) 목록을 준다. ★여기서 요금이 나간다."""
    from . import tts
    n = CFG["narration"]
    if not n.get("enabled") or not n.get("voice_id"):
        return []
    out, at = [], 0.0
    for i, s in enumerate(proj["segments"]):
        span = s["t1"] - s["t0"]
        text = (s.get("narration") or "").strip()
        if text:
            wav = os.path.join(work, f"narr{i:02d}.wav")
            _p, d = tts.synth(text, n, wav, os.path.join(work, "_tts"))
            if d > span:
                print(f"    ★나레 {i} 가 조각보다 길다 ({d:.1f}초 > {span:.1f}초)"
                      f" — 다음 대사와 겹친다", flush=True)
            print(f"    나레 {i}: {d:.2f}초  {text[:30]}", flush=True)
            out.append((round(at, 3), wav))
        at += span
    return out


def pick_sfx(tag):
    """`@꼬리표` 에서 하나를 고른다. 없으면 None — 조용히 넘기지 않고 알린다."""
    cat = os.path.join(CFG["paths"]["assets"], "catalog.json")
    if not os.path.isfile(cat) or not tag.startswith("@"):
        return None
    d = json.load(open(cat, encoding="utf-8"))
    cands = [s["file"] for s in d.get("sfx", []) if s.get("tag") == tag[1:]]
    if not cands:
        print(f"    ★효과음 {tag} 이 카탈로그에 없다", flush=True)
        return None
    return os.path.join(HERE, CFG["assets"]["sfx_dir"], random.choice(sorted(cands)))


def compose(cut, frame, ass, narrs, sfx_at, dst):
    """정적 층 위에 영상 상자를 얹고 자막을 태운 뒤 소리를 섞는다.

    ★입력 0 = 배경(정지 그림, loop) · 1 = 잘라 붙인 영상 · 2.. = 나레이션 · 그 뒤 = 효과음
    ★ass 필터는 시스템 글꼴만 본다 — `fontsdir` 로 우리 폴더를 알려줘야 한다.
      **두 경로 다 콜론을 이스케이프한다**(한쪽만 하면 필터 파싱이 통째로 실패한다).
    """
    n, a, b = CFG["narration"], CFG["audio"], L["video_box"]
    # ★★나레이션이 나오는 동안 **원음을 죽인다.** 안 그러면 배우 말과 겹쳐 둘 다
    #   안 들린다. 앞뒤로 조금 더 죽여야 말꼬리가 안 튄다.
    pad = n.get("duck_pad_sec", 0.15)
    duck = ""
    for at, wav in narrs:
        d = probe_dur(wav)
        duck += (f",volume={10 ** (n.get('duck_db', -30) / 20):.4f}"
                 f":enable='between(t,{max(0, at - pad):.2f},{at + d + pad:.2f})'")
    fontsdir = CFG["assets"]["fonts_dir"].replace("\\", "/").replace(":", "\\:")
    ass_p = ass.replace("\\", "/").replace(":", "\\:")

    ins = ["-loop", "1", "-i", frame, "-i", cut]
    amix = [f"[1:a]volume=1.0{duck}[a0]"]
    labels = ["[a0]"]
    for k, (at, wav) in enumerate(narrs):
        ins += ["-i", wav]
        amix.append(f"[{2+k}:a]adelay={int(at*1000)}|{int(at*1000)},"
                    f"volume={10 ** (n['gain_db'] / 20):.3f}[n{k}]")
        labels.append(f"[n{k}]")
    base = 2 + len(narrs)
    for k, (at, path) in enumerate(sfx_at):
        ins += ["-i", path]
        amix.append(f"[{base+k}:a]adelay={int(at*1000)}|{int(at*1000)},volume=0.7[s{k}]")
        labels.append(f"[s{k}]")

    fc = (f"[0:v][1:v]overlay=0:{b['y0']}:shortest=1[o];"
          f"[o]ass='{ass_p}':fontsdir='{fontsdir}'[v];"
          + ";".join(amix)
          + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0[am];"
          + f"[am]loudnorm=I={a['target_lufs']}:TP={a['true_peak_db']}:LRA={a['lra']}[ao]")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error"] + ins
        + ["-filter_complex", fc, "-map", "[v]", "-map", "[ao]",
           "-c:v", "libx264", "-preset", CFG["ffmpeg"]["preset"],
           "-crf", str(CFG["ffmpeg"]["crf"]), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", CFG["ffmpeg"]["audio_bitrate"],
           "-shortest", "-y", dst])
    return dst


def out_name(proj):
    if proj.get("out_name"):
        return proj["out_name"]
    o = CFG["output"]
    day = datetime.now().strftime(o.get("date_format", "%y%m%d"))
    t = proj.get("title") or proj.get("slug", "out")
    if isinstance(t, list):                              # ★제목은 2줄 배열이다
        t = "".join(t)
    for ch in ' \t:*?"<>|.,!~/\\':
        t = t.replace(ch, "")
    return f"{day}{t[:o.get('title_max', 24)]}.mp4"


def report_cuts(proj, work, src):
    """★원본의 어디를 잘랐는지와 Phase 배치를 남긴다. 굽고 나면 확인할 길이 없다."""
    def mmss(s):
        return f"{int(s)//60}:{s - (int(s)//60)*60:04.1f}"

    segs = proj["segments"]
    total = sum(s["t1"] - s["t0"] for s in segs)
    sd = probe_dur(src) if os.path.exists(src) else 0
    names = {p["no"]: p["name"] for p in CFG["edit"]["phases"]}
    print(f"\n── 원본의 어디를 잘랐나"
          + (f" (원본 {mmss(sd)} 중 {total:.1f}초 · {total/sd*100:.0f}%)" if sd else ""))
    at = 0.0
    for i, s in enumerate(segs):
        ph = s.get("phase", 0)
        print(f"  P{ph} {names.get(ph,'?'):<10} 완성본 {mmss(at)}  원본"
              f" {mmss(s['t0'])}-{mmss(s['t1'])} ({s['t1']-s['t0']:4.1f}초)"
              f"  punch {s.get('punch','-'):>2}  {(s.get('what') or '')[:26]}")
        at += s["t1"] - s["t0"]
    order = [s["t0"] for s in segs]
    back = sum(1 for i in range(1, len(order)) if order[i] < order[i - 1])
    print(f"  ★시간을 거스른 자리 {back}곳 — 이 채널은 훅을 위해 일부러 그렇게 한다"
          if back else "  시간 연결: 앞에서 뒤로만 간다")


def run_build(proj, path):
    slug = proj["slug"]
    work = os.path.join(HERE, CFG["paths"]["work"], slug)
    out = os.path.join(HERE, CFG["paths"]["out"])
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)

    src = os.path.join(HERE, CFG["paths"]["work"], f"{proj['source']['id']}.mp4")
    if not os.path.exists(src):
        print(f"원본이 없다: {src}\n  먼저 python -m s2pipe.plan <url>")
        return 1

    segs = proj["segments"]
    total = sum(s["t1"] - s["t0"] for s in segs)
    fps = proj["source"].get("fps") or 30.0
    print(f"구간 {len(segs)}개 · {total:.1f}초 · {fps:.3f}fps", flush=True)

    print("1/5 구간 자르고 붙이기", flush=True)
    cut = cut_and_join(src, segs, os.path.join(work, "cut.mp4"), work, fps)
    print("2/5 층 그리기", flush=True)
    ov = draw_frame(proj, os.path.join(work, "frame.png"))
    # ★나레이션을 먼저 굽는다 — 자막이 **실제 음성 길이**를 그대로 써야 어긋나지 않는다
    print("3/5 나레이션 (★요금)", flush=True)
    narrs = narrate(proj, work, total)
    print("4/5 자막", flush=True)
    ass = write_ass(proj, os.path.join(work, "sub.ass"), total, narrs)

    sfx_at = []
    if CFG["sfx"].get("enabled"):
        at = 0.0
        for s in segs:
            if s.get("phase") == 4:                      # Climax — 크래시 줌 자리
                p = pick_sfx(CFG["sfx"]["map"].get("punch", ""))
                if p:
                    sfx_at.append((round(at, 3), p))
            at += s["t1"] - s["t0"]

    print("5/5 합성·렌더", flush=True)
    dst = compose(cut, ov, ass, narrs, sfx_at, os.path.join(out, out_name(proj)))
    print(f"\n완성: {dst}  ({os.path.getsize(dst)/1024/1024:.1f} MB)")
    report_cuts(proj, work, src)
    return 0

# ★`run` 이라는 이름을 다시 쓰지 마라 — 위의 `run(argv)`(ffmpeg 실행기)를 덮어
#   `capture` 인자에서 죽는다. make.py 는 `run_build` 를 부른다.
