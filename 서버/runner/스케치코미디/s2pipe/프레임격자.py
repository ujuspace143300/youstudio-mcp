# -*- coding: utf-8 -*-
"""원본 프레임 격자 — 조각·비트·화면 전환 경계의 «단 하나의» 시각 규칙.

★2026-09-28 싱글51 «화면 전환 자리 1프레임 튐» 클래스 수리 (땜질 금지 — 경계 하나를 0.002초 옮기는 대신 규칙 하나로).
  실측: 완성본 72.16초(원본 128.545 화면 전환)에서 새 샷 첫 프레임이 앞 조각(택시 기사) 구도로 나갔고(이웃 프레임
  차이 48.6 → 다음 34.1), 28.16초(원본 77.33)에서도 새 샷 첫 프레임이 앞 비트 구도로 나갔다(50.5 → 11.4).
  원인은 시각을 세 가지 다른 자로 쟀기 때문이다 —
    ① 화면 전환 시각을 0.01초로 반올림(split.scene_cuts) → 올림된 전환(51편 28곳 중 13곳)은 새 샷 첫 프레임이
       전환 «앞» 비트에 들어가 앞 구도(crop)로 나갔다.
    ② 조각 프레임 수를 round((t1−t0)·fps) 로 셌다(build.cut_and_join) → t0 가 프레임 사이에 있으면 실제로 쓰는
       첫 프레임이 뒤로 밀린 만큼 끝도 밀려, t1 이 화면 전환이면 다음 샷 첫 프레임 1장이 조각 끝에 샜다
       (20.44~29.82 : 첫 프레임 491 · 225장 → 715번 = 다음 샷 첫 프레임). ffmpeg 입력 -to 는 «첫 프레임 + 길이» 로
       자르므로 막아 주지 못한다(실측).
    ③ «놓친 컷» 이분 탐색이 0.05초 격자에서 멈춘 자리를 round(,2) 로 경계 삼았다(framing.plan_beats) → 1~2프레임 늦게
       구도가 바뀌었다.
    ④ 프리미어 컷 in 점을 조각 t0(초)로 그대로 넣었다 — t0 가 프레임보다 조금 앞(p−0.002 등)이면 첫 화면이 앞 샷
       마지막 프레임이다(프리미어는 in 점이 든 프레임을 보여 준다 — 추정, 확인은 프리미어에서 첫 프레임 보기).

규칙 (이 파일 한 곳 — 굽기·준비·비트 계획·관문이 모두 여기를 부른다)
  · 경계는 «프레임 번호 k» 다: k 번 프레임이 새 조각(비트)의 첫 프레임이다.
  · 아무 시각 t 를 경계로 바꿀 때는 «가장 가까운 프레임 시작» — 번호(t). 0.01초 반올림(±5ms)·p−0.002·p+0.004 가
    모두 같은 k 가 된다(프레임 간격 41.7ms 의 절반 안).
  · 저장·전달하는 시각 = 경계값(k) = p_k − 0.002 (소수 4자리). ffmpeg 의 «pts ≥ 시각» 규칙(-ss·trim)이 k 를 첫
    프레임으로 고르고(실측: p−0.0005 까지 k), 번호() 로 되돌려도 k 다. 배치 에이전트가 손으로 넣던 값과 같은 꼴이다.
  · 조각 프레임 수 = k1 − k0. 시각 차 × fps 를 반올림하지 않는다.
  · 프리미어 in 점 = 시작(k) = p_k (+1µs — 틱 변환 내림 방지).
"""
import bisect
import json
import os
import subprocess
try:  # ffmpeg·ffprobe 스레드 상한은 ff.명령 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
    from . import ff
except ImportError:  # 단독 실행(python s2pipe/x.py)
    import ff  # type: ignore

δ = 0.002            # 경계값 = 프레임 시작 − δ (ffmpeg «pts ≥ 시각» 이 이 프레임을 첫 프레임으로 고른다)
_캐시 = {}


