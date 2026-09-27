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
#   ③ agy 줄 시작 t 를 a·t+b 로 옮겨 카드 시작과 가장 많이 겹치는 (a, b) 를 찾는다(첫 어림 — 후보 창만 정한다).
#   ④ 전역 단조 정렬(동적 계획법)로 줄마다 카드를 고른다 — 이웃 줄끼리 «카드 − agy» 어긋남이 매끄럽게 변하고,
#      카드 길이가 줄 길이와 비슷할수록 좋게. 못 붙인 줄은 양옆 붙은 줄의 어긋남으로 보간한다(맞춤() 설명).
#   벌점 값은 검수도구/맞춤평가.py(납품 편 완성본 Speechmatics 로 되돌린 참 시작과 대조)로 골랐다.
#   박힌 자막이 없는 원본(카드가 적음)은 손대지 않는다.
import json
import os
import re
import subprocess
import sys

import numpy as np

FPS = 10
띠위, 띠아래 = 0.80, 0.90   # 78~95% 로 넓혀 봤으나 편마다 카드 수가 엇갈려(207 −12 · 277 +12) 되돌림 — 2026-09-27
W, H = 960, 540


def 카드들(src):
    """박힌 자막 카드 [(시작, 끝)] — 원본 옆 `<원본>.카드.json` 에 한 번만 재 두고 다시 쓴다.
    ★2026-09-27 100편 배치 — 편마다 에이전트·카드경계검사가 이 함수를 여러 번 불러 원본 전체를 10fps 로
      매번 다시 풀었다(동시 5~6편 · 부하 40~50). 원본 크기·수정 시각이 같으면 저장해 둔 값을 쓴다."""
    src = os.path.abspath(os.path.expanduser(src))
    st = os.stat(src)
    key = f"{st.st_size}:{int(st.st_mtime)}:{FPS}:{W}x{H}:{띠위}-{띠아래}"
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
    # 띠 높이는 위 띠위·띠아래 (싱글207 은 자막이 93% 높이라 놓친 카드가 있다 — 알려진 한계)
    y0, y1 = int(H * 띠위), int(H * 띠아래)
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


def _전체배율(t, cs):
    """a·t+b 로 옮겼을 때 카드 시작 ±0.5초 안에 드는 줄 비율이 가장 큰 (a, b) — 첫 어림."""
    def 점수(a, b):
        d = np.min(np.abs((t * a + b)[:, None] - cs[None, :]), axis=1)
        return float((d < 0.5).mean())

    전 = 점수(1.0, 0.0)
    best = (전, 1.0, 0.0)
    # ★범위 0.70~1.30 (2026-09-27 싱글207 — 실제 0.79~0.82 가 필요했는데 0.80 끝에 걸려 25초 어긋남)
    for a in np.arange(0.70, 1.3001, 0.002):
        for b in np.arange(-15, 15.01, 0.1):
            sc = 점수(a, b)
            if sc > best[0] + 1e-9:
                best = (sc, a, b)
    return 전, best


