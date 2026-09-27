# 자막띠시각 옛 맞춤(커밋 a09b63b·c1c8bcd — 2026-09-27 운영판) — 맞춤평가.py 가 «옛» 열로 비교하려고 그대로 옮겨 둔다.
# 운영에서는 쓰지 않는다. 2026-09-28 싱글171(배율 0.740 → 뒤쪽 최대 10초 이름)·176(뒤쪽 한 칸씩 밀림 → 최대 6초 늦음)으로 바뀌었다.
import numpy as np

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
