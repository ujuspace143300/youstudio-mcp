#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_자막띠보정.py — 자막이 화면 **어디에** 어떤 **크기**로 있는지 실측한다 (분석 (a), 차원 D4·D5).

  왜: 제미나이 판독은 「나레 자막이 화면 아래(y 0.75~0.95)·글자 높이 4~8%」라고 **눈대중**으로 말했다.
      그 값을 우리 규격(나레 y 0.778 · 글자 8.9%)과 견주려면 **자로 재야** 한다.

  어떻게(추정 없이):
    ① 영상을 일정 간격으로 뽑아 **회색조**로 만들고, 가로는 줄이고 **세로는 유지**한다(행 위치를 안 잃는다).
    ② 행마다 **밝은 픽셀 수**(잉크)를 센다 → 프레임마다 「이 행에 글자가 있나」.
    ③ 여러 프레임을 겹쳐 **행별 등장 빈도**를 낸다 → 빈도가 솟은 구간 = **자막 레인**.
    ④ 레인 안에서 이어진 잉크 행 덩어리의 높이 = **글자 높이**(px·화면 대비 비율).
    ⑤ 사람이 눈으로 볼 **검증 캡처**를 남긴다 — 찾은 레인을 가로선으로 그린 실제 프레임.

  임계(잉크 밝기)는 이 스크립트로 **한 편에서 정하고** 10편에 같은 값을 쓴다.

사용:
  python 서버/runner/분석_자막띠보정.py --video <mp4> --out <폴더> [--매초 3] [--잉크 200] [--캡처 6]
