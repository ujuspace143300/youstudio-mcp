# -*- coding: utf-8 -*-
"""원본에 박힌(번인) 자막 «상자»가 완성본 화면에 들어오지 않게 — 카드마다 잰 한계와 최종 관문.

    python -m s2pipe.번인관문 <원본.mp4> <beats.json> [--prproj timeline_sk.json]   # 재기만(종료코드 1 = 걸림)

★2026-09-27 전수 점검(배치로그/잔존점검_결과.md) — 싱글266 26.7~27.9초(높이 뜬 한 줄 카드 · 글자 윗선 938 ·
  상자 윗변 918)·싱글188 68.7~71.5초(날짜 캡션 윗선 952)에 원본 자막 글자가, 85편에 반투명 상자 윗단(948)이
  완성본 상자 아래 끝에 비쳤다. 187 은 두 줄 카드(윗선 ≈910)를 편별 설정 safe_pad_px=80 으로 손으로 막았다.
  클래스: build.find_burned_subs 가 원본 전체에서 고르게 10장만 뽑아 «글자» 윗선의 «중앙값» 하나로 편 전체
  crop 한계를 정했다 — 소수 카드(두 줄·높이 뜬 카드·날짜 캡션)는 중앙값에서 버려지고, 글자보다 20px 위에서
  시작하는 반투명 상자는 처음부터 재지 않았다.
  수리: ① 카드(자막띠시각.카드들 — 박힌 자막이 바뀌는 시각)마다 «상자 윗변»을 잰다(카드상자들).
        ② 조각마다 «그 조각과 겹치는 카드 중 가장 높은 상자 윗변 − 여유» 로 한계를 정한다(조각한계).
        ③ 최종 관문 하나(걸림): 굽기(beats.json 의 모든 crop)와 준비(프리미어 컷 상자)가 같은 함수를 부른다.
           픽셀 글자 검출이 아니라 «crop 밑변 vs 카드 상자 윗변» 위치 비교라 옷·소품 글씨 오탐이 없다.
  왜 예전 검사를 통과했나: 준비의 «컷 하단 잔존 번인 자막 0» 은 프리미어 컷 상자만 봤고(납품 mp4 의 crop 은
  아무도 안 봤다), 픽셀 검출 문턱은 글자 윗머리 몇 px·반투명 상자를 원리상 못 잡는다.
한계(알려짐): 카드 검출 띠(높이 80~90% · 가운데 60%) 밖의 캡션(싱글268 좌상단 «2524년 대한민국» 류)은 카드가
  아니다 — 조각 표식 «가림» [[x0,y0,x1,y1,t0,t1], …] 로 사람이 잰 사각형을 넘기면 굽기(framing.가림경계)가 피하고
  같은 관문이 확인한다.
"""
import json
import os
import subprocess
import sys

import numpy as np

판 = 8                     # 잰 방법이 바뀌면 올린다(캐시 무효)
상자여유 = 20               # 글자 윗선 → 상자 윗변 최소 거리(한 줄 카드 968→948 · 266 높은 카드 938→918 실측)
상자최대 = 45               # 이보다 위로 잰 상자 윗변은 이상치(어두운 장면에서 안/밖 비교가 흐려짐) — 여기서 멈춘다
못잰윗선 = 824              # 카드인데 글자를 못 잰 경우 — 띠 윗끝(864) − 40 (가장 보수적 · 새는 쪽으로 버리지 않는다)
시각여유 = 0.2              # 카드 시각은 10fps 로 잰다 — 앞뒤 0.2초까지 겹친 것으로 본다(굽기 한계)
관문겹침 = 0.1              # 관문: 카드 시각은 10fps 로 재서 끝이 최대 0.1초 늦게 잡힌다 — 그만큼은 겹침이 아니다


def _프레임(src, t, W, H):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", src, "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8)
    return a[:W * H].reshape(H, W).astype(np.int16) if len(a) >= W * H else None


