#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""효과음자리시험.py — A3 효과음(훅·절정·반전)이 같은 트랙에서 겹치지 않는가 (s2pipe/효과음자리.py).

왜 (2026-10-04 루키치75·140·149·152)
  준비_prproj 가 절정 dudun·반전 gaze 를 하나씩 따로 말 틈(±2.5초)으로 옮기며 같은 A3 트랙의 다른 효과음을 안 봐서 둘이 겹쳤고,
  ⑧ 조립 verify «트랙 A3 겹침 0» 에서야 죽었다(네 번 — 배치 에이전트가 phase 를 손으로 바꿔 넘김).

무엇을 재나
  ① 실패 재현 — 시험자료/효과음겹침_3편.json(실패 당시 prproj 에서 되읽은 V1·A3 와 계획 JSON 의 말)을 옛 셈(옛자리잡기)에
     넣으면 실패 당시 A3 자리가 «장 단위로 그대로» 나오고 겹침이 있다. 새 셈(자리잡기)은 겹침 0.
  ② 모의 — 절정 조각 길이 0.3~6초 · 절정·반전 둘레 말 배치를 고루 바꾼 인공 편 수천 개에서 새 셈의 겹침 0 · 말 위 −12dB 나
     뺌이 «A3 빈 자리가 정말 없을 때만» 인지.
  종료코드 0 = 모두 통과.
쓰는 법
  python3 효과음자리시험.py