class 격자:
    """원본 한 편의 프레임 시각표. p[k] = k 번 프레임의 표시 시각(초, 파일 시작 기준 — ffmpeg -ss 와 같은 축)."""

    def __init__(self, src):
        self.src = src
        pr = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "stream=r_frame_rate,avg_frame_rate,time_base:format=start_time",
                             "-of", "json", src]), capture_output=True, text=True)
        j = json.loads(pr.stdout or "{}")
        st = (j.get("streams") or [{}])[0]
        a, b = (st.get("r_frame_rate") or "30/1").split("/")
        self.fps = int(a) / max(int(b), 1)
        tb_a, tb_b = (st.get("time_base") or "1/90000").split("/")
        tb = int(tb_a) / int(tb_b)
        fst = float((j.get("format") or {}).get("start_time") or 0.0)
        # 패킷 pts(정수) × time_base — 해독 없이 빠르다(140초 원본 0.1초). B 프레임 때문에 정렬한다.
        r = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "packet=pts", "-of", "csv=p=0", src]), capture_output=True, text=True)
        pts = sorted({int(x) for x in r.stdout.split() if x.strip().lstrip("-").isdigit()})
        self.p = [x * tb - fst for x in pts]
        if len(self.p) < 2:
            raise SystemExit(f"프레임 시각을 못 읽었다: {src}")
        self.n = len(self.p)
        self.T = (self.p[-1] - self.p[0]) / (self.n - 1)      # 평균 프레임 간격

    # ── 시각 ↔ 번호 ──────────────────────────────────────────────
    def 시작(self, k):
        """k 번 프레임의 표시 시각(초). k == n 이면 마지막 프레임의 끝."""
        if k <= 0:
            return self.p[0] if k == 0 else self.p[0] + k * self.T
        if k >= self.n:
            return self.p[-1] + (k - self.n + 1) * self.T
        return self.p[k]

    def 번호(self, t):
        """시각 t 에서 «가장 가까운 프레임 시작» 의 번호 — t 를 경계로 읽는 유일한 규칙."""
        i = bisect.bisect_left(self.p, t)
        if i <= 0:
            return 0
        if i >= self.n:
            return self.n if t - self.p[-1] >= self.T / 2 else self.n - 1
        return i if self.p[i] - t <= t - self.p[i - 1] else i - 1

    def 첫프레임(self, t):
        """ffmpeg 이 -ss t 로 주는 첫 프레임 번호(«pts ≥ t»). 옛 굽기를 재현·대조할 때만 쓴다."""
        return bisect.bisect_left(self.p, t - 1e-9)

    def 경계값(self, k):
        """k 번 프레임이 첫 프레임이 되는 경계 시각(저장·ffmpeg 용) = p_k − δ, 소수 4자리."""
        if k <= 0:
            return 0.0                                   # 첫 프레임 — 파일 시작(음수 -ss 금지)
        앞간격 = self.시작(k) - self.시작(k - 1)
        return round(self.시작(k) - min(δ, 앞간격 * 0.25), 4)

    def 맞춤(self, t):
        """시각 t → 격자 경계값 (번호 → 경계값)."""
        return self.경계값(self.번호(t))

    def 길이(self, k0, k1):
        """프레임 [k0, k1) 의 재생 길이(초)."""
        return self.시작(k1) - self.시작(k0)


def 얻기(src):
    """원본별 격자 (파일 크기·수정 시각이 같으면 다시 재지 않는다)."""
    try:
        st = os.stat(src)
        key = (os.path.abspath(src), st.st_size, int(st.st_mtime))
    except OSError:
        key = (os.path.abspath(src), 0, 0)
    if key not in _캐시:
        _캐시[key] = 격자(src)
    return _캐시[key]


def 프레임들(src, g, k0, k1, w=64, h=36):
    """원본 프레임 [k0, k1) 을 작은 회색 배열로 (정확한 번호 — 경계값으로 찾아간다)."""
    import numpy as np
    k0 = max(0, k0)
    k1 = min(g.n, k1)
    if k1 <= k0:
        return np.zeros((0, h, w), dtype=np.int16)
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", repr(g.경계값(k0)), "-i", src, "-frames:v", str(k1 - k0),
                        "-vf", f"scale={w}:{h}:flags=area", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"]), capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    m = len(a) // (w * h)
    return a[:m * w * h].reshape(m, h, w).astype(np.int16)


def 차이열(F):
    """이웃 프레임 평균 밝기 차 D[j] = |F[j] − F[j−1]| (D[0]=0)."""
    import numpy as np
    D = np.zeros(len(F))
    if len(F) > 1:
        D[1:] = np.abs(F[1:] - F[:-1]).mean(axis=(1, 2))
    return D