def _글자줄(mn, mx, x0, x1, 밝=185, 어=110):
    """정지 글자 = 최소밝기 ≥185 인 픽셀 가로 3px 안에 최대밝기 ≤110 인 픽셀(글자+외곽선/상자)."""
    br = mn[:, x0:x1] >= 밝
    dk = mx[:, x0:x1] <= 어
    near = np.zeros_like(dk)
    for k in (1, 2, 3):
        near[:, k:] |= dk[:, :-k]
        near[:, :-k] |= dk[:, k:]
    return br & near


def _한카드(src, c0, c1, W, H):
    """(상자윗변, 글자윗선, x0, x1, 잰방법) — 원본 픽셀 좌표.
    ① 카드 안 3장(0.1초 간격)의 최소/최대 밝기로 «정지한 글자» 만 남기고, 카드 앞·뒤 프레임 둘 다에 있던 글자꼴
       (장면 속 정지 무늬 — 후드티 글씨·소파 모서리)은 뺀다(2026-09-27 264·187·188 에서 글자 덩어리가 위 장면 무늬와 붙어
       윗선이 790 까지 튀었다).
    ② 띠(80~90%)에 걸친 줄을 씨앗으로, 위로 «가운데 정렬된 글자 줄»(두 줄·세 줄 카드)만 이어 붙인다.
    ③ 반투명 상자 윗변 = 글자 윗선 위 45px 안에서 «상자 안 밝기 − 상자 밖 밝기» 가 가장 크게 뛰는 줄.
       못 찾으면 글자 윗선 − 20(한 줄 카드 968→948 · 266 높은 카드 938→918 실측 간격). 둘 중 높은 쪽."""
    mid = (c0 + c1) / 2
    d = min(0.1, max(0.0, (c1 - c0) / 2 - 0.05))
    fr = [f for f in (_프레임(src, mid + k * d, W, H) for k in (-1, 0, 1)) if f is not None]
    if not fr:
        return (못잰윗선, None, 0, W, "프레임없음")
    st = np.stack(fr)
    X0, X1 = int(W * 0.12), int(W * 0.88)
    Y0 = int(H * 0.60)
    앞, 뒤 = _프레임(src, c0 - 0.25, W, H), _프레임(src, c1 + 0.25, W, H)
    정지 = None
    if 앞 is not None and 뒤 is not None:
        정지 = _글자줄(앞[Y0:], 앞[Y0:], X0, X1) & _글자줄(뒤[Y0:], 뒤[Y0:], X0, X1)
        z = 정지.copy()
        for k in (1, 2):
            z[k:] |= 정지[:-k]; z[:-k] |= 정지[k:]; z[:, k:] |= 정지[:, :-k]; z[:, :-k] |= 정지[:, k:]
        정지 = z
    mn3, mx3, m1 = st.min(axis=0), st.max(axis=0), st[len(st) // 2]
    두꺼움 = False
    # 앞·뒤에도 같은 글자가 있으면(카드 검출이 한 자막을 둘로 나눔) 정지 무늬 빼기가 글자까지 지운다 — 빼지 않고 다시 잰다
    #   «엄격» = 흰 글자(≥225)·검은 외곽/상자(≤70)만 — 장면 무늬가 자막 줄에 붙어 두꺼워진 카드(싱글187 137초 검은 셔츠)용
    for 방법, mn, mx, 뺌, 문 in (("정지3장", mn3, mx3, 정지, (185, 110)), ("정지3장·무늬포함", mn3, mx3, None, (185, 110)),
                              ("가운데1장", m1, m1, None, (185, 110)), ("정지3장·엄격", mn3, mx3, None, (225, 70))):
        if 방법 == "정지3장" and 정지 is None:
            continue
        g = _글자줄(mn[Y0:], mx[Y0:], X0, X1, *문)
        if 뺌 is not None:
            g = g & ~뺌
        rows = g.sum(axis=1)
        # 줄 덩어리(틈 6px 이하는 한 줄)
        runs, s0, last = [], None, None
        for y in range(len(rows)):
            if rows[y] >= 3:
                if s0 is None:
                    s0 = y
                elif y - last > 6:
                    runs.append((s0, last)); s0 = y
                last = y
        if s0 is not None:
            runs.append((s0, last))
        띠0, 띠1 = int(H * 0.80) - Y0, int(H * 0.90) - Y0
        # 씨앗 = 띠에 걸치거나 그 아래(93% 카드 — 싱글207)의 «한 줄 두께»(10~75px) 덩어리 중 가장 위.
        #   75px 넘는 덩어리는 장면 무늬(후드티 글씨 — 싱글264 42초)라 씨앗이 못 된다.
        걸침 = [r for r in runs if r[1] >= 띠0 and r[0] <= 띠1 + 60 and rows[r[0]:r[1] + 1].sum() >= 40]
        씨 = [r for r in 걸침 if 10 <= r[1] - r[0] <= 75]
        if 걸침 and not 씨:
            두꺼움 = True
        if not 씨:
            continue
        def 어두운바탕(r0, r1, cc):
            return float(np.median(mn[Y0 + r0:Y0 + r1 + 1, X0 + cc[0]:X0 + cc[-1] + 1])) <= 120

        def 폭(r):
            return np.where(g[r[0]:r[1] + 1].any(axis=0))[0]
        # 자막 줄 = 어두운 바탕(반투명 상자·외곽선) 위 밝은 글자. 그런 덩어리가 있으면 그중 가장 위, 없으면(상자 없는
        #   날짜 캡션 — 싱글188) 전체에서 가장 위 — 잘못 골라도 더 자르는 쪽(새는 쪽이 아니다).
        어둠 = [r for r in 씨 if 어두운바탕(r[0], r[1], 폭(r))]
        seed = min(어둠 or 씨, key=lambda r: r[0])

        def 가운데(r):
            cols = np.where(g[r[0]:r[1] + 1].any(axis=0))[0]
            return (X0 + (cols[0] + cols[-1]) / 2, cols[-1] - cols[0]) if len(cols) else (None, 0)
        sc, sw = 가운데(seed)
        top_r = seed
        for _ in range(2):                                   # 위로 두 줄까지(세 줄 카드)
            위 = [r for r in runs if r[1] < top_r[0] and top_r[0] - r[1] <= 35]
            if not 위:
                break
            r = max(위, key=lambda r: r[1])
            c, w_ = 가운데(r)
            if c is None or abs(c - W / 2) > W * 0.10 or abs(c - sc) > W * 0.10 or rows[r[0]:r[1] + 1].sum() < 40 \
                    or not (10 <= r[1] - r[0] <= 75):
                break
            # 자막 줄은 어두운 바탕(상자·외곽선) 위 밝은 글자다 — 밝은 바탕 위 어두운 글씨(후드티 «ORIGINALS»)는 아니다
            #   두 줄 사이 틈도 상자 안이라 어둡다(후드티·셔츠 무늬와 자막 사이는 옷감이라 밝다)
            cc = 폭(r)
            if not 어두운바탕(r[0], r[1], cc) or not 어두운바탕(r[1] + 1, max(r[1] + 1, top_r[0] - 1), 폭(top_r)):
                break
            top_r = r
        gtop = Y0 + top_r[0]
        cols = np.where(g[top_r[0]:seed[1] + 1].any(axis=0))[0]
        x0 = X0 + int(np.percentile(cols, 1))
        x1 = X0 + int(np.percentile(cols, 99)) + 1
        if gtop < 못잰윗선 + 상자여유:
            return (못잰윗선, gtop, x0, x1, 방법 + "·이상치")
        a = st.mean(axis=0)
        in0, in1 = x0 + 20, x1 - 20
        o0, o1 = (max(0, x0 - 90), max(0, x0 - 40)), (min(W, x1 + 40), min(W, x1 + 90))
        box = gtop - 상자여유
        if in1 - in0 > 20 and (o0[1] - o0[0]) + (o1[1] - o1[0]) > 20:
            p = np.array([np.median(a[y, in0:in1]) for y in range(gtop - 상자최대 - 3, gtop + 1)])
            q = np.array([np.median(np.r_[a[y, o0[0]:o0[1]], a[y, o1[0]:o1[1]]]) for y in range(gtop - 상자최대 - 3, gtop + 1)])
            base = gtop - 상자최대 - 3
            best, by = 0.0, None
            for y in range(gtop - 상자최대, gtop - 2):
                i = y - base
                step = (p[i - 3:i].mean() - p[i:i + 3].mean()) - (q[i - 3:i].mean() - q[i:i + 3].mean())
                if step > best:
                    best, by = step, y
            if by is not None and best >= 12:
                box = min(box, by)
                방법 += "·상자"
        return (int(box), int(gtop), int(x0), int(x1), 방법)
    return (못잰윗선, None, 0, W, "이상치·두꺼운 덩어리뿐" if 두꺼움 else "글자못잼")


def 카드상자들(src, log=None):
    """[{t0,t1,top,gtop,x0,x1,how}] — 박힌 자막 카드마다 상자 윗변(원본 픽셀). `<원본>.카드상자.json` 에 둔다."""
    from . import 자막띠시각 as 띠
    src = os.path.abspath(os.path.expanduser(src))
    cards = 띠.카드들(src)
    st = os.stat(src)
    key = f"{st.st_size}:{int(st.st_mtime)}:{len(cards)}:{판}"
    cache = src + ".카드상자.json"
    try:
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("key") == key:
            return c["boxes"]
    except (OSError, ValueError, KeyError):
        pass
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src], capture_output=True, text=True)
    W, H = (int(v) for v in r.stdout.strip().split(",")[:2])
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda c: _한카드(src, c[0], c[1], W, H), cards))
    boxes = [{"t0": c[0], "t1": c[1], "top": r_[0], "gtop": r_[1], "x0": r_[2], "x1": r_[3], "how": r_[4]}
             for c, r_ in zip(cards, res)]
    try:
        tmp = cache + f".{os.getpid()}"
        json.dump({"key": key, "W": W, "H": H, "boxes": boxes}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, cache)
    except OSError:
        pass
    if log:
        n이상 = sum(1 for b in boxes if "이상치" in b["how"] or "못" in b["how"])
        log(f"    박힌 자막 카드 {len(boxes)}장 상자 윗변 잼 — 가장 높은 {min((b['top'] for b in boxes), default='-')}"
            f" · 중앙 {sorted(b['top'] for b in boxes)[len(boxes) // 2] if boxes else '-'}"
            + (f" · 보수값/1장 {n이상}장" if n이상 else ""))
    return boxes