def 맞춤(L, cards, 배율=None, 창=30.0, 캡=6.0, 매끈=1.0, 허용=0.3, 늘폭=0.03, 줄벌=1.5, 카드벌=0.05,
        공유벌=1.0, 사전=0.0, 길이벌=0.6, 원시=0.0, 최소카드=0.5, 건너=8):
    """(a, b, 맞은비율 전, 후, 새 줄 목록)
    전역 단조 정렬(동적 계획법): 줄 i 를 카드 j(i) 에 붙이되 j 는 줄 순서대로 줄지 않는다.
      비용 = 매끈·min(캡, max(0, |어긋남 변화| − 허용 − 늘폭·줄 간격))   (어긋남 = 카드 시작 − agy 시작 ·
             캡 = agy 가 덩어리마다 다시 맞춰 어긋남이 한 번에 튀는 자리도 허용)
           + 길이벌·min(3, |카드 길이 − 줄 길이|) + 줄벌 × 못 붙인 줄 + 카드벌 × 건너뛴 카드
           + 공유벌(앞 줄과 같은 카드) + 사전·|카드 − (a·t+b)| + 원시·|카드 − t|
      최소카드초보다 짧은 카드는 붙일 자리에서 뺀다. 못 붙인 줄은 양옆 붙은 줄의 어긋남을 시각으로 보간해 옮긴다.
      벌점 기본값 = 검수도구/맞춤평가.py 로 짝수 편에서 고르고 홀수 편에서 확인(2026-09-27 · 41편 참 시작 대조:
      중앙 오차 1.33→0.13초 · p90 3.08→0.78 · 최대 3.81→1.31 · 2초 넘게 틀린 줄 21.7%→2.4%, 편 평균).
    ★2026-09-27 싱글249 «너희들 다 비키니 입을 거야?» 카드 182.3초가 vtt 에 192.2초 — 옛 방식(줄마다 가까운 카드에
      탐욕으로 붙이고 최근 7줄 중앙값을 따라감)은 한 칸 밀려 붙으면 계속 밀렸다(싱글248·257 뒤쪽 2~8초).
      agy 어긋남은 직선이 아니다(싱글248: −0.2 → −3.4 → −0.6초 — 덩어리마다 다시 맞는다)."""
    cs = np.array([c[0] for c in cards], dtype=float)
    ce = np.array([c[1] for c in cards], dtype=float)
    t = np.array([l[0] for l in L], dtype=float)
    N, M = len(L), len(cs)
    전, (sc, a, b) = 배율 or _전체배율(t, cs)
    if N == 0 or M == 0:
        return a, b, 전, sc, [(l[0], l[1], l[2]) for l in L]
    예 = t * a + b
    dur = np.array([l[1] - l[0] for l in L], dtype=float) * a
    cdur = ce - cs
    쓸 = cdur >= 최소카드                                   # 너무 짧은 카드(번쩍임·잘못 잰 조각)는 붙일 자리에서 뺀다
    후보 = [np.nonzero((np.abs(cs - 예[i]) <= 창) & 쓸)[0] for i in range(N)]
    # best[i][jj] = 줄 i 를 후보 jj 에 붙였을 때까지의 최소 비용 · 뒤로 따라갈 (k, kk)
    best, back = [], []
    for i in range(N):
        J = 후보[i]
        if len(J) == 0:
            best.append(np.zeros(0)); back.append(([], []))
            continue
        d_i = cs[J] - t[i]
        자리 = 사전 * np.abs(cs[J] - 예[i]) + 원시 * np.abs(cs[J] - t[i]) + 길이벌 * np.minimum(np.abs(cdur[J] - dur[i]), 3.0)
        cost = 줄벌 * i + 자리            # 이 줄이 첫 붙임일 때
        bk = np.full(len(J), -1); bkk = np.full(len(J), -1)
        for k in range(max(0, i - 건너 - 1), i):
            Jk = 후보[k]
            if len(Jk) == 0:
                continue
            d_k = cs[Jk] - t[k]
            gap = max(0.0, t[i] - t[k])
            변 = np.abs(d_i[None, :] - d_k[:, None])
            c = 매끈 * np.minimum(np.maximum(0.0, 변 - 허용 - 늘폭 * gap), 캡)
            dj = J[None, :] - Jk[:, None]
            c = np.where(dj < 0, np.inf, c)
            c = c + np.where(dj == 0, 공유벌, 카드벌 * np.maximum(0, dj - 1))
            tot = best[k][:, None] + c + 줄벌 * (i - k - 1)
            kk = np.argmin(tot, axis=0)
            v = tot[kk, np.arange(len(J))] + 자리
            better = v < cost
            cost = np.where(better, v, cost)
            bk = np.where(better, k, bk); bkk = np.where(better, kk, bkk)
        best.append(cost); back.append((bk, bkk))
    # 끝: 마지막 붙인 줄 뒤로 남은 줄은 못 붙임
    fin, arg = np.inf, None
    for i in range(N):
        if len(best[i]) == 0:
            continue
        v = best[i] + 줄벌 * (N - 1 - i)
        jj = int(np.argmin(v))
        if v[jj] < fin:
            fin, arg = float(v[jj]), (i, jj)
    붙 = {}
    while arg is not None and arg[0] >= 0:
        i, jj = arg
        붙[i] = int(후보[i][jj])
        k, kk = back[i][0][jj], back[i][1][jj]
        arg = (int(k), int(kk)) if k >= 0 else None
    # 같은 카드를 여럿이 나눠 가지면 첫 줄만 카드 시작에 — 나머지는 그 줄의 어긋남으로 옮긴다(보간 대상)
    쓴 = set()
    for i in sorted(붙):
        if 붙[i] in 쓴:
            del 붙[i]
        else:
            쓴.add(붙[i])
    ks = sorted(붙, key=lambda i: t[i])                     # np.interp 는 x 가 커지는 순서여야 한다
    dk = np.array([cs[붙[i]] - t[i] for i in ks]) if ks else None
    tk = np.array([t[i] for i in ks]) if ks else None
    새 = []
    for i, (t0, t1, x) in enumerate(L):
        if i in 붙:
            j = 붙[i]
            n0 = float(cs[j])
            n1 = n0 + (t1 - t0) * a
            if ce[j] > n0:
                n1 = min(n1, ce[j] + 0.3)
        else:
            d = float(np.interp(t0, tk, dk)) if ks else (예[i] - t0)
            n0 = t0 + d
            n1 = n0 + (t1 - t0) * a
        새.append((round(max(0.0, n0), 2), round(max(n0 + 0.2, n1), 2), x))
    for i in range(len(새) - 1):                            # 다음 줄 시작을 넘지 않게
        if 새[i][1] > 새[i + 1][0] and 새[i + 1][0] > 새[i][0] + 0.2:
            새[i] = (새[i][0], round(새[i + 1][0] - 0.05, 2), 새[i][2])
    s0 = np.array([x[0] for x in 새])
    후 = float((np.min(np.abs(s0[:, None] - cs[None, :]), axis=1) < 0.5).mean())
    return a, b, 전, 후, 새


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