"""
import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from s2pipe import 효과음자리 as E   # noqa: E402

자료 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "시험자료", "효과음겹침_3편.json")


def _재료(길이, wav길이, 절정, 반전):
    return [{"라벨": "훅", "t0": 0.0, "길이": 길이["훅"], "wav길이": wav길이["훅"], "스냅": False},
            {"라벨": "절정", "t0": 절정, "길이": 길이["절정"], "wav길이": wav길이["절정"], "스냅": True},
            {"라벨": "반전", "t0": 반전, "길이": 길이["반전"], "wav길이": wav길이["반전"], "스냅": True}]


def _틀들(재, 결과, total):
    return [(r["라벨"],) + E.틀(r["t0"], r["t1"], e["wav길이"], total) for e, r in zip(재, 결과) if not r["뺌"]]


def 실패재현():
    d = json.load(open(자료, encoding="utf-8"))
    탈 = 0
    for 이름, v in d["편"].items():
        재 = _재료(d["길이"], v["wav길이"], v["절정t0"], v["반전t0"])
        말 = [tuple(x) for x in v["말"]]
        옛 = E.옛자리잡기(재, 말, v["total"])
        옛틀 = _틀들(재, 옛, v["total"])
        옛겹 = E.겹침들(옛틀)
        재현 = sorted([a, b] for _n, a, b in 옛틀) == sorted(v["실패A3"])
        새 = E.자리잡기(재, 말, v["total"])
        새틀 = _틀들(재, 새, v["total"])
        새겹 = E.겹침들(새틀)
        ok = 재현 and 옛겹 and not 새겹
        탈 += not ok
        print(("[OK] " if ok else "[X] ") + f"{이름}: 옛 셈 A3 {[(n, round(a / 30, 3), round(b / 30, 3)) for n, a, b in 옛틀]}"
              + f" — 실패 당시와 {'같음' if 재현 else '다름'} · 겹침 {[(a, b, f'{k}장') for a, b, k in 옛겹]}")
        print(f"      새 셈 A3 {[(n, round(a / 30, 3), round(b / 30, 3)) for n, a, b in 새틀]} · 겹침 {len(새겹)}"
              + "".join(f"\n      · {r['글']}" for r in 새 if r["글"]))
    return 탈


def 모의(n=4000, 씨=20261004):
    rnd = random.Random(씨)
    길이 = {"훅": 3.349, "절정": 2.617, "반전": 2.311}
    wav길이 = {"훅": 3.349, "절정": 2.617, "반전": 2.311}
    셈 = {"편": 0, "옛겹침": 0, "새겹침": 0, "낮춤": 0, "뺌": 0, "헛낮춤": 0}
    for _ in range(n):
        total = rnd.uniform(60, 80)
        반전 = rnd.uniform(total - 20, total - 3)
        절정 = 반전 - rnd.uniform(0.3, 6.0)              # 절정 조각 길이
        말 = []
        t = max(0.0, 절정 - 6)
        while t < min(total, 반전 + 6):                  # 말 덩이와 틈을 섞는다 — 말이 빽빽한 편부터 듬성한 편까지
            d = rnd.uniform(0.15, 2.5)
            말.append((t, min(total, t + d)))
            t += d + rnd.choice([0.05, 0.1, 0.2, 0.4, 0.8, 1.5, 2.5])
        재 = _재료(길이, wav길이, 절정, 반전)
        옛 = E.옛자리잡기(재, 말, total)
        새 = E.자리잡기(재, 말, total)
        셈["편"] += 1
        셈["옛겹침"] += bool(E.겹침들(_틀들(재, 옛, total)))
        새틀 = _틀들(재, 새, total)
        셈["새겹침"] += bool(E.겹침들(새틀))
        for e, r in zip(재, 새):
            셈["낮춤"] += r["낮춤"]
            셈["뺌"] += r["뺌"]
            if r["낮춤"]:
                # −12dB 는 «말 틈 + A3 빈 자리» 가 ±2.5초 안에 정말 없을 때만이어야 한다
                놓인 = [x for x in 새틀 if x[0] != e["라벨"]]
                for k in range(0, 26):
                    for 부호 in (1, -1):
                        c = e["t0"] + 부호 * k * 0.1
                        창 = e["길이"] * 0.7
                        if c < 0 or c + 창 > total or any(not (b <= c or a >= c + 창) for a, b in 말):
                            continue
                        a_, b_ = E.틀(c, min(c + e["길이"], total), e["wav길이"], total)
                        if not E.겹침들(놓인 + [(e["라벨"], a_, b_)]):
                            셈["헛낮춤"] += 1
                            break
                    else:
                        continue
                    break
    ok = 셈["새겹침"] == 0 and 셈["헛낮춤"] == 0 and 셈["옛겹침"] > 0
    print(("[OK] " if ok else "[X] ") + f"모의 {셈['편']}편 — 옛 셈 겹침 {셈['옛겹침']}편 → 새 셈 {셈['새겹침']}편 · "
          f"−12dB {셈['낮춤']}개(헛낮춤 {셈['헛낮춤']}) · 뺌 {셈['뺌']}개")
    return 0 if ok else 1


def 틀같음():
    """틀() 이 조립_prproj_sk 의 셈(frame_ticks · 끝맞춤 · wav 길이 내림)과 같은가 — 조립 함수를 직접 불러 대조."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    import 조립_prproj_sk as J
    rnd = random.Random(7)
    틀림 = 0
    for _ in range(2000):
        total = rnd.uniform(40, 90)
        t0 = rnd.uniform(0, total)
        길 = rnd.uniform(0.5, 4)
        t1 = min(t0 + 길, total)
        wl = 길 + rnd.uniform(-0.05, 0.05)
        영상끝 = J.frame_ticks(total)
        a = J.frame_ticks(t0)
        n = min(min(J.frame_ticks(t1), 영상끝) - a, (int(wl * 48000) * (J.TPS // 48000) // J.FRAME) * J.FRAME)
        기대 = (a // J.FRAME, (a + n) // J.FRAME)
        got = E.틀(t0, t1, int(wl * 48000) / 48000, total)
        틀림 += 기대 != got
    print(("[OK] " if not 틀림 else "[X] ") + f"틀() = 조립 셈 — 2000개 중 틀림 {틀림}")
    return 1 if 틀림 else 0


if __name__ == "__main__":
    나쁨 = 실패재현() + 모의() + 틀같음()
    sys.exit(1 if 나쁨 else 0)
