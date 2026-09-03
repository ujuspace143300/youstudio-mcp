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
            assert rows and int(rows[0]["i"]) == 말[0][0], "첫 발화가 자막 밖이다"
            return out

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
        out = [{"t": d["t"], "text": d["text"]} for d in 고침]
        # 금지 패턴 ⓑ(조사·어미로 줄 시작) — 기계로 잡히는 것만 경고
        조사들 = {"은", "는", "이", "가", "을", "를", "에", "에서", "의", "도", "만",
                  "와", "과", "랑", "부터", "까지", "처럼", "보다", "한테", "에게"}
        for d in out:
            if d["text"].split()[0] in 조사들:
                print(f"  ★줄 첫머리가 조사다(금지 패턴 ⓑ): 「{d['text']}」 — 눈 확인 필요")
        return out
    except Exception as e:
        print("모델 작표 실패 — 쉼 기준 묶음(ASR 원문 14자)으로 간다:", str(e)[:70])
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
        목표 = len(re.sub(r"[\s?!()]", "", d["text"]))
        끝글, 누적 = None, 0
        for w in 내부:
            누적 += len(CLEAN.sub("", w["w"]))
            if 누적 >= 목표 * 0.9:
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
    dlg = 작표(words, proj["slug"], proj.get("logline", ""))
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

    # ── ③ 커버리지 게이트 — 모든 발화 단어는 자기 자막 줄 시작에서 6초(표시 최대) 안 ──
    dlg.sort(key=lambda x: x["t"])
    시작들 = [d["t"] for d in dlg]
    구멍 = []
    for w in words:
        if w.get("type") == "punctuation":
            continue
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
