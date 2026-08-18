#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_계측.py — 레퍼런스 영상 한 편을 우리 자로 잰다 (분석 단계 (a) 기계 실측).

  설계: `설계/분석_지무비.md` — 차원 D1(컷)·D3(턴 구조 재료)·D4(자막 타이밍)·D9(덕킹 재료).
  전사(Speechmatics)는 비용이 있어 이 스크립트에 넣지 않는다 — 별도 단계에서 돈다.

  재는 것
    ① 기본      ffprobe — 길이·해상도·fps·오디오 규격·파일 크기
    ② 컷        scene score 임계 이상 지점 = 컷 경계 → 컷 수·분당 컷·길이 분포·전환 세기 분포
    ③ 무음/발화 silencedetect(규격 「전사.무음스캔」 과 같은 값) → 발화 구간·무음 비율·최장 무음
    ④ 자막 띠   화면 아래/가운데 띠를 2fps 로 훑어 **글자가 있는가·바뀌었는가** → 큐 수·큐 길이·간격·무자막 최장
    ⑤ 소리 크기 1초 창 RMS → 나중에 나레 구간과 대조해 덕킹(dB 차)을 낸다

  한계(정직하게): ④ 는 표본이 2fps 라 시간 정밀도 ±0.5s 다. 0.1s 급 값(잔류)이 필요하면 --fps 10 으로 그 편만 다시 잰다.
                 ④ 는 「글자처럼 밝은 픽셀이 있나」로 판정하므로 밝은 배경·화면 내 텍스트에 헛짚을 수 있다 — 임계는 1편으로 보정한 뒤 쓴다.