def 번쩍임(F, D, j, 창=3, 비=0.5):
    """D[j] 봉우리가 «번쩍임»(조명 깜빡임·가스불·플래시)인가 — 화면이 1~3장 뒤 봉우리 앞 화면으로 «돌아오거나»(시작),
    봉우리 뒤 화면이 1~3장 앞 화면과 같다(끝). 돌아온 차이가 봉우리의 절반 아래면 같은 화면이다.

    ★2026-09-29 점심이네20 술파티 가스불 — 원본 103.3~104.7초에서 화면이 2장마다 밝아졌다 어두워져 봉우리가 2장 간격으로
      섰고(날카로운 봉우리 18개), 비트 계획이 그 하나하나를 «원본 화면 전환» 으로 받아 1~2장짜리 비트 18개를 만들며 구도를
      2장마다 옮겼다(crop x 800→818→921→957→853… · 컷 완화폭으로). 연달은 1장 비트는 굽기 concat 에서 장이 빠져
      «조각 프레임 309 ≠ 틀 311» 로 멈췄다. 번쩍임은 샷이 안 바뀌었다 — 경계도 구도 바뀜도 아니다."""
    if F is None or not (0 < j < len(D)) or len(F) != len(D):
        return False
    import numpy as np
    d = float(D[j])
    for L in range(1, 창 + 1):
        if j + L < len(F) and float(np.abs(F[j + L] - F[j - 1]).mean()) < 비 * d:
            return True
        if j - 1 - L >= 0 and float(np.abs(F[j] - F[j - 1 - L]).mean()) < 비 * d:
            return True
    return False


def 날카로운(D, j, 최소=12.0, 배=2.5, F=None):
    """D[j] 가 «샷 전환» 모양인가 — 크고, 이웃 두 칸보다 확 크다(움직임·디졸브는 이웃도 크다).
    F(D 를 만든 프레임들)를 주면 번쩍임(1~3장 뒤 같은 화면으로 돌아옴)은 전환이 아니다 — 비트 계획(framing)·경계 붙이기
    (전환들)·튐 관문이 모두 F 를 준다(2026-09-29 — 한 곳이라도 빠지면 계획과 관문이 서로 다른 전환을 본다)."""
    if j <= 0 or j >= len(D):
        return False

    # ★이웃은 «같은 장 되풀이»(D ≤ 0.5)를 건너뛴 가장 가까운 걸음이다 (2026-09-29 점심이네38 267.7~268.3초 — 12fps 로 찍어
    #   24fps 로 올린 소재는 장마다 두 번씩 나와 D 가 0·19·0·19 로 번갈았고, 이웃이 늘 0 이라 빠른 움직임의 걸음 하나하나가
    #   «날카로운 봉우리»(전환)가 되어 2장 비트 8개가 잇달았다. 납품본에도 그대로 나갔다 — 구도가 2장마다 옮겨졌다).
    def _옆(쪽):
        for s in (1, 2, 3):
            i = j + 쪽 * s
            if 1 <= i < len(D) and D[i] > 0.5:
                return float(D[i])
        return 0.0
    이웃 = max(_옆(-1), _옆(1))
    return D[j] >= 최소 and D[j] >= 배 * max(이웃, 1.0) and not 번쩍임(F, D, j)


def 전환들(src, g, k, 쪽=(-2, -1, 0, 1, 2)):
    """경계 k 둘레(쪽 = k 에서 떨어진 칸들)에서 샷 전환(날카로운 D 봉우리)이 난 프레임 번호들.
    «전환 프레임» = 새 샷의 첫 프레임(D[j] = |F[j] − F[j−1]| 이 봉우리인 j)."""
    lo, hi = k + min(쪽), k + max(쪽)
    F = 프레임들(src, g, lo - 5, hi + 6)            # 번쩍임(1~3장 뒤 돌아옴)을 가리려고 양쪽 4장씩 더 본다
    base = max(0, lo - 5)
    D = 차이열(F)
    return [base + j for j in range(1, len(D)) if (base + j - k) in 쪽 and 날카로운(D, j, F=F)]


def 전환인가(src, g, k):
    """k 번 프레임이 새 샷의 첫 프레임인가."""
    return k in 전환들(src, g, k, (0,))


def 컷맞춤(g, cuts):
    """scene_cuts 시각(옛 캐시는 0.01초 반올림) → 격자 경계값, 중복 없이 정렬."""
    return sorted({g.맞춤(c) for c in cuts if 0 < g.번호(c) < g.n})
