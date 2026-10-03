#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan관문시험.py [시리즈…] [--옛판 <옛 plan관문.py>] — plan 관문 ⑦ «설명시각» 의 영구 시험(가짜 반려 0 · 진짜 반려 유지).

  ★2026-10-03 루키치 배치 — 에이전트 보고 «plan관문의 설명시각 반려가 거의 매 편 가짜» (168 «주말인데 다들 머하심?» 21.5초 ↔ 카드 24.5 ·
    170 261.1 ↔ 265.0 · 172 156.7 ↔ 160.2 · 169 전사 약 40초 밀림 · 166·163·173·178·177·167·161·231·255·250·241·230·225·183 …).
    클래스(s2pipe/plan관문.py 대사찾기·⑦ 주석): (가) 앞 줄 딸려 옴 — 대사와 상관없는 앞 줄부터 이은 묶음이 먼저 최고점에 닿아 찾은
    자리가 3~6초 일렀다 (나) 시계가 agy 원본 전사 하나 — 전사는 박힌 카드보다 늦거나 통째로 밀린다.

  시험 넷(전부 원본 옆 캐시만 읽는다 — agy·유료 API·원본 영상 안 씀):
    ① 납품 최종본(projects/<편>.json) — 에이전트가 박힌 카드·샷·소리로 경계를 재고 납품한 조각. 설명시각 반려 = 가짜. 목표 0.
    ② plan 초안(projects/<편>.json.plan원본) — 참고(초안은 옛 관문을 통과한 답이라 대개 0).
    ③ 모의 틀린 plan — 최종본 조각마다 첫대사는 그대로 두고 시각만 «다른 장면» 으로 옮긴다(앞뒤 40초 이상 · 그 대사가 새 자리
       안에 없게). 반려 = 진짜(잡아야 한다). 목표 100%. 점심이네43(P4 설명은 124~143초인데 시각은 203~226초 — 이 관문이 생긴 사건)
       과 같은 모양이다.
    ④ 옛 2plan 로그의 설명시각 반려 줄(plan 1회차 초안 — 저장 안 됨, 반려 글의 시각·첫대사 16자로 되살린다) — 새 관문 판정을
       카드 시각과 함께 보인다(사람이 진짜·가짜를 확인하는 표).
  --옛판 을 주면 같은 재료를 옛 관문으로도 재서 나란히 보이고, ⑦ 밖 검사(나레덮음·꼭남길·셋업·결말 — 대사찾기를 같이 쓴다)
  값이 바뀐 편을 적는다(회귀 확인).
  종료코드: ① 가짜 반려 0 이고 ③ 진짜 반려 100% 면 0, 아니면 1.
