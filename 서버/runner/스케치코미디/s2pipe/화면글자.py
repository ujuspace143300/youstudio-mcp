# -*- coding: utf-8 -*-
"""원본 화면에 박힌 글자를 «글자 인식»(macOS 내장 Vision · 한국어)으로 찾는다 — 박힌 자막·화면 캡션의 단일 원천.

    python -m s2pipe.화면글자 <원본.mp4>            # 훑고(캐시) 자막 줄·캡션 후보·판정을 보인다
    python -m s2pipe.화면글자 <원본.mp4> --판정      # 캡션 후보를 agy 로 판정까지(캐시)

★2026-09-29 점심이네 64편 배치 — 박힌 글자 인식이 «특정 모양·특정 자리» 만 알았다(한 클래스, 세 증상):
  (a) 화면 가운데·좌하단에 크게 뜬 원본 캡션을 어떤 관문도 못 잡았다 — 점심이네2 1차 완성본 9~12초에 «6월 14일→1월 03일»
      (원본 21.52~25.78초 · 글줄 높이 0.23H · 가운데)이 보였는데 make·굽기·⑦ 준비 관문이 전부 통과했다. 같은 모양이
      «며칠 뒤»(26·32) «20분 후»(14) «N차 이슈 발생»(29) «강원도 인제»(17) «3시간 후»(1) «2012년·2026년»(36) «PM 6:07»(29)
      «한 달뒤»(22) «8년 전»(33) «다음 날»(37) — 19편 훑기에서 13편.
  (b) 흰 옷·회색 길 위 흰 자막(점심이네3 «너넨 뒤졌어»·«이리 와봐» 202.0~204.6)을 카드로 못 잡았다.
  (c) 밝은 운동화·보도블록(11 219~222)·의자 등받이(5 13.3)·파란 탁자(21 20.1)·냄비(52 247.2)·식탁·흰 티(37)를
      자막 카드로 잡아 전체화면·카드경계 관문이 가짜로 막혔다.
  클래스: 자막띠시각._카드재기 / 번인관문._한카드 는 «화면 아래 60~99% 띠 안의, 밝은 픽셀 3px 곁 어두운 픽셀» 이라는
    한 가지 모양으로 «글자가 있다» 를 정했다. 자리(가운데·좌하단 캡션은 띠 밖) · 대비(그림자만 있는 흰 자막) · 모양(밝은
    물건 가장자리도 같은 모양) 셋 중 하나만 어긋나도 틀린다 — 문턱을 옮기는 술래잡기로는 닫히지 않는다.
  수리(구조): 글자는 «글자 인식기가 읽은 글줄» 로 정한다. 화면 전체를 2fps 로 읽어(원본 250초 ≈ 26초) 글줄마다
    자리·크기·글자를 남기고,
      ① 가운데 아래 자리의 글줄 = 박힌 대사 자막 → 번인관문.카드상자들 이 카드를 «확인»(글자 없는 카드 = 가짜, 뺀다)하고
        카드가 놓친 자막을 채운다.
      ② 그 밖의 읽히는 큰 글줄 = 캡션 후보 → 편집으로 얹은 글자(캡션)인지 장면 속 물건 글자(휴대폰 화면·포장지·간판·책)
        인지를 agy 가 그림으로 판정한다(원본마다 한 번 · 캐시). 캡션은 번인관문 의 «화면캡션» 사각형이 되어 굽기(framing
        가림경계)가 피하고, 굽기·준비·make 관문이 같은 사각형으로 막는다.
    agy 판정이 끝내 안 되면 EvoLink 로 넘기지 않고 멈춘다(2026-09-26 사장님 결정 2 — 그림 판정). 인식기가 없는 컴퓨터(맥이
    아님)는 RuntimeError — 조용히 옛 픽셀 검출로 내려가지 않는다(내려가면 이 구멍이 그대로 열린다).
  주의: 인식기 실행 파일 이름에 한글이 있으면 Vision(CoreML)이 «Unable to compute the prediction» 으로 빈 답을 낸다
    (2026-09-29 실측) — 캐시 이름은 ASCII(screentext_vision_<해시>).
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SWIFT = os.path.join(HERE, "화면글자_vision.swift")
CACHE_DIR = os.path.expanduser("~/.cache/youstudio")

판 = 1                    # 읽는 방법이 바뀌면 올린다(캐시 무효)
FPS = 2.0                 # 훑기 간격 — 원본 캡션은 1초 넘게 뜬다(19편 실측 최단 1.0초)
폭 = 960                  # 읽는 그림 폭(원본 1920 의 절반 — 대사 자막 글줄 높이 ≈ 30px 로 충분)
# 캡션 후보: 확신 0.5 이상 · 한글/숫자 2자 이상 · 글줄 높이 0.045H 이상(19편 캡션 최소 «저녁식사 복불복» 0.048)이 한 장 이상,
#   흐린 표본(확신 0.3)까지 같은 자리에 두 장 이상
후보확신, 후보글자, 후보높이, 후보장수 = 0.5, 2, 0.045, 2
# 대사 자막 자리: 가운데(글줄 중심 x 가 0.5±0.15) · 자막띠 윗끝 0.12H 위(두 줄 자막 윗줄)부터 아래 · 글줄 높이 0.13H 이하
자막가로, 자막위, 자막높이 = 0.15, 0.12, 0.13
판정묶음 = 10             # agy 한 번에 보내는 후보 그림 수


# ───────────────────────── 인식기 ─────────────────────────
def 인식기():
    """컴파일된 인식기 경로(없으면 swiftc 로 만든다). 맥이 아니거나 swiftc 가 없으면 None."""
    if sys.platform != "darwin" or not shutil.which("swiftc"):
        return None
    h = hashlib.sha256(open(SWIFT, "rb").read()).hexdigest()[:12]
    exe = os.path.join(CACHE_DIR, f"screentext_vision_{h}")
    if os.path.exists(exe):
        return exe
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = exe + f".{os.getpid()}"
    r = subprocess.run(["swiftc", "-O", SWIFT, "-o", tmp], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("화면글자 인식기 컴파일 실패: " + r.stderr[-400:])
    os.replace(tmp, exe)
    return exe


def 그림들읽기(paths):
    """[[[확신, x, y, w, h, 글자, …], …] 그림마다] — 비율 좌표(원점 왼쪽 위)."""
    exe = 인식기()
    if exe is None:
        raise RuntimeError("화면글자 인식기 없음 — macOS Vision 전용(swiftc 필요). 박힌 글자 관문을 건너뛰지 않는다")
    if not paths:
        return []
    r = subprocess.run([exe], input="\n".join(paths) + "\n", capture_output=True, text=True, check=True)
    out = {}
    for line in r.stdout.splitlines():
        if line.strip():
            o = json.loads(line)
            out[o["f"]] = o["r"]
    return [out.get(p, []) for p in paths]


def 훑기(src, fps=FPS, width=폭):
    """[(t, rows)] — 원본을 fps 로 풀어 프레임마다 글줄."""
    d = tempfile.mkdtemp(prefix="screentext_")
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={fps},scale={width}:-2", "-q:v", "2",
                        os.path.join(d, "%06d.jpg")], check=True)
        fs = sorted(os.listdir(d))
        res = 그림들읽기([os.path.join(d, f) for f in fs])
        return [(round(i / fps, 3), r) for i, r in enumerate(res)]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def 시각들읽기(src, times, width=폭):
    """시각마다 한 장씩 읽는다 — [(t, rows)]. 카드 확인(짧은 카드는 2fps 훑기 사이에 빠진다)용."""
    d = tempfile.mkdtemp(prefix="screentext_")
    try:
        ps = []
        for k, t in enumerate(times):
            p = os.path.join(d, f"{k:06d}.jpg")
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", src, "-frames:v", "1",
                            "-vf", f"scale={width}:-2", "-q:v", "2", p], capture_output=True)
            ps.append(p)
        있음 = [p for p in ps if os.path.exists(p)]           # 원본 끝을 넘은 시각은 그림이 없다 — 빈 줄로 둔다
        읽음 = dict(zip(있음, 그림들읽기(있음)))
        return [(t, 읽음.get(p, [])) for t, p in zip(times, ps)]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def 원본fps(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        a, b = r.stdout.strip().split(",")[0].split("/")
        return float(a) / float(b or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


def 훑기시각(t, 훑기fps, 영상fps):
    """훑기 표본 시각 t 가 실제로 담은 프레임의 시각.
    ★2026-10-02 실측(합성 영상 — 프레임마다 밝기 = 번호): ffmpeg fps 필터는 [t−½간격, t+½간격) 안의 «마지막» 프레임을 낸다 —
      2fps·23.976 원본에서 표본 t = 원본 t+0.209~0.212초, 4fps 에서 t+0.083~0.085초. 루키치299 149.5초 표본이 읽은 «오빠» 는
      실제로 149.70초에 처음 뜬 자막이었다(조각 끝 149.65 — 안 보였다). 훑기 캐시 시각은 그대로 두고(카드 확인 ±0.3초 창이 이
      치우침 위에서 맞춰졌다) 시각을 정확히 써야 하는 곳(번인관문 글줄 자·비침관문)이 이 함수로 고친다."""
    return t + 0.5 / 훑기fps - 1.0 / 영상fps


def _wh(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", src], capture_output=True, text=True)
    return tuple(int(v) for v in r.stdout.strip().split(",")[:2])


def _캐시경로(src):
    return os.path.abspath(os.path.expanduser(src)) + ".화면글자.json"


def _캐시(src):
    src = os.path.abspath(os.path.expanduser(src))
    st = os.stat(src)
    key = f"{판}:{st.st_size}:{int(st.st_mtime)}:{FPS}:{폭}"
    try:
        c = json.load(open(_캐시경로(src), encoding="utf-8"))
        if c.get("key") == key:
            return c
    except (OSError, ValueError):
        pass
    W, H = _wh(src)
    c = {"key": key, "W": W, "H": H, "fps": FPS, "frames": 훑기(src), "판정": {}}
    _저장(src, c)
    return c


def _저장(src, c):
    p = _캐시경로(src)
    try:
        tmp = p + f".{os.getpid()}"
        json.dump(c, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, p)
    except OSError:
        pass


# ───────────────────────── 글줄 분류 ─────────────────────────
def _줄(row):
    c, x, y, w, h, s = row[:6]
    return {"c": c, "x": x, "y": y, "w": w, "h": h, "s": s,
            "한": len(re.findall(r"[가-힣]", s)), "수": len(re.findall(r"[가-힣0-9]", s))}


def 자막자리(l, 띠):
    """박힌 대사 자막 자리의 글줄인가 — 가운데 · 자막띠 근처 · 한 줄 높이."""
    return (abs(l["x"] + l["w"] / 2 - 0.5) <= 자막가로 and l["y"] + l["h"] / 2 >= 띠[0] - 자막위
            and l["h"] <= 자막높이)


def 자막글자(l):
    """대사 자막 자리에서 «글자가 있다» 고 볼 글줄 — 한글 1자 이상(확신 0.3 이상) 또는 글자 2자 이상(확신 0.5 이상).
    장면 속 영문 무늬(운동화 «OPEN»·옷 로고)는 한글이 아니라 대개 빠진다."""
    return (l["한"] >= 1 and l["c"] >= 0.3) or (l["수"] >= 2 and l["c"] >= 0.5)


자막가운데 = 0.06        # 카드 확인용 대사 자막 글줄: 같은 높이 글줄들을 합친 가로 중심이 0.5±0.06 (19편 자막 97% 가 ±0.04 —
                        #   벗어난 것은 휴대폰 자판 «스페이스»·포장지 값표 같은 장면 글자, 2026-09-29 실측)


def 자막표본(frames, 띠):
    """[(t, 줄)] — 카드 확인·채우기에 쓸 «박힌 대사 자막» 글줄. 한 장 안에서 같은 높이 글줄을 한 줄로 합쳐(인식기가 자막 한 줄을
    둘로 나누기도 한다 — 점심이네37 «팀장 입장에서는» 조각) 그 줄의 가로 중심이 가운데인 것만."""
    out = []
    for t, rows in frames:
        ls = [l for l in (_줄(r) for r in rows) if 자막자리(l, 띠) and 자막글자(l)]
        줄들 = []
        for l in sorted(ls, key=lambda l: l["y"]):
            for g in 줄들:
                if abs(g[0]["y"] - l["y"]) < 0.02 and 0.6 <= l["h"] / max(1e-6, g[0]["h"]) <= 1.6:
                    g.append(l)
                    break
            else:
                줄들.append([l])
        for g in 줄들:
            x0, x1 = min(l["x"] for l in g), max(l["x"] + l["w"] for l in g)
            if abs((x0 + x1) / 2 - 0.5) <= 자막가운데:
                out += [(t, l) for l in g]
    return out


확실확신 = 0.9          # 한 장만 읽힌 자막 표본을 «확실» 로 볼 확신(짧은 자막 «어?» 는 한 장 · 확신 1.0 — 루키치213 111.5초)
확실높이 = (0.6, 1.6)   # 원본 자막 표본 높이 중앙값의 이 배수 안 — 버스·포장지 큰 글씨(점심이네46 «빵빠레» 환산 1.8배)를 뺀다


def 확실한자막표본(표본):
    """자막표본 중 «박힌 대사 자막이 확실한» 것만 — 위치를 잴 때(번인관문._위치보정·글줄)와 완성본 비침 판정(비침관문)용.
    ★2026-10-02 비침관문 회귀(납품 155편) — 자막 자리 가운데에 든 장면 글자가 한 장씩 자막 표본에 섞였다: 점심이네46 아이스크림
      «빵빽»(401.5초 · 확신 0.3 · 한 장) · 59 컵라면 «쌀짬뽈»(315.0 · 0.5 · 한 장) · 35 게임 화면 «스낌이 아직…»(252.5 · 0.3 · 한 장).
      박힌 자막은 1초 넘게 같은 높이에 떠 있어 이웃 표본(±0.6초 · 높이 차 0.015 안 · 글줄 높이 비 0.7~1.4)이 있거나, 짧아도 확신이
      높다(0.9↑). 글줄 높이도 그 원본 자막 높이 중앙값의 0.6~1.6배 안이다. 이 셋으로 거른다.
    카드 확인(가짜 가르기)·놓친 자막 채우기는 예전처럼 모든 표본을 쓴다 — 거기서 빼면 진짜 카드를 버리는 쪽으로 샌다."""
    if not 표본:
        return []
    hs = sorted(l["h"] for _t, l in 표본)
    med = hs[len(hs) // 2]
    out = []
    for t, l in 표본:
        if not (확실높이[0] * med <= l["h"] <= 확실높이[1] * med):
            continue
        if l["c"] >= 확실확신 or any(0 < abs(t2 - t) <= 0.6 and abs(l2["y"] - l["y"]) <= 0.015
                                    and 0.7 <= l2["h"] / max(l["h"], 1e-6) <= 1.4 for t2, l2 in 표본):
            out.append((t, l))
    _윗선고르기(out, med)
    return out


def _비슷한글(a, b):
    ca, cb = re.findall(r"[가-힣0-9]", a), re.findall(r"[가-힣0-9]", b)
    if not ca or not cb:
        return True
    짧, 긴 = (ca, list(cb)) if len(ca) <= len(cb) else (cb, list(ca))
    n = 0
    for ch in 짧:
        if ch in 긴:
            긴.remove(ch)
            n += 1
    return n >= 0.5 * len(짧)


부푼상자 = 1.25        # 글줄 상자 높이가 자막 높이 중앙값의 이 배수를 넘으면 «부푼 상자» — 윗선을 아래 끝에서 잰다
부푼여유 = 1.1         # 부푼 상자의 윗선 = 아래 끝 − 중앙값 × 1.1


def 윗선추정(l, med):
    """글줄 하나의 글자 윗선(화면 비율) — 부푼 상자(높이 > 중앙값 1.25배)는 아래 끝 − 중앙값 × 1.1 (아래 _윗선고르기 주석)."""
    return l["y"] if l["h"] <= 부푼상자 * med else max(l["y"], l["y"] + l["h"] - 부푼여유 * med)


def _윗선고르기(표본, med):
    """같은 자막(이웃 표본 0.6초 안 · 윗선 차 0.04 안 · 글 절반 이상 같음)끼리 묶어 윗선 중앙값을 l["ys"] 에 둔다.
    ★2026-10-02 루키치296 161.0초 — 인식기가 «고마워요 오빠 예쁘게 봐줘서» 한 장만 상자를 위로 24px 크게 잡았다(y 0.830 · 앞뒤 0.852).
      한 장의 상자 흔들림이 카드 윗변·글줄 자를 끌어올려 가짜 걸림을 내지 않게, 위치는 자막 하나의 여러 장 중앙값으로 잰다.
    ★부푼 상자(같은 날 점심이네35 255.5·257.0초 — «야 나 좀 살려줘»·«안돼 안돼 안돼» 상자 윗선 900·901 · 높이 0.099 = 중앙값 1.5배,
      실제 글자 윗선 ≈940 · 같은 원본 보통 자막은 윗선 936·높이 0.063): 인식기 상자 «아래 끝» 은 흔들리지 않는다(0.933 · 보통 0.930) —
      높이가 중앙값 1.25배를 넘으면 윗선 = 아래 끝 − 중앙값 × 1.1 로 잰다(213 보통 자막은 높이 ≈ 중앙값이라 그대로)."""
    자취 = []
    for t, l in sorted(표본, key=lambda x: x[0]):
        for a in 자취:
            t2, l2 = a[-1]
            if 0 < t - t2 <= 0.6 and abs(l["y"] - l2["y"]) <= 0.04 and _비슷한글(l["s"], l2["s"]):
                a.append((t, l))
                break
        else:
            자취.append([(t, l)])
    for a in 자취:
        ys = sorted(윗선추정(l, med) for _t, l in a)
        m = ys[len(ys) // 2] if len(ys) % 2 else (ys[len(ys) // 2 - 1] + ys[len(ys) // 2]) / 2
        for _t, l in a:
            l["ys"] = m


def 캡션글자(l):
    return l["c"] >= 후보확신 and l["수"] >= 후보글자 and l["h"] >= 후보높이


def _띠(src):
    from . import 자막띠시각 as 띠시각
    try:
        _c, info = 띠시각.카드들(src, 정보=True)
        if info.get("띠"):
            return info["띠"]
    except Exception:                                    # noqa: BLE001
        pass
    return list(띠시각.옛띠)


def _겹침(a, l):
    """글줄 l 이 자취 a 의 마지막 상자와 겹치는가 — 겹친 넓이가 작은 쪽 넓이의 30% 이상 · 높이 비 0.5~2."""
    ix = min(a["_x1"], l["x"] + l["w"]) - max(a["_x0"], l["x"])
    iy = min(a["_y1"], l["y"] + l["h"]) - max(a["_y0"], l["y"])
    if ix <= 0 or iy <= 0:
        return False
    작 = min((a["_x1"] - a["_x0"]) * (a["_y1"] - a["_y0"]), l["w"] * l["h"])
    비 = l["h"] / max(1e-6, a["_y1"] - a["_y0"])
    return ix * iy >= 0.3 * 작 and 0.5 <= 비 <= 2.0


def 자취들(frames, 약함, 강함, fps=FPS):
    """약함(줄) 을 지난 글줄을 «같은 자리에 이어 뜬 것» 끼리 묶는다(두 표본 = 1초 비어도 잇는다) —
    [{t0,t1,x0,y0,x1,y1,글,n,강,c,대표}]. 강 = 강함(줄) 을 지난 표본 수(흐린 전환 프레임은 약함으로만 잇는다 —
    점심이네2 «6월 14일→1월 03일» 21.5~25.5 는 가운데 두 장이 확신 0.3 이었다)."""
    tr = []
    for t, rows in frames:
        for row in rows:
            l = row if isinstance(row, dict) else _줄(row)
            if not 약함(l):
                continue
            hit = None
            for a in tr:
                if t - a["t1"] <= 2.0 / fps + 0.01 and a["t1"] < t + 1e-6 and _겹침(a, l):
                    hit = a
                    break
            if hit is None:
                hit = {"t0": t, "t1": t, "x0": l["x"], "y0": l["y"], "x1": l["x"] + l["w"], "y1": l["y"] + l["h"],
                       "글들": [], "n": 0, "강": 0, "c": 0.0, "대표": None}
                tr.append(hit)
            hit["t1"] = t
            hit["_x0"], hit["_y0"], hit["_x1"], hit["_y1"] = l["x"], l["y"], l["x"] + l["w"], l["y"] + l["h"]
            hit["x0"], hit["y0"] = min(hit["x0"], l["x"]), min(hit["y0"], l["y"])
            hit["x1"], hit["y1"] = max(hit["x1"], l["x"] + l["w"]), max(hit["y1"], l["y"] + l["h"])
            hit["n"] += 1
            if 강함(l):
                hit["강"] += 1
                hit["c"] = max(hit["c"], l["c"])
                hit["글들"].append(l["s"])
                if hit["대표"] is None or l["w"] * l["h"] > hit["대표"]["w"] * hit["대표"]["h"]:
                    hit["대표"] = dict(l, t=t)
    out = []
    for a in tr:
        for k in ("_x0", "_y0", "_x1", "_y1"):
            a.pop(k, None)
        if a["강"]:
            a["글"] = max(a["글들"], key=lambda s: len(re.findall(r"[가-힣0-9]", s)))
            out.append(a)
    return out


def 판정키(글):
    return re.sub(r"[^가-힣0-9A-Za-z]", "", 글)


def 자막줄들(src, log=None):
    """박힌 대사 자막 자리의 글줄 자취 — 번인관문 카드 확인·채우기용. 좌표는 비율."""
    c = _캐시(src)
    띠 = _띠(src)
    장 = {}
    for t, l in 자막표본(c["frames"], 띠):
        장.setdefault(t, []).append(l)
    return 자취들(sorted(장.items()), lambda l: True, 자막글자, c["fps"])


def 캡션후보(src):
    c = _캐시(src)
    띠 = _띠(src)
    약 = lambda l: l["c"] >= 0.3 and l["수"] >= 1 and l["h"] >= 후보높이 and not 자막자리(l, 띠)   # noqa: E731
    return [a for a in 자취들(c["frames"], 약, 캡션글자, c["fps"]) if a["n"] >= 후보장수]


# ───────────────────────── agy 판정 ─────────────────────────
_물음 = """너는 영상 편집 검수자다. 아래 번호 붙은 그림은 한 원본 영상(한국 스케치 코미디 유튜브)의 프레임이고, 빨간 네모 안에 글자가 있다.
각 그림마다 빨간 네모 속 글자가 무엇인지 가려라.
- "overlay": 원본 편집자가 영상 위에 얹은 글자 — 시간·장소 자막(«며칠 뒤» «PM 6:07» «강원도 인제»), 제목 카드, 날짜 캡션, 대사 자막, 채널 로고·워터마크 등. 장면 속 물건과 상관없이 화면에 붙어 있다.
- "scene": 촬영된 장면 속 물건에 적힌 글자 — 휴대폰·모니터·TV 화면, 포장지·상자·병, 간판·표지판, 책·종이, 옷·신발 무늬 등.
헷갈리면 "overlay" 로 답한다.
JSON 만: {"items":[{"i":번호,"kind":"overlay"|"scene"}]}"""


def _후보그림(src, a, W, H, p, 좁게=False):
    """후보 그림 — 온 화면(640폭)에 빨간 네모. 좁게=True 면 글줄 자리만(글줄 높이만큼 둘레 여유) 잘라 네모 없이 —
    얼굴·몸이 안 들어가게(구글 안전 필터 대안 길 ①)."""
    from PIL import Image, ImageDraw
    import io
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a['대표']['t']:.3f}", "-i", src, "-frames:v", "1",
                        "-f", "image2", "-vcodec", "png", "-"], capture_output=True, check=True)
    im = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    w, h = im.size
    l = a["대표"]
    if 좁게:
        m = l["h"] * h * 0.6
        im = im.crop((int(max(0, l["x"] * w - m)), int(max(0, l["y"] * h - m)),
                      int(min(w, (l["x"] + l["w"]) * w + m)), int(min(h, (l["y"] + l["h"]) * h + m))))
        if im.width > 640:
            im = im.resize((640, max(1, int(im.height * 640 / im.width))))
        im.save(p)
        return
    im = im.resize((640, int(h * 640 / w)))
    w, h = im.size
    d = ImageDraw.Draw(im)
    d.rectangle([l["x"] * w - 4, l["y"] * h - 4, (l["x"] + l["w"]) * w + 4, (l["y"] + l["h"]) * h + 4],
                outline=(255, 0, 0), width=3)
    im.save(p)


_좁은물음 = """너는 영상 편집 검수자다. 아래 번호 붙은 그림은 한국 스케치 코미디 영상 프레임에서 글자 자리만 잘라낸 것이다.
각 그림의 글자가 무엇인지 가려라.
- "overlay": 원본 편집자가 영상 위에 얹은 글자(시간·장소·날짜 캡션, 제목 카드, 대사 자막, 로고) — 매끈한 디지털 글꼴이 장면 위에 떠 있다.
- "scene": 촬영된 물건에 적힌 글자(휴대폰·모니터·TV 화면, 포장지, 간판, 책, 옷 무늬) — 물건 표면·화면 테두리·원근·조명이 보인다.
헷갈리면 "overlay". 글자를 답에 옮겨 적지 마라. JSON 만: {"items":[{"i":번호,"kind":"overlay"|"scene"}]}"""

_글물음 = """너는 영상 편집 검수자다. 한국 스케치 코미디 유튜브 원본 한 편에서 글자 인식기가 읽은 «글줄 자취» 목록이다(그림 없음).
각 자취가 원본 편집자가 영상 위에 얹은 글자("overlay" — 시간·장소·날짜 캡션 «며칠 뒤» «PM 6:07» «강원도 인제», 제목 카드,
로고)인지, 촬영된 물건에 적힌 글자("scene" — 휴대폰·모니터 화면 문구, 포장지 상표, 간판, 책 글)인지 가려라.
단서: 얹은 캡션은 짧은 말(시간·장소·날짜·제목)이 크게, 화면 가장자리나 가운데에 떠 있고, 같은 자리·같은 크기로 여러 번 되풀이되며,
같은 장면에 다른 글줄이 거의 없다. 장면 글자는 상표·화면 UI 문구·긴 문장이 작게 여러 줄 함께 읽히고, 자리·크기가 들쭉날쭉하다.
헷갈리면 "overlay". 글자를 답에 옮겨 적지 마라. JSON 만: {"items":[{"i":번호,"kind":"overlay"|"scene"}]}
"""


def _자리말(a):
    xc, yc = (a["x0"] + a["x1"]) / 2, (a["y0"] + a["y1"]) / 2
    가 = "왼쪽" if xc < 0.35 else "오른쪽" if xc > 0.65 else "가운데"
    세 = "위" if yc < 0.35 else "아래" if yc > 0.65 else "가운데"
    return f"{세}·{가}"


def _글자취(c, 후보, a, 가림=False):
    """글 길 한 줄 — 글자(가림=True 면 ○)·자리·크기·시간·되풀이·함께 읽힌 글줄 수."""
    같은틀 = sum(1 for b in 후보 if b is not a and _iou(a, b) >= 0.6)
    같은글 = sum(1 for b in 후보 if b is not a and 판정키(b["글"]) == 판정키(a["글"]))
    t = a["대표"]["t"]
    함께 = next((len(rows) for tt, rows in c["frames"] if abs(tt - t) < 1e-6), 0) - 1
    글 = re.sub(r"[가-힣A-Za-z]", "○", a["글"]) if 가림 else a["글"]
    return (f"글자 «{글[:40]}»(한글·숫자 {len(re.findall(r'[가-힣0-9]', a['글']))}자) · 자리 {_자리말(a)}"
            f" (x {a['x0']:.2f}~{a['x1']:.2f} · y {a['y0']:.2f}~{a['y1']:.2f}) · 글줄 높이 화면의 {a['대표']['h']:.2f}"
            f" · {a['t1'] - a['t0'] + 0.5:.1f}초 동안 {a['n']}장에서 읽힘 · 인식 확신 {a['c']:.1f}"
            f" · 이 원본에서 같은 자리·같은 크기 글줄 {같은틀}번 더 · 같은 글 {같은글}번 더 · 같은 장면에 함께 읽힌 다른 글줄 {max(함께, 0)}개")


def _필터(글):
    """구글 안전 필터 차단인가 — plan.거절종류 와 같은 문구(2026-09-30 점심이네34 «content safety filters … sensitive words»)."""
    return bool(re.search(r"필터 차단|content safety|sensitive words|PROHIBITED_CONTENT|blocked by Gemini|\bSAFETY\b", 글 or "", re.I))


CALLER = "스케치코미디/화면글자"


def _묻기(parts, n, log):
    """agy 한 번 → ({번호: kind}, None) · 필터면 (None, "필터"). 그 밖의 실패는 멈춘다(EvoLink 로 넘기지 않는다 —
    2026-09-26 사장님 결정 2: 그림 판정 · 글 길도 그림 판정의 대신이라 같은 규칙)."""
    from . import gem
    jr = gem.judge_run
    payload = {"contents": [{"role": "user", "parts": parts}],
               "generationConfig": {"maxOutputTokens": 800, "responseMimeType": "application/json"}}
    까닭 = ""
    for _시도 in range(2):                               # 답 형식이 모자라면 한 번 더
        try:
            resp, 까닭 = jr.agy_먼저(payload, CALLER, limit_min=5, log=log)
        except jr.판정멈춤 as e:
            if _필터(str(e)):
                return None, "필터"
            raise
        if resp is None:
            if _필터(까닭):
                jr.기록(CALLER, "agy_fail_stop", 0, "화면 글자 판정 — 필터 차단 → EvoLink 안 감 · 다음 대안 길(plan 글 길 전례와 같은 route) — " + 까닭[:200])
                return None, "필터"
            jr.기록(CALLER, "agy_fail_stop", 0, "화면 글자 판정 — EvoLink 로 안 넘김(멈춤) — " + 까닭)
            raise jr.판정멈춤(f"화면 글자 판정 agy 실패 — EvoLink 로 넘기지 않고 멈춘다: {까닭}")
        txt = gem.agy_gemini.text_of(resp)
        if _필터(txt):
            return None, "필터"
        try:
            m = re.search(r"\{.*\}", txt or "", re.S)
            got = {int(it["i"]): it["kind"] for it in json.loads(m.group(0))["items"] if it.get("kind") in ("overlay", "scene")}
            if all(j in got for j in range(n)):
                return got, None
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
        까닭 = "답 형식 모자람: " + (txt or "")[:120]
    raise RuntimeError(f"화면 글자 판정(agy) 답이 모자라다 — {까닭}. 멈춘다(EvoLink 로 넘기지 않음)")


def _그림조각(src, c, 묶, d, 좁게=False):
    parts = [{"text": _좁은물음 if 좁게 else _물음}]
    for j, (k, a) in enumerate(묶):
        p = os.path.join(d, f"{'n' if 좁게 else 'w'}{j}_{abs(hash(k)) % 10**8}.png")
        _후보그림(src, a, c["W"], c["H"], p, 좁게=좁게)
        parts.append({"text": f"[{j}]"})
        parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(p, "rb").read()).decode()}})
    return parts


def 판정(src, log=print):
    """캡션 후보마다 overlay/scene — 글자(판정키)별로 한 번만 묻고 캐시에 둔다. {판정키: kind}
    ★구글 안전 필터 대안 길 (2026-09-30 점심이네34 — 온 화면 그림 5장 묶음이 «content safety filters … sensitive words» 로
      막혀 «그림 판정은 EvoLink 안 감 → 멈춤» 에 섰다. 필터 차단은 일시 오류가 아니라 그 편에서 매번 되풀이된다):
      묶음 그림 → (필터) 후보마다 한 장씩 온 화면 → 글줄 자리만 좁게 자른 그림(얼굴·몸 없음) → 글 길(글자·자리·크기·시간·
      되풀이 — 그림 없음) → 글자를 ○ 로 가린 글 길 → 그래도 필터면 멈춤. 필터 아닌 실패는 전처럼 곧장 멈춘다(EvoLink 금지 그대로).
      어느 길로 정했는지는 캐시 «판정근거» 에 남긴다(없으면 «그림» — 이 수리 전 판정)."""
    c = _캐시(src)
    후보 = 캡션후보(src)
    판 = c.setdefault("판정", {})
    근거 = c.setdefault("판정근거", {})
    남은, 본 = [], set()
    for a in 후보:
        k = 판정키(a["글"])
        if k in 판 or k in 본:
            continue
        본.add(k)
        남은.append((k, a))
    if not 남은:
        return 판
    d = tempfile.mkdtemp(prefix="screentext_j_")
    try:
        for s0 in range(0, len(남은), 판정묶음):
            묶 = 남은[s0:s0 + 판정묶음]
            got, 막 = _묻기(_그림조각(src, c, 묶, d), len(묶), log)
            if got is not None:
                for j, (k, a) in enumerate(묶):
                    판[k], 근거[k] = got[j], "그림"
            else:
                if log:
                    log(f"    화면 글자 판정 — 그림 {len(묶)}장 묶음이 구글 안전 필터에 막힘 → 후보마다 대안 길")
                for k, a in 묶:
                    for 길, 만들기 in (("그림1장", lambda: _그림조각(src, c, [(k, a)], d)),
                                     ("글자자리그림", lambda: _그림조각(src, c, [(k, a)], d, 좁게=True)),
                                     ("글", lambda: [{"text": _글물음 + "\n[0] " + _글자취(c, 후보, a)}]),
                                     ("가린글", lambda: [{"text": _글물음 + "\n[0] " + _글자취(c, 후보, a, 가림=True)}])):
                        g1, 막1 = _묻기(만들기(), 1, log)
                        if g1 is not None:
                            판[k], 근거[k] = g1[0], 길
                            break
                        if log:
                            log(f"      «{a['글'][:12]}» {길} — 필터")
                    else:
                        _저장(src, c)
                        from . import gem
                        gem.judge_run.기록(CALLER, "agy_fail_stop", 0, f"화면 글자 판정 — 모든 대안 길이 필터에 막힘 «{k[:20]}»(멈춤)")
                        raise gem.judge_run.판정멈춤(f"화면 글자 판정 — «{a['글'][:20]}» 이 그림·좁은 그림·글·가린 글 모두 구글 안전"
                                                    f" 필터에 막혔다. 멈춘다(EvoLink 로 넘기지 않음) — 사람이 조각에서 빼거나 판정을 적는다")
            if log:
                log("    화면 글자 판정 " + " · ".join(f"«{a['글'][:12]}» {판[k]}({근거[k]})" for k, a in 묶))
            _저장(src, c)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return 판


def _가장자리(src, c, a):
    """캡션이 처음·마지막으로 보인 시각을 0.05초 단위로 좁힌다 — 훑기(0.5초 간격) 첫 표본 앞 1초~뒤 0.15초·끝 표본 앞 0.15초~
    뒤 1초를 0.05초마다 읽어 같은 자리·같은 글자 글줄이 읽히는 가장 바깥 시각. 캐시(«가장자리»)에 둔다.
    (2026-09-29 점심이네2 «설날 며칠 전» — 훑기 표본 45.5 앞뒤 0.75초를 통째로 넓히면 45.42 에서 끝낸 조각이 가짜로 걸린다)"""
    k = f"v4:{a['t0']}:{a['t1']}:{a['x0']:.3f}:{a['y0']:.3f}"
    같은글 = set(re.findall(r"[가-힣0-9A-Za-z]", "".join(a["글들"])))
    가 = c.setdefault("가장자리", {})
    if k in 가:
        return tuple(가[k])
    간 = 1.0 / c["fps"]
    # 훑기 표본 시각은 fps 필터가 고른 프레임이라 ±반 프레임 어긋나고, 흐리게 사라지는 끝 표본은 훑기에서 빠지기도 한다
    #   (점심이네29 «4차 이슈 발생» 훑기 끝 204.0 · 실제 204.7) — 가장자리 둘레 1초를 0.05초마다 다시 읽는다
    폭_ = 1.0
    앞 = [round(a["t0"] - 폭_ + 0.05 * j, 3) for j in range(0, int(round((폭_ + 0.15) / 0.05)) + 1)]
    뒤 = [round(a["t1"] - 0.15 + 0.05 * j, 3) for j in range(0, int(round((폭_ + 0.15) / 0.05)) + 1)]
    ts = sorted({t for t in 앞 + 뒤 if t >= 0})
    본 = {}
    for t, rows in 시각들읽기(src, ts):
        for row in rows:
            l = _줄(row)
            # 같은 자리 · 같은 글자 하나 이상(장면 잡음 «1j» 가 가장자리를 넓히지 않게)
            if l["c"] >= 0.3 and set(re.findall(r"[가-힣0-9A-Za-z]", l["s"])) & 같은글 \
                    and _겹침({"_x0": a["x0"], "_y0": a["y0"], "_x1": a["x1"], "_y1": a["y1"]}, l):
                본[t] = True
    # 처음 읽힌 칸 한 칸(0.05초) 앞부터 · 마지막 읽힌 칸 한 칸 뒤까지 떠 있었다고 본다. 가장 바깥 칸까지 읽혔으면 한 표본 더 넓힌다.
    h0 = [t for t in 앞 if 본.get(t)]
    h1 = [t for t in 뒤 if 본.get(t)]
    e0 = (min(h0) - 0.05) if h0 and min(h0) > 앞[0] else a["t0"] - 폭_ - (간 if h0 else 0)
    e1 = (max(h1) + 0.05) if h1 and max(h1) < 뒤[-1] else a["t1"] + 폭_ + (간 if h1 else 0)
    가[k] = [round(e0, 2), round(e1, 2)]
    _저장(src, c)
    return tuple(가[k])


def _iou(a, b):
    ix = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    iy = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    if ix <= 0 or iy <= 0:
        return 0.0
    u = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]) + (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) - ix * iy
    return ix * iy / u


def 화면캡션(src, log=print, 판정하기=True):
    """원본에 얹힌 화면 캡션 — [{t0,t1,x0,y0,x1,y1,글}] (원본 픽셀·원본 초). 시각은 훑기 간격만큼 앞뒤로 넓힌다
    (2fps: 첫·끝 표본 ±0.5초 + 0.25초 — 사이에 떠 있던 시간을 놓치지 않게). scene 판정은 뺀다."""
    c = _캐시(src)
    판 = 판정(src, log=log) if 판정하기 else c.get("판정", {})
    W, H = c["W"], c["H"]
    후 = 캡션후보(src)
    틀 = [a for a in 후 if 판.get(판정키(a["글"]), "overlay") == "overlay"]
    out = []
    for a in 후:
        k = 판정키(a["글"])
        # ★같은 틀 — 편집자 캡션은 한 원본 안에서 같은 자리·같은 크기로 되풀이된다. agy 가 «scene» 이라 해도 overlay 로 판정된
        #   글줄과 상자가 겹치면(IoU 0.6 이상) overlay 로 본다(2026-09-29 점심이네29 «PM 6:25» 를 scene 으로 잘못 봤다 —
        #   같은 자리 «PM 6:07·PM 1:13» 은 overlay).
        if 판.get(k, "overlay") != "overlay" and not any(_iou(a, b) >= 0.6 for b in 틀):
            continue
        e0, e1 = _가장자리(src, c, a)
        out.append({"t0": round(max(0.0, e0), 2), "t1": round(e1, 2),
                    "x0": int(a["x0"] * W) - 6, "y0": int(a["y0"] * H) - 6,
                    "x1": int(a["x1"] * W) + 6, "y1": int(a["y1"] * H) + 6, "글": a["글"]})
    return out


if __name__ == "__main__":
    src = sys.argv[1]
    c = _캐시(src)
    print(f"훑기 {len(c['frames'])}장 · 자막띠 {_띠(src)}")
    zs = 자막줄들(src)
    print(f"대사 자막 자리 글줄 자취 {len(zs)}개")
    if "--판정" in sys.argv:
        판정(src)
    판_ = _캐시(src).get("판정", {})
    for a in 캡션후보(src):
        print(f"  후보 {a['t0']:7.1f}~{a['t1']:7.1f} x{a['x0']:.2f}~{a['x1']:.2f} y{a['y0']:.2f}~{a['y1']:.2f} n{a['n']:2d}"
              f" c{a['c']:.1f} {판_.get(판정키(a['글']), '?'):7s} {a['글'][:30]}")
