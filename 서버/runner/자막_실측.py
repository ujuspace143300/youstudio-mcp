#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/자막_실측.py — 렌더된 영상에서 자막을 **직접 재서** prproj 의 설정값과 나란히 놓는다.

  왜: 프리미어 「글꼴 크기」(폰트 em 설정)와 화면에 찍힌 **잉크 높이**는 다른 축이다.
      두 축을 같은 값으로 취급해 자막이 30~40% 작아지는 사고가 났다(진단일지 §25).
      그래서 같은 프로젝트를 렌더한 영상에서 큐마다 잉크를 재고, prproj 의 설정값과 짝지어 변환비를 얻는다.

  재는 것(큐마다): 잉크 높이 px·%(1080 기준) · 잉크 색(무리별) · 한 큐 안 색이 둘 이상인가(= 단어 강조)
  짝짓는 것: 도너 prproj 의 트랙·시각·폰트·글꼴 크기·런 구성

사용:
  python 서버/runner/자막_실측.py --prproj 도너/볼케이노_FullTime_v26_b05_ppro-v45.prproj
      --영상 <렌더.mp4> --출력 분석/도너자막_실측.json [--보기 3293,4211] [--한계 6]
"""
import argparse, json, os, re, subprocess, sys, tempfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "도너"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prproj_lib import Doc, load, track_items, parse_blob, param_blob, is_source_text, 이름인가, collect_lineage, TPS
from 조립_prproj import 공유계보

from PIL import Image, ImageDraw


def 큐목록(doc, 트랙UID, 트랙이름):
    공유 = 공유계보(doc)
    out = []
    items, _ = track_items(doc, 트랙UID)
    for it in items:
        b = doc.get(it)
        s = re.search(r"<Start>(\d+)</Start>", b)
        e = re.search(r"<End>(\d+)</End>", b)
        t0 = int(s.group(1)) / TPS if s else 0.0
        t1 = int(e.group(1)) / TPS if e else 0.0
        ids, _u = collect_lineage(doc, [it], stop=공유)
        남 = sorted(ids - 공유, key=int)
        st = [i for i in 남 if is_source_text(doc.get(i))]
        if not st:
            continue
        info = parse_blob(param_blob(doc.get(st[0]), doc.xml))
        pos = [i for i in 남 if "<Name>위치</Name>" in doc.get(i) or 이름인가(doc.get(i), "Position")]
        y = None
        if pos:
            m = re.search(r"<StartKeyframe>[^,]+,([^,]+),", doc.get(pos[0]))
            if m and ":" in m.group(1):
                y = float(m.group(1).split(":")[1])
        out.append({"트랙": 트랙이름, "item": it, "t0": round(t0, 3), "t1": round(t1, 3),
                    "y_norm": y, "폰트": info.get("fonts") or [],
                    "크기_설정": [r.get("size") for r in info["runs"]],
                    "런": [r["text"] for r in info["runs"]],
                    "글자": "".join(r["text"] for r in info["runs"])})
    return out


def 프레임(video, t, out, 높이=None):
    argv = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1"]
    if 높이:
        argv += ["-vf", f"scale=-2:{높이}"]                 # 4K 는 1080 으로 줄여서 잰다(비율은 그대로)
    subprocess.run(argv + [out], capture_output=True)
    return os.path.exists(out) and os.path.getsize(out) > 0


def 길이_s(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                       capture_output=True, text=True)
    try:
        return float((r.stdout or "0").strip())
    except ValueError:
        return 0.0


def 표본재기(video, 표본, 그림폴더, 보기수=0):
    """큐 시각을 모를 때 — 프레임을 고르게 뽑아 **자막 줄 높이**를 잰다(레퍼런스 영상용).
       판정은 도너와 **같은 자**: 밝거나 물든 픽셀 + 검은 테두리 + **0.2초 뒤에도 그대로**(전환 효과·모션블러 제외)."""
    dur = 길이_s(video)
    t1p = os.path.join(그림폴더, "_ref.png")
    t2p = os.path.join(그림폴더, "_ref2.png")
    높이들, 프레임수, 자막프레임 = [], 0, 0
    for i in range(표본):
        t = dur * (0.06 + 0.88 * i / max(1, 표본 - 1))
        if not 프레임(video, t, t1p, 높이=1080) or not 프레임(video, t + 0.2, t2p, 높이=1080):
            continue
        img = Image.open(t1p).convert("RGB")
        img2 = Image.open(t2p).convert("RGB")
        if img.size != img2.size:
            continue
        W, H = img.size
        프레임수 += 1
        y0, y1 = int(H * 0.60), H
        mask, 행 = 잉크(img, y0, y1)
        mask2, _행2 = 잉크(img2, y0, y1)
        줄 = []
        for a, b in 줄나누기(행):
            if not (0.012 * H <= b - a <= 0.16 * H) or 폭(mask, a, b) < 0.12 * W:
                continue
            A = {(yy, xx) for yy in range(a, b) for xx, *_ in mask[yy]}
            B = {(yy, xx) for yy in range(a, b) for xx, *_ in mask2[yy]}
            if not A or len(A & B) / len(A) < 0.6:      # 0.2초 뒤에 사라지거나 움직였다 = 자막이 아니다
                continue
            줄.append((a, b))
        if not 줄:
            continue
        자막프레임 += 1
        for a, b in [max(줄, key=lambda ab: sum(행[ab[0]:ab[1]]))]:      # 프레임마다 주 자막 줄 하나
            높이들.append({"t": round(t, 1), "px": b - a, "pct": round((b - a) / H * 100, 2),
                           "y_중심_pct": round((y0 + (a + b) / 2) / H * 100, 1),
                           "색": 색무리(mask, a, b)[:2]})
        if 보기수 and 자막프레임 <= 보기수:
            g = img.crop((0, y0, W, y1))
            d = ImageDraw.Draw(g)
            for a, b in 줄:
                d.rectangle([0, a, W - 1, b], outline=(255, 0, 0), width=2)
            g.save(os.path.join(그림폴더, f"참고_{os.path.basename(video)[:12]}_{i}.png"))
    return {"길이_s": round(dur, 1), "표본": 프레임수, "자막_있는_프레임": 자막프레임, "줄": 높이들}


def 폭(mask, a, b):
    xs = [xx for yy in range(a, b) for xx, *_ in mask[yy]]
    return (max(xs) - min(xs)) if xs else 0


def 부류(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 45:
        return "흰"
    if r == mx:
        return "노랑" if g >= r * 0.7 else "빨강"
    if g == mx:
        return "초록"
    return "파랑"


def 잉크(img, y0, y1, 밖=None, 짝=None, 획=True):
    """자막 픽셀만 남긴다 — 세 조건을 **모두** 만족해야 글자로 센다.

       ① 밝거나(흰 글자) 짙게 물든(색 글자) 픽셀
       ② **큐 밖 프레임과 다르다** — 자막은 큐 안에만 있다(배경이 아무리 밝아도 걸러진다)
       ③ **큐 안 다른 시각과 같다** — 자막은 큐 내내 그 자리에 가만히 있고, 배경(영상)은 움직인다
       ②③ 은 재료가 있을 때만 쓴다."""
    W, H = img.size
    px = img.crop((0, y0, W, y1)).convert("RGB").load()
    qx = 밖.crop((0, y0, W, y1)).convert("RGB").load() if 밖 is not None else None
    sx = 짝.crop((0, y0, W, y1)).convert("RGB").load() if 짝 is not None else None
    h = y1 - y0
    mask, 행 = [], [0] * h
    for yy in range(h):
        row = []
        for xx in range(0, W, 2):
            r, g, b = px[xx, yy]
            mx, mn = max(r, g, b), min(r, g, b)
            if not (mx >= 190 and mn >= 150) and not (mx >= 140 and (mx - mn) >= 60):
                continue
            if qx is not None:
                r2, g2, b2 = qx[xx, yy]
                if abs(r - r2) + abs(g - g2) + abs(b - b2) < 90:      # 큐 밖에도 있던 것 = 배경
                    continue
            if sx is not None:
                r3, g3, b3 = sx[xx, yy]
                if abs(r - r3) + abs(g - g3) + abs(b - b3) > 60:      # 큐 안에서 변한 것 = 배경
                    continue
            if 획:                                                  # 자막 글자는 **검은 테두리**를 두르고 있다
                동네 = [px[xx, max(0, yy - d)] for d in (3, 5, 7)] + [px[xx, min(h - 1, yy + d)] for d in (3, 5, 7)]
                if not any(max(q) <= 95 for q in 동네):
                    continue
            row.append((xx, r, g, b))
        mask.append(row)
        행[yy] = len(row)
    return mask, 행


def 줄나누기(행, 최소=6, 틈=6):
    """행 잉크 곡선을 **줄 단위**로 쪼갠다. 두 줄짜리 자막을 한 덩어리로 재면 높이가 두 배가 된다."""
    peak = max(행) if 행 else 0
    if peak < 최소:
        return []
    문턱 = max(3, peak * 0.10)
    줄, 시작, 빈 = [], None, 0
    for i, v in enumerate(행):
        if v >= 문턱:
            if 시작 is None:
                시작 = i
            빈 = 0
        elif 시작 is not None:
            빈 += 1
            if 빈 >= 틈:
                줄.append((시작, i - 빈 + 1)); 시작 = None
    if 시작 is not None:
        줄.append((시작, len(행)))
    return [(a, b) for a, b in 줄 if b - a >= 6]


def 색무리(mask, a, b):
    """잉크 픽셀을 색 부류로 나눈다 — 흰/빨강/노랑/파랑/초록"""
    c, 합 = Counter(), {}
    for yy in range(a, b):
        for xx, r, g, bb in mask[yy]:
            k = 부류(r, g, bb)
            c[k] += 1
            s = 합.setdefault(k, [0, 0, 0])
            s[0] += r; s[1] += g; s[2] += bb
    tot = sum(c.values()) or 1
    return [{"색": k, "비율": round(v / tot, 3), "평균RGB": [round(합[k][i] / v) for i in range(3)]}
            for k, v in c.most_common()]


def 가로무리(mask, a, b, 간격=14):
    """가로로 끊긴 덩어리(어절 뭉치)마다 색을 본다 — 한 큐 안 단어 강조를 잡는다"""
    cols = Counter()
    for yy in range(a, b):
        for xx, *_ in mask[yy]:
            cols[xx] += 1
    if not cols:
        return []
    xs = sorted(cols)
    무리, 시작, 앞 = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - 앞 > 간격:
            무리.append((시작, 앞)); 시작 = x
        앞 = x
    무리.append((시작, 앞))
    out = []
    for x0, x1 in 무리:
        if x1 - x0 < 10:
            continue
        c, 합 = Counter(), {}
        for yy in range(a, b):
            for xx, r, g, bb in mask[yy]:
                if x0 <= xx <= x1:
                    k = 부류(r, g, bb)
                    c[k] += 1
                    s = 합.setdefault(k, [0, 0, 0]); s[0] += r; s[1] += g; s[2] += bb
        if not c:
            continue
        k, v = c.most_common(1)[0]
        out.append({"x": [x0, x1], "색": k, "비율": round(v / sum(c.values()), 3),
                    "평균RGB": [round(합[k][i] / v) for i in range(3)]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prproj", default=None)
    ap.add_argument("--영상", required=True)
    ap.add_argument("--출력", required=True)
    ap.add_argument("--보기", default="", help="확인용 잘라낸 그림을 남길 item 번호들(쉼표)")
    ap.add_argument("--그림폴더", default=None)
    ap.add_argument("--한계", type=int, default=0)
    ap.add_argument("--표본", type=int, default=0, help="prproj 없이 프레임을 고르게 뽑아 재는 모드(레퍼런스 영상용)")
    a = ap.parse_args()
    if a.표본:
        그림폴더 = a.그림폴더 or os.path.join(tempfile.gettempdir(), "자막실측")
        os.makedirs(그림폴더, exist_ok=True)
        r = 표본재기(a.영상, a.표본, 그림폴더, 보기수=(3 if a.보기 else 0))
        px = sorted(x["pct"] for x in r["줄"])
        요약 = {"영상": os.path.basename(a.영상), **{k: v for k, v in r.items() if k != "줄"},
                "줄_수": len(px),
                "잉크_pct": {"p10": px[len(px) // 10] if px else None, "중앙": px[len(px) // 2] if px else None,
                             "p90": px[len(px) * 9 // 10] if px else None} if px else None,
                "줄": r["줄"]}
        out = os.path.join(ROOT, a.출력) if not os.path.isabs(a.출력) else a.출력
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(요약, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f'{요약["영상"][:40]} · 표본 {r["표본"]} · 자막 프레임 {r["자막_있는_프레임"]} · 줄 {len(px)}개 · 잉크 % '
              f'p10 {요약["잉크_pct"]["p10"] if px else "-"} · 중앙 {요약["잉크_pct"]["중앙"] if px else "-"} · p90 {요약["잉크_pct"]["p90"] if px else "-"}')
        return
    if not a.prproj:
        ap.error("--prproj 또는 --표본")
    doc = Doc(load(a.prproj if os.path.isabs(a.prproj) else os.path.join(ROOT, a.prproj)))
    T = json.load(open(os.path.join(ROOT, "스타일/영화롱폼/규격.json"), encoding="utf-8"))["조립"]["도너"]["트랙_UID"]
    cues = []
    for 트 in ("V2", "V3", "V4"):
        cues += 큐목록(doc, T[트], 트)
    cues.sort(key=lambda c: c["t0"])
    if a.한계:
        cues = cues[:a.한계]
    보기 = {x.strip() for x in a.보기.split(",") if x.strip()}
    그림폴더 = a.그림폴더 or os.path.join(tempfile.gettempdir(), "자막실측")
    os.makedirs(그림폴더, exist_ok=True)
    tmp = os.path.join(그림폴더, "_frame.png")
    tmp2 = os.path.join(그림폴더, "_frame_밖.png")
    tmp3 = os.path.join(그림폴더, "_frame_짝.png")
    결과 = []
    for k, c in enumerate(cues):
        t = c["t0"] + min(0.5, max(0.1, (c["t1"] - c["t0"]) / 2))
        if not 프레임(a.영상, t, tmp):
            c["실측"] = {"오류": "프레임 없음"}; 결과.append(c); continue
        img = Image.open(tmp).convert("RGB")
        W, H = img.size
        # 큐 밖 프레임 — **같은 컷**의 것이라야 배경이 지워진다.
        # 같은 컷인지는 자막이 없는 **위쪽 절반**만 보고 판단한다(자막 자리를 넣고 비교하면 자막 때문에 달라 보인다).
        yc0 = int((c["y_norm"] or 0.9) * H)
        위 = (0, 0, W, max(80, yc0 - 260))
        밖, 최소차 = None, None
        기준 = img.crop(위).resize((96, 40))
        for tb in (c["t0"] - 0.25, c["t1"] + 0.25, c["t0"] - 0.6, c["t1"] + 0.6):
            if tb <= 0 or not 프레임(a.영상, tb, tmp2):
                continue
            cand = Image.open(tmp2).convert("RGB")
            if cand.size != img.size:
                continue
            차 = sum(abs(p - q) for P, Q in zip(cand.crop(위).resize((96, 40)).getdata(), 기준.getdata())
                     for p, q in zip(P, Q)) / (96 * 40 * 3)
            if 최소차 is None or 차 < 최소차:
                밖, 최소차 = cand, 차
        if 최소차 is not None and 최소차 > 18:      # 컷이 바뀌었다 — 배경 지우기에 쓸 수 없다
            밖 = None
        yc = int((c["y_norm"] or 0.9) * H)
        y0, y1 = max(0, yc - 260), min(H, yc + 170)
        짝 = None                       # 같은 큐 안 다른 시각 — 자막은 그대로, 배경은 움직인다
        if c["t1"] - c["t0"] >= 0.7:
            tp = c["t1"] - 0.15 if abs(c["t1"] - 0.15 - t) > 0.25 else c["t0"] + 0.15
            if 프레임(a.영상, tp, tmp3):
                cand = Image.open(tmp3).convert("RGB")
                if cand.size == img.size:
                    짝 = cand
        mask, 행 = 잉크(img, y0, y1, 밖, 짝)
        줄 = 줄나누기(행)
        if not 줄:
            c["실측"] = {"오류": "잉크 없음", "시각": round(t, 2)}; 결과.append(c); continue
        높이 = sorted(b - a for a, b in 줄)
        a0, b0 = max(줄, key=lambda ab: sum(행[ab[0]:ab[1]]))      # 잉크가 가장 많은 줄 = 주 자막 줄
        대표 = b0 - a0
        c["실측"] = {"시각": round(t, 2), "줄수": len(줄), "줄높이_px": 높이,
                     "잉크_px": 대표, "잉크_pct": round(대표 / H * 100, 2),
                     "잉크_y": [y0 + a0, y0 + b0], "밖프레임": (round(최소차, 1) if 밖 is not None else None), "짝프레임": 짝 is not None,
                     "색": 색무리(mask, a0, b0), "가로무리": 가로무리(mask, a0, b0)}
        설정 = [x for x in c["크기_설정"] if x]
        if 설정:
            c["실측"]["잉크대설정"] = round(대표 / max(설정), 3)
        if str(c["item"]) in 보기:
            g = img.crop((0, y0, W, y1))
            d = ImageDraw.Draw(g)
            for a2, b2 in 줄:
                d.rectangle([0, a2, W - 1, b2], outline=(255, 0, 0), width=2)
            g.save(os.path.join(그림폴더, f'큐{c["item"]}_{c["트랙"]}.png'))
        결과.append(c)
        if (k + 1) % 20 == 0:
            print(f"  … {k + 1}/{len(cues)}", flush=True)
    out = os.path.join(ROOT, a.출력) if not os.path.isabs(a.출력) else a.출력
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"영상": os.path.basename(a.영상), "prproj": os.path.basename(a.prproj), "큐": 결과},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    잰것 = [c for c in 결과 if "잉크_px" in c.get("실측", {})]
    print(f'\n큐 {len(결과)}개 · 잰 것 {len(잰것)}개 · 못 잰 것 {len(결과) - len(잰것)}개 → {out}')
    if 보기:
        print("확인 그림:", 그림폴더)


if __name__ == "__main__":
    main()
