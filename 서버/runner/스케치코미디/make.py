# -*- coding: utf-8 -*-
"""한 편을 검사하고 굽는다.

    python make.py projects/<편>.json --check    검사만 (공짜)
    python make.py projects/<편>.json            굽기 (★TTS 요금)

★검사가 이 파이프라인의 핵심이다. sketch 는 「구조가 좋은가」를 사람 눈에 맡겼는데,
  여기서는 **5-Phase 가 기계로 검증된다** — 훅이 약한가, Climax 가 너무 빠른가,
  사람들이 웃은 자리를 빠뜨렸는가. 전부 굽기 전에 잡힌다.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PHASES = {p["no"]: p for p in CFG["edit"]["phases"]}


def _g(path, default):
    """생성 config 의 _정답지(판정 대역)에서 값을 꺼낸다 — 없으면 sketch2 시절 기본값.
    판정의 정본은 서버(sk_check)지만, 이 이중 빗장의 상수도 원천은 정답지 한 곳이다."""
    cur = CFG.get("_정답지", {})
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur



def 말끝_실측(src, c0, cap):
    """큐 시작 c0 부터 말대역(800~3500Hz) 에너지가 꺼지는 «실측» 끝시각 → (끝, 창시작, 에너지열, 문턱).
    글자 수 추정(0.17s/자)은 스케치 말속도(8~10음절/초)에서 두 배로 부풀어 납품분 전부를 반려했다 —
    추정 말고 소리를 잰다(2026-09-09 Deep60). 바닥(BGM)은 큐 앞뒤 3초를 더한 넓은 창의 20% 백분위 —
    말로 꽉 찬 짧은 창에서 백분위를 재면 문턱이 말 위로 올라가 끝이 시작으로 튄다(Deep62 «애쓰지 않아도» 실측).
    쉼 0.6초(줄 나눔 gap 0.55 와 맞춤)면 말이 끝난 것으로 본다. cap(다음 큐 시작)을 넘지 않는다."""
    import subprocess as _sp
    try:
        import numpy as _np
    except ImportError:
        return min(cap, c0 + 0.3), None, None, None
    b = max(c0 - 3.0, 0.0)
    d = min(cap + 2.0, c0 + 11.0) - b
    if d <= 0.4 or not os.path.exists(src):
        return min(cap, c0 + 0.3), None, None, None
    r = _sp.run(["ffmpeg", "-v", "error", "-ss", f"{b:.2f}", "-t", f"{d:.2f}", "-i", src,
                 "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
    a = _np.frombuffer(r.stdout, dtype=_np.int16).astype(_np.float32) / 32768
    win = 1600                                     # 0.1초
    if len(a) < win * 4:
        return min(cap, c0 + 0.3), None, None, None
    f = _np.fft.rfftfreq(win, 1 / 16000)
    sel = (f > 800) & (f < 3500)
    h = _np.hanning(win)
    e = _np.array([20 * _np.log10(_np.abs(_np.fft.rfft(a[i:i + win] * h))[sel].sum() + 1e-6)
                   for i in range(0, len(a) - win, win)])
    th = float(_np.percentile(e, 20)) + 8.0            # 바닥(BGM) 대비 +8dB 가 말
    spk = e > th
    i0 = int((c0 - b) / 0.1)
    i_cap = min(len(spk), int((cap - b) / 0.1) + 1)
    last, gap = i0, 0
    for i in range(i0, i_cap):
        if spk[i]:
            last, gap = i, 0
        else:
            gap += 1
            if gap >= 6 and i > i0 + 3:                  # 0.6초 쉬면 말이 끝난 것
                break
    return min(cap, round(b + (last + 1) * 0.1, 2)), b, e, th


def 나레곁검사(proj, subs):
    """(반려, 주의) — check() 의 «나레 곁 대사» 관문. 납품 편 재기(검수도구)도 이 함수를 그대로 부른다."""
    n = CFG["narration"]
    bad, warn = [], []
    # ★나레 곁 대사 (2026-09-28 저녁 싱글287 — 나레가 앞 대사 말끝 0.02초 뒤에 붙어 «숨겨놓으면 웃기겠다» 가 완성본 mp4
    #   에서만 사라지고(프리미어엔 남음) 덕킹이 말끝을 먹었다. 154·180 도 같은 류).
    #   클래스: 굽기(build.write_ass)와 프리미어(⑦ 화자색.대사큐)가 나레 곁 대사를 서로 다른 규칙으로 감췄다 — 납품 편 대부분의
    #     mp4 에 프리미어엔 있는 줄이 빠져 있었다(납품 420편 중 325편 · 431줄). make 에 이 관문이 없어 굽기 전에 못 잡았다.
    #   수리: 두 산출물이 화자색.나레곁 하나를 쓴다(겹치면 나레 앞에서 끊거나 뒤로 밀고 0.3초 미만만 감춤) — 그래서 여기서는
    #     «그 규칙으로도 감춰지는데 말은 들리는 줄»(자막 없이 말만 나감)을 반려하고, 말끝·말머리가 덕킹 창에 드는 줄은 주의로 알린다.
    #   나레 창 = 조각 머리(굽기 실측 beats.json 이 맞으면 그것 · 아니면 계획 길이) + 나레 길이(TTS 캐시에 이 문구가 있으면
    #     굽기와 같은 후처리로 잰 실측 · 없으면 글자수 × 0.108초(납품 415편 실측 비율 — 화자색.나레초당글자) 어림 —
    #     어림일 때는 반려 대신 주의, 굽기 뒤 ⑤ 재검사가 실측으로 다시 본다).
    #   덕킹 창 = 나레 ± 여유 — 완성본 0.15초(duck_pad_sec, −30dB) · 프리미어 0.2초(조립, −15dB) 가운데 큰 쪽으로 잰다.
    #   왜 기준을 «겹치면 반려» 가 아니라 이렇게 뒀나: 납품 편 재기에서 나레 창 ±0.2초에 대사가 걸린 편이 70%(297/422) —
    #     이 채널은 나레가 조각 머리에 얹혀 그 조각 첫 대사를 덮는 것이 설계다(«나레 동안 원음을 죽인다»). 막을 것은 두 산출물의
    #     불일치(구조로 없앰)와 «들리는 말의 자막이 사라짐» 이다.
    try:
        from s2pipe import 화자색 as _HS
        _nrs = _HS.나레자리(proj)
        if len(_nrs) > 1:
            bad.append(f"★나레가 붙은 조각이 {len(_nrs)}개({[i for i, _a, _t in _nrs]}) — 프리미어(⑦ 준비)는 나레 1줄만 싣는다."
                       " 완성본 mp4 에는 나레가 다 나가 두 산출물이 달라진다. 나레를 한 조각에만 남겨라")
        elif _nrs and n.get("hide_line_subs", True):
            from s2pipe import tts as _tts
            _wd = os.path.join(HERE, CFG["paths"]["work"], proj.get("slug", ""))
            _i, _at, _글 = _nrs[0]
            _머리, _총, _실머리 = _HS.조각머리(proj, _wd)
            _keep = [k for k, s in enumerate(proj["segments"]) if s.get("keep")]
            _a = _머리[_keep.index(_i)] if _i in _keep else _at
            _d = _tts.캐시길이(_글, n, os.path.join(_wd, "_tts")) if n.get("voice_id") else None
            _실측 = _d is not None
            if _d is None:
                _d = len(_글) * _HS.나레초당글자               # 굽기 전 어림 — 실측 비율(설정 sec_per_char 0.161 은 49% 길다)
            _b = _a + _d
            _pad = float(n.get("duck_pad_sec", 0.15))
            _P = max(_pad, _HS.나레덕킹여유)                  # 두 산출물 중 큰 덕킹 여유(완성본 0.15 · 프리미어 0.2)
            _근거 = f"나레 {_a:.2f}~{_b:.2f}초({'실측' if _실측 else '길이 추정 — 굽기 뒤 ⑤ 가 실측으로 다시 본다'})"
            _줄 = [x for x in subs if x.get("kind") != "narr"]
            _보임 = _HS.나레곁(_줄, [(_a, _b)], _총, _pad)
            _먹힘 = []
            _앞끝 = None                                    # 나레 머리 앞(앞 조각) 마지막 대사 끝 — 이음매(=나레 머리)에서 자른 값
            for x, v in zip(_줄, _보임):
                t, t1 = x["t"], x.get("t1")
                if not t1:
                    continue                                # 끝시각 없는 초안 줄(싱크 전) — ⑤ 재검사가 본다
                if t < _a:
                    # ★나레는 늘 조각 머리(=이음매)에 얹힌다 — 앞 조각 소리는 이음매에서 끝난다. 재전사 낱말 끝이 이음매를 넘어
                    #   부풀면(싱글46 «거잖아요» 끝 17.54 > 이음매 17.45 · 원본 소리로 잰 말끝 17.06) 이음매에서 자른 값으로 잰다.
                    t1 = min(t1, _a)
                    _앞끝 = (x, t1) if _앞끝 is None or t1 >= _앞끝[1] else _앞끝
                밖 = max(0.0, min(t1, _a - _pad) - t) + max(0.0, t1 - max(t, _b + _pad))   # 완성본 덕킹 밖(들리는) 말
                안 = max(0.0, min(t1, _b + _P) - max(t, _a - _P))                          # 두 산출물 덕킹 창 안 말
                if v is None and 밖 >= 0.2:
                    (bad if _실측 else warn).append(
                        f"★나레 곁 대사 자막 사라짐 — 「{x['text']}」 {x['t']:.2f}~{t1:.2f}초가 {_근거} ±{_pad}초 창에 걸려 보일 자리가"
                        f" 0.3초도 안 남아 감춰지는데 말은 {밖:.2f}초 들린다(자막 없이 말만 나감). 고치는 법: 나레를 대사 없는 샷으로"
                        f" 옮기거나, 나레 조각을 나눠 나레를 늦춰라(싱글287: 조각을 31.75초에서 나눠 나레를 0.72초 늦춤)")
                elif t >= _a and 안 >= 0.15 and 밖 >= 0.15:     # 나레 안에서 시작해 나레 뒤로 이어지는 말 — 말머리가 덕킹에 먹힘
                    _먹힘.append(f"「{x['text'][:10]}」 {x['t']:.2f}~{t1:.2f}초 중 {안:.2f}초")
            # 나레 머리 앞 말끝 = 싱크 자막(완성본 Speechmatics) 끝을 이음매(=나레 머리)에서 자른 값. 싱크 전(①)에는 끝시각이 없어
            #   ⑤ 재검사가 본다. 소리 에너지로 잰 말끝(make.말끝_실측 — 0.6초 쉼까지)도 시험했으나 문장 안 쉼·배경음에 흔들려
            #   287 «…숨겨놓으면 웃기겠다»(참 끝 원본 29.13) 를 27.9 로 재는 등 1초 넘게 일러 쓰지 않았다(2026-09-28 저녁).
            _알림 = []
            if _앞끝 is not None and _a - _앞끝[1] < _P:
                _알림.append(f"나레 시작 − 앞 대사 끝 {_a - _앞끝[1]:.2f}초(「{_앞끝[0]['text'][:12]}」 끝 {_앞끝[1]:.2f} · 이음매에서 자른 값)")
            if _먹힘:
                _알림.append(f"나레 안에서 시작해 뒤로 이어지는 말 {len(_먹힘)}줄(" + " · ".join(_먹힘[:3]) + ")")
            if _알림:
                warn.append("나레 곁 원음 덕킹 — " + " · ".join(_알림) + f" — 덕킹(완성본 ±{_pad}초 −30dB · 프리미어 ±0.2초 −15dB)이"
                            " 말끝·말머리를 먹을 수 있다(자막은 두 산출물 모두 나레 앞에서 끊기거나 뒤로 밀려 같게 보인다)."
                            " 들어 보고 거슬리면 나레 조각을 나눠 나레를 늦추거나 대사 없는 샷으로 옮겨라")
    except Exception as _e:                                # noqa: BLE001
        warn.append(f"나레 곁 대사 검사 못 함: {str(_e)[:80]}")

    return bad, warn


def check(proj, path):
    """반려 사유와 주의를 낸다. rc 0 이면 통과."""
    e, n, tb = CFG["edit"], CFG["narration"], CFG["layout"]["title"]
    bad, warn = [], []

    segs = [s for s in proj.get("segments", []) if s.get("keep", True)]
    if not segs:
        return ["구간이 하나도 없다"], []

    # ★sketch 대본을 잘못 넣는 것을 먼저 잡는다. 소재가 같아 헷갈리기 쉽다.
    # ★★껍데기(제목 2줄·댓글 층)를 sketch 에서 가져온 뒤로 **겉모습이 거의 같아졌다.**
    #   제목 형식으로도, 댓글 유무로도 못 가른다 — 둘 다 한 번씩 오인해서 자기 대본을
    #   막았다. **남은 확실한 표식은 `phase` 하나뿐이다**(5-Phase 는 sketch2 에만 있다).
    if not any("phase" in s for s in segs):
        return (["★이건 sketch 대본이다 — sketch2 는 다른 채널이다."
                 "\n     조각에 `phase` 가 없으면 저쪽 형식이다(5-Phase 는 여기에만 있다)."
                 "\n     sketch2 는 `python -m s2pipe.plan <URL>` 로 새로 계획한다."], [])
    total = sum(s["t1"] - s["t0"] for s in segs)
    lo, hi = e["target_sec"]

    # ── 길이
    if total > e["max_sec"]:
        bad.append(f"완성 길이 {total:.0f}초 — 상한 {e['max_sec']}초를 넘는다")
    elif not (lo <= total <= hi):
        warn.append(f"완성 길이 {total:.0f}초 — 목표 {lo}~{hi}초 밖이다")

    # ── ★5-Phase 구조. 이 파이프라인이 sketch 와 갈리는 지점이다
    used = [s.get("phase", 0) for s in segs]
    missing = [p for p in (1, 2, 3, 4, 5) if p not in used]
    if missing:
        names = ", ".join(f"{p} {PHASES[p]['name']}" for p in missing)
        bad.append(f"Phase 가 빠졌다 — {names}. 기승전결이 서지 않는다")

    if used != sorted(used):
        bad.append(f"Phase 가 순서대로 배열되지 않았다 — {used}")

    # Hook — 첫 조각이 약하면 3초 안에 스크롤을 못 멈춘다
    p1 = PHASES[1]
    if segs[0].get("phase") != 1:
        bad.append(f"첫 조각이 Phase 1(Hook)이 아니다 — P{segs[0].get('phase')}")
    elif segs[0].get("punch", 0) < p1["min_punch"]:
        bad.append(f"★훅이 약하다 — 첫 조각 punch {segs[0].get('punch')}"
                   f" (Hook 은 {p1['min_punch']} 이상이어야 한다)."
                   f" 상황 설명으로 열지 말고 센 대사를 앞으로 끌어와라")

    # ★★조각끼리 겹치면 **같은 장면이 두 번 나온다.** 되감기처럼 보여 눈에 띈다.
    #   밀도가 100% 를 넘으면 그 신호다 — 겹친 만큼 합이 범위보다 커지기 때문이다.
    order = sorted(segs, key=lambda s: s["t0"])
    for a, b in zip(order, order[1:]):
        ov = a["t1"] - b["t0"]
        if ov > _g("구조.G-조각겹침.겹침_max_sec", 0.05):
            bad.append(f"★조각이 {ov:.1f}초 겹친다 — 원본 {b['t0']:.1f}~{a['t1']:.1f} 이"
                       f" 두 번 나온다. 한쪽 끝을 물러라")

    # ★★★**밀도가 완성도를 가른다.** 완성 길이 ÷ 원본에서 펼친 범위.
    #   넓게 퍼뜨리면 대목 사이 맥락이 끊겨 이야기가 안 이어진다 — 같은 소재로
    #   견줘 46% 인 편이 18% 인 편을 이겼다(구조 딱지는 18% 쪽이 더 정확했는데도).
    lo_d, hi_d = e.get("density", [0.40, 0.75])
    # ★결말 점프(2026-09-01 A안) — 마지막 P5 조각이 규격 결말점프_최대_s 이하면
    #   밀도 계산에서 통째로 뺀다(길이·범위 모두). 서버 check.ts 와 같은 규칙.
    jump_max = e.get("결말점프_최대_s", 0)
    # ★결말 장면이 여러 컷일 수 있다(2026-09-09 Deep61: 달력 5.6s + 블랙아웃 카드 «2주 전이다» 1.1s).
    #   본체에서 큰 간격(>60s) 뒤로 떨어진 «끝 블록»을 통째로 뺀다 — 마지막 한 조각만 빼면
    #   달력이 span 에 남아 밀도가 20%로 무너졌다. 블록 총길이가 jump_max 이하이고 P5 로 끝날 때만.
    #   (2026-09-09 재수정 — 큰 간격이 없을 때 제외를 아예 안 해 Deep55 단일 끝조각이 밀도를 깨뜨렸다:
    #   여러 컷 끝장면은 큰 간격(>15s) 앞까지 통째로, 큰 간격이 없으면 마지막 한 조각만 뺀다.)
    # ★계산은 s2pipe/밀도.계산 한 곳(2026-09-29 점심이네 배치 — 먼 도입 셋업·가운데 광고·결말 쪽 훅이 범위를
    #   부풀려 셋업을 못 넣던 구멍). 훅 제외·광고 제외·도입 점프는 규격 스위치(edit.훅_밀도제외·광고_밀도제외·
    #   도입점프_최대_s)로만 켠다 — 꺼져 있으면 예전 계산과 같다. 기준값 35% 는 그대로다.
    from s2pipe import 밀도 as _밀도
    _md = _밀도.계산(segs, e, proj)
    span, c_total, dens = _md["span"], _md["c_total"], _md["dens"]
    bad += _md["반려"]
    warn += _md["주의"]
    if dens < lo_d:
        _뺌 = (" (범위에서 뺀 것: " + " · ".join(_md["뺀것"]) + ")") if _md["뺀것"] else ""
        _셋업 = ""
        if float(e.get("도입점프_최대_s", 0) or 0) > 0 and not proj.get("도입점프"):
            _셋업 = (f" · 뒤에서 갚히는 먼 도입 셋업(P2, {e['도입점프_최대_s']}초 이하) 때문이면"
                     f" proj[\"도입점프\"]={{\"근거\":…,\"짝\":[갚는 원본 시각]}} 로 선언할 수 있다")
        bad.append(f"★밀도 {dens*100:.0f}% — 원본 {span:.0f}초에 걸쳐 {c_total:.0f}초를"
                   f" 뽑았다{_뺌}. {lo_d*100:.0f}% 이상이어야 한다."
                   f" **넓게 퍼뜨리면 맥락이 끊겨 이야기가 안 이어진다** —"
                   f" 좋은 대목이 몰린 곳으로 범위를 좁혀라{_셋업}")
    elif dens > hi_d:
        warn.append(f"밀도 {dens*100:.0f}% — 한 구간을 통으로 쓴 것에 가깝다."
                    f" 원본의 늘어짐이 그대로 남는다")

    # ★한 Phase 가 편을 통째로 먹는 것만 막는다.
    # ★★**지침서의 시간표(0-3·3-10·10-30·30-45·45-50)는 50초 편의 「예시」이지
    #   강제 비율이 아니다.** 처음에 2.2배로 걸었더니 **완성도가 가장 좋다고 판정된
    #   편이 반려됐다**(Hook 16%·Context 39% — 지침서 몫은 6%·14%). 좋은 편일수록
    #   앞부분이 두툼했다. 그래서 「명백히 비대한 것」만 잡도록 3.5배로 풀었다 —
    #   실제로 막아야 했던 것은 Punchline 이 49% 를 먹은 경우였다.
    span = PHASES[5]["sec"][1] or 50
    for no, p in PHASES.items():
        got = sum(s["t1"] - s["t0"] for s in segs if s.get("phase") == no)
        if not got:
            continue
        want = (p["sec"][1] - p["sec"][0]) / span
        if got / total > want * _g("구조.G-Phase몫.배수_max", 3.5):
            bad.append(f"★P{no} {p['name']} 가 {got:.0f}초({got/total*100:.0f}%)를"
                       f" 차지한다 — 한 칸이 편을 통째로 먹었다."
                       f" 나머지 Phase 가 밀려난다. 짧게 자르거나 쪼개라")

    # Climax 위치 — 앞에 오면 뒤가 무너진다
    at, climax_at = 0.0, None
    for s in segs:
        if s.get("phase") == 4 and climax_at is None:
            climax_at = at
        at += s["t1"] - s["t0"]
    if climax_at is not None and total and climax_at / total < _g("구조.G-Climax위치.min_pos", 0.6):
        bad.append(f"★Climax 가 너무 빠르다 — {climax_at:.0f}초"
                   f"({climax_at/total*100:.0f}% 지점). 전체의 60% 를 지나서 와야 한다")

    # ★글꼴 실물 게이트 (2026-09-07 사장님 «제목 글씨체 달라졌다» — 히스토리 재작성 때
    #   자산/ 이 지워졌는데 사다리가 조용히 시스템 얇은 글꼴로 폴백해 두 편이 얇게 나갔다.
    #   규격 글꼴이 없으면 굽기 전에 멈춘다. 복원: bash 서버/도구/자산스테이징.sh)
    for _k in ("title", "subtitle", "narration_sub"):
        _fp = (CFG["layout"].get(_k) or {}).get("font")
        if _fp and not os.path.exists(_fp):
            bad.append(f"★규격 글꼴 없음({_k}): {_fp} — 자산스테이징.sh 로 복원하라"
                       f" (조용한 폴백 금지)")

    # ★글자 모양 게이트 (2026-10-02 루키치185 «라잌»·«오 쉣» 이 완성본에 빈칸) — sub.ttf·title.ttf 는 한글 11,172자가
    #   cmap 에 다 있지만 8,822자는 모양(윤곽)이 비어 있다(완성형 2,350자만 그려짐). cmap 만 보는 폴백 검사는 «있다» 로
    #   통과시켜 빈칸이 그대로 나갔다(감사: Deep87 깄 · 루키치198 줜 · 싱글147·172 쉣 · 싱글211 읎 · 싱글251 쌰 · 싱글160 제목 퇼).
    #   화면에 박히는 글(자막·나레 자막·제목·하단 원제)의 글자마다 그 글꼴에 윤곽이 있는지 잰다 — 없으면 반려.
    def _빈글자(fp, 글):
        if not fp or not os.path.exists(fp) or not 글:
            return []
        try:
            from fontTools.ttLib import TTFont
            from fontTools.pens.boundsPen import BoundsPen
        except ImportError:
            return []
        _c = _빈글자.__dict__.setdefault("캐시", {})
        if fp not in _c:
            _t = TTFont(fp)
            _c[fp] = (_t.getBestCmap(), _t.getGlyphSet(), {})
        cm, gs, memo = _c[fp]
        out = []
        for ch in sorted(set(글)):
            if ch.isspace() or not ch.isprintable():
                continue
            if ch not in memo:
                g = cm.get(ord(ch))
                if g is None:
                    memo[ch] = True
                else:
                    bp = BoundsPen(gs)
                    gs[g].draw(bp)
                    memo[ch] = bp.bounds is None and ch not in " 　"
            if memo[ch]:
                out.append(ch)
        return out
    _lay = CFG["layout"]
    _제목글 = proj.get("title") or []
    _제목글 = "".join(_제목글 if isinstance(_제목글, list) else [str(_제목글)])
    _검사 = [("자막", (_lay.get("subtitle") or {}).get("font"), "".join(s.get("text", "") for s in proj.get("subs", []))),
            ("나레 자막", (_lay.get("narration_sub") or {}).get("font") or (_lay.get("subtitle") or {}).get("font"),
             "".join(s.get("narration") or "" for s in segs)),
            ("제목", (_lay.get("title") or {}).get("font"), _제목글),
            ("하단 원제", (_lay.get("credit") or {}).get("font"), (proj.get("credit") or {}).get("title") or "")]
    for _이름, _fp, _글 in _검사:
        _빈 = _빈글자(_fp, _글)
        if _빈:
            bad.append(f"★글꼴에 모양이 없는 글자({_이름}): {''.join(_빈)} — 완성본에 빈칸으로 나간다. "
                       f"보통 글자로 풀어 써라(예: 잌→크 · 쉣→쉐엣 · 줜나→존X · 읎→없) — {os.path.basename(_fp)}")

    # ★조각 안 통암전 — 굽기 전에 잡는다 (2026-09-27 싱글236: 원본 화면 전환용 검은 화면이 조각에 들어가
    #   ⑦ 준비의 같은 관문에서야 걸려 유료 굽기를 한 번 더 했다). 준비_prproj_sk.py 통암전 게이트와 같은 기준 —
    #   1초 간격 표본 2개 연속 «평균<12 이고 밝은 픽셀(>60) 거의 없음»(글자 카드는 통암전 아님).
    _src암 = os.path.join(HERE, CFG["paths"]["work"], f"{proj['source']['id']}.mp4")
    if os.path.exists(_src암):
        for _k, _s in enumerate(segs):
            _연, _t = 0, _s["t0"] + 0.5
            while _t < _s["t1"]:
                _r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{_t:.2f}", "-i", _src암, "-frames:v", "1",
                                     "-vf", "scale=320:-2", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                    capture_output=True)
                _b = _r.stdout
                _어 = len(_b) > 0 and sum(_b) / len(_b) < 12 and sum(1 for _x in _b if _x > 60) < len(_b) * 0.0008
                _연 = _연 + 1 if _어 else 0
                if _연 >= 2:
                    bad.append(f"★조각 {_k} 안에 통암전(검은 화면) — 원본 {_t - 1.0:.1f}초쯤. 조각에서 빼라"
                               f" (⑦ 준비에서 걸려 재굽기가 된다)")
                    break
                _t += 1.0

    # ★원문화면·전체화면 조각에 박힌 자막이 있으면 반려 (2026-09-27 싱글235 — 얼굴을 살리려 대사 샷 5곳을 원문화면으로
    #   바꿨더니 원본 박힌 자막이 그대로 보이고, 원문화면 규칙이 우리 자막까지 뺐다. 사장님 «자막만 안 나오면 돼»).
    #   가로 전체를 보이는 조각은 박힌 자막 카드가 없는 샷이어야 한다(겹침 0.1초 = 10fps 잰 오차까지만).
    if os.path.exists(_src암) and any(s.get("원문화면") or s.get("전체화면") for s in segs):
        try:
            # ★굽기·준비와 같은 관문(s2pipe/번인관문.걸림 — 2026-09-27)을 굽기 전에 부른다. 가로 전체 = 원본 전체 사각형.
            from s2pipe import 번인관문 as _관
            _박 = _관.카드상자들(_src암)
            _wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                  "stream=width,height", "-of", "csv=p=0", _src암], capture_output=True, text=True).stdout
            _W, _H = (int(v) for v in _wh.strip().split(",")[:2])
            for _k, _s in enumerate(segs):
                if not (_s.get("원문화면") or _s.get("전체화면")):
                    continue
                _걸 = _관.걸림(_박, [{"t0": _s["t0"], "t1": _s["t1"], "x": 0, "y": 0, "w": _W, "h": _H, "이름": f"조각{_k}"}])
                if _걸:
                    _겹 = sum(g["겹초"] for g in _걸)
                    bad.append(f"★조각 {_k}({_s['t0']:.1f}~{_s['t1']:.1f}) 이 원문화면·전체화면인데 박힌 자막이 {_겹:.1f}초 보인다"
                               f" — 가로 전체를 보이면 원본 자막이 그대로 나간다. 박힌 자막 없는 샷만 쓰거나 표식을 빼라")
        except Exception as _e:                            # noqa: BLE001
            warn.append(f"원문화면 박힌 자막 검사 못 함: {str(_e)[:60]}")

    # ★원본 화면 캡션 (2026-09-29 점심이네2 — 가운데 날짜 캡션 «6월 14일→1월 03일»(원본 21.52~25.78)이 1차 완성본 9~12초에
    #   나갔는데 make·굽기·⑦ 준비 관문이 모두 통과했다. 자막띠 밖 캡션은 카드도 «가림» 도 아니라 비교 대상이 없었다).
    #   글자 인식 + agy 판정(s2pipe/화면글자.py)으로 찾은 캡션이 조각에 걸리면 굽기 전에 본다:
    #   전체화면 조각 · 굽기(framing.가림경계)가 피해도 쓸 세로가 절반이 안 되는 캡션(가운데 큰 캡션) = 반려, 나머지 = 주의(굽기가 피한다).
    if os.path.exists(_src암):
        try:
            from s2pipe import 번인관문 as _관2
            _b2, _w2 = _관2.캡션조각검사(_src암, segs, CFG["layout"].get("video_box") or {}, log=print)
            bad += _b2
            warn += _w2
        except SystemExit:
            raise
        except Exception as _e:                            # noqa: BLE001
            bad.append(f"★원본 화면 캡션 검사 못 함 — {str(_e)[:120]} (조용히 넘기지 않는다 · s2pipe/화면글자.py)")

    if segs[-1].get("phase") != 5:
        bad.append(f"마지막 조각이 Phase 5(Punchline)가 아니다 — P{segs[-1].get('phase')}")
    elif segs[-1].get("punch", 0) < PHASES[5]["min_punch"]:
        warn.append(f"마지막 punch {segs[-1].get('punch')} — 최고 웃음 포인트로 끝나야 한다")

    # ★결말 포함 게이트 (2026-09-07 사장님 «기승전결이 맞아? 결론 어디에 빼먹었어» —
    #   Deep09 실측: 잔존 번인 게이트에 걸리자 결말 명언 화면을 잘라내고 발견 장면에서
    #   끊었다. 길이·밀도·절정 위치는 재는데 «결(結)이 소재의 실제 엔딩을 담는가»는 아무도
    #   안 쟀다). 마지막 조각은 원본의 마지막 유의미 발화 비트와 겹쳐야 한다.
    try:
        import re as _re
        _vtt = os.path.join(HERE, CFG["paths"]["work"], f"{proj['source']['id']}.ko.vtt")
        _src = os.path.join(HERE, CFG["paths"]["work"], f"{proj['source']['id']}.mp4")

        def _어두운가(t):
            # 검은꼬리 절단(build)과 같은 기준(밝기<12) — 게이트끼리 기준이 갈리면 충돌한다
            # (2026-09-07 Deep10: 암전 위 아웃트로 노래를 «마지막 발화»로 세서 절단과 싸웠다)
            import subprocess as _sp
            r = _sp.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.2f}", "-i", _src,
                         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                        capture_output=True)
            # ★build.py 와 같은 기준 (2026-09-09 Deep61 블랙아웃 펀치라인 카드) — 밝은 글자 픽셀이
            #   있으면 «어둡다» 아님. 안 그러면 «암전 위 소리는 결이 아니다» 규칙이 카드 결말을 버린다
            d = r.stdout
            if not d:
                return False
            bright = sum(1 for x in d if x > 60)
            return (sum(d) / len(d)) < 12 and bright < len(d) * 0.0008

        끝발화 = None
        후보들 = []
        if os.path.exists(_vtt):
            for m in _re.finditer(r"(\d+):(\d+):(\d+\.\d+) --> [^\n]+\n(.*)", open(_vtt, encoding="utf-8").read()):
                글 = _re.sub(r"[^가-힣]", "", m.group(4))
                if len(글) >= 3 and not _re.fullmatch(r"[하호흐히헤아어오우음야에]+", 글):
                    후보들.append(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)))
        for t in reversed(후보들[-4:]):          # 끝에서 최대 4개만 프레임을 재본다
            if os.path.exists(_src) and _어두운가(t + 0.3):
                continue                          # 암전 위 소리(아웃트로 노래·크레딧)는 결이 아니다
            끝발화 = t
            break
        # ★반려 (2026-09-07 사장님 확정 규칙 — «스케치코미디는 기본적으로 마지막 부분에
        #   결론이 다 있다. 마지막 부분을 생략하면 결론이 잘 나오기가 힘들다».
        #   Deep11 실측: 중반 자축을 결말로 잡았다가 원본 끝의 «본능» 반전을 놓쳤다.)
        #   예외 — 원본 꼬리가 결론이 아닌 단순 아웃트로임을 사람이 확인한 편(Deep10
        #   «정적 개그» 사례)만 proj["결말확인"]: true 로 명시해 통과시킨다.
        # ★결말 발화 «끝» 절단 게이트 (2026-09-07 Deep18 «100만원 영원»·Deep20 «고백 직관
        #   진짜» 실측 ×2 — 마지막 조각 t1 이 결말 발화 꼬리를 잘라 문구가 토막났다.
        #   vtt 끝시각은 실제 말끝보다 이르게 찍히므로 +0.7s 여유를 요구한다(0.4 로는 Deep27 «커플이 있다» 꼬리를 또 놓쳤다).)
        # ★큐 끝시각 신뢰 (2026-09-09 Deep60 «이래서 소개팅 주» 실측 — 편시작이 쓰던 vtt 끝시각이
        #   전부 «시작+0.999» 가짜였다. 그래서 이 게이트는 큐 시작 1.7초 안쪽만 봤고, 9글자 대사가
        #   1.0초 뒤 잘려도 통과했다. 같은 판 조각 8 «태용 씨가 확실히 보는 눈이» 도 1.0초 뒤 절단.
        #   두 구멍: ① 가짜 끝 ② 마지막 조각만 봄 ③ «결말확인» 이 이 게이트까지 통째로 껐음.
        #   수리: 편시작은 단어 끝시각을 쓴다 / 옛 vtt(전 큐 0.999s)는 글자 수로 끝을 추정한다 /
        #   모든 조각의 t1 을 본다 / 결말확인은 «결론 미포함» 게이트만 넘기고, 발화 절단 예외는
        #   proj["결말절단허용"]: [큐 시작초, …] 로 큐 하나씩 명시한다(Deep23 카드 위 보이스오버형).
        큐들 = []
        if os.path.exists(_vtt):
            for m in _re.finditer(r"(\d+):(\d+):(\d+\.\d+) --> (\d+):(\d+):(\d+\.\d+)\n(.*)",
                                  open(_vtt, encoding="utf-8").read()):
                g2 = m.groups()
                큐들.append([int(g2[0]) * 3600 + int(g2[1]) * 60 + float(g2[2]),
                            int(g2[3]) * 3600 + int(g2[4]) * 60 + float(g2[5]),
                            g2[6], _re.sub(r"[^가-힣]", "", g2[6])])
        가짜끝 = bool(큐들) and sum(1 for c in 큐들 if 0.99 <= c[1] - c[0] <= 1.0) >= 0.9 * len(큐들)
        # ★agy 원본 전사(2026-09-26 사장님 결정 B — 원본 전사는 agy flash 3.8, 자막만 Speechmatics)는
        #   말 끝을 0.5~1초 늦게 잡는다 — 승인·납품된 Deep90·91·93 이 여기서 «발화 중간 절단» 가짜 반려됐다
        #   (소리 재측·소리 맞춤 보정·flash-high 모두 같은 자리에서 가짜 반려, 실측). 그래서 agy 전사면
        #   아래 절단 판정은 «주의» 로만 내고, 반려는 완성본 Speechmatics 낱말로 재는 s2pipe/이음매관문.py
        #   (한편 ④ 작표 맨 앞)가 한다. «결론 미포함» 게이트는 그대로 반려한다(대목 수준이라 agy 로 충분).
        from s2pipe.agy_asr import 원본전사_출처
        원agy = bool(큐들) and 원본전사_출처(_vtt) == "agy"
        절단판정 = warn if 원agy else bad
        agy표 = " (agy 원본 전사 추정 — 반려는 ④ 이음매 관문이 완성본 낱말로)" if 원agy else ""

        _활성표 = []

        def _말끝(c0, cap):
            end, b, e, th = 말끝_실측(_src, c0, cap)
            if e is not None:
                _활성표.append((b, e, th))
            return end

        def _말하는중(t):
            """t 직전 0.3초가 또렷한 말소리인가(바닥+11dB 평균) — 실측한 창 안에서만 답한다. 모르면 None."""
            for b, e, th in _활성표:
                i = int((t - b) / 0.1)
                if 3 <= i <= len(e):
                    return bool(float(e[i - 3:i].mean()) > th + 3.0)   # ★numpy bool 은 `is False` 에 안 걸린다
            return None

        if 가짜끝:
            # 옛 vtt — 조각 경계(t0·t1) 앞 5초 안에서 시작하는 큐만 실측한다(나머지는 게이트가 안 본다)
            경계 = [s["t0"] for s in segs] + [s["t1"] for s in segs]
            for i, c in enumerate(큐들):
                cap = 큐들[i + 1][0] - 0.05 if i + 1 < len(큐들) else c[0] + 8.0
                if any(x - 5.0 <= c[0] < x for x in 경계):
                    c[1] = max(c[0] + 0.3, _말끝(c[0], cap))
                else:
                    c[1] = max(c[0] + 0.3, min(cap, c[0] + 0.12 * len(c[3]) + 0.3))
        허용 = proj.get("결말절단허용") or []

        # ★결말 «늘려라» 의 벽 — 원본 암전·아웃트로 로고 (2026-10-03 루키치164: agy 큐 끝은 1~3초 늦게 잡혀 결말 말끝이
        #   로고 뒤로 가 있었다 — 이 주의가 «t1 을 암전 전까지 늘려라» 라며 실제로는 암전·로고 쪽으로 늘리라고 권했다.
        #   사람이 프레임으로 보고 끝을 로고 164.54 앞 164.45 로 두었다). 벽 = 조각 _엔드카드시작 · build.엔드카드시작(굽기·준비와
        #   같은 검출) · t1 뒤 첫 암전 프레임(s2pipe/경계자리.암전시각들 — 프레임마다). 이미 벽 앞이면 늘리라고 하지 않는다.
        _벽캐시 = {}

        def _끝벽(a, b):
            if "아웃트로" not in _벽캐시:
                _e = [x.get("_엔드카드시작") for x in segs if x.get("_엔드카드시작")]
                if _e:
                    _벽캐시["아웃트로"] = float(min(_e))
                else:
                    try:
                        from s2pipe.build import 엔드카드시작 as _엔드
                        _벽캐시["아웃트로"] = _엔드(_src, float(proj["source"].get("dur") or 0)) if os.path.exists(_src) else None
                    except (Exception, SystemExit):           # noqa: BLE001
                        _벽캐시["아웃트로"] = None
            # ★벽 판정은 s2pipe/경계자리.결말벽 한 곳 (2026-10-03 — 준비 여운 상한·prproj끝검사 납품 관문과 같은 자: 아웃트로 카드 ·
            #   첫 암전 프레임 · 카드 로고/바탕이 먼저 뜬 프레임 · 그 앞 페이드). 원본이 없으면 아웃트로만.
            _아 = _벽캐시["아웃트로"]
            if os.path.exists(_src):
                try:
                    from s2pipe.경계자리 import 결말벽 as _결말벽
                    벽, _까닭 = _결말벽(_src, a + 0.01, b, 아웃트로=_아)
                    return 벽
                except Exception:                          # noqa: BLE001
                    pass
            return _아 if _아 is not None and _아 > a - 0.05 else None

        for si, s in enumerate(segs):
            for c0, c1, tx, 글2 in 큐들:
                if len(글2) < 3 or not (s["t0"] <= c0 < s["t1"]) or c1 >= s["t1"] + 3.0:
                    continue
                끝추정 = "(실측)" if 가짜끝 else ""
                if si == len(segs) - 1:
                    if c1 + 0.7 > s["t1"] + 0.02:          # 0.02 = 부동소수 여유(304.2+0.7 > 304.9 오판)
                        벽 = _끝벽(s["t1"], c1 + 0.7)
                        if any(abs(c0 - h) < 0.3 for h in 허용):
                            warn.append(f"결말 발화 「{tx[:16]}」 {c0:.1f}~{c1:.1f}{끝추정} 가 t1={s['t1']:.1f} 에"
                                        f" 걸리지만 «결말절단허용» 명시로 통과")
                        elif 벽 is not None and 벽 <= s["t1"] + 0.3:
                            warn.append(f"결말 발화 「{tx[:16]}」 큐 끝 {c1:.1f}초{끝추정} 가 t1={s['t1']:.2f} 뒤지만 원본이"
                                        f" {벽:.2f}초부터 암전·로고다 — 더 늘릴 자리 없음(큐 끝이 늦게 잡힌 것 · 늘리지 말 것)."
                                        f" 결말 말끝 잘림은 ④ 이음매 관문(완성본 낱말)이 본다")
                        elif 벽 is not None:
                            절단판정.append(f"★결말 발화 끝 절단{agy표} — 마지막 조각이 {s['t1']:.1f}초에"
                                       f" 끝나는데 발화 「{tx[:16]}」 큐가 {c1:.1f}초{끝추정}까지다."
                                       f" t1 을 늘리되 원본 암전·로고 {벽:.2f}초 앞까지만(넘으면 로고·검은 화면이 들어온다)"
                                       f" (카드 위 보이스오버 등 사람이 확인한 예외만 결말절단허용: [{c0:.1f}])")
                            break
                        else:
                            절단판정.append(f"★결말 발화 끝 절단{agy표} — 마지막 조각이 {s['t1']:.1f}초에"
                                       f" 끝나는데 발화 「{tx[:16]}」 큐가 {c1:.1f}초{끝추정}까지다."
                                       f" t1 을 {c1 + 0.7:.1f}초 이상으로(암전 전까지) 늘려라"
                                       f" (카드 위 보이스오버 등 사람이 확인한 예외만 결말절단허용: [{c0:.1f}])")
                            break
                else:
                    if c0 + 0.25 <= s["t1"] < c1 - 0.25:
                        # 실측 vtt(가짜끝)는 «말소리가 컷까지 이어지는가»로 반려/주의를 가른다 —
                        # 문장 안 긴 쉼(«태용 씨가 … 확실히») 은 에너지로 못 가르니 사람이 큐 글을 읽고 판단한다.
                        if 가짜끝 and _말하는중(s["t1"]) is False:
                            warn.append(f"조각 {si} 큐 안 쉼에서 절단 — t1={s['t1']:.1f}, 「{tx[:16]}」"
                                        f" {c0:.1f}~{c1:.1f}{끝추정}. 문장 중간이면 t1 을 {c1 + 0.5:.1f} 이상으로")
                        else:
                            절단판정.append(f"★조각 {si} 발화 중간 절단{agy표} — t1={s['t1']:.1f} 인데 「{tx[:16]}」 큐가"
                                       f" {c0:.1f}~{c1:.1f}{끝추정}다. t1 을 {c1 + 0.5:.1f} 이상으로 늘리거나"
                                       f" {c0 - 0.1:.1f} 이전으로 당겨라")
                            break
                    elif c1 - 0.25 <= s["t1"] < c1 + 0.3:
                        warn.append(f"조각 {si} 꼬리 빠듯 — t1={s['t1']:.1f}, 「{tx[:12]}」 끝 {c1:.1f}{끝추정}")
            for c0, c1, tx, 글2 in 큐들:
                if len(글2) >= 3 and c0 < s["t0"] - 0.4 and c1 > s["t0"] + 0.3:
                    warn.append(f"조각 {si} 발화 중간 시작 — t0={s['t0']:.1f}, 「{tx[:12]}」 {c0:.1f}~{c1:.1f}{끝추정}")
        if 끝발화 and segs[-1]["t1"] < 끝발화 - 1.0:
            if proj.get("결말확인"):
                warn.append(f"원본 발화가 {끝발화:.0f}초까지 이어지지만 «결말확인» 명시로 통과"
                            f" — 마지막 조각 {segs[-1]['t1']:.0f}초")
            else:
                bad.append(f"★결론 미포함 — 원본 마지막 유의미 발화가 {끝발화:.0f}초인데 마지막"
                           f" 조각이 {segs[-1]['t1']:.0f}초에 끝난다. 스케치코미디의 결론은"
                           f" 마지막 부분에 있다(2026-09-07 사장님) — 엔딩 구간을 담아라."
                           f" 꼬리가 결론이 아닌 단순 아웃트로로 확인된 편만 «결말확인»: true")
    except Exception:
        pass

    for s in segs:
        ph = PHASES.get(s.get("phase"))
        if ph and s.get("punch", 0) < ph["min_punch"]:
            warn.append(f"P{s['phase']} {ph['name']} 조각의 punch {s['punch']}"
                        f" — 이 자리는 {ph['min_punch']} 이상이 어울린다")

    # ── ★나레이션 패딩 법칙. 읽을 시간보다 화면이 짧으면 다음 대사가 겹친다
    for i, s in enumerate(segs):
        nr = (s.get("narration") or "").strip()
        if not nr:
            continue
        # ★속도는 목소리마다 다르다 — config 에 실측값을 넣어 둔다(narration.sec_per_char).
        #   어림값을 쓰면 「나레이션이 화면보다 긴가」 판정이 통째로 어긋난다.
        need = len(nr) * n.get("sec_per_char", 0.15)
        if need > n["max_sec"]:
            bad.append(f"조각 {i} 나레이션이 {need:.1f}초짜리다 —"
                       f" {n['max_sec']:.0f}초 이내로 줄여라: {nr[:30]}")
        span = s["t1"] - s["t0"]
        if span < need:
            bad.append(f"★조각 {i} 패딩 부족 — 나레이션은 {need:.1f}초인데"
                       f" 화면은 {span:.1f}초다. 다음 대사가 겹쳐 튀어나온다")
        elif span < need + _g("나레이션.G-나레이션.패딩_여유_soft_sec", 0.5):
            warn.append(f"조각 {i} 패딩이 빠듯하다 (나레 {need:.1f}초 / 화면 {span:.1f}초)")
    nrs = [s for s in segs if (s.get("narration") or "").strip()]
    if not nrs:
        warn.append("나레이션이 하나도 없다 — 이 채널의 핵심 장치다")
    elif len(nrs) > _g("나레이션.G-나레이션.개수_권장", [1, 2])[1] + 1:
        warn.append(f"나레이션 {len(nrs)}개 — 1~2개면 충분하다. 많으면 설명이 된다")
    # ★★나레이션이 나오는 동안 원음이 죽는다. 그러니 **웃음이 터지는 자리에는
    #   얹으면 안 된다** — 훅과 펀치라인은 배우 말이 들려야 산다.
    for s in nrs:
        ph = s.get("phase")
        if ph in (1, 5):
            bad.append(f"★P{ph} {PHASES[ph]['name']} 에 나레이션이 있다 —"
                       f" 그 구간은 원음이 죽는다. **훅과 펀치라인은 배우 말이"
                       f" 들려야 한다**: {s['narration'][:24]}")
        elif s.get("punch", 0) >= 9:
            warn.append(f"punch {s['punch']} 조각에 나레이션이 있다 —"
                        f" 웃음이 터지는 대사를 덮는 것은 아닌지 본다")

    # ── 제목·해시태그
    # ★제목은 **껍데기가 정한 2줄**이다(sketch 템플릿). 후보는 그중 하나를 고르는
    #   것이므로 화면에 박히는 `title` 만 반려하고 나머지는 주의로 둔다.
    title = proj.get("title") or []
    if isinstance(title, str):
        title = [title]
    titles = proj.get("title_candidates") or ([title] if title else [])
    if not title:
        bad.append("제목이 없다")
    else:
        if len(title) != tb["lines"]:
            bad.append(f"제목이 {len(title)}줄 — 이 채널은 항상 {tb['lines']}줄이다:"
                       f" {' / '.join(title)}")
        for ln in title:
            if len(ln) > tb["max_chars"]:
                bad.append(f"제목 한 줄이 {len(ln)}자 — 상한 {tb['max_chars']}자다: {ln}")
        # ★상단 제목 ≠ 하단 원제 (2026-09-26 사장님 «원본제목이랑 상단 제목이 동일하네 이게 맞아?» — 싱글286·285).
        #   추천제목 후보 파일의 «대표 제목» 은 mp4 파일명 = 하단 출처 원제다. 그걸 상단에 고르면 위아래가
        #   같은 글이 된다. 길이만 보던 검사가 못 잡았다 — 글자를 비교해 같거나 거의 같으면 반려한다.
        import difflib as _dl
        _원제 = ((proj.get("credit") or {}).get("title") or "").strip()
        if _원제:
            _n = lambda s: re.sub(r"[^0-9A-Za-z가-힣]", "", s)
            _상, _하 = _n("".join(title)), _n(_원제)
            _닮음 = _dl.SequenceMatcher(None, _상, _하).ratio()
            if _상 and (_상 in _하 or _하 in _상 or _닮음 >= 0.75):
                bad.append(f"★상단 제목이 하단 원제와 같다(닮음 {_닮음:.2f}) — 상단 «{' / '.join(title)}»"
                           f" · 하단 «{_원제}». 상단은 내용에 맞춘 다른 제목으로(후보 4개 이상 → 사장님이 고름)")
        end = CFG["title_formula"]["end_mark"]
        if title and not title[-1].endswith(tuple(end)):
            bad.append(f"★제목 끝이 ? ! ... 이 아니다 — 호기심이 안 남는다:"
                       f" {title[-1]}")
    over = [t for t in titles
            if any(len(ln) > tb["max_chars"] for ln in (t if isinstance(t, list) else [t]))]
    if over:
        warn.append(f"후보 {len(over)}개가 한 줄 {tb['max_chars']}자를 넘는다 — 고를 때 뺀다")
    want = CFG["output"]["titles"]
    if len(titles) < want:
        warn.append(f"제목 후보 {len(titles)}개 — {want}개를 뽑는다")
    if not (proj.get("hashtag") or "").strip():
        warn.append("서브 해시태그가 없다")

    if len(proj.get("hooks") or []) < CFG["output"]["hook_lines"]:
        warn.append(f"후킹 대사 {len(proj.get('hooks') or [])}개 —"
                    f" {CFG['output']['hook_lines']}개를 뽑는다")

    # ── 자막
    subs = sorted(proj.get("subs", []), key=lambda x: x["t"])
    gaps = [(subs[i - 1]["t"], subs[i]["t"]) for i in range(1, len(subs))
            if subs[i]["t"] - subs[i - 1]["t"] >= _g("자막.G-자막공백.빈구간_warn_sec", 3.0)]
    if gaps:
        warn.append(f"자막이 3초 이상 비는 곳 {len(gaps)}군데"
                    f" (예: {gaps[0][0]:.0f}~{gaps[0][1]:.0f}초)")
    mx = CFG["layout"]["subtitle"]["max_chars"]
    longs = [s for s in subs if s.get("kind") != "narr" and len(s.get("text", "")) > mx]
    if longs:
        # ★2026-09-03 사장님(14자·의미단위는 절대 규칙) — 주의가 아니라 반려다.
        #   Deep04 에서 주의로 넘겼다가 20자 복원 줄이 화면 밖까지 넘쳤다.
        bad.append(f"자막 {len(longs)}줄이 {mx}자를 넘는다 — 예: {longs[0]['text'][:20]}")

    # ★구두점 금지 (정답지 G-구두점, hard · 2026-09-01 절대 규칙) — 서버 check.ts 와 같은 규칙
    banned = CFG["layout"]["subtitle"].get("구두점_금지") or []
    # ★숫자 사이 점·쉼표(4.5 · 1,000)는 구두점이 아니다 — sync 정돈과 같은 규칙(2026-09-28 싱글62: «평점 4.5» 가
    #   반려돼 «사 점 오» 로 풀어 써야 했다. sync 는 09-27 싱글185 때 숫자 사이 점을 남기게 고쳤는데 이 관문만 남아 있었다).
    import re as _re
    def _구두점검사용(t):
        return _re.sub(r"(?<=\d)[.,](?=\d)", "", t or "")
    dirty_s = [s for s in subs if any(ch in _구두점검사용(s.get("text")) for ch in banned)]
    dirty_n = [s for s in segs if any(ch in _구두점검사용(s.get("narration")) for ch in banned)]
    if dirty_s or dirty_n:
        ex = (dirty_s[0].get("text") if dirty_s else dirty_n[0].get("narration"))[:20]
        bad.append(f"★구두점 금지(절대 규칙) — 자막 {len(dirty_s)}줄·나레이션 {len(dirty_n)}건에"
                   f" 금지 글자({' '.join(banned)})가 있다. 마침표·말줄임은 지우고 쉼표는"
                   f" 공백으로 바꿔라 (예: {ex})")

    # ── ★나레 곁 대사 — 나레곁검사() 설명
    _b, _w = 나레곁검사(proj, subs)
    bad += _b
    warn += _w

    # ── ★나레 줄 = 나레 조각 (2026-10-03 루키치165 «초안자막쪼갬 이 나레 줄도 14자로 둘로 가름» · 204 «조각을 다시 짠 뒤
    #   나레 줄 시각이 옛 자리에 남음» — 납품 669편 중 갈림 85 · 옛 자리 274). 자막 표의 나레 줄은 조각에서 파생되는 값이라
    #   main() 이 검사·굽기 직전에 화자색.나레줄맞춤() 으로 덮는다 — 이 관문은 그 뒤에도 어긋난 것(다른 길로 들어온 값)을 막는
    #   최종 관문이다: 나레 줄 수 = 나레 조각 수 · 시작 = 조각 머리 ±0.05초 · 문구 = 조각 narration (subs·subs_before_sync).
    try:
        from s2pipe import 화자색 as _HS2
        for _m in _HS2.나레줄검사(proj, os.path.join(HERE, CFG["paths"]["work"], proj.get("slug", ""))):
            bad.append(f"★나레 줄 어긋남 — {_m}. 나레 줄은 조각에서 만든다: make.py 로 다시 돌리면 저절로 맞춘다"
                       " (s2pipe/화자색.py 나레줄맞춤)")
    except Exception as _e:                               # noqa: BLE001
        bad.append(f"나레 줄 관문 못 돎: {str(_e)[:80]}")

    # ── 원본·fps
    src = proj.get("source", {})
    if not src.get("fps"):
        bad.append("원본 fps 가 없다 — 마진이 프레임 단위라 fps 없이는 못 굽는다")
    mp4 = os.path.join(HERE, CFG["paths"]["work"], f"{src.get('id')}.mp4")
    if not os.path.exists(mp4):
        bad.append(f"원본 영상이 없다: {mp4}")

    return bad, warn


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    path = args[0] if os.path.isabs(args[0]) else os.path.join(HERE, args[0])
    proj = json.load(open(path, encoding="utf-8"))

    # ★나레 줄은 조각에서 파생 — 검사·굽기 직전 «한 곳» 에서 저장본을 조각 기준으로 덮는다 (2026-10-03 루키치165·204 —
    #   조각을 다시 짠 뒤 에이전트가 편마다 손으로 나레 줄 시각을 옮기고, 갈린 나레 줄을 손으로 지웠다). 대사 줄은 그대로.
    from s2pipe import 화자색 as _HS
    _바뀜 = _HS.나레줄맞춤(proj, os.path.join(HERE, CFG["paths"]["work"], proj.get("slug", "")))
    if _바뀜:
        json.dump(proj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        for _m in _바뀜:
            print(f"  나레 줄을 조각에서 다시 맞춤 — {_m}")

    bad, warn = check(proj, path)
    print(f"─ {os.path.basename(path)}")
    for w in warn:
        print(f"  주의  {w}")
    for b in bad:
        print(f"  반려  {b}")
    if bad:
        print(f"\n반려 {len(bad)}건 — 고쳐야 굽는다")
        return 1
    print("  통과" + (" (주의 있음)" if warn else ""))

    if "--check" in sys.argv:
        return 0

    from s2pipe import build
    # --화자색: 대사 줄 화자 색(⑦ 프리미어와 같은 판정) — 한편_sk.sh ⑥ 재굽기가 준다 (2026-09-28)
    return build.run_build(proj, path, 화자색켬="--화자색" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