사용: python 서버/runner/분석_계측.py --video <mp4> --out <폴더> [--limit_s 120] [--fps 2] [--scene 0.3]
"""
import argparse, json, os, re, subprocess, sys

def run(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)

def pct(xs, p):
    if not xs: return None
    ys = sorted(xs)
    k = (len(ys) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ys) - 1)
    return round(ys[lo] + (ys[hi] - ys[lo]) * (k - lo), 3)

def 분포(xs):
    if not xs: return None
    return {"n": len(xs), "min": round(min(xs), 3), "p10": pct(xs, 0.10), "p25": pct(xs, 0.25),
            "중앙": pct(xs, 0.50), "p75": pct(xs, 0.75), "p90": pct(xs, 0.90), "max": round(max(xs), 3),
            "평균": round(sum(xs) / len(xs), 3)}

# ── ① 기본 ──────────────────────────────────────────────────────────────────
def 기본(video):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", video])
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = round(float(num) / float(den or 1), 3) if float(den or 1) else None
    return {"파일": os.path.basename(video), "크기_MB": round(os.path.getsize(video) / 1048576, 1),
            "길이_s": round(float(d.get("format", {}).get("duration", 0)), 3),
            "해상도": [v.get("width"), v.get("height")], "fps": fps, "비디오코덱": v.get("codec_name"),
            "오디오": {"코덱": a.get("codec_name"), "샘플레이트": a.get("sample_rate"), "채널": a.get("channels")}}

# ── ② 컷 ────────────────────────────────────────────────────────────────────
def 컷(video, limit_s, th):
    argv = ["ffmpeg", "-hide_banner", "-v", "info"]
    if limit_s: argv += ["-t", str(limit_s)]
    argv += ["-i", video, "-an", "-filter_complex", f"select='gt(scene,{th})',metadata=print:file=-", "-f", "null", "-"]
    r = run(argv)
    txt = (r.stdout or "") + (r.stderr or "")
    times, scores = [], []
    cur = None
    for line in txt.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m: cur = float(m.group(1)); continue
        m = re.search(r"lavfi\.scene_score=([\d.]+)", line)
        if m and cur is not None:
            times.append(round(cur, 3)); scores.append(round(float(m.group(1)), 3)); cur = None
    dur = limit_s or 기본(video)["길이_s"]
    lens = [round(times[i + 1] - times[i], 3) for i in range(len(times) - 1)]
    return {"임계": th, "컷_경계_수": len(times), "분당_컷": round(len(times) / (dur / 60), 2) if dur else None,
            "컷_길이_분포_s": 분포(lens), "장면점수_분포": 분포(scores),
            "_안내": "경계 = scene score 가 임계를 넘은 지점. 점수가 높을수록 하드컷, 임계 근처는 디졸브·움직임일 수 있다",
            "경계_s": times}

# ── ③ 무음/발화 ─────────────────────────────────────────────────────────────
def 무음(video, limit_s, noise_db=-24, d_s=0.4):
    argv = ["ffmpeg", "-hide_banner", "-v", "info"]
    if limit_s: argv += ["-t", str(limit_s)]
    argv += ["-i", video, "-af", f"highpass=f=200,lowpass=f=3500,silencedetect=noise={noise_db}dB:d={d_s}", "-f", "null", "-"]
    r = run(argv)
    txt = (r.stdout or "") + (r.stderr or "")
    sil, start = [], None
    for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", txt):
        if m.group(1) == "start": start = float(m.group(2))
        elif start is not None: sil.append([round(start, 3), round(float(m.group(2)), 3)]); start = None
    dur = limit_s or 기본(video)["길이_s"]
    if start is not None: sil.append([round(start, 3), round(dur, 3)])
    speech, cur = [], 0.0
    for a, b in sil:
        if a > cur: speech.append([round(cur, 3), round(a, 3)])
        cur = max(cur, b)
    if cur < dur: speech.append([round(cur, 3), round(dur, 3)])
    sp = sum(b - a for a, b in speech)
    return {"설정": {"noise_dB": noise_db, "d_s": d_s}, "발화_구간_수": len(speech), "발화_s": round(sp, 3),
            "발화_비율": round(sp / dur, 3) if dur else None, "무음_최장_s": round(max([b - a for a, b in sil], default=0), 3),
            "발화_길이_분포_s": 분포([round(b - a, 3) for a, b in speech]), "발화_구간": speech}

# ── ④ 자막 띠 ───────────────────────────────────────────────────────────────
def 자막띠(video, limit_s, fps, band, 이름, W=32, H=8, 잉크=200, 변화=12):
    """band = (y0, y1) 화면 높이 비율. 밝은 픽셀 수(잉크)와 프레임 간 차이로 큐 경계를 잡는다."""
    y0, y1 = band
    vf = f"fps={fps},crop=w=iw:h=ih*{round(y1 - y0, 4)}:x=0:y=ih*{round(y0, 4)},scale={W}:{H},format=gray"
    argv = ["ffmpeg", "-hide_banner", "-v", "error"]
    if limit_s: argv += ["-t", str(limit_s)]
    argv += ["-i", video, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    r = subprocess.run(argv, capture_output=True)
    buf, size = r.stdout, W * H
    frames = [buf[i:i + size] for i in range(0, len(buf) - size + 1, size)]
    if not frames: return {"이름": 이름, "오류": "프레임 없음", "stderr": (r.stderr or b"")[:200].decode("utf-8", "replace")}
    ink = [sum(1 for px in f if px >= 잉크) for f in frames]              # 밝은 픽셀 수 = 글자가 있나
    diff = [0] + [sum(abs(frames[i][j] - frames[i - 1][j]) for j in range(size)) // size for i in range(1, len(frames))]
    있음 = [k > 0 for k in ink]
    큐, cur = [], None
    for i, has in enumerate(있음):
        t = i / fps
        if has and cur is None: cur = t
        elif has and cur is not None and diff[i] > 변화: 큐.append([round(cur, 3), round(t, 3)]); cur = t   # 내용이 바뀌었다 = 다음 큐
        elif not has and cur is not None: 큐.append([round(cur, 3), round(t, 3)]); cur = None
    if cur is not None: 큐.append([round(cur, 3), round(len(frames) / fps, 3)])
    큐 = [c for c in 큐 if c[1] - c[0] >= 1.0 / fps]
    dur = limit_s or 기본(video)["길이_s"]
    간격 = [round(큐[i + 1][0] - 큐[i][1], 3) for i in range(len(큐) - 1)]
    빈틈 = [round(큐[i + 1][0] - 큐[i][1], 3) for i in range(len(큐) - 1)]
    return {"이름": 이름, "띠_높이비율": [y0, y1], "표본_fps": fps, "큐_수": len(큐),
            "분당_큐": round(len(큐) / (dur / 60), 2) if dur else None,
            "큐_길이_분포_s": 분포([round(b - a, 3) for a, b in 큐]), "큐_사이_간격_분포_s": 분포(간격),
            "무자막_최장_s": round(max(빈틈, default=0), 3), "잉크_있는_프레임_비율": round(sum(있음) / len(있음), 3),
            "큐": 큐[:400]}

# ── ⑤ 소리 크기 ─────────────────────────────────────────────────────────────
def 소리크기(video, limit_s, win=1.0):
    argv = ["ffmpeg", "-hide_banner", "-v", "info"]
    if limit_s: argv += ["-t", str(limit_s)]
    argv += ["-i", video, "-af", f"astats=metadata=1:reset={win},ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"]
    r = run(argv)
    txt = (r.stdout or "") + (r.stderr or "")
    vals = [round(float(m.group(1)), 2) for m in re.finditer(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+)", txt)]
    return {"창_s": win, "구간_수": len(vals), "RMS_dB_분포": 분포(vals), "RMS_dB": vals[:600]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit_s", type=float, default=None, help="앞부분만 잰다(시험용)")
    ap.add_argument("--fps", type=float, default=2.0, help="자막 띠 표본 fps")
    ap.add_argument("--scene", type=float, default=0.3, help="컷 검출 임계")
    ap.add_argument("--나레띠", default="0.55,0.72", help="나레 자막 레인 높이 비율")
    ap.add_argument("--대사띠", default="0.72,0.95", help="대사 자막 레인 높이 비율")
    ap.add_argument("--잉크", type=int, default=200, help="글자로 볼 밝기 임계(0~255). **자막 있는 영상 1편으로 보정한 뒤 10편에 쓴다**")
    ap.add_argument("--변화", type=int, default=12, help="다음 큐로 볼 프레임 간 평균 차이")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    slug = os.path.splitext(os.path.basename(a.video))[0]
    say = lambda *x: print(*x, file=sys.stderr)

    say(f"[1/5] 기본 {slug}")
    doc = {"슬러그": slug, "원본": os.path.abspath(a.video), "잰_범위_s": a.limit_s, "기본": 기본(a.video)}
    say("[2/5] 컷 검출")
    doc["컷"] = 컷(a.video, a.limit_s, a.scene)
    say("[3/5] 무음/발화")
    doc["발화"] = 무음(a.video, a.limit_s)
    say("[4/5] 자막 띠")
    doc["자막띠"] = [자막띠(a.video, a.limit_s, a.fps, tuple(float(x) for x in a.나레띠.split(",")), "나레레인", 잉크=a.잉크, 변화=a.변화),
                   자막띠(a.video, a.limit_s, a.fps, tuple(float(x) for x in a.대사띠.split(",")), "대사레인", 잉크=a.잉크, 변화=a.변화)]
    say("[5/5] 소리 크기")
    doc["소리"] = 소리크기(a.video, a.limit_s)

    path = os.path.join(a.out, f"{slug}.계측.json")
    json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    b = doc["기본"]
    print(json.dumps({"저장": path, "길이_s": b["길이_s"], "해상도": b["해상도"], "fps": b["fps"],
                      "컷_경계": doc["컷"]["컷_경계_수"], "분당_컷": doc["컷"]["분당_컷"],
                      "컷_길이_중앙": (doc["컷"]["컷_길이_분포_s"] or {}).get("중앙"),
                      "발화_비율": doc["발화"]["발화_비율"],
                      "나레레인_큐": doc["자막띠"][0].get("큐_수"), "대사레인_큐": doc["자막띠"][1].get("큐_수"),
                      "RMS_중앙": (doc["소리"]["RMS_dB_분포"] or {}).get("중앙")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
