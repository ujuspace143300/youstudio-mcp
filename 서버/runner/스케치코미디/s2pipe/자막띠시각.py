# 원본에 박힌(번인) 자막 띠로 agy 원본 전사의 시각을 바로잡는다 — «확인·맞춤 용도로만» 쓴다.
#
#   python -m s2pipe.자막띠시각 <원본.mp4> <agy.vtt> [--쓰기]
#
# ★2026-09-27 사장님 결정(A): «자막만 안 나오면 돼. 온전히 확인하는 용도로만». 박힌 자막의 글자는 쓰지 않는다 —
#   «언제 새 자막이 떴는가»(시각)만 재서 agy 시각을 맞춘다. 납품 영상에 박힌 자막이 안 보이게 하는 처리
#   (build·준비의 자막 구역 배제)는 그대로다.
# 왜: agy 통째 읽기가 영상마다 시간을 조금씩 늘려 센다 — 싱글282 는 3번 다 약 4%(끝에서 8초) 늦었다
#   («요즘 애들이 일을 참 잘해!» 실제 222.3초 · agy 230.9초). 틀린 시각으로 구간을 자르면 결말이 빠진다.
# 방법:
#   ① 화면 아래 자막 띠(높이 80~90%, 가운데 60% 폭)를 0.1초마다 — 검은 자막 상자 위 흰 글자 모양을 본다.
#   ② 글자 모양이 바뀌면 «새 자막 카드» — 카드 [(시작, 끝)] 목록.
#   ③ agy 줄 시작 t 를 a·t+b 로 옮겨 카드 시작과 가장 많이 겹치는 (a, b) 를 찾는다(전체 늘어남·밀림).
#   ④ 옮긴 뒤 각 줄 시작을 ±0.6초 안 가장 가까운 카드 시작에 붙인다(끝은 그 카드 끝 — 다음 줄 시작 전까지).
#   박힌 자막이 없는 원본(카드가 적음)은 손대지 않는다.
import json
import os
import re
import subprocess
import sys

import numpy as np

FPS = 10
W, H = 960, 540


def 카드들(src):
    """박힌 자막 카드 [(시작, 끝)] — 원본 옆 `<원본>.카드.json` 에 한 번만 재 두고 다시 쓴다.
    ★2026-09-27 100편 배치 — 편마다 에이전트·카드경계검사가 이 함수를 여러 번 불러 원본 전체를 10fps 로
      매번 다시 풀었다(동시 5~6편 · 부하 40~50). 원본 크기·수정 시각이 같으면 저장해 둔 값을 쓴다."""
    src = os.path.abspath(os.path.expanduser(src))
    st = os.stat(src)
    key = f"{st.st_size}:{int(st.st_mtime)}:{FPS}:{W}x{H}"
    cache = src + ".카드.json"
    try:
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("key") == key:
            return [tuple(x) for x in c["cards"]]
    except (OSError, ValueError, KeyError):
        pass
    cards = _카드재기(src)
    try:
        tmp = cache + f".{os.getpid()}"
        json.dump({"key": key, "cards": cards}, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, cache)
    except OSError:
        pass
    return cards


