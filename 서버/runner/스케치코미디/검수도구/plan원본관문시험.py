#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan원본관문시험.py [--편 슬러그…] [--나레없이] [--자세히] — plan 관문 ⑨ 원본검사·나레 줄 헛 반려 수리의 영구 시험.

  ★2026-10-05 수리D5 (루키치 배치 60~1 — 거의 매 편 에이전트가 plan 을 손으로 다시 짰다 · s2pipe/plan관문.py ⑨ 주석).
    놓침: 박힌 카드 한가운데·말 위를 자르는 경계(루키치40·53·5·2) · 결말 마지막 대사 빠짐(40) · 원본 순서 뒤섞임(53) ·
          조각 머리 순흑 1초(14). 헛 반려: «나레 줄 2 ≠ 나레 조각 1»(9·53) · «0 ≠ 1»(46) — make 가 저절로 맞추는 항목.

  시험 셋 (원본 영상·화면글자 캐시·원본 소리만 읽는다 — agy·유료 API·굽기 없음):
    ① 납품 최종본(배치로그/결과.tsv «납품» · 루키치·점심이네·싱글 · 원본 영상이 남은 편) — 에이전트가 프레임·소리로 경계를 재고
       납품한 조각이다. ⑨ 반려 = 가짜. 목표 0.
    ② 사건 초안(배치로그/<편>_2plan.txt 의 저장된 조각 표) — 아래 «꼭» 표의 딱지가 반려로 나와야 한다(놓침 0).
       나머지 초안(plan원본 · 2plan 로그)은 참고로 반려 수만 센다.
    ③ 나레 줄 — 납품 최종본의 나레 줄을 갈라·지워·옮겨 넣은 모의 초안을 plan관문.make구조 에 넣는다. «나레 줄» 반려 0 이어야 한다
       (같은 모의를 make.check 에 바로 넣으면 반려가 나는 것도 같이 보인다 — 모의가 진짜 어긋남인지 확인). --나레없이 면 건너뜀.
  종료코드: ① 가짜 0 · ② 놓침 0 · ③ 헛 반려 0 이면 0.
