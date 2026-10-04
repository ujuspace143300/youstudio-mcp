#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""결말벽시험.py — 결말 벽이 «부르는 쪽의 창» 에 따라 갈리지 않는가 (s2pipe/경계자리.결말벽 · 결말벽판정 · 여운관문).

왜 (2026-10-04 루키치87)
  준비_prproj 는 결말 벽을 208.123초(«로고 208.125»), 납품 관문 prproj끝검사는 208.039초(«아웃트로 카드 208.248 · 페이드
  208.041~»)로 잡아, 준비가 늘린 여운이 관문 벽을 1장 넘어 납품이 반려됐다(배치 에이전트가 여운 0.15 로 손 처리).
  37da614 가 함수 하나(경계자리.결말벽)로 묶었지만 부르는 쪽마다 창 끝(b)·아웃트로 인자가 달랐고, 결말벽의 결과가 b 에 따라
  달랐다(로고 판정은 «카드와 같아진 장» 이 창 안에 있어야 서고, 페이드 되짚기는 가장 이른 후보 하나에서만 했다).
  그때 37da614 의 모의 76편은 «준비 창» 하나로만 재서 이 갈림을 못 봤다 — 이 시험이 그 구멍을 메운다.

무엇을 재나
  편마다 이야기끝 a(마지막 조각 t1 의 프레임) 뒤 결말 벽을 창 넷(b 없음 · a+0.2 · a+2.0 · a+3.8 — 납품 관문·준비 여운 0.15·
  준비 기본 여운 1.8·가장 긴 창)으로 재서 «한 값» 인지 본다. 또 여운관문(준비·끝검사가 같이 부르는 것)에 벽 1장 앞 끝을 주면
  통과, 벽 1장 뒤 끝을 주면 탈인지 본다. 루키치87 은 벽 = 208.0392(페이드 208.041~)로 고정 값까지 본다.

쓰는 법
  S2_CONFIG=<작업폴더>/config.json ~/.volcano/venv/bin/python3 결말벽시험.py [--작업 ~/Desktop/스케치코미디] [편이름 …]
  편이름을 안 주면 루키치87 하나만. --전부 면 projects/ 의 원본 있는 편 전부(오래 걸린다 — 편당 수 초).
  종료코드 0 = 모두 한 값 · 1 = 갈린 편 있음.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 경계자리 as W, 프레임격자 as G   # noqa: E402

고정 = {"루키치87": 208.0392}       # 사람이 프레임으로 본 값(2026-10-04 — 208.041 부터 카드로 섞여 드는 페이드)


def 한편(작업, 이름):
    p = json.load(open(os.path.join(작업, "projects", 이름 + ".json"), encoding="utf-8"))
    src = os.path.join(작업, "work", p["source"]["id"] + ".mp4")
    segs = [s for s in p.get("segments", []) if s.get("keep")]
    if not (segs and os.path.exists(src)):
        return None
    g = G.얻기(src)
    막 = segs[-1]
    a = g.시작(g.번호(막["t1"]))
    굽 = float(막["_엔드카드시작"]) if 막.get("_엔드카드시작") else None
    아 = W.결말아웃트로(src, a, 굽)
    값 = {}
    for 이름b, b in (("관문", None), ("+0.2", a + 0.2), ("+2.0", a + 2.0), ("+3.8", a + 3.8)):
        벽, 까닭 = W.결말벽(src, a, b, 아웃트로=아)
        값[이름b] = (벽, 까닭)
    벽들 = {(g.번호(v[0]) if v[0] is not None else None) for v in 값.values()}
    판 = W.결말벽판정(src, a, 굽)
    탈 = []
    if len(벽들) != 1:
        탈.append("창에 따라 벽이 갈림 " + " · ".join(f"{k}={v[0]}({v[1]})" for k, v in 값.items()))
    if 판["벽"] is not None and (g.번호(판["벽"]) not in 벽들):
        탈.append(f"결말벽판정 {판['벽']} 이 창별 값과 다름")
    if 판["벽"] is not None:
        kw = g.번호(판["벽"])
        기록 = {"전_src_end": round(a, 4), "벽": 판["벽"], "까닭": 판["까닭"], "굽기카드": 굽}
        if kw - 1 > g.번호(a):
            r = W.여운관문(src, 기록, g.시작(kw - 1))
            if r["탈"]:
                탈.append("여운관문이 벽 1장 앞 끝을 막음 — " + r["글"])
        r = W.여운관문(src, 기록, g.시작(kw + 1))
        if not r["탈"]:
            탈.append("여운관문이 벽 1장 뒤 끝을 못 막음 — " + r["글"])
    if 이름 in 고정 and (판["벽"] is None or g.번호(판["벽"]) != g.번호(고정[이름])):
        탈.append(f"고정 값 {고정[이름]} 과 다름 — {판['벽']}")
    return {"편": 이름, "a": a, "벽": 판["벽"], "까닭": 판["까닭"], "탈": 탈}


def main(argv):
    작업 = os.path.expanduser("~/Desktop/스케치코미디")
    if "--작업" in argv:
        작업 = os.path.expanduser(argv[argv.index("--작업") + 1])
    os.environ.setdefault("S2_CONFIG", os.path.join(작업, "config.json"))
    편들 = [x for i, x in enumerate(argv) if not x.startswith("--") and (i == 0 or argv[i - 1] != "--작업")]
    if "--전부" in argv:
        편들 = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(작업, "projects", "*.json")))
    if not 편들:
        편들 = ["루키치87"]
    잰, 나쁨 = 0, 0
    for 이름 in 편들:
        try:
            r = 한편(작업, 이름)
        except Exception as e:                      # noqa: BLE001
            print(f"[?] {이름}: 못 잼 — {str(e)[:80]}")
            continue
        if r is None:
            continue
        잰 += 1
        if r["탈"]:
            나쁨 += 1
            print(f"[X] {이름}: a={r['a']:.3f} 벽={r['벽']} — " + " / ".join(r["탈"]))
        else:
            print(f"[OK] {이름}: a={r['a']:.3f} 벽={'%.4f' % r['벽'] if r['벽'] is not None else '없음'} {r['까닭']}")
    print(f"잰 편 {잰} · 갈림·관문 탈 {나쁨}")
    return 1 if 나쁨 or not 잰 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
