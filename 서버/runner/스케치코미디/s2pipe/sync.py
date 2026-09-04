# -*- coding: utf-8 -*-
"""대사 자막을 **ASR(단어 전사) 기준으로 다시 짠다** — 시각·커버리지는 ASR, 문구는 모델.

    python -m s2pipe.asr  projects/<편>.json     먼저 (★ASR 요금)
    python -m s2pipe.sync projects/<편>.json     그다음 (EvoLink 무료 경로 1회)

■ 왜 이 구조인가 (2026-09-03 Deep02 사건으로 전면 개정)
    이전엔 「모델이 쓴 자막표」를 원천으로 두고 시각만 ASR 에 맞췄다. 그런데 표가
    통째로 틀린 편에서 두 결함이 같이 터졌다 — ① 표에 없는 대사(14.4·16.7초)는
    자막이 **아예 없고**, ② 의역이라 글자 정렬 닻이 약해 보간 잔차가 ±2초 남았다.
    근본 원인은 원천이 추정이라는 것. 그래서 뒤집는다:
      · **시각·줄 나눔·커버리지 = subs_asr** (Speechmatics 단어 실측 — 참값)
      · **문구 = 모델이 영상을 보며 ASR 줄을 제자리에서 다듬는다** (오인식 교정 —
        「잭팟→책팟」 실측이 있어 ASR 문구를 그대로 쓰지 않는다. 줄 수·순서 불변을
        기계로 강제하고, 다듬기가 실패하면 ASR 원문에서 구두점만 걷어 쓴다)
      · **괄호 효과자막**(`(샤프 탁)` 류 — 소리에 없음)만 옛 모델 표에서 가져오되,
        강근거 글자 정렬로 매핑한 시각에 놓는다.

■ 다시 돌려도 같은 결과 — 원천이 subs_asr·subs_before_sync(옛 모델 표)라 몇 번을
    돌려도 이미 옮긴 값에 다시 맞추는 일이 없다.
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CLEAN = re.compile(r"[\s.,!?~…()（）\[\]\"'·]")
구두점 = re.compile(r"[.,…·]")          # 채널 절대규칙 — 마침표·쉼표 금지 (? ! 허용)


def 정돈(text):
    return re.sub(r"\s+", " ", 구두점.sub("", text)).strip()


def 추임새다(w):
    """웃음·감탄 발성 — 자막 문구에 없는 소리. 시각 계산에서 뺀다.
       (2026-09-03 실측: 「하하하…」 단어에 첫 줄 시각이 붙어 웃음 동안 자막이 떴다)"""
    s = CLEAN.sub("", w if isinstance(w, str) else (w.get("w") or ""))
    # {2,}→{1,} (2026-09-04): 웃음이 「하 하」 처럼 한 글자씩 전사되면 빠져나갔다
    return bool(re.fullmatch(r"[하호흐히헤]{1,}|[아어오우음야에]", s))


def 작표(words, slug, logline):
    """★2026-09-03 구조 — 모델은 «몇 번 단어부터 한 줄인지»(경계)와 문구만 고른다.
       각 줄의 시각은 무조건 그 시작 단어의 실측 시각이다 — 모델이 시각을 틀릴 방법이 없다.
       (기계 휴리스틱은 «…다음 / 주까지야» 같은 어중간한 경계를 남겼고, 모델 자유작표는
        시각·커버리지를 통째로 틀렸다 — 각자 잘하는 것만 맡긴다.)
       반환: [{"t", "text"}] 또는 None(실패 — 호출부가 쉼 기준 묶음으로 폴백)."""
    말 = [(i, w) for i, w in enumerate(words) if w.get("type") != "punctuation"]
    try:
        import base64
        from s2pipe import gem
        from s2pipe.cfg import CFG as _C
        models = _C.get("gemini", {}).get("models", ["gemini-3.5-flash"])
        cut = os.path.join(HERE, _C["paths"]["work"], slug, "cut.mp4")
        목록 = " ".join(f"{i}:{w['w']}({w['t']:.1f})" for i, w in 말)
        # ★줄 구성 규칙(2026-09-03 사장님 지시 — 중요): 최대 14자·의미 단위 절대 준수.
        #   근거 = 설계/한국어_줄바꿈규칙.md (국어원 어문규범 2·41·42항 + Netflix + 실무).
        prompt = (f"숏폼({logline})의 단어 전사다. 형식 = 번호:단어(초).\n"
                  f"영상을 보고 자막 줄을 짜라 — 각 줄은 «시작 단어 번호(i)»와 «문구(text)»만 낸다.\n"
                  f"★한 줄은 공백 포함 **최대 14자**다. 그리고 반드시 **의미 단위로 떨어져야** 한다:\n"
                  f"- 끊기 좋은 자리 순서: 문장 끝 > 연결어미 뒤(~고 ~는데 ~어서 ~니까 ~면서) >\n"
                  f"  부사어 뒤 > 체언+조사 뒤. 이 자리들로 14자 안에 들어오게 나눠라.\n"
                  f"- 금지: 조사·어미·의존명사로 줄을 시작하는 것 / 수식어와 피수식어를 가르는 것\n"
                  f"  (「새빨간 ⏎ 장미」 금지) / 명사구 한중간 절단 / 14자를 맞추려 말이 안 되게 자르는 것\n"
                  f"  — 애매하면 더 짧게 나누는 쪽이 낫다.\n"
                  f"- 추임새·웃음·하품 소리(아, 어, 하하 등)는 **문구에서 빼고** 줄 경계로도 쓰지 마라.\n"
                  f"- 문구는 그 줄 구간의 말을 다듬은 것 — 오인식 교정, 뜻·말투 유지. 없는 말 금지.\n"
                  f"- i 는 오름차순, 첫 줄은 i={말[0][0]}. 마침표·쉼표·말줄임표 금지(? ! 허용).\n"
                  f"JSON 만, 공백 없이 한 줄: {{\"lines\":[{{\"i\":번호,\"text\":\"문구\"}},...]}}\n\n{목록}")
        vid_b64 = base64.b64encode(open(gem.shrink_for_inline(cut), "rb").read()).decode()

        def 한번(추가=""):
            payload = {"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "video/mp4", "data": vid_b64}},
                {"text": prompt + 추가}]}],
                "generationConfig": {"maxOutputTokens": 8000, "responseMimeType": "application/json"}}
            txt, _r, _m = gem.ask(payload, models, timeout=600)
            rows = json.loads(txt)["lines"]
            out, last = [], -1
            for r in rows:
                i, tx = int(r["i"]), 정돈(str(r["text"]))
                assert 0 <= i < len(words), f"단어 번호 밖: {i}"
                if i <= last or not tx:
                    continue                               # 역행·빈 문구는 앞 줄에 흡수
                out.append({"i": i, "t": round(float(words[i]["t"]), 2), "text": tx})
                last = i
            assert 8 <= len(out) <= 90, f"줄 수 이상: {len(out)}"
            first_i = int(rows[0]["i"])
            건너뜀 = [w for j, w in 말 if j < first_i]
            assert all(추임새다(w["w"]) for w in 건너뜀), "첫 발화가 자막 밖이다"
            return out

        try:
            out = 한번()
        except Exception as e1:
            # ★한 번의 일시 오류(JSON 깨짐·타임아웃)로 의미 단위를 모르는 폴백에 떨어지면
            #   «것» 고아 같은 줄이 나온다(2026-09-04 실측) — 폴백 전에 1회 재시도한다.
            print(f"  모델 작표 1차 실패({str(e1)[:120]}) — 재시도 1회")
            out = 한번()
        긴줄 = [d["text"] for d in out if len(d["text"]) > 14]
        if 긴줄:                                            # ★14자 게이트 — 1회 재요청
            print(f"  14자 초과 {len(긴줄)}줄 — 의미 단위 재분할을 다시 시킨다")
            out = 한번("\n\n★직전 답에서 다음 줄이 14자를 넘었다 — 의미 단위를 지키며 더 잘게 나눠라:\n"
                       + "\n".join(f"- {t}({len(t)}자)" for t in 긴줄[:10]))
        # 그래도 넘는 줄은 기계 최후수단 — 가운데 가까운 어절 경계에서 절반씩 (경고 남김)
        고침 = []
        for d in out:
            고침.append(d)
            while len(고침[-1]["text"]) > 14 and " " in 고침[-1]["text"]:
                cur = 고침.pop()
                mid, best = len(cur["text"]) // 2, None
                for m in (j for j, ch in enumerate(cur["text"]) if ch == " "):
                    if best is None or abs(m - mid) < abs(best - mid):
                        best = m
                앞, 뒤 = cur["text"][:best].strip(), cur["text"][best:].strip()
                span = [w for j, w in 말 if cur["i"] <= j]
                누적, t뒤 = 0, cur["t"] + 0.8
                for w in span:
                    누적 += len(w["w"])
                    if 누적 >= len(앞.replace(" ", "")):
                        t뒤 = w["e"]
                        break
                print(f"  ★기계 절반 분할(모델이 14자 못 맞춤): 「{cur['text']}」")
                고침.append({"i": cur["i"], "t": cur["t"], "text": 앞})
                고침.append({"i": cur["i"], "t": round(t뒤, 2), "text": 뒤})
        # ★시작 스냅 — 줄이 웃음·추임새 단어에서 시작하면(문구는 그 소리로 시작 안 함)
        #   시각을 첫 실제 말 단어로 민다 (2026-09-03 「하하하」에 첫 줄이 붙은 실측)
        말사전 = dict(말)
        for d in 고침:
            j, 헤드 = d["i"], CLEAN.sub("", d["text"])[:1]
            for _ in range(10):
                w = 말사전.get(j)
                if w is None or not 추임새다(w["w"]) or CLEAN.sub("", w["w"])[:1] == 헤드:
                    break
                j += 1
                while j < len(words) and words[j].get("type") == "punctuation":
                    j += 1
            if j in 말사전:
                d["t"] = round(float(말사전[j]["t"]), 2)
        out = [{"t": d["t"], "text": d["text"]} for d in 고침]
        # 금지 패턴 ⓑ(조사·어미로 줄 시작) — 기계로 잡히는 것만 경고
        조사들 = {"은", "는", "이", "가", "을", "를", "에", "에서", "의", "도", "만",
                  "와", "과", "랑", "부터", "까지", "처럼", "보다", "한테", "에게"}
        for d in out:
            if d["text"].split()[0] in 조사들:
                print(f"  ★줄 첫머리가 조사다(금지 패턴 ⓑ): 「{d['text']}」 — 눈 확인 필요")
        return out
    except Exception as e:
        print("★모델 작표 실패(재시도 포함) — 쉼 기준 묶음(ASR 원문 14자)으로 간다:", str(e)[:200])
        return None


def 끝시각채우기(dlg, words, 쉼=0.7):
    """★자막 끝 = 말 끝 (2026-09-03 사장님: 대사가 끝나면 자막도 딱 사라져야 한다 — 이것도 싱크다).
       줄 끝 = 줄 시작부터 **이어 말한 구간**(단어 사이 쉼 < 0.7s)의 마지막 단어 끝.
       ★쉼 뒤에 오는 추임새·웃음·하품 소리(「아 아」로 전사됨)는 끝을 못 늘린다 —
       12.3초 하품까지 자막이 남았던 실측(2026-09-03 캡쳐) 후 개정.
       구간에 단어가 없으면(괄호 효과자막) 2.5초 기본."""
    말 = [w for w in words if w.get("type") != "punctuation"]
    dlg.sort(key=lambda x: x["t"])
    for k, d in enumerate(dlg):
        nxt = dlg[k + 1]["t"] if k + 1 < len(dlg) else 10 ** 9
        내부 = [w for w in 말 if d["t"] - 0.05 <= w["t"] < nxt]
        if not 내부:
            d["t1"] = round(d["t"] + 2.5, 2)
            continue
        # ① 쉼 기준 — 줄 시작부터 이어 말한 구간의 끝
        끝쉼 = float(내부[0]["e"])
        for w in 내부[1:]:
            if float(w["t"]) - 끝쉼 >= 쉼:
                break
            끝쉼 = max(끝쉼, float(w["e"]))
        # ② 글자수 기준 — ★문구(추임새 제외)가 소화하는 만큼의 단어까지만 (2026-09-03 재발:
        #   하품 「아 아」가 대사 직후 0.4s 만에 이어져 쉼 기준을 통과해 끝을 13.5s 까지 늘렸다.
        #   문구 글자수를 다 채운 단어에서 끝낸다 — 그 뒤 발성은 문구에 없는 소리다.)
        알맹이 = " ".join(t for t in d["text"].split() if not 추임새다(t))
        목표 = len(re.sub(r"[\s?!()]", "", 알맹이))
        끝글, 누적 = None, 0
        for w in 내부:
            if 추임새다(w["w"]):
                continue                                  # 웃음·감탄은 글자수에 안 센다
            누적 += len(CLEAN.sub("", w["w"]))
            if 목표 and 누적 >= 목표 * 0.9:
                끝글 = float(w["e"])
                break
        끝 = min(끝쉼, 끝글) if 끝글 is not None else 끝쉼
        d["t1"] = round(max(끝, d["t"] + 0.4), 2)


def main():
    if len(sys.argv) < 2:
        print("python -m s2pipe.sync projects/<편>.json [--끝만]")
        return 1
    pj = sys.argv[1] if os.path.isabs(sys.argv[1]) else os.path.join(HERE, sys.argv[1])
    proj = json.load(open(pj, encoding="utf-8"))

    if "--끝만" in sys.argv:
        # 무료 수리 모드 — 문구·시작 시각은 그대로 두고 줄 끝만 단어 실측으로 다시 단다
        words = proj.get("asr_words") or []
        assert words, "asr_words 가 없다"
        dlg = [s for s in proj["subs"] if s.get("kind") != "narr"]
        끝시각채우기(dlg, words)
        json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"줄 끝 실측 부여 {len(dlg)}줄 · 저장: {pj}")
        return 0

    words = proj.get("asr_words") or []
    asr_lines = proj.get("subs_asr") or []
    if not words or not asr_lines:
        print("ASR 결과가 없다 — 먼저 `python -m s2pipe.asr` 를 돌려라 (★요금)")
        return 1

    # 옛 모델 표 — 괄호 효과자막의 출처이자, 재실행 시 항상 같은 원천
    src = proj.get("subs_before_sync") or proj.get("subs", [])
    narr = [s for s in src if s.get("kind") == "narr"]
    model_dlg = sorted([dict(s) for s in src if s.get("kind") != "narr"], key=lambda x: x["t"])

    # ── ① 대사 자막 — 시각 = 시작 단어 실측, 경계·문구 = 모델 (실패 시 쉼 기준 묶음) ──
    # ★작표 캐시 (2026-09-04 실측: 재실행마다 모델이 새로 굴려 «사보타지»→«서버타지» 퇴행.
    #   입력(단어·로그라인)이 같으면 지난 결과를 그대로 쓴다 — 게이트만 다시 돈다.)
    import hashlib as _hl
    작표키 = _hl.md5((json.dumps([w["w"] for w in words], ensure_ascii=False)
                      + proj.get("logline", "")).encode()).hexdigest()[:12]
    캐시 = proj.get("_작표캐시") or {}
    if 캐시.get("key") == 작표키 and 캐시.get("lines"):
        dlg = [dict(x) for x in 캐시["lines"]]
        print(f"  작표 캐시 재사용({작표키}) — 입력이 같아 지난 경계·문구 유지")
    else:
        dlg = 작표(words, proj["slug"], proj.get("logline", ""))
        if dlg is not None:
            proj["_작표캐시"] = {"key": 작표키, "lines": [dict(x) for x in dlg]}
    출처 = "모델 경계·문구 + 단어 실측 시각"
    if dlg is None:
        출처 = "쉼 기준 묶음(ASR 원문 14자)"
        from s2pipe import asr as _asr
        dlg = [{"t": round(float(l["t"]), 2), "text": 정돈(l["text"])}
               for l in _asr.to_lines(words, 14) if 정돈(l["text"])]
    print(f"대사 자막 {len(dlg)}줄 — {출처}")

    # ── ② 괄호 효과자막 — 옛 모델 표에서 가져와 강근거 정렬로 시각 매핑 ────────
    괄호 = [s for s in model_dlg if s.get("text", "").lstrip().startswith("(")]
    if 괄호:
        achars, atimes = [], []
        for w in words:
            for ch in CLEAN.sub("", w.get("w") or w.get("text") or ""):
                achars.append(ch)
                atimes.append(w["t"])
        sub_s, heads = "", []
        for s in model_dlg:
            heads.append(len(sub_s))
            sub_s += CLEAN.sub("", s.get("text", ""))
        blocks = [b for b in difflib.SequenceMatcher(None, sub_s, "".join(achars),
                                                     autojunk=False).get_matching_blocks() if b.size > 0]

        def at(pos):
            for a, b, size in blocks:
                if a <= pos < a + size and size >= 8:      # 8자 이상 = 우연일 수 없는 닻
                    return atimes[b + (pos - a)]
            return None
        닻 = [(model_dlg[i]["t"], t) for i in range(len(model_dlg))
              if (t := at(heads[i])) is not None]
        def 매핑(t원):
            if not 닻:
                return t원
            앞 = [(o, n) for o, n in 닻 if o <= t원]
            뒤 = [(o, n) for o, n in 닻 if o > t원]
            if 앞 and 뒤:
                (o0, n0), (o1, n1) = 앞[-1], 뒤[0]
                r = (t원 - o0) / (o1 - o0) if o1 > o0 else 0.5
                return n0 + r * (n1 - n0)
            base = (앞[-1] if 앞 else 뒤[0])
            return t원 + (base[1] - base[0])
        for s in 괄호:
            새 = round(매핑(s["t"]), 2)
            print(f"  괄호 자막 {s['t']:6.2f} → {새:6.2f}  {s['text'][:20]}")
            dlg.append({"t": 새, "text": 정돈(s["text"]) or s["text"]})

    # 버린 모델 줄 보고 — 말로 실재하는 것은 ASR 줄이 이미 덮는다
    버림 = len(model_dlg) - len(괄호)
    if 버림:
        print(f"옛 모델 표의 대사 {버림}줄은 ASR 줄이 대신한다 (커버리지·시각 참값)")

    # ── ②b 6초 넘게 걸치는 줄 쪼개기 — 가사처럼 느린 발화는 한 줄이 10초를 덮는다(실측).
    #    자막 표시 최대(6초)를 넘는 구간은 넘친 첫 단어부터 ASR 원문으로 줄을 보강한다.
    dlg.sort(key=lambda x: x["t"])
    말들 = [w for w in words if w.get("type") != "punctuation"]
    보강 = []
    for k, d in enumerate(dlg):
        끝 = dlg[k + 1]["t"] if k + 1 < len(dlg) else 10 ** 9
        넘침 = [w for w in 말들 if d["t"] + 5.5 < w["t"] < 끝]
        from s2pipe import asr as _asr
        while 넘침:
            t0 = 넘침[0]["t"]
            그룹 = [w for w in 넘침 if w["t"] - t0 <= 5.5]
            for l in _asr.to_lines(그룹, 14):              # 보강 줄도 14자·쉼 기준
                tx = 정돈(l["text"])
                if tx:
                    보강.append({"t": round(float(l["t"]), 2), "text": tx})
            넘침 = [w for w in 넘침 if w["t"] - t0 > 5.5]
    if 보강:
        print(f"  6초 초과 줄 보강 {len(보강)}줄: " + " · ".join(f"{b['t']:.1f}s" for b in 보강))
        dlg += 보강

    # ── ②c 줄 끝 = 말 끝 실측 (2026-09-03 사장님) ─────────────────────────────
    끝시각채우기(dlg, words)

    # ── ③b 원본 전사 교차 대조 (2026-09-03 Deep03: 전화 너머 여자 대답이 컷 재전사에서
    #    통째로 빠져 자막이 없었다) — 원본(고음질) 전사 줄을 구간 매핑으로 컷 시각에 놓고,
    #    어떤 자막도 안 덮는 줄은 원본 전사 문구로 되살린다. 컷 전사가 못 들은 조용한
    #    말의 마지막 안전망이다.
    면제구간 = []                                   # 오인식 제거 구간 — 커버리지 게이트 면제
    try:
        from s2pipe.cfg import CFG as _C3
        vtt경로 = os.path.join(HERE, _C3["paths"]["work"], f"{proj['slug']}.ko.vtt")
        segs = [s for s in proj.get("segments", []) if s.get("keep")]
        if os.path.exists(vtt경로) and segs:
            그림, 누적 = [], 0.0
            for s in segs:
                그림.append((누적, s["t0"], s["t1"]))
                누적 += s["t1"] - s["t0"]
            def 컷시각(t원):
                for c0, o0, o1 in 그림:
                    if o0 - 0.01 <= t원 < o1:
                        return c0 + (t원 - o0)
                return None
            원줄 = []
            for b in open(vtt경로, encoding="utf-8").read().split("\n\n"):
                ls = b.strip().splitlines()
                if len(ls) >= 2 and "-->" in ls[0]:
                    h, m2, s2 = ls[0].split(" --> ")[0].split(":")
                    원줄.append((int(h) * 3600 + int(m2) * 60 + float(s2), ls[1]))
            복원 = []
            for t원, 글 in 원줄:
                tc = 컷시각(t원)
                깨끗 = 정돈(글)
                if tc is None or not 깨끗:
                    continue
                if all(추임새다(tok) for tok in 깨끗.split()):
                    continue
                덮임 = any(d["t"] - 0.8 <= tc <= d.get("t1", d["t"] + 6) + 0.3 for d in dlg)
                if not 덮임:
                    복원.append({"t": round(tc, 2), "text": 깨끗})
            for k, r in enumerate(복원):
                다음 = min([d["t"] for d in dlg if d["t"] > r["t"]] + [r["t"] + 2.0])
                r["t1"] = round(min(r["t"] + 2.0, max(다음 - 0.05, r["t"] + 0.6)), 2)
            if 복원:
                print(f"  ★컷 전사가 놓친 대사 {len(복원)}줄 — 원본 전사로 복원 (문구는 원본 전사 그대로):")
                for r in 복원:
                    print(f"     [{r['t']:.1f}~{r['t1']:.1f}s] {r['text'][:24]}")
                dlg += 복원
            # ★유령 자막 제거 (2026-09-04 Deep07 «참고로 이동네» — 컷 재전사가 배경 소음을
            #   말로 오인). 복원의 대칭: 컷 시각을 원본 시각으로 되매핑해, 원본(고음질)
            #   전사가 ±2.5s 안에 아무 말도 못 들은 줄은 유령으로 지운다. 괄호 효과자막은
            #   소리가 없는 게 정상이라 제외.
            def 원시각(tc):
                for c0, o0, o1 in 그림:
                    if c0 <= tc < c0 + (o1 - o0):
                        return o0 + (tc - c0)
                return None
            유령 = []
            for d in list(dlg):
                if d["text"].lstrip().startswith("("):
                    continue
                to = 원시각(d["t"])
                if to is None:
                    continue
                이웃 = [(t원, 글) for t원, 글 in 원줄 if abs(t원 - to) <= 3.0]
                if not 이웃:
                    유령.append(d)                       # 원본 전사엔 그 지점에 말이 없다
                    dlg.remove(d)
                    continue
                # ★문구 대조(2026-09-04 «참고로 이동네» — 작은 소리를 컷 전사가 전혀 다른
                #   문구로 오인). 원본(고음질) 전사와 글자가 거의 안 겹치면 오인식 — 뺀다.
                창글 = 정돈(" ".join(g for _t, g in 이웃))
                내글 = CLEAN.sub("", d["text"])
                if len(내글) >= 4:
                    # 포함 비율 — 줄 글자가 원본 창 안에서 얼마나 이어지는가 (짧은 줄 vs 긴 창
                    # 에서도 공정. quick_ratio 는 길이차에 눌려 정상 줄까지 지웠다 — 실측 14줄)
                    sm = difflib.SequenceMatcher(None, 내글, CLEAN.sub("", 창글), autojunk=False)
                    맞은 = sum(b.size for b in sm.get_matching_blocks())
                    if 맞은 / len(내글) < 0.8:
                        # ★지우지 않는다(2026-09-04 «권은비의 사보타지» 삭제 실측) — 원본 전사
                        #   «도» 오인할 수 있다(«거 냄비에 서버 타지»). 말은 있는데 문구가 안
                        #   닮은 줄(«양보 좀↔좋아» 한 단어 차이 0.71 실측 포함)은 ③c 중재로
                        #   회부한다. 삭제는 말 없는 유령만.
                        d["_분쟁원문"] = 창글.strip()[:40]
            if 유령:
                print(f"  ★유령/오인 자막 {len(유령)}줄 제거 — 원본 전사와 대조:")
                for g in 유령:
                    print(f"     [{g['t']:.1f}s] {g['text'][:24]}")
            # 제거 구간은 커버리지 게이트 면제(그 소리는 자막감이 아니라고 판정한 것)
            면제구간.extend((g["t"] - 0.2, g.get("t1", g["t"] + 2.0) + 0.2) for g in 유령)
    except Exception as e:
        print("★원본 전사 교차 대조 실패(복원 없이 진행):", str(e)[:60])

    # ── ③c 문구 갈림 중재 (2026-09-04 사장님 «전사는 무조건 스피치매틱스» — 제2 엔진
    #    (whisper) 금지. 근본은 이미 옆에 있었다: 린박스 전사.py 처럼 Speechmatics 에
    #    additional_vocab(낱말사전)을 보내면 고유명사를 그쪽으로 받아 적는다(s2pipe.asr).
    #    그래도 원본↔완성본 두 전사가 갈린 줄(③b 의 _분쟁원문)은 모델이 영상+로그라인으로
    #    중재해 문구를 확정한다. 갈림 = 못 믿을 곳 신호.)
    try:
        분쟁 = [(d, d["_분쟁원문"]) for d in dlg if d.get("_분쟁원문")]
        if 분쟁:
            from s2pipe.cfg import CFG as _C4
            cut4 = os.path.join(HERE, _C4["paths"]["work"], proj["slug"], "cut.mp4")
            print(f"  ★원본·완성본 전사가 갈린 줄 {len(분쟁)}건 — 모델이 영상·문맥으로 중재:")
            import base64 as _b64
            from s2pipe import gem as _gem
            models4 = _C4.get("gemini", {}).get("models", ["gemini-3.5-flash"])
            vb = _b64.b64encode(open(_gem.shrink_for_inline(cut4), "rb").read()).decode()
            목록 = "\n".join(f"- t={d['t']:.1f}s A안(완성본 전사)「{d['text']}」 B안(원본 전사)「{w[:40]}」"
                             for d, w in 분쟁)
            pr = (f"숏폼 영상이다(로그라인: {proj.get('logline', '')}).\n"
                  "아래 각 시각의 대사를 두 번의 전사(원본·완성본)가 다르게 들었다.\n"
                  "영상을 그 시각에서 직접 듣고(입모양·문맥 포함) 실제 대사를 판정하라.\n"
                  "- 고유명사(신곡명·이름·브랜드)는 로그라인·화면 표기를 따른다 — 전사 엔진은\n"
                  "  고유명사를 자주 엉뚱한 낱말로 쪼갠다(«사보타지»→«서버 타지» 실측).\n"
                  "- text 는 그 줄의 실제 말. A안·B안 중 맞는 쪽을 고르거나, 둘 다 틀리면 들리는 대로.\n"
                  "- 공백 포함 14자 이내, 뜻·말투 유지, 없는 말 금지. 확신이 없으면 A안 그대로.\n"
                  f"JSON 만: {{\"fixes\":[{{\"t\":시각,\"text\":\"문구\"}},...]}}\n\n{목록}")
            payload = {"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "video/mp4", "data": vb}}, {"text": pr}]}],
                "generationConfig": {"maxOutputTokens": 4000, "responseMimeType": "application/json"}}
            txt4, _r4, _m4 = _gem.ask(payload, models4, timeout=600)
            고정 = {round(float(f["t"]), 1): str(f["text"]).strip()
                    for f in json.loads(txt4).get("fixes", [])}
            정정 = 0
            for d, w in 분쟁:
                새 = 고정.get(round(d["t"], 1))
                if 새 and 새 != d["text"] and len(새) <= 20:
                    print(f"     [{d['t']:.1f}s] 「{d['text']}」 → 「{새}」")
                    d["text"] = 새
                    정정 += 1
            print(f"  [OK] 문구 갈림 중재 — 갈림 {len(분쟁)}건 · 정정 {정정}건")
        else:
            print("  [OK] 문구 갈림 중재 — 원본·완성본 전사 일치")
    except Exception as e:
        print("★문구 갈림 중재 실패(현재 문구 유지 — 눈 확인 필요):", str(e)[:120])
    for d in dlg:
        d.pop("_분쟁원문", None)

    # ── 문구교정 핀 (2026-09-04 — 화자교정과 같은 사상): 사장님이 귀로 확정한 문구는
    #    엔진·모델이 못 뒤집는다. proj["문구교정"] = {"<시각>": "<문구>"} — 재작표해도 이긴다.
    for 핀t, 핀글 in (proj.get("문구교정") or {}).items():
        핀tf = float(핀t)
        # 작표마다 줄 경계가 달라진다 — 시각이 줄 구간에 «겹치는» 줄을 찾고,
        # 확정 문구가 이미 들어 있으면 통과, 없으면 그 줄을 교체한다.
        후보줄 = [d for d in dlg
                  if d["t"] - 0.4 <= 핀tf <= d.get("t1", d["t"] + 2.0) + 0.4]
        if 후보줄:
            d = min(후보줄, key=lambda x: abs(x["t"] - 핀tf))
            if CLEAN.sub("", 핀글) in CLEAN.sub("", d["text"]):
                print(f"  [OK] 문구교정 핀 [{핀t}s] — 확정 문구가 이미 들어 있다: 「{d['text']}」")
            else:
                print(f"  ★문구교정 핀 적용: [{d['t']:.1f}s] 「{d['text']}」 → 「{핀글}」")
                d["text"] = 핀글
        else:
            print(f"  ★문구교정 핀 [{핀t}s] 에 맞는 줄이 없다 — 시각 확인 필요")

    # ── ③a 최종 관문 (2026-09-03 사장님 «왜 자꾸 반복되나» — 규칙을 경로마다 따로 걸었던 게
    #    원인) — 작표·괄호·보강·복원 어느 경로로 만들어졌든 **모든 대사 줄이 여기서 같은
    #    규칙을 통과한다.** 14자 초과는 가운데 가까운 어절 경계에서 쪼개고(시각은 글자수
    #    비례) 그래도 넘으면 저장을 막는다.
    최대 = 14
    관문 = []
    # 추임새 단독 줄(«아» 등)은 자막 가치가 없고 아모르 도구도 못 삼킨다(2026-09-03 Deep06)
    dlg = [d for d in dlg if not all(추임새다(tok) for tok in d["text"].split())]
    # ★기능어 고아 줄 병합 (2026-09-04 사장님 «것 이라는 자막이 혼자» — 모델 작표가
    #   실패하면 폴백(쉼 기준 묶음)이 의미 단위를 몰라 의존명사를 고아로 남겼다.
    #   생성 경로가 무엇이든 여기서 잡는다 — 규칙은 최종 관문 하나에.)
    from s2pipe.asr import 의존명사
    dlg.sort(key=lambda x: x["t"])
    병합후 = []
    for d in dlg:
        내글 = CLEAN.sub("", d["text"])
        if 병합후 and " " not in d["text"].strip() and 내글 in 의존명사:
            앞줄 = 병합후[-1]
            앞줄["text"] = (앞줄["text"] + " " + d["text"]).strip()   # 14자 초과는 아래 스택이 재분할
            if d.get("t1"):
                앞줄["t1"] = max(앞줄.get("t1", 0), d["t1"])
            print(f"  ★기능어 고아 줄 병합: 「{d['text']}」 → 「{앞줄['text']}」")
        else:
            병합후.append(d)
    # ★의존명사로 시작하는 줄 재흐름 (같은 클래스 — «계시는 | 것 같은데요» 도 수식어와
    #   피수식어를 가른 것이다): 앞줄 마지막 어절을 끌어내려 「계시는 것 같은데요」로 만든다.
    #   시각은 끌어내린 단어의 실측 시각으로 민다(asr_words 대조) — 안 찾히면 문구만 옮긴다.
    _말들 = [w for w in (proj.get("asr_words") or []) if w.get("type") != "punctuation"]
    for k in range(1, len(병합후)):
        줄, 앞줄 = 병합후[k], 병합후[k - 1]
        첫어절 = 줄["text"].split()[0]
        앞어절들 = 앞줄["text"].split()
        if CLEAN.sub("", 첫어절) not in 의존명사 or len(앞어절들) < 2:
            continue
        내릴 = 앞어절들[-1]
        if len(내릴 + " " + 줄["text"]) > 최대:
            continue
        앞줄["text"] = " ".join(앞어절들[:-1])
        줄["text"] = 내릴 + " " + 줄["text"]
        후보 = [w for w in _말들 if CLEAN.sub("", w["w"]) == CLEAN.sub("", 내릴)
                and 앞줄["t"] - 0.1 <= w["t"] <= 줄["t"] + 0.1]
        if 후보:
            w = 후보[-1]
            줄["t"] = round(float(w["t"]), 2)
            앞줄["t1"] = min(앞줄.get("t1") or 줄["t"], 줄["t"])
        print(f"  ★의존명사 줄머리 재흐름: 「…{내릴} | {줄['text'].split(' ', 1)[1]}」 → 「{줄['text']}」")
    dlg = 병합후
    for d in dlg:
        스택 = [d]
        while 스택:
            c = 스택.pop(0)
            if len(c["text"]) <= 최대 or " " not in c["text"]:
                관문.append(c)
                continue
            mid, best = len(c["text"]) // 2, None
            어절들 = c["text"].split()
            for j, ch in enumerate(c["text"]):
                if ch != " ":
                    continue
                # 의존명사 바로 앞은 절단 금지 — 고아를 다시 만든다 (2026-09-04)
                if c["text"][j + 1:].split()[0] in 의존명사 and len(어절들) > 2:
                    continue
                if best is None or abs(j - mid) < abs(best - mid):
                    best = j
            if best is None:
                best = c["text"].index(" ")
            앞, 뒤 = c["text"][:best].strip(), c["text"][best:].strip()
            t1c = c.get("t1", c["t"] + 2.0)
            중간 = round(c["t"] + (t1c - c["t"]) * (len(앞) / max(len(앞) + len(뒤), 1)), 2)
            스택 = [{"t": c["t"], "t1": 중간, "text": 앞},
                    {"t": max(중간, c["t"] + 0.1), "t1": t1c, "text": 뒤}] + 스택
    긴 = [d["text"] for d in 관문 if len(d["text"]) > 최대]
    print(f"  [{'OK' if not 긴 else 'X'}] 최종 관문 — 대사 {len(관문)}줄 전부 {최대}자 이내"
          + (f" · 초과 {긴[:3]}" if 긴 else ""))
    assert not 긴, "14자 초과 줄이 남았다(공백 없는 장문) — 위 목록"
    dlg = 관문

    # ── ③ 커버리지 게이트 — 모든 발화 단어는 자기 자막 줄 시작에서 6초(표시 최대) 안 ──
    dlg.sort(key=lambda x: x["t"])
    시작들 = [d["t"] for d in dlg]
    구멍 = []
    for w in words:
        if w.get("type") == "punctuation" or 추임새다(w["w"]):
            continue                                      # 웃음·감탄은 자막 밖이어도 정상
        if any(a0 <= w["t"] <= a1 for a0, a1 in 면제구간):
            continue                                      # 오인식 제거 구간 — 자막 없는 게 맞다
        덮는 = max((t for t in 시작들 if t <= w["t"] + 0.05), default=None)
        if 덮는 is None or w["t"] - 덮는 > 6.0:
            구멍.append(round(w["t"], 1))
    print(("  [OK] " if not 구멍 else "  [X] ") +
          f"발화 커버리지 — 단어 {sum(1 for w in words if w.get('type') != 'punctuation')}개 중 "
          f"자막 밖 {len(구멍)}개 {구멍[:6]}")
    assert not 구멍, "커버리지 구멍 — 위 목록"

    proj.setdefault("subs_before_sync", [dict(x) for x in src])
    proj["subs"] = sorted(dlg + narr, key=lambda x: x["t"])
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n저장: {pj}\n★대본이 바뀌었으니 다시 검사해야 제작할 수 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
