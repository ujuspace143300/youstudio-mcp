#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원본자막대조시험.py — 원본 박힌 자막에 없는 «괄호 설명 줄 · 노래 가사 · 알림 소리» 를 sync 가 거르는가 (s2pipe/원본자막대조.판정).

왜 (2026-10-05 수리D3 — 루키치 배치 사건)
  루키치14 노래 «Smoke» 가사 13줄 · 17 «(루이비통 선물 투척)» · 11·67 «카톡» · 4 «배달의민족 주문!» 이 자막으로 나갔고 사람이
  빼기 핀으로 지웠다. 같은 클래스인데 사람도 놓쳐 납품된 줄: 195·168 «카톡» · 181·194·66 괄호 설명 줄.
  정상 줄(사람이 빼기 핀으로 지우지 않은 줄)은 하나도 빠지면 안 된다 — 원본이 자막을 안 단 진짜 대사(124·80·93 …)도 있다.

판정 입력 = 그 편의 «작표 첫판»(projects json `_작표캐시` — 첫 굽기 뒤 ④ 가 핀 없이 본 대사 줄) + plan 초안의 괄호 줄,
  줄 끝은 sync.끝시각채우기 그대로. 원본 카드·글자 인식은 원본 옆 캐시(`.카드상자.json` · `.화면글자.json` · `.카드2.json`)에서.

쓰는 법
  S2_CONFIG=~/Desktop/스케치코미디/config_누룽지독.json ~/.volcano/venv/bin/python3 원본자막대조시험.py           시험자료로(종료코드 0 = 맞음)
  … 원본자막대조시험.py --전체        이 컴퓨터의 루키치 편 전부(캐시 있는 편)로 — 회귀 재기
  … 원본자막대조시험.py --자료만들기   시험자료/원본자막대조_루키치.json 을 다시 뜬다(아래 편 목록)
