#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카드경계검사.py <슬러그>... — 원본에 박힌 자막 카드가 조각 경계(t0·t1)를 «가로지르는» 자리를 찾는다.

  2026-09-27 싱글277·270 실측: ④ 이음매 관문(완성본 Speechmatics 낱말)은 통과했는데 문장이 반쯤 잘려 나갔다.
   · 277 — 훅 시작 180.0 이 카드 «초록색 빨간색 있는 게 꼭 크리스마스 같지 않아?»(178.4~181.0) 한가운데.
     훅엔 뒷반, 본문엔 앞반만 들어가 «크리스마스 같지 않아?» 가 본문에서 사라졌다.
   · 270 — 조각 시작 114.1 이 카드 «이렇게 꾹~ 참고 기다려주잖아»(111.3~115.5) 안. 문장 앞머리가 통째로 빠졌다.
  왜 이음매 관문을 지났나: 관문은 완성본 «안» 의 낱말만 본다 — 잘려 나간 쪽 말은 완성본에 없으니 못 본다.
  잘린 자리가 문장 속 짧은 쉼이면 양쪽 낱말이 이음매에 안 붙어 통과한다. 영상 맨 앞(훅 시작)은 이음매도 아니다.
  원본에 박힌 자막 카드는 «한 문장이 화면에 떠 있는 동안» 이라 문장 경계를 사람 눈과 같게 준다(시각 확인 용도만 —
  2026-09-27 사장님 A: 글자는 쓰지 않는다).
  판정: 원본에서 맞닿지 않은 경계 t 가 카드 (s, e) 안에 s+0.3 < t < e-0.3 로 들어가면 «가로지름».
  고침: 시작이면 카드 시작 앞 조용한 곳까지 당기고, 끝이면 카드 끝 뒤까지 민다(이음매수리.py 와 같은 소리 기준).
