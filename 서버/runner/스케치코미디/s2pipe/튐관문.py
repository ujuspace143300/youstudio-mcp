# -*- coding: utf-8 -*-
"""완성본 «경계 1프레임 튐» 관문 — 굽기 뒤 cut.mp4 와 원본으로 조각·비트 경계를 잰다.

    python -m s2pipe.튐관문 <work/슬러그 폴더> [--원본 <원본.mp4>] [--완성본 <납품.mp4>]   # 재기만(종료코드 1 = 걸림)

★2026-09-28 싱글51 — 완성본 72.16초(원본 128.545 화면 전환)에서 새 샷 첫 프레임이 앞 조각 구도로 나갔고(이웃 프레임
  차이 48.6 → 다음 34.1), 28.16초에서도 새 샷 첫 프레임이 앞 비트 구도였다(50.5 → 11.4). 싱글47 은 조각 끝을 전환
  프레임 시각에 딱 두자 다음 샷 첫 장이 딸려 온 번쩍임이 3곳. 납품 22편 표본 재기에서 편마다 4~40곳.
  ★기존 검사가 못 잡은 까닭: ⑦ «컷별 원음 대조(±150ms)» 는 소리만 본다(영상 1프레임 = 42ms 는 소리로 안 보인다).
   build 의 «비트 조각 프레임 수 = 목표 N» 관문은 «몇 장인가» 만 봤지 «어느 장인가» 를 안 봤다 — N 을 틀린 자로
   셌으니 틀린 N 장을 맞게 구운 것으로 통과했다. 번인관문·통암전·정지카드 관문은 경계 프레임을 안 본다.

재는 것 (둘 다 걸리면 반려 — 수리 지침을 붙인다)
  ㉮ 겹봉우리(완성본): 계획 경계 둘레 ±2프레임에서 이웃 프레임 차이 D 가 «크게» 두 번 난다 — 한 번에 바뀌어야 할
     화면이 두 걸음에 바뀐 것(새 샷 첫 장이 앞 구도 · 다음 샷 첫 장이 조각 끝에 샘 · 앞 샷 끝 장이 조각 머리에 낌).
     «크게» = max(8, 3 × 둘레 기준) — 기준은 경계 앞 −10~−4 · 뒤 +4~+10 프레임 D 의 중앙값 중 큰 쪽.
     원본의 같은 프레임들에도 겹봉우리가 있으면(원본 자체의 번쩍임) 뺀다. 큰 걸음이 3번 넘게 이어지면(디졸브·빠른
     동작) 뺀다.
  ㉯ 원본 정렬(계획 ↔ 원본 전환): 원본 전환(이웃 프레임 차이의 날카로운 봉우리 — 프레임격자.날카로운)이
     · 점프 컷 조각의 첫 2장·끝 2장 안에 있으면 «자투리»(다른 샷 1~2장),
     · 구도가 바뀌는 비트 경계의 ±2프레임 안인데 경계와 어긋나 있으면 «구도 어긋남»(새 샷 첫 장이 앞 구도).
"""
import json
import os
import subprocess
import sys

import numpy as np

from . import 프레임격자 as G

크게_최소 = 8.0
크게_배 = 3.0