def 겹친카드(boxes, t0, t1, 여유=시각여유):
    return [b for b in boxes if b["t0"] < t1 + 여유 and b["t1"] > t0 - 여유]


def 조각한계(boxes, t0, t1, 기본, pad):
    """조각 [t0,t1] 에서 crop 이 쓸 수 있는 세로(밑변 y 상한). 카드가 없으면 기본(=sub_zone_top − pad)보다 올리지 않는다."""
    겹 = 겹친카드(boxes, t0, t1)
    if not 겹:
        return 기본, None
    hi = min(겹, key=lambda b: b["top"])
    return min(기본, hi["top"] - pad), hi


def 걸림(boxes, crops, 가림=None):
    """최종 관문 — crops: [{t0,t1,x,y,w,h,이름}] (원본 시각·원본 픽셀). 가림: [{t0,t1,x0,y0,x1,y1}] 사람이 잰 화면 캡션.
    crop 사각형이 겹치는 카드 상자(윗변 아래 전부, 가로는 글자 범위)나 가림 사각형과 만나면 걸림."""
    out = []
    for c in crops:
        bx0, bx1, by0, by1 = c["x"], c["x"] + c["w"], c["y"], c["y"] + c["h"]
        for b in boxes:
            겹초 = min(b["t1"], c["t1"]) - max(b["t0"], c["t0"])
            if 겹초 <= 관문겹침:
                continue
            if by1 > b["top"] and bx0 < b["x1"] + 30 and bx1 > b["x0"] - 30:
                out.append({"이름": c.get("이름"), "t": round(max(b["t0"], c["t0"]), 2), "겹초": round(겹초, 2),
                            "밑변": by1, "상자윗변": b["top"], "침범px": by1 - b["top"], "종류": "카드",
                            # 글자 = crop 밑변이 박힌 글자 윗선까지 내려옴(글자가 보인다). 아니면 반투명 상자 윗단만(띠).
                            #   글자 윗선을 못 잰 카드는 글자로 본다(새는 쪽으로 버리지 않는다).
                            "글자": b.get("gtop") is None or by1 > b["gtop"]})
        for g in 가림 or []:
            겹초 = min(g["t1"], c["t1"]) - max(g["t0"], c["t0"])
            if 겹초 <= 관문겹침:
                continue
            if bx0 < g["x1"] and bx1 > g["x0"] and by0 < g["y1"] and by1 > g["y0"]:
                out.append({"이름": c.get("이름"), "t": round(max(g["t0"], c["t0"]), 2), "겹초": round(겹초, 2),
                            "밑변": by1, "상자윗변": g["y0"], "침범px": None, "종류": "가림", "글자": True})
    return out


