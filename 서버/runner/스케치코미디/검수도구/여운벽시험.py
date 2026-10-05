#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""여운벽시험.py — 프리미어 끝 여운이 결말 뒤 쿠키·페이드아웃·정지화면·다음 말 머리를 담지 않는가 (s2pipe/경계자리.여운벽 · 여운관문).

왜 (2026-10-05 루키치 수리 D1)
  여운(기본 1.8초 — 마지막 컷을 원본에서 더 틀기)의 끝을 결말 벽(아웃트로 카드·암전·로고·그 벽으로 다가가는 빠른 페이드)과
  날카로운 샷 전환으로만 막아, 벽까지 비어 있으면 결말 뒤 내용을 그대로 담았다. 납품 관문(prproj끝검사)도 결말 벽만 봐서 지나갔다.
    19  카페베네 엔딩 정지화면·비명 1.8초 (224.474 디졸브 → 224.808~ 정지)
    8   흰 번쩍 «찰칵» 뒤 세 사람 사진 정지화면 1.8초 (237.195~)
    29  페이드아웃 + 다음 문장 «두 번째…» 머리 (184.59 소리 시작)
    4   117.03~ 페이드아웃 1.1초
    17  이야기 끝 전부터 이어진 페이드아웃 1.4초
    75  다음 말 «셧더» (241.26 소리 시작) 0.5초 — 2026-10-05 모의에서 새로 찾음
  수리: 경계자리.여운벽(한 곳) — 준비가 여운을 그 앞에서 멈추고, 여운관문(준비 굽기 전 · prproj끝검사 납품)이 다시 잰다.

무엇을 재나
  ① 사건 표본: 여운벽이 결함 내용 «앞» 에서 서는가(값 상한) · 납품된 프리미어 끝으로 여운관문을 부르면 «여운탈» 인가.
     29 는 페이드가 먼저 서도 «다음 말» 후보(184.45~184.6 소리 시작)를 따로 찾는가.
  ② 정상 표본: 여운이 30장 넘게 들어가 문제없이 납품된 편 — 여운벽이 납품 끝보다 앞서지 않고 여운관문이 통과하는가(회귀 없음).
  ③ 결말 벽만 보는 기존 관문 동작은 결말벽시험.py 가 본다(여운관문 «결말탈» 칸).

쓰는 법
  S2_CONFIG=<작업폴더>/config_누룽지독.json ~/.volcano/venv/bin/python3 여운벽시험.py [--작업 ~/Desktop/스케치코미디]
  종료코드 0 = 틀림 0 · 1 = 틀림 있음 · 2 = 표본 자료 없음.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 경계자리 as W, 프레임격자 as G   # noqa: E402

# 편 → (여운벽 상한 초 — 이 시각 «앞» 에서 서야 한다 · 까닭에 들어야 할 말)
사건 = {
    "루키치19": (224.475, "다른 그림"),
    "루키치8": (237.196, "다른 그림"),
    "루키치29": (184.56, "페이드아웃"),
    "루키치4": (117.06, "페이드아웃"),
    "루키치17": (235.20, "페이드아웃"),
    "루키치75": (241.26, "다음 말"),
}
정상 = ["루키치105", "루키치106", "루키치116", "루키치122", "루키치132", "루키치136", "루키치145", "루키치42", "루키치46",
        "루키치76", "루키치84", "루키치93"]


def 읽기(작업, 이름):
    d = os.path.join(작업, f"프리미어_{이름}")
    tl = json.load(open(os.path.join(d, "timeline_sk.json"), encoding="utf-8"))
    기록 = dict(tl["여운"])
    src = 기록.get("원본") or os.path.join(작업, "work", 이름 + ".mp4")
    기록["원본"] = src
    pc = tl["picture"][-1]
    끝 = float(pc["src_in"]) + float(pc["t1"]) - float(pc["t0"])
    return src, 기록, 끝


def main(argv):
    작업 = os.path.expanduser("~/Desktop/스케치코미디")
    if "--작업" in argv:
        작업 = os.path.expanduser(argv[argv.index("--작업") + 1])
    os.environ.setdefault("S2_CONFIG", os.path.join(작업, "config_누룽지독.json"))
    틀림, 잰 = 0, 0
    for 이름, (상한, 말) in 사건.items():
        try:
            src, 기록, 끝 = 읽기(작업, 이름)
        except (OSError, KeyError, ValueError) as e:
            print(f"[?] {이름}: 자료 없음 {e!r}")
            continue
        잰 += 1
        a = float(기록["전_src_end"])
        벽, 까닭, 후보 = W.여운벽(src, a, 자세히=True)
        탈 = []
        if 벽 is None or 벽 >= 상한:
            탈.append(f"여운벽 {벽} 이 {상한} 앞에서 서지 않음")
        if 말 not in 까닭:
            탈.append(f"까닭에 «{말}» 없음")
        if 이름 == "루키치29":
            g = G.얻기(src)
            if not any("다음 말" in c and 184.40 <= g.시작(k) <= 184.60 for k, c in 후보):
                탈.append("다음 말(«두 번째…» 184.45~184.6) 후보를 못 찾음")
        r = W.여운관문(src, {k: v for k, v in 기록.items() if k != "여운벽"}, 끝)
        if not r["여운탈"]:
            탈.append("납품된 끝으로 여운관문이 탈이 아님 — " + r["글"])
        틀림 += bool(탈)
        print(("[X] " if 탈 else "[OK] ") + f"사건 {이름}: 이야기끝 {a:.3f} 납품 끝 {끝:.3f} → 여운벽 {벽} ({까닭})"
              + (" — " + " / ".join(탈) if 탈 else ""))
    for 이름 in 정상:
        try:
            src, 기록, 끝 = 읽기(작업, 이름)
        except (OSError, KeyError, ValueError) as e:
            print(f"[?] {이름}: 자료 없음 {e!r}")
            continue
        잰 += 1
        a = float(기록["전_src_end"])
        g = G.얻기(src)
        벽, 까닭 = W.여운벽(src, a)
        r = W.여운관문(src, {k: v for k, v in 기록.items() if k != "여운벽"}, 끝)
        탈 = []
        if 벽 is not None and g.번호(벽) < g.번호(끝):
            탈.append(f"여운벽 {벽}({까닭}) 이 납품 끝 {끝:.3f} 앞 — 정상 편 여운을 깎음")
        if r["탈"]:
            탈.append("여운관문 탈 — " + r["글"])
        틀림 += bool(탈)
        print(("[X] " if 탈 else "[OK] ") + f"정상 {이름}: 여운 {g.번호(끝) - g.번호(a)}장 · 여운벽 "
              + (f"{벽:.3f} ({까닭})" if 벽 is not None else "없음") + (" — " + " / ".join(탈) if 탈 else ""))
    print(f"잰 편 {잰} · 틀림 {틀림}")
    if not 잰:
        return 2
    return 1 if 틀림 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