"""
import importlib.util
import json
import os
import re
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, R)
from s2pipe import plan관문 as G   # noqa: E402

W = os.path.expanduser("~/Desktop/스케치코미디")
옛길 = sys.argv[sys.argv.index("--옛판") + 1] if "--옛판" in sys.argv else None
시리즈 = [a for a in sys.argv[1:] if not a.startswith("--") and a != 옛길] or ["루키치", "점심이네"]
옛 = None
if 옛길:
    import importlib.machinery
    로더 = importlib.machinery.SourceFileLoader("옛plan관문", 옛길)   # 확장자가 .py 가 아니어도(수리 전 사본) 읽는다
    spec = importlib.util.spec_from_loader("옛plan관문", 로더)
    옛 = importlib.util.module_from_spec(spec)
    로더.exec_module(옛)
옮김 = 40.0                         # ③ 모의 — 이만큼 넘게 옮겨야 «다른 장면»


def 편들():
    out = []
    for f in sorted(os.listdir(os.path.join(W, "projects"))):
        m = re.match(r"(.+?)(\d+)\.json$", f)
        if m and m[1] in 시리즈:
            out.append(f[:-5])
    return sorted(out, key=lambda s: (re.match(r"\D+", s)[0], int(re.search(r"\d+", s)[0])))


def 파악(slug):
    접두 = re.match(r"\D+", slug)[0]
    p = os.path.join(W, "배치로그", "agy파악" if 접두 == "싱글" else f"agy파악_{접두}", f"{slug}.md")
    return G.파악읽기(p)


def 설명시각(mod, pj, 큐, 카드줄, 파):
    kw = {"카드줄": 카드줄} if mod is G else {}
    bad, _w, 값 = mod.검사(pj, 큐, 파, None, "", make도=False, **kw)
    return [g for d, g in bad if d == "설명시각"], 값


def 그안에(대사, t0, t1, 줄들):
    """대사가 [t0−3, t1+2] 안에 시작하는 줄(1~3줄 이음)에 있는가 — 모의 자리에 같은 대사가 또 있으면(되풀이) 모의로 못 쓴다."""
    안줄 = [c for c in 줄들 if t0 - 6.0 <= c[0] <= t1 + 3.0]
    f = G.대사찾기(대사, [t0], 안줄, 창=1e9, 기준=0.6) if 안줄 else None
    return f is not None and t0 - 3.0 <= f[0] <= t1 + 2.0


def 모의(pj, dur, 큐, 카드줄):
    """최종본 조각을 하나씩 다른 장면으로 옮긴 모의 plan 들 — [(이름, 모의 proj)]."""
    out = []
    말 = G._말큐(큐)
    segs = [s for s in pj.get("segments", []) if s.get("keep", True)]
    for i, s in enumerate(segs):
        if len(G.뗀((s.get("첫대사") or "").replace("○", ""))) < 4:
            continue
        길이 = s["t1"] - s["t0"]
        for d in (+옮김, -옮김, +옮김 * 2, -옮김 * 2):
            t0 = s["t0"] + d
            if t0 < 0 or t0 + 길이 > dur:
                continue
            첫 = re.sub(r"^\s*\[?\d{1,2}:\d{2}(?:[.:]\d+)?\]?\s*", "", (s.get("첫대사") or "").replace("○", ""))
            if 그안에(첫, t0, t0 + 길이, 말) or (카드줄 and 그안에(첫, t0, t0 + 길이, 카드줄)):
                continue
            m = json.loads(json.dumps(pj))
            ms = [x for x in m["segments"] if x.get("keep", True)]
            ms[i]["t0"], ms[i]["t1"] = round(t0, 2), round(t0 + 길이, 2)
            m["segments"] = [ms[i]]                     # 옮긴 조각 하나만 잰다(다른 조각 반려가 섞이지 않게)
            out.append((f"P{s.get('phase')}#{i} {d:+.0f}초", m))
            break
    return out


def 로그반려(slug):
    """2plan 로그의 1회차 설명시각 반려 줄 → [(t0, t1, 첫대사16자, 옛 전사 시각)]."""
    p = os.path.join(W, "배치로그", f"{slug}_2plan.txt")
    if not os.path.exists(p):
        return []
    out = []
    for 줄 in open(p, encoding="utf-8"):
        if "[설명시각]" not in 줄:
            continue
        for m in re.finditer(r"P(\d) 원본 ([\d.]+)~([\d.]+)초의 첫대사 «([^»]*)» 는 전사에서 ([\d.]+)초", 줄):
            out.append((int(m[1]), float(m[2]), float(m[3]), m[4], float(m[5])))
    return out


합 = {"최종조각": 0, "최종가짜": 0, "최종가짜옛": 0, "최종편": 0, "최종편옛": 0, "초안가짜": 0, "초안가짜옛": 0,
     "모의": 0, "모의잡음": 0, "모의잡음옛": 0, "시계카드": 0, "시계전사": 0, "로그": 0, "로그남음": 0, "회귀편": []}
남은가짜, 놓친모의, 로그표 = [], [], []
for slug in 편들():
    pj = json.load(open(os.path.join(W, "projects", f"{slug}.json"), encoding="utf-8"))
    sid = pj["source"]["id"]
    큐 = G.큐읽기(os.path.join(W, "work", f"{sid}.ko.vtt"))
    if not 큐:
        continue
    카드줄 = G.카드줄읽기(os.path.join(W, "work", f"{sid}.mp4"), 만들기=False)
    파 = 파악(slug)
    dur = float(pj["source"].get("dur") or 9999)
    # ① 최종본
    새, 값 = 설명시각(G, pj, 큐, 카드줄, 파)
    합["최종조각"] += sum(1 for s in pj.get("segments", []) if s.get("keep", True) and len(G.뗀(s.get("첫대사") or "")) >= 4)
    합["최종가짜"] += 값.get("첫대사어긋남", 0)
    합["최종편"] += bool(새)
    합["시계카드"] += 값.get("첫대사시계", {}).get("카드", 0)
    합["시계전사"] += 값.get("첫대사시계", {}).get("전사", 0)
    if 새:
        남은가짜.append((slug, 새[0][:300]))
    if 옛:
        o, o값 = 설명시각(옛, pj, 큐, None, 파)
        합["최종가짜옛"] += o값.get("첫대사어긋남", 0)
        합["최종편옛"] += bool(o)
        # ⑦ 밖 검사 회귀 — 대사찾기를 같이 쓰는 값
        for k in ("나레덮음", "훅중복"):
            합.setdefault(f"{k}옛", 0)
            합.setdefault(f"{k}새", 0)
            합[f"{k}옛"] += o값.get(k) or 0
            합[f"{k}새"] += 값.get(k) or 0
        for k in ("찾음", "빠짐", "묶음통째빠짐"):
            합.setdefault(f"꼭남길{k}옛", 0)
            합.setdefault(f"꼭남길{k}새", 0)
            합[f"꼭남길{k}옛"] += (o값.get("꼭남길") or {}).get(k, 0)
            합[f"꼭남길{k}새"] += (값.get("꼭남길") or {}).get(k, 0)
        다른 = [k for k in ("나레덮음", "꼭남길", "셋업", "결말", "훅중복") if json.dumps(값.get(k)) != json.dumps(o값.get(k))]
        if 다른:
            합["회귀편"].append(f"{slug}: " + ", ".join(f"{k} {o값.get(k)}→{값.get(k)}" for k in 다른))
    # ② 초안
    pp = os.path.join(W, "projects", f"{slug}.json.plan원본")
    if os.path.exists(pp):
        cj = json.load(open(pp, encoding="utf-8"))
        합["초안가짜"] += 설명시각(G, cj, 큐, 카드줄, 파)[1].get("첫대사어긋남", 0)
        if 옛:
            합["초안가짜옛"] += 설명시각(옛, cj, 큐, None, 파)[1].get("첫대사어긋남", 0)
            # 초안에서 잡던 다른 반려(나레덮음·결말누락·로고결말·훅중복)를 그대로 잡는가 — 대사찾기·시계를 같이 쓴다
            새딱 = sorted({d for d, _g in G.검사(cj, 큐, 파, None, "", make도=False, 카드줄=카드줄)[0] if d != "설명시각"})
            옛딱 = sorted({d for d, _g in 옛.검사(cj, 큐, 파, None, "", make도=False)[0] if d != "설명시각"})
            합.setdefault("초안다른반려옛", 0)
            합.setdefault("초안다른반려새", 0)
            합["초안다른반려옛"] += len(옛딱)
            합["초안다른반려새"] += len(새딱)
            if 새딱 != 옛딱:
                합.setdefault("초안다른반려바뀜", []).append(f"{slug}: {옛딱}→{새딱}")
    # ③ 모의 틀린 plan
    for 이름, m in 모의(pj, dur, 큐, 카드줄):
        합["모의"] += 1
        잡 = bool(설명시각(G, m, 큐, 카드줄, 파)[0])
        합["모의잡음"] += 잡
        if not 잡:
            놓친모의.append(f"{slug} {이름} «{m['segments'][0].get('첫대사', '')[:20]}»")
        if 옛:
            합["모의잡음옛"] += bool(설명시각(옛, m, 큐, None, 파)[0])
    # ④ 옛 2plan 로그 반려 줄
    for ph, t0, t1, 첫, 옛시각 in 로그반려(slug):
        m = {"segments": [{"phase": ph, "t0": t0, "t1": t1, "첫대사": 첫, "keep": True}], "source": pj["source"]}
        남 = bool(설명시각(G, m, 큐, 카드줄, None)[0])
        fc = G.대사찾기(첫, [t0], 카드줄, 창=max(60.0, t1 - t0 + 30)) if 카드줄 else None
        합["로그"] += 1
        합["로그남음"] += 남
        로그표.append(f"{slug:10s} P{ph} {t0:6.1f}~{t1:6.1f} «{첫[:16]}» 옛전사 {옛시각:6.1f} · 카드 "
                    f"{(f'{fc[0]:6.1f}({fc[2]:.2f})' if fc else '  없음    ')} → {'반려' if 남 else '통과'}")

print("④ 옛 2plan 로그의 설명시각 반려 줄 — 새 관문 판정(카드 시각과 함께)")
for 줄 in 로그표:
    print("  " + 줄)
print(f"\n① 납품 최종본 — 첫대사 있는 조각 {합['최종조각']} (카드 시계 {합['시계카드']} · 전사 시계 {합['시계전사']})")
print(f"   설명시각 가짜 반려: 새 {합['최종가짜']}조각/{합['최종편']}편" + (f" · 옛 {합['최종가짜옛']}조각/{합['최종편옛']}편" if 옛 else ""))
for slug, g in 남은가짜[:20]:
    print(f"     남음 {slug}: {g}")
print(f"② plan 초안 설명시각 반려: 새 {합['초안가짜']}" + (f" · 옛 {합['초안가짜옛']}" if 옛 else ""))
if 옛:
    print(f"   초안의 다른 반려(편×종류): 옛 {합.get('초안다른반려옛', 0)} → 새 {합.get('초안다른반려새', 0)}")
    for x in 합.get("초안다른반려바뀜", []):
        print("     바뀜 " + x)
print(f"③ 모의 틀린 plan(조각을 {옮김:.0f}초 넘게 다른 장면으로): {합['모의']}개 중 새 {합['모의잡음']} 잡음"
      + (f" · 옛 {합['모의잡음옛']}" if 옛 else ""))
for x in 놓친모의[:20]:
    print(f"     놓침 {x}")
print(f"④ 옛 로그 반려 줄 {합['로그']}개 중 새 관문도 반려 {합['로그남음']}")
if 옛:
    print(f"⑦ 밖 검사 값이 바뀐 편 {len(합['회귀편'])} — 합계(옛→새): 나레덮음 {합.get('나레덮음옛')}→{합.get('나레덮음새')} · "
          f"훅중복 {합.get('훅중복옛')}→{합.get('훅중복새')} · 꼭남길 찾음 {합.get('꼭남길찾음옛')}→{합.get('꼭남길찾음새')} · "
          f"빠짐 {합.get('꼭남길빠짐옛')}→{합.get('꼭남길빠짐새')} · 묶음통째빠짐 {합.get('꼭남길묶음통째빠짐옛')}→{합.get('꼭남길묶음통째빠짐새')}"
          " (납품 최종본이라 빠짐·덮음은 줄수록 가짜가 준 것)")
    for x in 합["회귀편"][:200 if "--자세히" in sys.argv else 15]:
        print("     " + x)
ok = 합["최종가짜"] == 0 and 합["모의잡음"] == 합["모의"]
print("\n판정:", "통과" if ok else "미통과")
sys.exit(0 if ok else 1)
