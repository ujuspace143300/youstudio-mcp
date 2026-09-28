# -*- coding: utf-8 -*-
"""화자색 — 대사 줄마다 말하는 사람을 판정해 색을 정하는 규칙 «한 곳».

★2026-09-28 사장님 — 완성본 mp4 에도 프리미어와 같은 화자별 대사 색을 넣는다.
  예전엔 판정이 ⑦ 준비(준비_prproj_sk.py)에만 있어 mp4(⑥ 재굽기 build.write_ass)는 대사가 전부 흰색이었다.
  이제 두 곳이 이 모듈의 같은 함수를 부른다:
    · ⑥ build.run_build — 나레 굽기 «뒤», 자막 쓰기 «앞» (새 cut.mp4·나레 길이가 있어 ⑦ 과 같은 재료)
      → 판정해 저장(work/<slug>/_화자판정캐시.json) → write_ass 가 대사 줄에 색을 입힌다.
    · ⑦ 준비_prproj_sk — 같은 키로 저장본을 읽는다(두 번 묻지 않는다) → 프리미어 dlg 큐 색.
  ④ 뒤(⑥ 앞)에서 판정하면 cut.mp4·나레 길이가 달라 판정이 달라질 수 있어 그 자리는 쓰지 않는다.

  판정 입력 = (cut.mp4, ⑦ 규칙으로 만든 대사 큐의 글·시작 시각, logline, 화자수).
  그래서 굽기도 ⑦ 과 «똑같은» 대사 큐를 만든다(대사큐) — 나레 창은 beats.json 실측 조각 머리(나레창).
"""
import hashlib
import json
import os
import wave
from collections import Counter

# 화자1(가장 많이 말한 사람) = 기본색(흰) — 팔레트에 없다. 효과 줄은 나레와 같은 노랑.
팔레트 = {"효과": (245, 244, 37), "2": (135, 206, 250), "3": (255, 182, 193),
          "4": (144, 238, 144), "5": (255, 200, 150)}          # 4·5는 예비(화자가 더 많을 때)
F = 60                                                          # 대사 큐 격자(프리미어 60fps)
캐시이름 = "_화자판정캐시.json"