def _읽기(path, W=160, crop=None):
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height,r_frame_rate", "-of", "csv=p=0", path],
                        capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(pr[0]), int(pr[1])
    a, b = pr[2].split("/")
    fps = int(a) / max(int(b), 1)
    vf = []
    if crop:
        vf.append("crop=%d:%d:%d:%d" % crop)
        w, h = crop[0], crop[1]
    H = max(2, int(round(W * h / w / 2)) * 2)
    vf.append(f"scale={W}:{H}:flags=area")
    r = subprocess.run(["ffmpeg", "-v", "error", "-threads", "2", "-i", path, "-vf", ",".join(vf),
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    F = np.frombuffer(r.stdout, dtype=np.uint8)
    m = len(F) // (W * H)
    return F[:m * W * H].reshape(m, H, W).astype(np.int16), fps


def 경계표(log, g):
    """beats.json(log) → [(출력 프레임 b, 종류, 조각 번호, 원본 f_앞, 원본 f_뒤, 구도바뀜, 조각 창)]
    새 beats.json(«격자» 칸)은 적힌 프레임 번호를 쓰고, 옛 것은 옛 굽기 규칙(ffmpeg «pts ≥ 시각» · N = round(out_dur·fps))
    으로 되짚는다(납품본 훑기용)."""
    segs = log.get("segments") or []
    새 = bool(log.get("격자"))
    out, b0 = [], 0
    이전 = None
    창목록 = []
    for si, s in enumerate(segs):
        if 새 and "f0" in s:
            A = s.get("앞멈춤", 0)
            f0, M, N = s["f0"] + A, s["M"], s["N"]           # f0 = 실제 첫 프레임(머리 멈춤 뒤)
        else:
            A = 0
            f0 = g.첫프레임(s["t0"])
            N = int(round(s["out_dur"] * g.fps))
            M = N
        창 = {"f0": f0, "M": M, "N": N, "A": A, "b0": b0, "i": s["i"]}
        창목록.append(창)
        if si > 0:
            이어짐 = 이전 is not None and 이전["f0"] + 이전["M"] == f0 and 이전["M"] == 이전["N"] and not A
            out.append((b0, "조각(이어짐)" if 이어짐 else "조각", s["i"], 이전["f0"] + 이전["M"] - 1, f0, True, 창))
        bs = [x for x in log.get("beats") or [] if x["seg"] == s["i"]]
        for q in range(1, len(bs)):
            if 새 and bs[q].get("f0") is not None:
                k = bs[q]["f0"]
            else:
                k = g.첫프레임(s["t0"] + round(bs[q]["t0"] - s["t0"], 3))
            if not (f0 < k < f0 + M):
                continue
            앞끝 = bs[q - 1]["crop"]
            새시작 = bs[q].get("시작crop") or bs[q]["crop"]
            바뀜 = tuple(앞끝[:2]) != tuple(새시작[:2]) or max(abs(앞끝[2] - 새시작[2]), abs(앞끝[3] - 새시작[3])) > 2
            out.append((b0 + A + (k - f0), "비트컷" if bs[q].get("at_cut") else "비트", s["i"], k - 1, k, 바뀜, 창))
        b0 += N
        이전 = 창
    return out, 창목록


def 재기(work_dir, src, 완성본=None, 로그=None):
    """조각·비트 경계 튐을 잰다 → (걸림 목록, 요약 문자열). 걸림 = {"종류","출력초","조각","원본프레임","글"}."""
    log = 로그 if 로그 is not None else json.load(open(os.path.join(work_dir, "beats.json"), encoding="utf-8"))
    g = G.얻기(src)
    경계, 창목록 = 경계표(log, g)
    if 완성본:
        # 납품 완성본: 영상 상자 윗부분(자막 띠 위 y544~1130)만 — 자막·댓글이 D 를 흔들지 않게. 25fps 로 다시 뜬 옛 완성본은
        #   같은 프레임 두 번(D≈0)을 하나로 합쳐 원본 프레임 차례로 되돌린다.
        Fo, fo = _읽기(완성본, crop=(1080, 586, 0, 544))
        if abs(fo - g.fps) > 0.01:
            d = np.abs(Fo[1:] - Fo[:-1]).mean(axis=(1, 2))
            keep = [0] + [j + 1 for j in range(len(d)) if d[j] > 0.35]
            Fo = Fo[keep]
    else:
        Fo, _ = _읽기(os.path.join(work_dir, "cut.mp4"))
    Do = G.차이열(Fo)
    걸림 = []
    # 원본 D — 조각마다 한 번에(64x36)
    원본D, 창들 = {}, {}
    for 창 in 창목록:
        lo = max(0, 창["f0"] - 4)
        원본D[창["i"]] = (lo, G.차이열(G.프레임들(src, g, lo, 창["f0"] + 창["M"] + 4)))
        창들[창["i"]] = 창

    # 완성본 프레임 j → (조각, 원본 프레임) — 멈춤 장은 원본 걸음 0 (같은 장) 으로 본다
    대응, 계획경계 = {}, {b for b, *_ in 경계}
    for c in 창들.values():
        for j in range(c["N"]):
            r = j - c.get("A", 0)
            if 0 <= r < c["M"]:
                대응[c["b0"] + j] = (c["i"], c["f0"] + r)

    def 원본전환(i, k):
        lo, D = 원본D[i]
        j = k - lo
        return 0 < j < len(D) and G.날카로운(D, j)

    첫창 = None
    for b, 종류, si, kp, kn, 바뀜, 창 in 경계:
        # ── ㉯ 원본 정렬 ─────────────────────────────────────
        글 = ""
        if 종류 == "조각":
            앞창 = next((c for c in 창들.values() if c["b0"] + c["N"] == b), None)
            if 앞창 is not None and 앞창["i"] not in 원본D:
                lo = max(0, 앞창["f0"] - 4)
                원본D[앞창["i"]] = (lo, G.차이열(G.프레임들(src, g, lo, 앞창["f0"] + 앞창["M"] + 4)))
            머리 = [k for k in (kn + 1, kn + 2) if k < 창["f0"] + 창["M"] and 원본전환(창["i"], k)]
            꼬리 = []
            if 앞창 is not None:
                끝 = 앞창["f0"] + 앞창["M"]
                꼬리 = [k for k in (끝 - 1, 끝 - 2) if k > 앞창["f0"] and 원본전환(앞창["i"], k)]
            if 머리:
                글 = f"자투리 — 조각 {si} 첫 {max(머리) - kn}장이 앞 샷(원본 전환 프레임 {max(머리)})"
            if 꼬리:
                글 += (" · " if 글 else "") + f"자투리 — 앞 조각 끝 {앞창['f0'] + 앞창['M'] - min(꼬리)}장이 다음 샷(원본 전환 프레임 {min(꼬리)})"
        elif 바뀜:
            # 비트 경계와 «원본에서 이어진» 조각 경계 — 구도가 바뀌는 자리는 화면 전환 프레임 바로 거기이거나 전환에서
            #   3장 이상 떨어져야 한다(싱글51 128.545: 전환 3082 · 이어진 이음매 3083 → 새 샷 첫 장이 앞 조각 구도).
            if 종류 == "조각(이어짐)":
                앞창 = next((c for c in 창들.values() if c["b0"] + c["N"] == b), None)
                if 앞창 is not None and 앞창["i"] not in 원본D:
                    lo = max(0, 앞창["f0"] - 4)
                    원본D[앞창["i"]] = (lo, G.차이열(G.프레임들(src, g, lo, 앞창["f0"] + 앞창["M"] + 4)))
                옆 = [kn + d for d in (-2, -1) if 앞창 is not None and kn + d > 앞창["f0"] and 원본전환(앞창["i"], kn + d)]
                옆 += [kn + d for d in (1, 2) if kn + d < 창["f0"] + 창["M"] and 원본전환(창["i"], kn + d)]
            else:
                옆 = [kn + d for d in (-2, -1, 1, 2) if 창["f0"] < kn + d < 창["f0"] + 창["M"] and 원본전환(창["i"], kn + d)]
            if 옆 and not 원본전환(창["i"], kn):
                글 = f"구도 어긋남 — 구도가 원본 프레임 {kn} 에서 바뀌는데 화면 전환은 {옆[0]}({옆[0] - kn:+d}장)"
        # ── ㉮ 계획에 없는 화면 바뀜(완성본) ─────────────────────────
        #   경계 둘레 ±3장에서 D 가 크게 바뀐 걸음이 «계획 경계» 도 아니고 «그 자리 원본 프레임의 움직임» 으로도 설명이
        #   안 되면 — 다른 샷 장이 샜거나(47편 조각 끝) 구도가 한두 장 늦게 바뀐 것(51편 28.16초)이다. 원본이 빨리
        #   움직이는 새 샷(279편 8.88초: 원본 D 11.6·9.7 → 확대 화면 D 25~31)은 원본 움직임이 설명하므로 뺀다.
        겹 = ""
        if 3 <= b < len(Do) - 3:
            앞 = Do[max(1, b - 10):max(1, b - 3)]
            뒤 = Do[b + 4:b + 11]
            기준 = max(float(np.median(앞)) if len(앞) else 0.0, float(np.median(뒤)) if len(뒤) else 0.0, 1.0)
            문턱 = max(크게_최소, 크게_배 * 기준)
            수상 = []
            for j in range(b - 3, b + 4):
                if j in 계획경계 or not (1 <= j < len(Do)) or Do[j] < 문턱:
                    continue
                σ = 대응.get(j)
                if σ is None:
                    continue
                i_, k_ = σ
                lo, D = 원본D[i_]
                원 = float(D[k_ - lo]) if 0 < k_ - lo < len(D) else 0.0
                if 원 < 0.2 * float(Do[j]):
                    수상.append((j - b, float(Do[j]), 원))
            if 수상:
                겹 = "계획에 없는 화면 바뀜 " + " · ".join(f"{d:+d}장 D {v:.1f}(원본 {w:.1f})" for d, v, w in 수상) + \
                     f" · 둘레 D " + " ".join(f"{float(Do[b + d]):.1f}" for d in (-2, -1, 0, 1, 2)) + f" (문턱 {문턱:.1f})"
        if 글 or 겹:
            걸림.append({"종류": 종류, "출력초": round(b / g.fps, 3), "출력프레임": b, "조각": si,
                         "원본프레임": kn, "원본초": round(g.시작(kn), 4),
                         "글": " · ".join(x for x in (겹, 글) if x)})
    요약 = f"경계 {len(경계)}곳 · 걸림 {len(걸림)}곳"
    return 걸림, 요약


def 지침(걸림, 호환=False):
    """걸림 목록 → 사람이 읽을 수리 지침 (반려 글에 붙인다)."""
    줄 = []
    for x in 걸림[:8]:
        줄.append(f"  · 완성본 {x['출력초']:.2f}초(조각 {x['조각']} {x['종류']} · 원본 {x['원본초']:.3f}초): {x['글']}")
    if len(걸림) > 8:
        줄.append(f"  · …외 {len(걸림) - 8}곳")
    if 호환:
        줄.append("  수리: 이 편은 옛 코드 시간축으로 자막을 맞춘 «호환» 굽기다 — 경계를 못 옮긴다. 조각 t0/t1 을 원본 화면 전환"
                  " 프레임 시각으로 고친 뒤 FROM=2 로 다시 구워라(③ 재전사 유료). 새 굽기는 경계를 전환 프레임에 스스로 붙인다.")
    else:
        줄.append("  수리: s2pipe/프레임격자.py(경계 = 프레임 번호) · framing.plan_beats(비트 경계 = 전환 프레임) · build.조각틀 을"
                  " 우회한 길이 생겼는지 본다. 원본 자체의 번쩍임이면 그 조각 경계를 번쩍임 밖으로 옮긴다.")
    return "\n".join(줄)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    wd = sys.argv[1].rstrip("/")
    log = json.load(open(os.path.join(wd, "beats.json"), encoding="utf-8"))
    src = None
    if "--원본" in sys.argv:
        src = sys.argv[sys.argv.index("--원본") + 1]
    else:
        slug = os.path.basename(wd)
        src = os.path.join(os.path.dirname(wd), f"{slug}.mp4")
    완성본 = sys.argv[sys.argv.index("--완성본") + 1] if "--완성본" in sys.argv else None
    걸림, 요약 = 재기(wd, src, 완성본, log)
    print(f"{os.path.basename(wd)}: {요약}" + (" (완성본)" if 완성본 else ""))
    for x in 걸림:
        print(f"  ★{x['종류']:7s} 조각{x['조각']:2d} 완성본 {x['출력초']:6.2f}s · 원본 {x['원본초']:.3f}s — {x['글']}")
    return 1 if 걸림 else 0


if __name__ == "__main__":
    sys.exit(main())