"""
import copy
import json
import os
import re
import sys
from multiprocessing import Pool

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)
os.environ.setdefault("S2_CONFIG", os.path.expanduser("~/Desktop/스케치코미디/config_누룽지독.json"))
W = os.path.expanduser("~/Desktop/스케치코미디")

# 사건 초안이 반려돼야 할 딱지 — (딱지, 그 반려 글에 들어 있어야 할 조각) (2026-10-05 진행_루키치.md «도구 거리» · 2plan 로그)
꼭 = {
    "루키치5": [("문장자름", "68.00초"), ("문장자름", "82.00초")],   # «야 문 닫지 마!» 카드 한가운데 · «와 저게 되네»(픽셀 카드가 놓친 문장)
    "루키치40": [("문장자름", "102.00초"), ("결말꼬리", "아")],       # 카드 101.5~103.2 · 마지막 대사 «아...» 128.2
    "루키치2": [("문장자름", "")],                                   # 46.5 «…» 카드 46.2~47.1 (81.5 «얘들아 왜 그래» 는 말끝 0.02초라 못 잡음 — 아래 주석)
    "루키치53": [("순서", "P4 원본 50.0")],                          # 민지 장면 P4 50.0~60.0 이 박격포 P3 99.5~107.0 뒤
    "루키치14": [("통암전", "145.0")],                               # 마지막 조각 머리 순흑 145.02~146.02
}
# 루키치2 81.5: 카드 «얘들아 왜 그래...» 80.2~81.7 · 말소리는 81.50 한 칸(20ms)에서 끝난다 — 남는 쪽 말 0.02초. 남는 말 하한(0.1초)을
#   0.02 로 낮추면 납품 최종본 가짜가 생긴다(«카드 양쪽 말» 최종 39곳이 남는 말 0.02~0.04초 — 루키치101·102·103…). 그래서 놓친다.
#   초안 2 는 46.5 문장자름으로 반려된다(남는 말 0.14 · 잘려 나가는 말 0.34 · 골 0.04초).


def 로그조각(slug):
    p = os.path.join(W, "배치로그", f"{slug}_2plan.txt")
    if not os.path.exists(p):
        return None
    segs = []
    for 줄 in open(p, encoding="utf-8"):
        if re.match(r"^구간 \d+개", 줄):
            segs = []
        m = re.match(r"^\s+P(\d)\s+\S+\s+[\d.]+초\s+원본\s+([\d.]+)~\s*([\d.]+)\s+punch", 줄)
        if m:
            segs.append({"phase": int(m[1]), "t0": float(m[2]), "t1": float(m[3]), "keep": True})
    return segs or None


def 잰다(slug):
    from s2pipe import plan관문 as G
    try:
        pj = json.load(open(os.path.join(W, "projects", f"{slug}.json"), encoding="utf-8"))
        src = os.path.join(W, "work", f"{pj['source']['id']}.mp4")
        if not os.path.exists(src):
            return {"slug": slug, "건너뜀": "원본 없음"}
        카드줄 = G.카드줄읽기(src, 만들기=False)
        out = {"slug": slug}
        pp = os.path.join(W, "projects", f"{slug}.json.plan원본")
        초 = json.load(open(pp, encoding="utf-8"))["segments"] if os.path.exists(pp) else 로그조각(slug)
        for 이름, segs in (("최종", pj["segments"]), ("초안", 초)):
            if not segs:
                continue
            m = {"segments": segs, "source": pj["source"]}
            값 = {}
            bad, warn = G.원본검사(m, src, 카드줄, 값)
            out[이름] = {"반려": bad, "주의": warn, "값": 값}
        return out
    except Exception as e:                                # noqa: BLE001
        return {"slug": slug, "오류": f"{type(e).__name__} {e}"[:300]}


def 나레시험(slugs):
    """③ — [(편, 모의, 바로 check 반려 수, make구조 반려 수)]."""
    os.chdir(R)
    import make
    from s2pipe import plan관문 as G
    out = []
    for slug in slugs:
        pj = json.load(open(os.path.join(W, "projects", f"{slug}.json"), encoding="utf-8"))
        if not any(x.get("kind") == "narr" for x in pj.get("subs", [])):
            continue
        for 이름 in ("갈림", "없음", "옛자리"):
            p = copy.deepcopy(pj)
            for 칸 in ("subs", "subs_before_sync"):
                if 칸 not in p:
                    continue
                n = [x for x in p[칸] if x.get("kind") == "narr"]
                rest = [x for x in p[칸] if x.get("kind") != "narr"]
                if 이름 == "갈림":                         # 초안자막쪼갬 이 나레 줄을 14자로 가른 꼴(루키치165)
                    n = [dict(x, text=x["text"][:len(x["text"]) // 2]) for x in n] + \
                        [dict(x, t=x["t"] + 1.0, text=x["text"][len(x["text"]) // 2:]) for x in n]
                elif 이름 == "없음":                       # plan 이 나레 줄을 안 만든 꼴(루키치46 «0 ≠ 1»)
                    n = []
                else:                                      # 조각을 다시 짠 뒤 옛 자리에 남은 꼴(루키치5 «7.50 ≠ 7.00»)
                    n = [dict(x, t=x["t"] + 0.5) for x in n]
                p[칸] = sorted(rest + n, key=lambda x: x["t"])
            바로 = sum(1 for b in make.check(copy.deepcopy(p), "")[0] if "나레 줄" in b)
            새 = sum(1 for b in G.make구조(p, "")[0] if "나레 줄" in b)
            out.append((slug, 이름, 바로, 새))
    return out


def main():
    자세히 = "--자세히" in sys.argv
    if "--편" in sys.argv:
        편 = [a for a in sys.argv[sys.argv.index("--편") + 1:] if not a.startswith("--")]
    else:
        편 = set()
        for l in open(os.path.join(W, "배치로그", "결과.tsv"), encoding="utf-8"):
            a = l.rstrip("\n").split("\t")
            if len(a) > 1 and a[1] == "납품" and re.fullmatch(r"(루키치|점심이네|싱글)\d+", a[0]):
                편.add(a[0])
        편 = sorted(편 | set(꼭), key=lambda s: (re.match(r"\D+", s)[0], int(re.search(r"\d+", s)[0])))
    with Pool(4) as pool:
        결과 = pool.map(잰다, 편)
    가짜, 놓침, 초안반려, 잰편, 건너뜀, 오류 = [], [], {}, 0, 0, []
    for r in 결과:
        if "오류" in r:
            오류.append(f"{r['slug']} {r['오류']}")
            continue
        if "건너뜀" in r:
            건너뜀 += 1
            continue
        잰편 += 1
        fb = (r.get("최종") or {}).get("반려") or []
        if fb:
            가짜.append(f"{r['slug']}: " + " / ".join(f"[{d}] {g[:220]}" for d, g in fb))
        cb = (r.get("초안") or {}).get("반려") or []
        for d, _g in cb:
            초안반려[d] = 초안반려.get(d, 0) + 1
        if r["slug"] in 꼭:
            for 딱, 조각 in 꼭[r["slug"]]:
                if not any(d == 딱 and 조각 in g for d, g in cb):
                    놓침.append(f"{r['slug']} 초안이 [{딱}] «{조각}» 반려여야 하는데 — 반려 {[(d, g[:120]) for d, g in cb]}")
            if 자세히:
                print(f"  사건 {r['slug']} 초안 반려: " + " / ".join(f"[{d}] {g[:260]}" for d, g in cb))
                print(f"         초안 주의: {[w[:200] for w in (r.get('초안') or {}).get('주의', [])]}")
    print(f"① 납품 최종본 {잰편}편(원본 없음 {건너뜀} · 오류 {len(오류)}) — ⑨ 가짜 반려 {len(가짜)}편")
    for x in 가짜:
        print("     가짜 " + x)
    for x in 오류[:10]:
        print("     오류 " + x)
    print(f"② 사건 초안 {len(꼭)}편 — 놓침 {len(놓침)} · 초안 전체 반려 딱지별 편 수(참고): {초안반려}")
    for x in 놓침:
        print("     놓침 " + x)
    헛 = []
    if "--나레없이" not in sys.argv:
        for slug, 이름, 바로, 새 in 나레시험(["루키치9", "루키치46", "루키치53"]):
            print(f"③ 나레 줄 모의 {slug} {이름}: make.check 바로 «나레 줄» 반려 {바로} → plan관문.make구조 {새}")
            if 새 or not 바로:                             # 바로 0 이면 모의가 어긋남을 못 만든 것 — 시험이 무효
                헛.append((slug, 이름, 바로, 새))
    ok = not 가짜 and not 놓침 and not 헛 and not 오류
    print("\n판정:", "통과" if ok else "미통과")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
