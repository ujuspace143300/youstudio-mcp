#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이음매수리.py <슬러그> [--쓰기] — ④ 이음매 관문이 반려한 자리의 조각 경계를 원본 소리로 고친다.

  2026-09-26 싱글283·282 실측: 경계제안.py 가 «틈 안 가장 조용한 20ms» 를 고르다 문장 안 짧은 숨을 골라
  이음매 관문에 6곳이 걸렸다. agy 원본 전사 시각은 0.5~2초 틀려 줄 시각으로도 못 가린다.
  그래서 반려된 이음매마다 원본 소리를 직접 본다:
   · 앞 조각 끝(t1) 바로 뒤 0.25초에 말소리가 이어지면 → 말이 끝나지 않은 것 — t1 을 뒤로, 조용함이
     «0.2초 이상 이어지는» 첫 자리까지(최대 2.5초) 민다.
   · 뒤 조각 시작(t0) 바로 앞 0.25초에 말소리가 있으면 → 말 머리가 잘린 것 — t0 을 앞으로, 같은 기준으로 당긴다.
  «조용함» = 말대역(300~3500Hz) 소리가 그 둘레 6초의 바닥(20% 백분위)+6dB 아래. 숨(0.1초 안팎)은 0.2초를 못 넘는다.
  반영 뒤에는 ② 굽기부터 다시(FROM=2) — 재전사가 다시 돌고 이음매 관문이 다시 본다.
"""
import json, os, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 이음매관문  # noqa: E402

slug = sys.argv[1]
쓰기 = "--쓰기" in sys.argv
W = os.path.expanduser("~/Desktop/스케치코미디")
pj = f"{W}/projects/{slug}.json"
proj = json.load(open(pj, encoding="utf-8"))

# ★체인이 도는 중이면 고치지 않는다 (2026-09-26 — 도는 체인이 옛 내용을 덮어써 고친 값이 사라진 사건)
def _체인중인가(pj):
    import os as _o
    lk = pj + ".체인중"
    if _o.path.exists(lk):
        try:
            _o.kill(int(open(lk).read().strip()), 0)
            return True
        except (ValueError, OSError):
            return False
    return False
if _체인중인가(pj):
    sys.exit(f"★{os.path.basename(pj)} 체인이 도는 중이다 — 끝난 뒤 고친다(고쳐도 체인이 덮어쓴다)")
src = f"{W}/work/{proj['source']['id']}.mp4"
r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                   capture_output=True, check=True)
x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
dur = len(x) / 16000
FR = 320                                              # 20ms
f = np.fft.rfftfreq(FR, 1 / 16000)
sel = (f > 300) & (f < 3500)
han = np.hanning(FR)
n = len(x) // FR
spec = np.abs(np.fft.rfft(x[:n * FR].reshape(n, FR) * han, axis=1))[:, sel].sum(axis=1)
E = 20 * np.log10(spec + 1e-9)                         # 20ms 마다 말대역 dB


def 조용(i):
    a, b = max(0, i - 150), min(n, i + 150)            # 둘레 6초
    return E[i] < np.percentile(E[a:b], 20) + 6.0


def 말이어짐(t0, t1):
    i0, i1 = int(t0 / 0.02), int(t1 / 0.02)
    return sum(0 if 조용(i) else 1 for i in range(max(0, i0), min(n, i1))) >= max(1, (i1 - i0) // 2)


def 조용한데까지(t, 방향, 최대=3.5, 연속=0.2):
    """t 에서 방향(+1 뒤로 / -1 앞으로)으로 가며 조용함이 «연속» 초 이어지는 첫 자리의 가운데."""
    i = int(t / 0.02)
    need = int(연속 / 0.02)
    run = 0
    for k in range(int(최대 / 0.02)):
        j = i + 방향 * k
        if j < 0 or j >= n:
            break
        run = run + 1 if 조용(j) else 0
        if run >= need:
            mid = j - 방향 * (need // 2)
            return round(mid * 0.02, 2)
    # 끝까지 0.2초 조용함이 없으면(배경음이 계속 깔린 자리) 범위 안 가장 조용한 0.1초의 가운데로
    js = [i + 방향 * k for k in range(int(최대 / 0.02)) if 0 <= i + 방향 * k < n - 5]
    if not js:
        return None
    j = min(js, key=lambda j_: float(E[j_:j_ + 5].mean()))
    return round((j + 2) * 0.02, 2)


bad, _warn = 이음매관문.검사(proj)
joints, _total = 이음매관문.이음매(proj)
segs = [s for s in proj["segments"] if s.get("keep", True)]
반려J = []
for b in bad:
    for J, i, _t1 in joints:
        if f"이음매 {J:.2f}초" in b:
            반려J.append((J, i))
print(f"{slug}: 반려 이음매 {len(반려J)}곳")
고침 = []
for J, i in 반려J:
    a, b2 = segs[i], segs[i + 1]
    꼬리 = 말이어짐(a["t1"], a["t1"] + 0.25)
    머리 = 말이어짐(b2["t0"] - 0.25, b2["t0"])
    if 꼬리:
        새 = 조용한데까지(a["t1"], +1)
        if 새:
            고침.append((a, "t1", a["t1"], 새, "앞 조각 끝 뒤로 말이 이어짐 — 말끝 뒤 조용한 곳까지"))
    if 머리:
        새 = 조용한데까지(b2["t0"], -1)
        if 새:
            고침.append((b2, "t0", b2["t0"], 새, "뒤 조각 시작 앞에 말 머리 — 말 시작 앞 조용한 곳까지"))
    if not 꼬리 and not 머리:
        print(f"  이음매 {J:.2f} — 양쪽 다 조용하다(완성본 전사가 붙여 들음) — 손대지 않음")
for s, k, a0, b0, why in 고침:
    print(f"  {k} {a0:.2f} → {b0:.2f}  ({why})")
    if 쓰기:
        s[k] = b0
if 쓰기 and 고침:
    json.dump(json.load(open(pj, encoding="utf-8")), open(pj + ".이음매전", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    proj["_est_sec"] = round(sum(s["t1"] - s["t0"] for s in segs), 1)
    proj.setdefault("_이음매수리", []).append([(k, a0, b0, why) for _s, k, a0, b0, why in 고침])
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  반영 — 합계 {proj['_est_sec']}초 · 이전 판 {os.path.basename(pj)}.이음매전 · 다음: FROM=2")