def beats_crops(log, W, H):
    """beats.json → crop 목록. 비트 · 한 장 구도(frames) · 전체/원문화면 · 프레임-인-프레임 모두.
    (2026-09-27 이전 beats.json 엔 한 장 구도 crop 이 없다 — 그 조각은 «미기록» 으로 돌려준다)"""
    crops, 미기록 = [], []
    for b in log.get("beats", []):
        w, h, x, y = b["crop"]
        crops.append({"t0": b["t0"], "t1": b["t1"], "x": x, "y": y, "w": w, "h": h, "이름": f"조각{b['seg']} 비트"})
    for f in log.get("frames", []):
        w, h, x, y = f["crop"]
        crops.append({"t0": f["t0"], "t1": f["t1"], "x": x, "y": y, "w": w, "h": h, "이름": f"조각{f['seg']} {f.get('kind', '')}"})
    seen = {f["seg"] for f in log.get("frames", [])}
    for s in log.get("segments", []):
        if s.get("beats", 0) == 0 and s["i"] not in seen:
            미기록.append(s["i"])
    return crops, 미기록


def 가림목록(segs):
    """조각 표식 «가림»: [[x0,y0,x1,y1(,t0,t1)], …] (원본 픽셀·원본 초) — 화면 속 캡션 자리(시각 없으면 조각 전체).
    굽기는 framing.가림경계 로 그 자리를 피하고, 이 관문이 같은 사각형으로 확인한다."""
    out = []
    for s in segs:
        for r in s.get("가림") or []:
            t0, t1 = (r[4], r[5]) if len(r) >= 6 else (s["t0"], s["t1"])
            out.append({"t0": t0, "t1": t1, "x0": r[0], "y0": r[1], "x1": r[2], "y1": r[3]})
    return out


