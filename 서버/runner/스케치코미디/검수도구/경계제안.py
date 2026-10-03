#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경계제안.py <슬러그|projects json 경로> [--쓰기] — 말을 자르는 plan 조각 경계(t0·t1)만 «같은 샷 안» 의 깨끗한 자리로 옮기자고 제안한다.

  2026-09-26 싱글285·286 실측: plan 경계는 대사 한가운데를 자주 자른다(편마다 3~6곳). 사람이 원본 전사와
  말대역 소리 크기를 손으로 재서 옮겼고, 그래도 두 곳은 ④ 이음매 관문(완성본 Speechmatics)에 걸려 다시 구웠다.
  이 도구가 그 손일을 한다. 원본에서 맞닿은 이음(앞 조각 t1 = 다음 조각 t0)은 자른 자리가 아니므로 건드리지 않는다.
  최종 확인은 여전히 ④ 이음매 관문이 완성본 낱말로 한다.

  ★2026-10-03 루키치 배치(161~179) — 옛 판은 «경계가 agy 전사 한 줄 안이면 그 줄 끝/시작으로 넓히고, 앞뒤 ±0.3초 틈에서
    말대역이 가장 작은 20ms 로 맞춘다» 였다. 거의 매 편 제안 7~18곳을 배치 에이전트가 하나도 받지 않았다
    (샷 전환·로고·큰 제목 카드를 넘음 · agy 시각이 1~3초 늦어 말 한가운데로 감 — 170 은 10곳 전부). 167 은 «틈 안 더 조용한
    자리» 라며 빠른 카톡 낭독의 말 사이 0.05초 골에 경계를 놓아 말끝 «돼» 가 잘려 재굽기 1회.
    납품 19편 납품 경계에 옛 판을 다시 돌려 잰 숫자와 수리 뒤 숫자는 검수도구/경계제안시험.py 머리 주석에 있다.
    이제 판정·자리 찾기는 s2pipe/경계자리.py 한 곳(이음매수리.py 와 같이 씀):
     · 문제(카드 한가운데에서 말을 자름 · 말소리 위 · 나레 앞 덕킹 여유 모자람)가 있는 경계만 옮긴다 — 옛 판은 문제없는
       경계도 «더 조용한 20ms» 로 옮기자고 했고 그것이 제안 대부분이었다.
     · 같은 샷 안에서만 · 암전·아웃트로 앞에서만 · 조용한 골 0.25초↑(샷 전환 자리는 0.1초↑) · 옆 문장을 끌어들이지 않게.
     · agy 원본 전사 시각은 쓰지 않는다(박힌 카드 시각 + 원본 소리 + 샷 전환).
     · 고칠 자리가 없으면 옮기지 않고 까닭을 찍는다(사람이 조각을 다시 짠다).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W = os.path.expanduser("~/Desktop/스케치코미디")


def _체인중인가(pj):
    """★체인이 도는 중이면 고치지 않는다 (2026-09-26 — 도는 체인이 옛 내용을 덮어써 고친 값이 사라진 사건)"""
    lk = pj + ".체인중"
    if os.path.exists(lk):
        try:
            os.kill(int(open(lk).read().strip()), 0)
            return True
        except (ValueError, OSError):
            return False
    return False


def 제안(proj, 자리):
    """(바뀜 [(조각, 키, 옛값, 새값, 까닭)], 메모 [(조각, 키, 값, 까닭)]) — 겹침 방지까지. proj 는 바꾸지 않는다."""
    segs = proj["segments"]
    # 맞닿음은 «완성본 순서»로 잇닿은 두 조각이 원본에서도 붙어 있을 때만 — 원본에서 붙어 있어도 사이에 다른 조각이
    # 끼면(훅 앞당김: 싱글286 훅 116.5~120.5 · 본문 120.5~) 완성본에선 이음매라 말이 잘린다(2026-09-26 시험에서 발견)
    살린 = [i for i, s in enumerate(segs) if s.get("keep", True)]
    맞닿음 = set()
    for a, b in zip(살린, 살린[1:]):
        if abs(segs[b]["t0"] - segs[a]["t1"]) < 0.05:
            맞닿음 |= {(a, "t1"), (b, "t0")}
    # 나레 조각 바로 앞(완성본 순서) 조각 — 그 끝(t1)이 나레 머리 이음매다(★2026-09-28 저녁 싱글44 — 나레 앞 말끝 여유)
    나레앞조각 = {a for a, b in zip(살린, 살린[1:]) if (segs[b].get("narration") or "").strip()}
    바뀜, 메모 = [], []
    for i in 살린:
        s = segs[i]
        for k in ("t0", "t1"):
            if (i, k) in 맞닿음:
                continue
            문, 새, 까닭 = 자리.판정(s[k], k, 나레앞=(k == "t1" and i in 나레앞조각))
            if not 문:
                continue
            if 새 is None:
                # 소리만으로 부른 문제(카드 가장자리 말소리 · 말 사이 골)는 배경음·효과음일 수 있다 — 주의로 낮춰 말한다
                소리만 = all(m.startswith(("카드 가장자리", "말소리", "말 사이")) for m in 문)
                메모.append((i, k, s[k], ("주의(소리만 — 배경음일 수 있다) " if 소리만 else "") + " · ".join(문) + " — " + 까닭))
            elif abs(새 - s[k]) >= 0.02:
                바뀜.append((i, k, s[k], 새, " · ".join(문) + " → " + 까닭))

    # ★넓히다 두 조각이 원본에서 겹치면 같은 대사가 두 번 나온다(훅 반복 — 2026-09-22 사장님 «훅 반복 금지»).
    #   완성본에서 뒤에 나오는 조각의 시작을 앞 조각의 끝으로 민다(싱글286 «왜 부부끼리…» 가 훅·본문 양쪽에 들어갈 뻔).
    새값 = {(i, k): 새 for i, k, _a, 새, _w in 바뀜}

    def 값(i, k):
        return 새값.get((i, k), segs[i][k])
    for a_i, a in enumerate(살린):
        for b in 살린[a_i + 1:]:
            a0, a1, b0, b1 = 값(a, "t0"), 값(a, "t1"), 값(b, "t0"), 값(b, "t1")
            if b0 < a1 <= b1 and a0 <= b0:                     # 뒤 조각 머리가 앞 조각 꼬리와 겹침
                바뀜.append((b, "t0", b0, a1, f"조각 {a} 과 겹침 — 같은 대사 두 번 방지"))
                새값[(b, "t0")] = a1
            elif a0 < b1 <= a1 and b0 <= a0:                   # 뒤 조각 꼬리가 앞 조각 머리와 겹침
                바뀜.append((b, "t1", b1, a0, f"조각 {a} 과 겹침 — 같은 대사 두 번 방지"))
                새값[(b, "t1")] = a0
    return 바뀜, 메모