종료코드: 가로지름이 있으면 1.
"""
import json, os, subprocess, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 자막띠시각  # noqa: E402
# ffmpeg·ffprobe 스레드 상한은 s2pipe/ff.py 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
import os as _ff_os, sys as _ff_sys  # noqa: E402
_ff_d = _ff_os.path.dirname(_ff_os.path.abspath(__file__))
_ff_d = _ff_os.path.dirname(_ff_d)
if _ff_d not in _ff_sys.path:
    _ff_sys.path.append(_ff_d)
from s2pipe import ff  # noqa: E402

W = os.path.expanduser("~/Desktop/스케치코미디")
나쁨 = 0
for slug in [a for a in sys.argv[1:] if not a.startswith("--")]:
    pj = slug if os.sep in slug else f"{W}/projects/{slug}.json"     # 경로를 주면 그 판(예: .경계전 백업)을 잰다
    proj = json.load(open(pj, encoding="utf-8"))
    src = f"{W}/work/{proj['source']['id']}.mp4"
    # ★2026-09-29 — 글자 인식으로 확인된 카드만(점심이네11 운동화·21 파란 탁자·52 냄비 가장자리를 카드로 잡아 가짜 가로지름이
    #   났다). 규칙은 s2pipe/번인관문._글자확인 한 곳 — 픽셀 카드 중 그 시간에 자막 글줄이 안 읽힌 것은 뺀다.
    from s2pipe import 번인관문  # noqa: E402
    cards = 번인관문.확인된카드들(src)
    segs = [s for s in proj["segments"] if s.get("keep", True)]
    붙음 = set()
    for a, b in zip(segs, segs[1:]):                 # 완성본 순서로 잇닿고 원본에서도 맞닿은 이음은 자른 자리가 아니다
        if abs(b["t0"] - a["t1"]) < 0.05:
            붙음 |= {(id(a), "t1"), (id(b), "t0")}
    # 카드는 말보다 먼저 뜨고 말 뒤에 남는다(싱글276 «뭐라고 부르면 될까요?» — 카드 63.1 · 말 63.9~) — 그래서
    #   «잘려 나가는 쪽에 실제 말소리가 0.2초 이상 있는가» 를 소리로 한 번 더 본다(이음매수리.py 와 같은 기준).
    x = np.frombuffer(subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                                      "-f", "s16le", "-"]), capture_output=True, check=True).stdout,
                      dtype=np.int16).astype(np.float32) / 32768
    FR = 320
    n = len(x) // FR
    f = np.fft.rfftfreq(FR, 1 / 16000)
    sel = (f > 300) & (f < 3500)
    E = 20 * np.log10(np.abs(np.fft.rfft(x[:n * FR].reshape(n, FR) * np.hanning(FR), axis=1))[:, sel].sum(axis=1) + 1e-9)

    def 말초(a, b):
        """a~b 사이 말소리(둘레 6초 바닥 20% 백분위 + 6dB 위) 길이(초)."""
        i0, i1 = max(0, int(a / 0.02)), min(n, int(b / 0.02))
        return sum(0.02 for i in range(i0, i1)
                   if E[i] >= np.percentile(E[max(0, i - 150):min(n, i + 150)], 20) + 6.0)

    걸림 = []
    for i, s in enumerate(segs):
        for k in ("t0", "t1"):
            if (id(s), k) in 붙음:
                continue
            t = s[k]
            for cs, ce in cards:
                if cs + 0.3 < t < ce - 0.3:
                    말 = 말초(max(cs, t - 1.5), t) if k == "t0" else 말초(t, min(ce, t + 1.5))
                    if 말 >= 0.2:
                        걸림.append((i, k, t, cs, ce, 말))
    if not cards:
        print(f"{slug}: 박힌 자막 카드 없음 — 건너뜀")
        continue
    print(f"{slug}: 카드 {len(cards)}개 · 경계 가로지름 {len(걸림)}곳")
    for i, k, t, cs, ce, 말 in 걸림:
        쪽 = f"시작을 {cs:.2f} 앞으로" if k == "t0" else f"끝을 {ce:.2f} 뒤로"
        print(f"  ★조각 {i} {k}={t:.2f} 이 카드 {cs:.2f}~{ce:.2f} 한가운데 · 잘려 나가는 쪽 말소리 {말:.1f}초 — {쪽}")
    나쁨 += len(걸림)
    if "--쓰기" in sys.argv and 걸림:
        # 카드 가장자리 둘레 0.5초에서 말대역이 가장 작은 0.1초 가운데로 — 시작은 카드 시작 앞, 끝은 카드 끝 뒤
        def 조용한곳(a, b):
            js = range(max(0, int(a / 0.02)), min(n - 5, int(b / 0.02)))
            j = min(js, key=lambda j_: float(E[j_:j_ + 5].mean()))
            return round((j + 2) * 0.02, 2)
        옛 = json.load(open(pj, encoding="utf-8"))
        for i, k, t, cs, ce, _말 in 걸림:
            # ★옆 카드(앞·뒤 말) 안으로 넘어가지 않는다 (2026-09-27 싱글277 — 끝을 카드 끝 +0.5 안에서 찾다
            #   160.52 로 가 다음 말 «으유 알았슈»(카드 160.0~) 머리가 딸려 들어갔다)
            앞끝 = max([e for s_, e in cards if e <= cs + 0.01] + [cs - 0.5])
            뒤시작 = min([s_ for s_, e in cards if s_ >= ce - 0.01] + [ce + 0.5])
            새 = (조용한곳(max(cs - 0.5, 앞끝 - 0.02), cs + 0.05) if k == "t0"
                 else 조용한곳(ce - 0.05, min(ce + 0.5, 뒤시작 + 0.02)))
            print(f"  고침 조각 {i} {k}: {t:.2f} → {새:.2f}")
            segs[i][k] = 새
        for ai, a in enumerate(segs):                   # 넓히다 원본에서 겹치면 같은 대사 두 번 — 뒤 조각을 민다
            for b in segs[ai + 1:]:
                if b["t0"] < a["t1"] <= b["t1"] and a["t0"] <= b["t0"]:
                    print(f"  겹침 방지 t0 {b['t0']:.2f} → {a['t1']:.2f}")
                    b["t0"] = a["t1"]
                elif a["t0"] < b["t1"] <= a["t1"] and b["t0"] <= a["t0"]:
                    print(f"  겹침 방지 t1 {b['t1']:.2f} → {a['t0']:.2f}")
                    b["t1"] = a["t0"]
        합 = round(sum(s["t1"] - s["t0"] for s in segs), 1)
        if 합 > 79.0:
            print(f"  ★합계 {합}초 — 80초 한도에 걸린다. 곁 대사를 사람이 덜어 내야 한다(반영은 한다)")
        json.dump(옛, open(pj + ".카드경계전", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        proj["_est_sec"] = 합
        # 조각이 바뀌면 완성본 시각이 밀려 문구교정 핀이 엉뚱한 줄에 붙는다 — 비우고 대조표로 다시 단다
        if proj.pop("문구교정", None):
            print("  문구교정 핀을 비웠다 — 다시 구운 뒤 자막대조표로 다시 단다(이전 핀은 .카드경계전 에)")
        json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  반영 — 합계 {합}초 · 이전 판 {os.path.basename(pj)}.카드경계전 · 다음: FROM=2")
sys.exit(1 if 나쁨 else 0)