def 멈춤(걸):
    """★2026-09-27 23:50 사장님 결정 — 상자 띠만 있는 옛 납품편(85편)은 다시 굽지 않는다. 옛 편을 다시 조립(⑦~⑨)할 때
    막히지 않게 «준비» 는 글자 노출·화면 캡션만 멈추고 상자 윗단(띠)은 주의로 둔다. 굽기(build)는 새로 정한 한계가
    띠까지 빼므로 둘 다 멈춘다(회귀 감시)."""
    return [g for g in 걸 if g.get("글자")]


def 글(걸):
    return "; ".join(f"{g['이름']} {g['t']}초 밑변 {g['밑변']} > {g['종류']} 윗변 {g['상자윗변']}" for g in 걸[:6]) \
        + (f" 외 {len(걸) - 6}건" if len(걸) > 6 else "")


if __name__ == "__main__":
    src, bj = sys.argv[1], sys.argv[2]
    boxes = 카드상자들(src, log=print)
    log = json.load(open(bj, encoding="utf-8"))
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src], capture_output=True, text=True)
    W, H = (int(v) for v in r.stdout.strip().split(",")[:2])
    crops, 미기록 = beats_crops(log, W, H)
    걸 = 걸림(boxes, crops)
    print(("걸림 " + str(len(걸)) + f"(글자 {len(멈춤(걸))}) — " + 글(걸)) if 걸 else "걸림 0", "· 한장구도 미기록 조각", 미기록)
    sys.exit(1 if 걸 else 0)
