#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""나레 자막 줄바꿈 금지 패턴 전수 검사 — 규칙은 `설계/한국어_줄바꿈규칙.md`.

  판정은 형태소 분석기 없이 어휘 목록 + 어절 모양으로만 한다. 확정(ⓑⓒⓔ)과 의심(ⓐⓓ)을 나눠 센다.
  게이트 `G-줄바꿈` 후보의 원형(2026-08-17 진단용). 진단 결과는 `설계/진단일지.md` 20절.

사용: python 서버/runner/줄바꿈검사.py <timeline.json> [결과.json]
"""
import io, json, re, sys

TL_PATH = sys.argv[1] if len(sys.argv) > 1 else "C:/Users/user/Desktop/youstudio_work/fulltime/subtitle/timeline.json"
tl = json.load(io.open(TL_PATH, encoding="utf-8"))
nar = [c for c in tl["cues"] if c["lane"] == "nar"]

# ── 어휘 목록 ───────────────────────────────────────────────────────────────
JOSA = ["은", "는", "이", "가", "을", "를", "에", "에서", "에게", "으로", "로", "와", "과", "도", "만", "까지",
        "부터", "처럼", "보다", "의", "라도", "조차", "마저", "이나", "나", "밖에", "대로", "께서", "한테", "라고", "이라고"]
# 의존명사·위치명사 — 앞말에 붙어야 뜻이 서는 말
BOUND = ["것", "게", "거", "수", "줄", "바", "데", "뿐", "채", "척", "만큼", "따름", "터", "때", "안", "속", "앞",
         "뒤", "위", "아래", "옆", "사이", "동안", "중", "밖", "무렵", "까닭", "등", "편", "쪽", "님", "덕분", "탓", "대신"]
DET = ["새", "그", "이", "저", "첫", "온", "전", "각", "여러", "모든", "어떤", "무슨", "웬", "딴", "별", "온갖", "한", "두", "세"]
# 종결어미(지무비체) — 이 뒤는 좋은 분할점
END = ["습니다", "ㅂ니다", "니다", "죠", "요", "다", "까", "래", "군요", "네요", "거든요"]
# 연결어미 — 절 경계(이 뒤도 괜찮은 분할점)
CONN = ["고", "지만", "는데", "은데", "어서", "아서", "니까", "면서", "며", "다가", "거나", "든지", "도록", "게", "려고", "자"]

def 어절(s):
    return [w for w in re.split(r"\s+", s.strip()) if w]

def 조사시작(w):
    """줄이 조사/의존명사로 시작하는가 — 붙은 조사까지 감싸서 본다"""
    core = re.sub(r"[.!?…]+$", "", w)
    for j in sorted(JOSA, key=len, reverse=True):
        if core == j:
            return f"조사 「{j}」 단독"
    for b in sorted(BOUND, key=len, reverse=True):
        if core == b or re.fullmatch(re.escape(b) + "(" + "|".join(sorted(JOSA, key=len, reverse=True)) + ")", core):
            return f"의존·위치명사 「{b}」(으)로 시작"
    return None

def 종결로끝(w):
    core = re.sub(r"[.!?…]+$", "", w)
    return any(core.endswith(e) for e in END)

def 연결로끝(w):
    core = re.sub(r"[.!?…]+$", "", w)
    return any(core.endswith(c) for c in CONN)

def 조사로끝(w):
    core = re.sub(r"[.!?…]+$", "", w)
    return any(core.endswith(j) for j in sorted(JOSA, key=len, reverse=True))

def 맨명사끝(w):
    """조사도 어미도 없이 끝난 어절 = 명사구가 아직 안 끝났을 가능성"""
    core = re.sub(r"[.!?…]+$", "", w)
    if not core or not re.search(r"[가-힣]$", core):
        return False
    return not (종결로끝(w) or 연결로끝(w) or 조사로끝(w))

# ── 블록별로 줄을 모아 인접 쌍을 본다 ────────────────────────────────────────
blocks = {}
for c in nar:
    blocks.setdefault(c["ref"], []).append(c)
for k in blocks:
    blocks[k].sort(key=lambda c: c["t0"])

rows = []
for ref, lines in blocks.items():
    for i, c in enumerate(lines):
        ws = 어절(c["text"])
        bad = []
        # ⓒ 한두 글자 조각
        core = re.sub(r"[.!?…\s]+", "", c["text"])
        if len(core) <= 3:
            bad.append(("ⓒ", f"조각 {len(core)}자"))
        # ⓑ 이 줄이 조사·의존명사로 시작 (앞 줄이 있을 때만 = 분할된 것)
        if i > 0 and ws:
            r = 조사시작(ws[0])
            if r:
                bad.append(("ⓑ", r))
        # ⓐ/ⓓ 앞 줄 끝 ↔ 이 줄 시작
        if i > 0 and ws and 어절(lines[i - 1]["text"]):
            prev = 어절(lines[i - 1]["text"])[-1]
            pcore = re.sub(r"[.!?…]+$", "", prev)
            if pcore in DET:
                bad.append(("ⓓ", f"관형사 「{pcore}」 뒤에서 끊김"))
            elif 맨명사끝(prev):
                # 다음 줄 첫 어절이 명사처럼 보이면 명사구 절단 의심
                bad.append(("ⓐ", f"조사·어미 없는 「{pcore}」 뒤에서 끊김 → 다음 줄 「{ws[0]}」"))
        # ⓔ 어절 중간 절단
        if re.search(r"[가-힣]$", c["text"]) is None and c["text"].endswith("-"):
            bad.append(("ⓔ", "어절 중간"))
        prev_txt = lines[i - 1]["text"] if i > 0 else None
        # 왜 여기서 끊겼나 — 저자가 찍은 「..」 자리인가, 분할기가 길이 때문에 자른 자리인가
        원인 = None if prev_txt is None else ("저자 .." if re.search(r"\.\.!?$", prev_txt.strip()) else "길이")
        rows.append({"ref": ref, "i": i, "n_lines": len(lines), "t0": c["t0"], "t1": c["t1"], "text": c["text"],
                     "prev": prev_txt, "원인": 원인, "bad": bad})

split_rows = [r for r in rows if r["n_lines"] > 1]
확정 = [r for r in rows if any(t in ("ⓑ", "ⓒ", "ⓓ", "ⓔ") for t, _ in r["bad"])]
의심 = [r for r in rows if any(t == "ⓐ" for t, _ in r["bad"]) and r not in 확정]
print(f"나레 큐 {len(nar)}개 · 블록 {len(blocks)}개 · 여러 줄로 쪼개진 블록의 줄 {len(split_rows)}개")
print(f"확정 위반(ⓑⓒⓓⓔ) {len(확정)}건 · 명사구 절단 의심(ⓐ) {len(의심)}건")
print()
for tag, name in (("ⓐ", "명사구 내부 절단(의심)"), ("ⓑ", "조사·의존명사로 시작하는 줄"), ("ⓒ", "한두 글자 조각"), ("ⓓ", "수식어와 피수식어 분리"), ("ⓔ", "어절 중간 절단")):
    hits = [r for r in rows if any(t == tag for t, _ in r["bad"])]
    print(f"── {tag} {name}: {len(hits)}건")
    for r in hits:
        why = " · ".join(d for t, d in r["bad"] if t == tag)
        prev = f"「{r['prev']}」 | " if r["prev"] else ""
        print(f"   [{r['원인'] or '-'}] {r['ref']} {r['t0']:7.2f}s  {prev}「{r['text']}」   ← {why}")
    print()

# ── 원인별 집계: 분할기가 길이 때문에 자른 자리에서 난 위반이 '우리가 고칠 것' ──
길이위반 = [r for r in rows if r["bad"] and r["원인"] == "길이"]
저자위반 = [r for r in rows if r["bad"] and r["원인"] == "저자 .."]
print(f"── 원인별: 분할기(길이) {len(길이위반)}건 · 저자가 찍은 「..」 자리 {len(저자위반)}건")
print(f"   길이 때문에 끊긴 자리 총 {len([r for r in rows if r['원인'] == '길이'])}곳 중 위반 {len(길이위반)}곳")
for r in 길이위반:
    print(f"   · {r['ref']} {r['t0']:7.2f}s 「{r['prev']}」 | 「{r['text']}」  {[t for t,_ in r['bad']]}")

if len(sys.argv) > 2:
    json.dump(rows, io.open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