def 화자판정(lines, cut_mp4, logline, times=None, 예상화자수=None, 회수=3):
    """대사 줄마다 화자 번호(1·2·3…) 또는 «효과»를 배정한다 (EvoLink 무료 경로).

    ★2026-09-02 사장님 지시(같은 화자 색 바뀜 재발 금지)로 전면 개편 —
      한 번 판정을 그대로 믿다가 같은 사람이 두 색으로 갈렸다. 원인 셋:
      ① 줄에 시각이 없어 모델이 자막↔영상 정렬을 혼자 맞춰야 했다 → 시각을 준다.
      ② 인물 정체를 고정하는 장치가 없어 장면이 바뀌면 같은 사람에 새 번호가 붙었다
         → 겉모습(cast) 목록을 먼저 쓰게 강제하고, 사람이 아는 화자 수를 힌트로 준다.
      ③ 검증 없이 1회 판정 → 독립 3회 판정 후 번호를 정렬해 다수결. 과반 미달 줄은
         «불안정»으로 보고한다(게이트).

    반환 (who, 불안정줄번호목록, cast설명). 전부 실패하면 ([None]*n, [], {})."""
    import base64
    from collections import Counter
    from . import gem
    from .cfg import CFG as _C
    models = _C.get("gemini", {}).get("models", ["gemini-3.5-flash"])
    if times:
        목록 = "\n".join(f"{i}. [{t:.1f}초] {s}" for i, (t, s) in enumerate(zip(times, lines)))
    else:
        목록 = "\n".join(f"{i}. {s}" for i, s in enumerate(lines))
    힌트 = (f"- 이 영상의 화자는 {예상화자수}명으로 알려져 있다(효과 제외). "
            f"그보다 많게 나누려거든 정말 다른 사람인지 겉모습을 다시 확인하라.\n") if 예상화자수 else ""
    vid = base64.b64encode(open(gem.shrink_for_inline(cut_mp4), "rb").read()).decode()
    prompt = (f"숏폼({logline})의 자막 줄 목록이다. 줄 앞 [초]는 그 자막이 영상에 뜨는 시각이다.\n"
              f"영상을 보고 줄마다 **말하는 사람**을 배정하라.\n"
              f"- 먼저 등장인물 목록(cast)을 만들어라 — 번호마다 겉모습(성별·옷·자리)을 한 줄로.\n"
              f"  같은 사람은 장면이 바뀌어도 **반드시 같은 번호**다. 목소리도 근거로 써라.\n"
              f"{힌트}"
              f"- 시각을 이용해 그 순간 말하는 사람을 확인하라.\n"
              f"- ★화면에 보이는 사람이 곧 말하는 사람이라고 단정하지 마라 — 대화 장면은 듣는\n"
              f"  사람을 비추는 컷(리버스샷)이 많다. 입 움직임·목소리·대화 맥락(질문과 대답은\n"
              f"  보통 화자가 교대한다)으로 판정하라.\n"
              f"- 사람이 말하는 대사가 아닌 줄(상황 설명·괄호·효과)은 \"효과\" 로.\n"
              f"JSON 만, 공백 없이 한 줄로. ★who 를 먼저: {{\"who\":[줄별 값,...],"
              f"\"cast\":{{\"1\":\"겉모습\",...}}}} — who 는 줄 수 {len(lines)}개와 같아야 한다.\n\n{목록}")
    표, cast = [], {}
    import re as _re2
    # ★회차를 동시에 부른다 (2026-09-27 100편 배치 — 3회 표결을 차례로 불러 ⑦ 준비가 편당 42~50분, 편 전체의 약 45%.
    #   agy 는 동시 호출이 한 번과 같은 시간에 끝난다(2026-09-26 실측 10개 동시). 판정·표결 규칙은 그대로.)
    payload = {"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "video/mp4", "data": vid}},
        {"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 6000, "responseMimeType": "application/json"}}
    from concurrent.futures import ThreadPoolExecutor as _TPE

    def _한번(_n):
        try:
            return gem.ask(payload, models, timeout=600)[0], None
        except BaseException as _e:                     # noqa: BLE001 — AgyStop 도 회차 실패로 센다
            return None, _e
    with _TPE(max_workers=회수) as _ex:
        답들 = list(_ex.map(_한번, range(회수)))
    # ★영상이 구글 안전 필터(«sensitive words»)에 막히면 글만으로 다시 판정한다 (2026-09-27 싱글233 — 영상+자막은
    #   두 번 다 거절, 같은 자막 목록을 글만 보내면 통과했다). 글만이면 겉모습 대신 대화 맥락(질문·대답 교대,
    #   호칭)으로 판정한다 — 영상 판정보다 거칠어 로그에 남긴다. 거절이 아닌 장애(시간 제한 등)는 여기로 오지 않는다.
    if all(e is not None for _t, e in 답들) and all("sensitive" in str(e).lower() for _t, e in 답들):
        print("  주의  화자 판정 — 영상이 구글 안전 필터에 막힘 → 글(자막 목록)만으로 다시 판정")
        payload = {"contents": [{"role": "user", "parts": [{"text":
            "(영상 없이 판정한다 — 대화 맥락·호칭·질문과 대답의 교대로 말하는 사람을 정하라. "
            "겉모습 대신 말투·역할을 cast 에 적어라.)\n" + prompt}]}],
            "generationConfig": {"maxOutputTokens": 6000, "responseMimeType": "application/json"}}
        with _TPE(max_workers=회수) as _ex:
            답들 = list(_ex.map(_한번, range(회수)))
    for n회, (txt, 오류) in enumerate(답들):
        if 오류 is not None:
            # ★AgyStop 은 BaseException 이라 아래 except Exception 을 빠져나가 한 회차 거절에 체인 전체가 멈췄다
            #   (2026-09-27 싱글197 — 3회 중 1회만 안전 필터 거절, 2회는 성공). 회차 실패로만 센다; 전부 실패면 아래 «if not 표» 가 멈춘다.
            print(f"화자 판정 {n회 + 1}회차 실패:", str(오류)[:60])
            continue
        try:
            try:
                j = json.loads(txt)
                if isinstance(j, list):
                    # 모델이 {"who":[…]} 대신 목록만 내는 일이 잦다(2026-09-27 배치 — «list indices must be integers» 로
                    #   회차가 버려져 3회 표결이 2회로 줄었다). 줄 수가 맞는 목록이면 그대로 who 로 받는다.
                    j = {"who": j[0]["who"]} if j and isinstance(j[0], dict) and "who" in j[0] else {"who": j}
                who = [str(w) for w in j["who"]]
                c = {str(k): str(v) for k, v in (j.get("cast") or {}).items()}
            except Exception:
                # ★응답이 뒤에서 잘려도(2026-09-03 3회 연속 실측) who 배열만 온전하면 살린다
                #   — 그래서 프롬프트가 who 를 앞에 쓰게 한다.
                m = _re2.search(r'"who"\s*:\s*\[(.*?)\]', txt or "", _re2.S)
                if not m:
                    raise
                who = [w.strip().strip('"') for w in m.group(1).split(",")]
                c = {}
            assert len(who) == len(lines), f"who {len(who)}개 ≠ 줄 {len(lines)}개"
            표.append(who)
            if not cast and c:
                cast = c
        except Exception as e:
            print(f"화자 판정 {n회 + 1}회차 실패:", str(e)[:60])
    if not 표:
        # 회차가 전부 agy 실패(AgyStop — EvoLink 금지로 멈춤)면 예전처럼 멈춘다 — 동시 호출로 바꾸며 «색 없이 진행» 으로
        #   조용히 품질이 떨어지지 않게(2026-09-27).
        멈춤 = [e for _t, e in 답들 if e is not None and not isinstance(e, Exception)]
        if 멈춤:
            raise 멈춤[0]
        print("화자 판정 전부 실패 — 색 구분 없이 간다")
        return [None] * len(lines), [], {}
    # 회차마다 번호 체계가 다를 수 있다 — 1회차 기준으로 겹침 최대 매칭(그리디)으로 재명명
    기준 = 표[0]
    맞춘 = [기준]
    for run in 표[1:]:
        쌍 = Counter((a, b) for a, b in zip(run, 기준) if a != "효과" and b != "효과")
        사상, 씀 = {}, set()
        for (a, b), _n in 쌍.most_common():
            if a not in 사상 and b not in 씀:
                사상[a] = b
                씀.add(b)
        맞춘.append(["효과" if w == "효과" else 사상.get(w, w) for w in run])
    who, 불안정 = [], []
    for i in range(len(lines)):
        표결 = Counter(r[i] for r in 맞춘)
        값, 표수 = 표결.most_common(1)[0]
        who.append(값)
        if 표수 * 2 <= len(맞춘):                      # 과반 미달 = 회차끼리 갈렸다
            불안정.append(i)
    print(f"화자 판정 {len(맞춘)}회 표결 — 과반 일치 {len(lines) - len(불안정)}/{len(lines)}줄")
    return who, 불안정, cast


def 화자교정적용(dlg_cues, 교정, 팔레트):
    """★사장님 교정(2026-09-02: «저 사람 두고 말한 거야?» 색 뒤바뀜) — 사장님이 확정한
       줄별 화자({"시각": "1|2|3|효과"})를 색에 강제 적용한다. 판정이 몇 번을 다시 돌아도
       교정이 이긴다. 시각은 ±0.3s 로 맞춘다. "1" = 기본색(흰)."""
    n = 0
    for k, v in (교정 or {}).items():
        t = float(k)
        cand = min(dlg_cues, key=lambda c: abs(c["t0"] - t))
        if abs(cand["t0"] - t) > 0.3:
            print(f"★화자교정 {k}s — 맞는 자막을 못 찾았다(가장 가까운 {cand['t0']:.1f}s). 건너뜀")
            continue
        v = str(v)
        cand["color"] = list(팔레트[v]) if v in 팔레트 else None
        n += 1
    return n


def 대사큐(subs, nar_t0, nar_t1, total, pad):
    """⑦ 프리미어 대사 큐 규칙(옛 준비_prproj_sk 776~807행 그대로).

    subs = 시각순 자막 전부(kind=narr 포함 — 여기서 뺀다). 60fps 격자에서 끝 = min(말 끝+0.25, 다음 시작, 총길이).
    ★나레이션이 뜨는 동안 대사 자막은 감춘다(규격 narration.hide_line_subs — 2026-09-01 사장님 재확인).
      겹치면 자르고, 0.3초도 안 남으면 뺀다.
    반환 (큐목록, 큐별 원래 줄 번호(대사 줄 목록 기준), 감춘 수, 늘어짐 목록, 끝없음 수)."""
    n0f, n1f = round((nar_t0 - pad) * F), round((nar_t1 + pad) * F)
    lines = [x for x in subs if x.get("kind") != "narr"]
    큐, 번호, 숨김 = [], [], 0
    늘어짐, 끝없음 = [], 0
    for i, x in enumerate(lines):
        t0f = round(x["t"] * F)
        nxtf = round((lines[i + 1]["t"] if i + 1 < len(lines) else total) * F)
        # ★자막 끝 = 말 끝 + 0.25s (2026-09-03 사장님: 대사가 끝나면 자막도 딱 사라져야
        #   한다 — 이것도 싱크다). 짧은 외마디는 읽을 시간 1.0s 는 보장하되
        #   다음 자막·총길이를 넘지 않는다. 끝시각이 없는 줄(옛 데이터)만 6s 상한.
        if x.get("t1"):
            끝f = max(round((x["t1"] + 0.25) * F), t0f + round(1.0 * F))
        else:
            끝f = t0f + 6 * F
        t1f = min(끝f, nxtf, round(total * F))
        if t1f <= t0f:
            t1f = t0f + 1
        if t0f < n1f and t1f > n0f:                  # 나레이션 창과 겹침
            if t0f >= n0f:
                t0f = n1f                            # 나레 중 시작 → 나레 끝으로 민다
            else:
                t1f = n0f                            # 나레 전 시작 → 나레 앞에서 끊는다
            if t1f - t0f < round(0.3 * F):
                숨김 += 1
                continue
        큐.append({"lane": "dlg", "t0": round(t0f / F, 4), "t1": round(t1f / F, 4), "text": x["text"]})
        번호.append(i)
        if x.get("t1"):
            늘어짐.append(round(t1f / F, 4) - x["t1"])
        else:
            끝없음 += 1
    return 큐, 번호, 숨김, 늘어짐, 끝없음


def 판정키(source_id, 조각, 큐, logline, 화자수):
    """저장본 키 — 조각(cut.mp4 를 만든 원본 구간)·대사 글·대사 시작·logline·화자수. 같으면 판정 입력이 같다."""
    return hashlib.sha1(json.dumps([source_id, [(round(s["t0"], 2), round(s["t1"], 2)) for s in 조각],
                                    [c["text"] for c in 큐], [round(c["t0"], 2) for c in 큐],
                                    logline, 화자수], ensure_ascii=False).encode()).hexdigest()


def 판정조각(segs):
    """키에 넣는 조각 = cut.mp4 를 만든 구간. ⑦ 은 마지막 조각을 여운만큼 늘려 쓰는데(_여운전t1 에 원래 끝),
    여운은 cut.mp4 에 없고 굽기는 여운을 모른다 — 원래 끝으로 되돌려 두 곳의 키를 같게 한다."""
    return [dict(s, t1=s.get("_여운전t1", s["t1"])) for s in segs]


def 색칠(큐, proj, wdir, 조각, 옛키조각=None, cut_mp4=None, log=print, 실패다시=False):
    """큐(dlg)마다 color 를 채운다 — 저장본(같은 키)이 있으면 쓰고, 없으면 판정해 저장한다.
    옛키조각: ⑦ 이 2026-09-28 전에 저장한 키(여운 늘인 조각)도 찾아본다 — 옛 납품편을 다시 판정하지 않게.
    판정이 전부 agy 멈춤(AgyStop)이면 멈춘다(예외가 그대로 나간다) · 일부 실패는 계속 · 전부 일반 실패면 색 없이.
    ★전부 일반 실패도 «실패 기록» 으로 저장한다 (2026-09-28 실패 주입 시험 — 기록이 없으면 ⑥ 은 흰 자막으로 굽고
      ⑦ 이 저장본을 못 찾아 새로 판정해 프리미어만 색이 들어갔다: 싱글84 복제본 ⑥ 색 0줄 · ⑦ 32/49큐).
      ⑦(실패다시=False)은 실패 기록을 그대로 따라 색 없이 간다 = mp4 와 같다. ⑥(실패다시=True)은 다시 구울 때
      실패 기록을 믿지 않고 새로 판정한다 — 색을 넣으려면 FROM=6 으로 다시 돌리면 된다.
    반환 판정 결과가 있었는가(bool)."""
    logline, 화자수 = proj.get("logline", ""), proj.get("화자수")
    sid = proj["source"].get("id")
    키 = 판정키(sid, 조각, 큐, logline, 화자수)
    캐 = os.path.join(wdir, 캐시이름)
    try:
        저장 = json.load(open(캐, encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        저장 = {}
    옛키 = 판정키(sid, 옛키조각, 큐, logline, 화자수) if 옛키조각 is not None else None
    실패기록 = 키 in 저장 and "_실패" in (저장[키][2] or {})
    if 실패기록 and not 실패다시:
        who, 불안정, cast = [None] * len(큐), [], {}
        log(f"화자 판정 — ⑥ 판정 실패 기록 사용 · 색 없이(완성본 mp4 와 같게) · {len(who)}줄")
    elif 키 in 저장 and not 실패기록:
        who, 불안정, cast = 저장[키]
        log(f"화자 판정 — 저장본 사용(조각·자막 그대로) · {len(who)}줄")
    elif 옛키 and 옛키 in 저장:
        who, 불안정, cast = 저장[옛키]
        log(f"화자 판정 — 저장본 사용(조각·자막 그대로 · 옛 키) · {len(who)}줄")
    else:
        who, 불안정, cast = 화자판정([c["text"] for c in 큐], cut_mp4 or os.path.join(wdir, "cut.mp4"),
                                    logline, times=[c["t0"] for c in 큐], 예상화자수=화자수)
        if any(w for w in who):
            json.dump({키: [who, 불안정, cast]}, open(캐, "w", encoding="utf-8"), ensure_ascii=False)
        else:                                            # 전부 일반 실패 — ⑦ 이 따로 판정하지 않게 기록한다
            json.dump({키: [[None] * len(큐), [], {"_실패": "화자 판정 전부 실패 — 색 없이"}]},
                      open(캐, "w", encoding="utf-8"), ensure_ascii=False)
            log("화자 판정 실패 기록 저장 — ⑦ 도 색 없이 간다(색을 넣으려면 FROM=6 으로 다시)")
    if any(w for w in who):
        # 가장 많이 말한 화자 = 1번(기본색) 로 정규화 — 모델이 번호를 어떤 순서로 매겨도 주인공은 기본색
        말수 = Counter(w for w in who if w and w != "효과")
        순위 = [w for w, _n in 말수.most_common()]
        재배 = {w: str(i + 1) for i, w in enumerate(순위)}
        for c, w in zip(큐, who):
            key = "효과" if w == "효과" else (재배.get(w) if w else None)
            c["color"] = list(팔레트[key]) if key in 팔레트 else None
        log("화자 분포: " + str(dict(Counter(("효과" if w == "효과" else 재배.get(w, "?")) for w in who if w))))
        for 원, 겉 in cast.items():
            log(f"  화자{재배.get(원, 원)}: {겉}")
        # ★게이트(2026-09-02) — 회차끼리 갈린 줄은 색이 틀렸을 확률이 높다. 명단을 보고하고
        #   완성 보고에 «화자 검사» 항목으로 남긴다. 불안정 줄이 있으면 사람 눈 확인 필수.
        if 불안정:
            log(f"★화자 불안정 {len(불안정)}줄 — 눈으로 확인 필요:")
            for i in 불안정:
                log(f"   [{큐[i]['t0']:.1f}초] {큐[i]['text'][:30]}")
        if 화자수 and len(말수) != int(화자수):
            log(f"★화자 수 불일치 — 판정 {len(말수)}명 vs 사장님 확인 {화자수}명. 보고 필요.")
    n교정 = 화자교정적용(큐, proj.get("화자교정"), 팔레트)
    if n교정:
        log(f"사장님 화자교정 {n교정}줄 강제 적용 — 판정보다 우선한다")
    return any(w for w in who)


def 나레창(proj, wdir):
    """굽기 쪽에서 ⑦ 과 같은 나레 창(t0, t1)·총길이를 구한다 — ⑦ 준비_prproj_sk 의 규칙 그대로:
    조각 머리는 beats.json 실측(out_dur 누적 · 조각 수·t0 가 계획과 같을 때만, 아니면 계획 길이),
    나레 길이는 narrNN.wav 의 표본 수. ⑦ 의 여운(마지막 조각 연장)은 대사 시작 시각에 영향이 없어 뺀다.
    나레 조각이 하나가 아니면 None(⑦ 이 그 자리에서 멈춘다)."""
    나레조각 = [i for i, s in enumerate(proj["segments"]) if (s.get("narration") or "").strip()]
    if len(나레조각) != 1:
        return None
    segs = [s for s in proj["segments"] if s.get("keep")]
    nar_seg = next((s for s in segs if s.get("narration")), None)
    if nar_seg is None:
        return None
    실측 = None
    try:
        bj = json.load(open(os.path.join(wdir, "beats.json"), encoding="utf-8"))
        if len(bj.get("segments", [])) == len(segs) and all(
                abs(e["t0"] - s["t0"]) < 0.01 for e, s in zip(bj["segments"], segs)):
            실측 = bj["segments"]
    except Exception:                                    # noqa: BLE001
        pass
    머리, cum = [], 0.0
    for i, s in enumerate(segs):
        머리.append(round(cum, 4))
        cum += 실측[i]["out_dur"] if 실측 else (s["t1"] - s["t0"])
    total = round(cum, 4)
    w = wave.open(os.path.join(wdir, f"narr{나레조각[0]:02d}.wav"))
    dur = w.getnframes() / w.getframerate()
    w.close()
    t0 = 머리[segs.index(nar_seg)]
    return round(t0, 3), round(t0 + dur, 3), total


def 프리미어색(dlg_cues, 번호, proj, wdir, pad, 조각, 옛키조각=None, log=print):
    """⑦ 용 — 판정 입력은 ⑥ 과 «똑같은» 큐(나레창·여운 뺀 총길이)로 만들고, 색은 줄 번호로 ⑦ 큐에 옮긴다.

    ★2026-09-28 조건 시험 — ⑦ 은 끝맺음 여운만큼 총길이가 길어, 나레가 영상 맨 끝(0.3초 안)까지 걸리면
      ⑥ 에서 감춘(0.3초 미만) 마지막 대사가 ⑦ 에서는 살아남는다(모의: 나레 78.5~79.6 · 영상 80.0 · 여운 0.5 → ⑥ 큐 1 · ⑦ 큐 2).
      그러면 판정키가 달라 ⑦ 이 새로 판정해 mp4 와 다른 색이 나올 수 있다. 판정 큐를 ⑥ 과 같게 만들면 키가 같고,
      ⑦ 에만 있는 줄은 기본색(mp4 에서는 나레와 겹쳐 build 가 감춘다)."""
    창 = 나레창(proj, wdir)
    if 창 is None:
        return 색칠(dlg_cues, proj, wdir, 조각, 옛키조각=옛키조각, log=log)
    subs = sorted(proj["subs"], key=lambda x: x["t"])
    판정큐, 판정번호, *_ = 대사큐(subs, *창, pad)
    같음 = [(c["text"], round(c["t0"], 2)) for c in 판정큐] == [(c["text"], round(c["t0"], 2)) for c in dlg_cues]
    if 같음:
        return 색칠(dlg_cues, proj, wdir, 조각, 옛키조각=옛키조각, log=log)
    log(f"  주의  ⑦ 대사 큐 {len(dlg_cues)}줄 ≠ ⑥ 판정 큐 {len(판정큐)}줄 (여운·나레 끝 차이) — ⑥ 큐로 판정·저장본을 찾고 줄 번호로 옮긴다")
    r = 색칠(판정큐, proj, wdir, 조각, 옛키조각=옛키조각, log=log)
    색of = {i: c.get("color") for c, i in zip(판정큐, 판정번호)}
    for c, i in zip(dlg_cues, 번호):
        c["color"] = 색of.get(i)
    화자교정적용(dlg_cues, proj.get("화자교정"), 팔레트)
    return r


def 굽기색(proj, wdir, pad, log=print):
    """⑥ 굽기용 — ⑦ 과 같은 대사 큐를 만들어 판정·저장하고, {(원래 줄 시각, 글): (r,g,b) | None} 을 준다.
    mp4 자막(write_ass)은 이 표로 «글·시각» 짝을 찾아 칠한다. 짝 없는 줄(나레 근처에서 ⑦ 이 감춘 줄 등)은 기본색."""
    창 = 나레창(proj, wdir)
    if 창 is None:
        log("    ★화자 색 — 나레 조각이 하나가 아니다(⑦ 이 멈출 편) · mp4 대사는 기본색")
        return {}
    nar_t0, nar_t1, total = 창
    subs = sorted(proj["subs"], key=lambda x: x["t"])
    큐, 번호, *_ = 대사큐(subs, nar_t0, nar_t1, total, pad)
    if not 큐:
        return {}
    segs = [s for s in proj["segments"] if s.get("keep")]
    색칠(큐, proj, wdir, 판정조각(segs), log=log, 실패다시=True)
    lines = [x for x in subs if x.get("kind") != "narr"]
    return {(round(lines[i]["t"], 3), lines[i]["text"]): (tuple(c["color"]) if c.get("color") else None)
            for c, i in zip(큐, 번호)}