"""
import argparse, json, os, re, subprocess, sys

def ffmpeg_rows(video, 매초, 높이, 폭, 잉크, limit_s=None):
    """세로 해상도를 유지한 회색조 프레임을 훑어 행별 잉크 수를 돌려준다."""
    vf = f"fps=1/{매초},scale={폭}:{높이},format=gray"
    argv = ["ffmpeg", "-hide_banner", "-v", "error"]
    if limit_s: argv += ["-t", str(limit_s)]
    argv += ["-i", video, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    buf = subprocess.run(argv, capture_output=True).stdout
    size = 폭 * 높이
    프레임 = [buf[i:i + size] for i in range(0, len(buf) - size + 1, size)]
    행잉크 = []
    for f in 프레임:
        행잉크.append([sum(1 for x in f[r * 폭:(r + 1) * 폭] if x >= 잉크) for r in range(높이)])
    return 행잉크


def 구간(참행, 최소=2):
    """참인 행들이 이어진 덩어리 [시작행, 끝행]"""
    out, cur = [], None
    for i, v in enumerate(참행 + [False]):
        if v and cur is None: cur = i
        elif not v and cur is not None:
            if i - cur >= 최소: out.append([cur, i - 1])
            cur = None
    return out


def 레인찾기(video, 매초=3.0, 잉크=200, 높이=540, 폭=160, 최소행비율=0.06, 최대행비율=0.6,
           레인빈도=0.06, 레인상한=0.85, 최대두께=0.25, 최소글자=2.5, 솟음폭=0.05, H0=1080, limit_s=None):
    """자막 레인을 찾아 (자막레인, 기타_요소, 행별_빈도, 표본수) 를 돌려준다.
       계측기(분석_계측.py)와 보정기가 **같은 계산**을 쓰도록 여기 한 벌만 둔다."""
    행잉크 = ffmpeg_rows(video, 매초, 높이, 폭, 잉크, limit_s)
    n = len(행잉크)
    if not n: return [], [], [], 0
    최소칸, 최대칸 = max(1, int(폭 * 최소행비율)), int(폭 * 최대행비율)
    글자있음 = [[최소칸 <= f[r] <= 최대칸 for r in range(높이)] for f in 행잉크]
    빈도 = [sum(1 for g in 글자있음 if g[r]) / n for r in range(높이)]
    # 문턱을 고정값으로 두면 **화면 전체가 밝은 영상**(웹툰·애니)에서 모든 행이 걸린다(01편 실측: 화면 0~1.0 이 한 덩어리).
    #   그래서 「주변보다 솟았는가」로 본다 — 각 행을 위아래 ±80행의 중앙값(배경)과 견준다.
    def 기준선(i):
        창 = sorted(빈도[max(0, i - 80):min(높이, i + 80)])
        return 창[len(창) // 2] if 창 else 0.0
    솟음 = [v >= max(레인빈도, 기준선(i) + 솟음폭) and v <= 레인상한 for i, v in enumerate(빈도)]
    후보 = 구간(솟음, 최소=3)
    자막레인, 기타 = [], []
    for s2, e2 in 후보:
        hs = []
        for g in 글자있음:
            블록 = 구간([g[r] for r in range(s2, e2 + 1)], 최소=1)
            if 블록: hs.append(max(b[1] - b[0] + 1 for b in 블록))
        hs.sort()
        중앙 = hs[len(hs) // 2] if hs else 0
        x = {"레인_행": [s2, e2], "y_비율": [round(s2 / 높이, 4), round((e2 + 1) / 높이, 4)],
             "글자높이_행_중앙": 중앙, "글자높이_px": round(중앙 * H0 / 높이, 1),
             "글자높이_화면대비_%": round(중앙 / 높이 * 100, 2), "글자_보인_프레임": len(hs), "표본_프레임": n,
             "띠_두께": round((e2 + 1 - s2) / 높이, 4)}
        (자막레인 if (x["띠_두께"] <= 최대두께 and x["글자높이_화면대비_%"] >= 최소글자) else 기타).append(x)
    return 자막레인, 기타, 빈도, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--매초", type=float, default=3.0, help="몇 초마다 한 장 뽑을지")
    ap.add_argument("--높이", type=int, default=540, help="분석용 세로 해상도(원본 세로와 비례. 1080 → 540 이면 1행 = 2px)")
    ap.add_argument("--폭", type=int, default=160)
    ap.add_argument("--잉크", type=int, default=200, help="글자로 볼 밝기(0~255)")
    ap.add_argument("--최소행비율", type=float, default=0.06, help="한 행이 '글자 있음'이 되려면 가로 몇 %가 밝아야 하는지")
    ap.add_argument("--최대행비율", type=float, default=0.6, help="이보다 넓게 밝으면 글자가 아니라 그림으로 본다")
    ap.add_argument("--레인상한", type=float, default=0.85, help="이보다 자주 켜져 있으면 자막이 아니라 고정 요소(헤더·워터마크)로 본다")
    ap.add_argument("--레인빈도", type=float, default=0.06, help="행이 레인이 되려면 몇 %의 프레임에서 글자가 보여야 하는지")
    ap.add_argument("--솟음폭", type=float, default=0.05, help="주변(±80행) 중앙값보다 이만큼 높아야 레인으로 본다")
    ap.add_argument("--최대두께", type=float, default=0.25, help="레인 두께가 화면의 이 비율을 넘으면 자막이 아니라 그림")
    ap.add_argument("--최소글자", type=float, default=2.5, help="글자 높이가 화면의 이 %% 미만이면 자막이 아니라 잔글씨(헤더·워터마크)")
    ap.add_argument("--캡처", type=int, default=6, help="검증 캡처 장수")
    ap.add_argument("--limit_s", type=float, default=None)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    slug = os.path.splitext(os.path.basename(a.video))[0][:30]
    say = lambda *x: print(*x, file=sys.stderr)

    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-show_entries", "format=duration", "-of", "json", a.video], capture_output=True, text=True, encoding="utf-8")
    meta = json.loads(r.stdout or "{}")
    W0, H0 = meta["streams"][0]["width"], meta["streams"][0]["height"]
    dur = float(meta["format"]["duration"])
    say(f"{slug} · {W0}x{H0} · {round(dur/60,1)}분 · {a.매초}초마다 표본")

    자막레인, 기타, 빈도, n = 레인찾기(a.video, 매초=a.매초, 잉크=a.잉크, 높이=a.높이, 폭=a.폭,
                                   최소행비율=a.최소행비율, 최대행비율=a.최대행비율, 레인빈도=a.레인빈도,
                                   레인상한=a.레인상한, 최대두께=a.최대두께, 최소글자=a.최소글자, 솟음폭=a.솟음폭,
                                   H0=H0, limit_s=a.limit_s)
    if not n: raise SystemExit("프레임을 못 뽑았다")
    높이표 = 자막레인 + 기타

    # 검증 캡처 — 레인을 가로선으로 그린 실제 프레임
    캡처 = []
    if a.캡처 > 0 and 자막레인:
        # 캡처는 절반 크기로 줄여 저장하므로, 띠 좌표도 **줄인 화면 기준**으로 계산한다
        #   (2026-08-18: 원본 기준으로 계산해 화면 밖에 그려지는 바람에 띠가 안 보였다)
        캡H = H0 // 2
        선 = "".join(f",drawbox=x=0:y={int(x['레인_행'][0]*캡H/a.높이)}:w=iw:h={max(2,int((x['레인_행'][1]-x['레인_행'][0]+1)*캡H/a.높이))}:color=red@0.35:t=fill" for x in 자막레인)
        for k in range(a.캡처):
            t = dur * (k + 1) / (a.캡처 + 1)
            p = os.path.join(a.out, f"{slug}_보정_{k+1}.png")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(round(t, 2)), "-i", a.video,
                            "-vf", f"scale={W0//2}:{H0//2}{선}", "-frames:v", "1", p], capture_output=True)
            캡처.append({"시각_s": round(t, 1), "파일": p})

    doc = {"영상": os.path.basename(a.video), "해상도": [W0, H0], "길이_s": round(dur, 1),
           "설정": {"매초": a.매초, "잉크": a.잉크, "최소행비율": a.최소행비율, "최대행비율": a.최대행비율, "레인빈도": a.레인빈도, "레인상한": a.레인상한, "분석높이": a.높이},
           "표본_프레임": n, "레인": 자막레인, "기타_요소": 기타,
           "행별_빈도": [round(v, 3) for v in 빈도], "검증_캡처": 캡처}
    out = os.path.join(a.out, f"{slug}.자막띠.json")
    json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"저장": out, "표본_프레임": n, "레인": [{k: v for k, v in x.items() if k != "레인_행"} for x in 자막레인], "기타_요소_수": len(기타),
                      "캡처": [c["파일"] for c in 캡처]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