def 자막옮김(옛segs, 새segs, subs):
    """초안 자막을 새 경계 시간축으로 옮긴다 — 대사는 원본 시각을 따라가고(없어진 구간 줄은 버림),
    나레는 제 조각 머리에 붙는다(나레 소리는 굽기가 조각 머리에 놓는다 — 어긋나면 소리·자막이 따로 논다)."""
    def 누적(ss):
        out, at = [], 0.0
        for s_ in ss:
            if s_.get("keep", True):
                out.append((at, s_))
                at += s_["t1"] - s_["t0"]
            else:
                out.append((None, s_))
        return out
    옛, 새 = 누적(옛segs), 누적(새segs)
    결과 = []
    for x_ in subs:
        for (oa, os_), (na, ns_) in zip(옛, 새):
            if oa is None or na is None:
                continue
            if oa <= x_["t"] < oa + (os_["t1"] - os_["t0"]):
                y = dict(x_)
                if x_.get("kind") == "narr":
                    y["t"] = round(na + (x_["t"] - oa), 2)
                else:
                    원 = os_["t0"] + (x_["t"] - oa)
                    if not (ns_["t0"] <= 원 < ns_["t1"]):
                        break                                  # 새 경계 밖으로 나간 줄 — 버린다(sync 가 다시 짠다)
                    y["t"] = round(na + (원 - ns_["t0"]), 2)
                결과.append(y)
                break
    return sorted(결과, key=lambda z: z["t"])


def main():
    from s2pipe.경계자리 import 원본자리
    arg = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    쓰기 = "--쓰기" in sys.argv
    pj = arg if os.sep in arg else f"{W}/projects/{arg}.json"   # 경로를 주면 그 판(예: .plan원본)을 잰다(쓰기는 그 파일에)
    proj = json.load(open(pj, encoding="utf-8"))
    slug = proj.get("slug") or os.path.basename(pj)
    if 쓰기 and _체인중인가(pj):
        sys.exit(f"★{os.path.basename(pj)} 체인이 도는 중이다 — 끝난 뒤 고친다(고쳐도 체인이 덮어쓴다)")
    src = f"{W}/work/{proj['source']['id']}.mp4"
    자리 = 원본자리(src, proj, log=print)
    바뀜, 메모 = 제안(proj, 자리)
    segs = proj["segments"]
    새값 = {(i, k): 새 for i, k, _a, 새, _w in 바뀜}
    살린 = [i for i, s in enumerate(segs) if s.get("keep", True)]
    합 = sum(새값.get((i, "t1"), segs[i]["t1"]) - 새값.get((i, "t0"), segs[i]["t0"]) for i in 살린)
    print(f"{slug}: 경계 제안 {len(바뀜)}곳 · 고칠 자리 없음 {len(메모)}곳 · 합계 {합:.1f}초"
          + ("" if 쓰기 else " (재기만 — --쓰기 로 반영)")
          + f" · 카드 {len(자리.cards)}장 · 아웃트로 {자리.outro if 자리.outro is None else round(자리.outro, 2)}")
    for i, k, a, b, why in 바뀜:
        print(f"  조각 {i} {k}: {a:.2f} → {b:.2f}  ({why})")
    for i, k, a, why in 메모:
        print(f"  조각 {i} {k}: {a:.2f} 그대로 — {'' if why.startswith('주의') else '★'}{why}")
    if 쓰기 and 바뀜:
        옛판 = json.load(open(pj, encoding="utf-8"))
        json.dump(옛판, open(pj + ".경계전", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        for (i, k), 새 in 새값.items():
            segs[i][k] = 새
        proj["subs"] = 자막옮김(옛판["segments"], segs, 옛판.get("subs", []))
        proj["_est_sec"] = round(합, 1)
        proj.setdefault("_경계제안", []).append([(i, k, a, b, why) for i, k, a, b, why in 바뀜])
        json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  반영 — 이전 판 {os.path.basename(pj)}.경계전")


if __name__ == "__main__":
    main()