"""
import json
import glob
import os
import re
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)
from s2pipe import 원본자막대조 as 대조  # noqa: E402
from s2pipe import 번인관문, 화면글자 as 글, sync  # noqa: E402

W = os.path.expanduser("~/Desktop/스케치코미디")
자료파일 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "시험자료", "원본자막대조_루키치.json")

# 사람도 놓쳐 납품된 같은 클래스 줄(원본 자막에 없음 — 화면글자 캐시로 확인 2026-10-05) — 빼는 게 맞다
놓친같은클래스 = {("루키치195", 0.0), ("루키치195", 61.53), ("루키치168", 0.02)}
# 반드시 빠져야 하는 사건 줄 — (편, 시각 범위, 글 일부)
사건빼기 = [("루키치14", 64.0, 79.5, None, 13), ("루키치17", 0, 999, "루이비통", 1), ("루키치11", 72.9, 73.1, "카톡", 1),
          ("루키치67", 6.7, 6.9, "카톡", 1), ("루키치4", 14.9, 15.1, "배달의민족", 1)]
# 빼지 않고 «주의» 로만 알려야 하는 줄 (수업 말 — 짧은 무자막 줄은 진짜 대사와 갈라지지 않는다)
사건주의 = [("루키치5", 9.0, 12.5, 3)]
# 시험자료에 담을 편 — 사건 + 괄호 줄 있는 편 + 무자막 짧은 연속이 있는 정상 편 + 고른 정상 편
자료편 = ["루키치14", "루키치17", "루키치11", "루키치67", "루키치4", "루키치5", "루키치149", "루키치206", "루키치76", "루키치83",
        "루키치181", "루키치194", "루키치66", "루키치195", "루키치168", "루키치112", "루키치130", "루키치124", "루키치80",
        "루키치93", "루키치6", "루키치38", "루키치2", "루키치33", "루키치158", "루키치21", "루키치101", "루키치143",
        "루키치3", "루키치46", "루키치48", "루키치129", "루키치209", "루키치229", "루키치274", "루키치198", "루키치287",
        "루키치92"]   # 229·274 = 원본 자막 없는 긴 진짜 대사(원본 전사 있음 — 노래로 빼면 틀림) · 209·198·287 = 사람이 지운 무자막 줄


def 편자료(slug):
    """한 편의 판정 입력 — 원본 영상이 없어도 캐시만으로(번인관문.확인된카드들과 같은 규칙)."""
    proj = json.load(open(f"{W}/projects/{slug}.json", encoding="utf-8"))
    lines = (proj.get("_작표캐시") or {}).get("lines")
    words = proj.get("asr_words") or []
    src = f"{W}/work/{proj['source']['id']}.mp4"
    if not lines or not words or not os.path.exists(src + ".카드상자.json") or not os.path.exists(src + ".화면글자.json"):
        return None
    boxes = [b for b in json.load(open(src + ".카드상자.json", encoding="utf-8"))["boxes"] if not b.get("가짜")]
    cards = 번인관문.글줄가르기([(b["t0"], b["t1"]) for b in boxes if b.get("출처", "카드") == "카드"],
                            [(b["t"], b.get("글", ""), b.get("top", 0)) for b in boxes if b.get("출처") == "글줄" and "t" in b])
    try:
        띠 = json.load(open(src + ".카드2.json", encoding="utf-8")).get("띠") or list(글.옛띠 if hasattr(글, "옛띠") else (0.8, 0.9))
    except OSError:
        from s2pipe import 자막띠시각
        띠 = list(자막띠시각.옛띠)
    c = json.load(open(src + ".화면글자.json", encoding="utf-8"))
    표본 = [(round(t, 2), l["s"]) for t, l in 글.자막표본(c["frames"], 띠)]
    dlg = [{"t": round(float(x["t"]), 2), "text": x["text"]} for x in lines]
    dlg += [{"t": round(float(s["t"]), 2), "text": s["text"]} for s in proj.get("subs_before_sync", [])
            if s.get("kind") != "narr" and s.get("text", "").lstrip().startswith("(")]
    dlg.sort(key=lambda d: d["t"])
    sync.끝시각채우기(dlg, words)
    빼기핀 = sorted(float(k) for k, v in (proj.get("문구교정") or {}).items() if v == "")
    원줄 = 대조.원본전사읽기(f"{W}/work/{slug}.ko.vtt")
    return {"편": slug, "그림": 대조.원본그림(proj), "cards": cards, "표본": 표본, "원줄": 원줄,
            "dlg": [{"t": d["t"], "t1": d.get("t1"), "text": d["text"]} for d in dlg], "빼기핀": 빼기핀}


def 줄이기(e):
    """시험자료 크기 줄이기 — 판정이 보는 창(줄 원본 시각 ±2.5초) 밖 표본·원본 전사는 버린다(판정 결과는 같다)."""
    창 = []
    for d in e["dlg"]:
        to, o1 = 대조._원(e["그림"], d["t"])
        if to is not None:
            창.append((to - 2.5, min(to + max(0.0, (d.get("t1") or d["t"] + 1.0) - d["t"]), o1) + 2.5))
    안 = lambda t: any(a <= t <= b for a, b in 창)   # noqa: E731
    e["표본"] = [x for x in e["표본"] if 안(x[0])]
    if e.get("원줄") is not None:
        e["원줄"] = [x for x in e["원줄"] if 안(x[0])]
    return e


def 사람이지움(e, d):
    return any(d["t"] - 0.4 <= p <= max(d.get("t1") or d["t"] + 2.0, d["t"] + 0.5) + 0.05 for p in e["빼기핀"])


def 잰다(자료들, 자세히=False):
    틀림, 통 = [], {"편": 0, "켜짐": 0, "뺌": 0, "주의": 0, "줄": 0, "사람지움": 0, "사람지움_뺌": 0}
    by = {}
    for e in 자료들:
        r = 대조.판정(e["dlg"], e["그림"], e["cards"], e["표본"], e.get("원줄"))
        by[e["편"]] = (e, r)
        통["편"] += 1
        통["줄"] += len(e["dlg"])
        통["켜짐"] += r["켜짐"]
        통["뺌"] += len(r["빼기"])
        통["주의"] += len(r["주의"])
        통["사람지움"] += sum(사람이지움(e, d) for d in e["dlg"])
        for d, 까닭 in r["빼기"]:
            맞음 = 사람이지움(e, d) or (e["편"], d["t"]) in 놓친같은클래스 or d["text"].lstrip().startswith("(")
            통["사람지움_뺌"] += 사람이지움(e, d)
            if not 맞음:
                틀림.append(f"{e['편']} [{d['t']:.2f}] 「{d['text']}」 — 사람이 둔 줄을 뺌({까닭})")
            elif 자세히:
                print(f"   뺌 {e['편']} [{d['t']:.2f}] 「{d['text']}」 {까닭}")
    for 편, a, b, 글자, n in 사건빼기:
        if 편 not in by:
            if not 자세히:
                틀림.append(f"{편} 자료 없음")
            continue
        e, r = by[편]
        뺀 = [d for d, _ in r["빼기"] if a <= d["t"] <= b and (글자 is None or 글자 in d["text"])]
        ok = len(뺀) >= n
        print(("[OK] " if ok else "[X] ") + f"사건 {편} {a}~{b}s {글자 or ''} — 뺌 {len(뺀)}/{n}")
        if not ok:
            틀림.append(f"사건 {편} 못 뺌")
    for 편, a, b, n in 사건주의:
        if 편 not in by:
            continue
        e, r = by[편]
        주 = [x for x in r["주의"] if a <= x["d"]["t"] <= b]
        뺀 = [d for d, _ in r["빼기"] if a <= d["t"] <= b]
        ok = len(주) >= n and not 뺀
        print(("[OK] " if ok else "[X] ") + f"주의 {편} {a}~{b}s — 주의 {len(주)}/{n} · 뺌 {len(뺀)}(0 이어야)")
        if not ok:
            틀림.append(f"주의 {편}")
    return 틀림, 통


def main():
    if "--자료만들기" in sys.argv:
        자료들 = [줄이기(x) for x in (편자료(s) for s in 자료편) if x]
        os.makedirs(os.path.dirname(자료파일), exist_ok=True)
        json.dump(자료들, open(자료파일, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"시험자료 {len(자료들)}편 → {자료파일} ({os.path.getsize(자료파일) // 1024} KB)")
        return 0
    if "--전체" in sys.argv:
        slugs = sorted({re.sub(r"\.json$", "", os.path.basename(p)) for p in glob.glob(f"{W}/projects/루키치*.json")
                        if re.fullmatch(r"루키치\d+\.json", os.path.basename(p))}, key=lambda s: int(s[3:]))
        자료들 = [x for x in (편자료(s) for s in slugs) if x]
    else:
        자료들 = json.load(open(자료파일, encoding="utf-8"))
    틀림, 통 = 잰다(자료들, 자세히="--자세히" in sys.argv)
    print(f"편 {통['편']} (켜짐 {통['켜짐']}) · 줄 {통['줄']} · 뺌 {통['뺌']} · 주의 {통['주의']} · "
          f"사람이 빼기 핀으로 지운 줄 {통['사람지움']} 중 뺌 {통['사람지움_뺌']}")
    for t in 틀림:
        print("[X]", t)
    print(f"틀림 {len(틀림)}")
    return 1 if 틀림 else 0


if __name__ == "__main__":
    sys.exit(main())