def _카드재기(src):
    """박힌 자막 카드 [(시작, 끝)] — 글자 모양이 바뀌는 자리로 나눈다.
    글자 = 밝은 픽셀(>190) 가로 3px 안에 어두운 픽셀(<90) — 자막 상자(검은 반투명) 위 흰 글자만 잡고, 밝은 배경은 거른다.
    2026-09-27 싱글282 164~175초 실측: 카드 바뀜 7곳을 실제(프레임 확인) 대비 0.1~0.2초 안에서 다 잡았다."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf",
                        f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    fr = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(fr) // (W * H)
    y0, y1 = int(H * 0.80), int(H * 0.90)
    x0, x1 = int(W * 0.2), int(W * 0.8)
    띠 = fr[:n * W * H].reshape(n, H, W)[:, y0:y1, x0:x1]
    밝 = 띠 > 190
    어 = 띠 < 90
    곁 = np.zeros_like(어)
    for k in (1, 2, 3):
        곁[:, :, k:] |= 어[:, :, :-k]
        곁[:, :, :-k] |= 어[:, :, k:]
    글자 = 밝 & 곁
    수 = 글자.reshape(n, -1).sum(axis=1)
    있음 = 수 >= 12
    cards, s = [], None
    for i in range(n):
        if 있음[i] and s is None:
            s = i
        elif s is not None:
            바뀜 = False
            if 있음[i]:
                a, b = 글자[i - 1], 글자[i]
                합 = (a | b).sum()
                바뀜 = 합 > 0 and (a & b).sum() / 합 < 0.5      # 글자 모양이 절반 넘게 달라짐 = 새 카드
            if not 있음[i] or 바뀜:
                if i - s >= 3:                                 # 0.3초보다 짧은 번쩍임은 버린다
                    cards.append((round(s / FPS, 2), round(i / FPS, 2)))
                s = i if 있음[i] else None
    if s is not None and n - s >= 3:
        cards.append((round(s / FPS, 2), round(n / FPS, 2)))
    return cards


def 읽기(vtt):
    txt = open(vtt, encoding="utf-8").read()
    L = [(int(a) * 3600 + int(b) * 60 + float(c), int(d) * 3600 + int(e) * 60 + float(f), x)
         for a, b, c, d, e, f, x in re.findall(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)\n(.+)", txt)]
    return txt, L


def 맞춤(L, cards):
    """(a, b, 맞은비율 전, 후, 새 줄 목록)"""
    cs = np.array([c[0] for c in cards])
    t = np.array([l[0] for l in L])

    def 점수(a, b):
        d = np.min(np.abs((t * a + b)[:, None] - cs[None, :]), axis=1)
        return float((d < 0.5).mean())

    전 = 점수(1.0, 0.0)
    best = (전, 1.0, 0.0)
    for a in np.arange(0.90, 1.1001, 0.002):
        for b in np.arange(-12, 12.01, 0.1):
            sc = 점수(a, b)
            if sc > best[0] + 1e-9:
                best = (sc, a, b)
    sc, a, b = best
    # 늘어남이 직선이 아니다(싱글282 — 전체 배율로 가운데는 맞았지만 끝이 2초 이르다) — 줄을 차례로 걸으며
    #   «지금까지의 어긋남»(누적 보정)을 조금씩 따라간다. 줄마다 예측 자리 ±2.5초 안, 앞 줄보다 뒤의 가장 가까운
    #   카드 시작에 붙이고, 그 차이의 절반만큼 보정을 옮긴다(한 줄 오판에 휘둘리지 않게).
    새, 차들 = [], []
    for t0, t1, x in L:
        보정 = float(np.median(차들[-7:])) if 차들 else 0.0     # 최근 7줄 어긋남의 중앙값 — 한 줄 오판에 안 흔들린다
        예 = t0 * a + b + 보정
        j = int(np.argmin(np.abs(cs - 예)))
        if abs(cs[j] - 예) <= 1.2:
            n0 = float(cs[j])
            차들.append(보정 + (n0 - 예))
            n1 = n0 + (t1 - t0) * a
            if cards[j][1] > n0:
                n1 = min(n1, cards[j][1] + 0.3)
        else:
            n0, n1 = 예, 예 + (t1 - t0) * a
        새.append((round(max(0.0, n0), 2), round(max(n0 + 0.2, n1), 2), x))
    for i in range(len(새) - 1):                            # 다음 줄 시작을 넘지 않게
        if 새[i][1] > 새[i + 1][0] and 새[i + 1][0] > 새[i][0] + 0.2:
            새[i] = (새[i][0], round(새[i + 1][0] - 0.05, 2), 새[i][2])
    return a, b, 전, sc, 새


def 쓰기(vtt, 원문, 새):
    머리 = 원문.split("\n\n", 2)
    head = "\n\n".join(머리[:2]) if len(머리) > 1 and "NOTE" in 머리[1] else 머리[0]
    with open(vtt, "w", encoding="utf-8") as f:
        f.write(head.strip() + " · 자막띠시각 맞춤\n\n")
        for t0, t1, x in 새:
            f.write(f"{int(t0//3600):02d}:{int(t0%3600//60):02d}:{t0%60:06.3f} --> "
                    f"{int(t1//3600):02d}:{int(t1%3600//60):02d}:{t1%60:06.3f}\n{x}\n\n")


def 실행(src, vtt, 반영=False, log=print):
    원문, L = 읽기(vtt)
    cards = 카드들(src)
    if len(cards) < max(8, len(L) // 3):
        log(f"자막띠시각: 박힌 자막 카드 {len(cards)}개 — 적어서 맞추지 않는다")
        return None
    a, b, 전, 후, 새 = 맞춤(L, cards)
    log(f"자막띠시각: 카드 {len(cards)}개 · 늘어남 배율 {a:.3f} · 밀림 {b:+.1f}초 · 카드와 맞은 줄 {전:.0%} → {후:.0%}")
    if 반영:
        if not os.path.exists(vtt + ".맞춤전"):
            open(vtt + ".맞춤전", "w", encoding="utf-8").write(원문)
        쓰기(vtt, 원문, 새)
    return a, b, 전, 후


if __name__ == "__main__":
    실행(sys.argv[1], sys.argv[2], "--쓰기" in sys.argv)
