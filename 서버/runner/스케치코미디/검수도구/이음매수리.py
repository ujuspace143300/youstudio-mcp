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

  ★2026-10-03 루키치161 — 앞 조각 끝을 130.59→131.40 으로 늘리자고 했는데 130.589 가 화면 전환이라 다음 샷(아빠)의 대사까지
    들어올 뻔했다(«샷을 모르는 알려진 한계» — 배치 지침에 «같은 샷 안으로 옮기면 화면이 튄다 · 원본 화면 전환 자리 우선» 으로만
    적혀 있었다). 같은 클래스(경계 고침 도구가 샷 전환·암전·로고를 모르고 소리 크기만 본다)를 경계제안.py 와 함께
    s2pipe/경계자리.py 한 곳으로 고쳤다: 옮길 자리는 같은 샷 안 · 암전·아웃트로 앞 · 조용한 골 0.25초↑(샷 전환 자리는 0.1초↑) ·
    박힌 카드 한가운데가 아닌 곳. 자리가 없으면 옮기지 않고 «반려가 가짜인지 원본 소리로 확인 → 이음매허용(근거)» 또는
    «사람이 조각을 다시 짠다» 를 찍는다(161 은 실제로 완성본 전사가 엄마 말끝을 다음 낱말에 붙여 들은 가짜 반려였다).
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 이음매관문  # noqa: E402

arg = [a_ for a_ in sys.argv[1:] if not a_.startswith("--")][0]
쓰기 = "--쓰기" in sys.argv
W = os.path.expanduser("~/Desktop/스케치코미디")
pj = arg if os.sep in arg else f"{W}/projects/{arg}.json"   # 경로를 주면 그 판을 잰다(쓰기는 그 파일에)
proj = json.load(open(pj, encoding="utf-8"))
slug = proj.get("slug") or os.path.basename(pj)

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
from s2pipe.경계자리 import 원본자리  # noqa: E402
자리 = 원본자리(src, proj, log=print)


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
    나레앞 = bool((b2.get("narration") or "").strip())
    결과 = 자리.이음매고침(a["t1"], b2["t0"], 나레앞=나레앞)
    for k, 옛, 새, 까닭 in 결과:
        s_ = a if k == "t1" else b2
        if 새 is None:
            print(f"  이음매 {J:.2f} {k} {옛:.2f} 그대로 — ★{까닭}. 반려가 가짜인지(완성본 전사가 앞뒤 낱말을 붙여 들음)"
                  f" 원본 소리로 확인해 이음매허용(근거)으로 두거나, 사람이 조각을 다시 짠다")
        else:
            고침.append((s_, k, 옛, 새, 까닭))
    if not 결과:
        print(f"  이음매 {J:.2f} — 양쪽 다 조용하다(완성본 전사가 붙여 들음) — 손대지 않음")
for s, k, a0, b0, why in 고침:
    print(f"  {k} {a0:.2f} → {b0:.2f}  ({why})")
    s[k] = b0
# ★넓히다 원본에서 겹치면 같은 대사가 두 번 나온다(2026-09-27 싱글277 — 훅 끝을 뒤로, 클라이맥스 시작을 앞으로
#   넓혀 1.4초가 겹쳤다). 완성본에서 뒤에 오는 조각의 시작을 앞 조각 끝으로 민다 — 경계제안.py 와 같은 규칙.
for ai, a in enumerate(segs):
    for b in segs[ai + 1:]:
        if b["t0"] < a["t1"] <= b["t1"] and a["t0"] <= b["t0"]:
            print(f"  t0 {b['t0']:.2f} → {a['t1']:.2f}  (앞 조각과 겹침 — 같은 대사 두 번 방지)")
            고침.append((b, "t0", b["t0"], a["t1"], "겹침 방지"))
            b["t0"] = a["t1"]
        elif a["t0"] < b["t1"] <= a["t1"] and b["t0"] <= a["t0"]:
            print(f"  t1 {b['t1']:.2f} → {a['t0']:.2f}  (앞 조각과 겹침 — 같은 대사 두 번 방지)")
            고침.append((b, "t1", b["t1"], a["t0"], "겹침 방지"))
            b["t1"] = a["t0"]
합 = sum(s_["t1"] - s_["t0"] for s_ in segs)
if 합 > 79.0:
    print(f"  ★넓힌 뒤 합계 {합:.1f}초 — 80초 한도에 걸린다. 곁 대사를 사람이 덜어 내야 한다(반영은 한다)")
if not 쓰기:
    sys.exit(0)
if 쓰기 and 고침:
    json.dump(json.load(open(pj, encoding="utf-8")), open(pj + ".이음매전", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    proj["_est_sec"] = round(sum(s["t1"] - s["t0"] for s in segs), 1)
    proj.setdefault("_이음매수리", []).append([(k, a0, b0, why) for _s, k, a0, b0, why in 고침])
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  반영 — 합계 {proj['_est_sec']}초 · 이전 판 {os.path.basename(pj)}.이음매전 · 다음: FROM=2")
