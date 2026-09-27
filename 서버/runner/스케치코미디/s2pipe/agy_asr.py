# 원본 전사를 agy(제미나이 구독)로 받는다 — Speechmatics(유료) 대신.
#
#   python -m s2pipe.agy_asr <원본.mp4> <출력.vtt> [--slug DeepNN] [--채널 "띱 Deep"] [--model ...]
#
# ★2026-09-26 사장님 결정(B안): «전사를 스피치매틱스로 하는 게 아니라 agy 로 하고 자막만 스피치매틱스로».
#   원본 전사(편시작 ③)는 agy 로, 완성본 재전사(한편 ③ s2pipe.asr)는 그대로 Speechmatics 다.
#   제미나이 시각은 Speechmatics 보다 거칠다(윈도우 실측 중앙 0.3초·최대 1~2초) — 그래서
#   vtt 머리에 «NOTE 출처 agy» 를 남기고, 시각을 정밀하게 쓰는 소비처(make 절단 게이트 등)는
#   이 표시를 보고 소리 실측으로 받친다(원본전사_출처()).
#
# ★영상은 통째로 한 번에 읽힌다 — 조각으로 잘라 읽히지 않는다 (2026-09-26 사장님 «영상을 통째로 읽어야해.
#   절대로 조각되서 읽으면 안되고»). 처음 판은 약 60초 조각으로 잘랐다 — «긴 걸 주면 뒤로 갈수록 시각이 밀린다»는
#   짐작 때문이었고, 통째 읽기와는 한 번도 견주지 않았다. 통째로 주면 앞뒤 흐름(사투리·이름·화자)을 다 본다.
# ★예외 하나 (2026-09-28 싱글126): 통째 답이 agy 출력 토큰 한도를 넘으면(생각이 출력의 85~90%) 같은 질문을 되풀이해도
#   또 넘는다 — 그때만 절반씩(겹침 2.5초) 나눠 묻고 잇는다(_구간전사). 통째 읽기를 먼저 한 번 묻는 순서는 그대로다.
#   끝에 «끝 확인»(끝 40초 따로 전사해 글 대조 — 싱글146 끝 대사 통째 누락)이 붙는다.
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import agy_gemini  # noqa: E402  서버/runner/agy_gemini.py

MODEL = "gemini-3.8-flash-high"  # ★2026-09-26 사장님 지정 «agy flash-high 로». (실측: 8분 원본 12분 41초 · low 는 약 3분 반)
MAX_CHARS = 28          # Speechmatics to_lines 와 같은 줄 상한
TRIES = 3               # agy 시도 횟수
AGY_여유 = 1.0           # 시각을 겹침 판정에 쓰는 소비처가 더하는 여유(초) — Deep93 실측(소리 맞춤 뒤)
                        #   시작 오차 중앙 0.25·90% 1.48초. 1.0 이면 대부분을 덮고, 넓힐수록 배제(확대)가 는다
출처표시 = "NOTE 출처 agy"   # vtt 머리 — 소비처가 이 줄로 거친 시각임을 안다

SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "t": {"type": "number"},
                    "e": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["t", "e", "text"],
            },
        }
    },
    "required": ["lines"],
}


def _dur(path):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(o.stdout.strip())


def _prompt(span, vocab, 부분=None):
    v = ""
    if vocab:
        v = ("\n등장 고유명사(이 표기로 적어라): " +
             ", ".join(x["content"] if isinstance(x, dict) else str(x) for x in vocab))
    if 부분 is None:
        머리 = (f"첨부한 영상(소리 포함)은 한국어 스케치 코미디 한 편 전체({span:.1f}초)다. "
              "처음부터 끝까지 들리는 말을 전부 받아 적어라.\n")
        기준 = "영상 0초 기준"
    else:
        머리 = (f"첨부한 영상(소리 포함)은 한국어 스케치 코미디 한 편에서 잘라 낸 한 구간({span:.1f}초)이다. "
              "이 구간의 처음부터 끝까지 들리는 말을 전부 받아 적어라.\n")
        기준 = "이 첨부 영상 0초 기준(원본 전체 시각이 아니다)"
    끝줄 = ("- 구간 맨 앞·맨 끝에서 말이 잘려 있으면 들린 부분만 적는다.\n" if 부분 is not None else "")
    return (
        머리 + "규칙:\n"
        "- 들린 그대로 적는다. 사투리·반말·더듬는 말·짧은 감탄(아, 어, 야)도 그대로. 없는 말을 지어내지 않는다.\n"
        "- 작은 목소리·전화 너머 목소리·겹치는 말도 빠뜨리지 않는다. 노래 가사·효과음은 적지 않는다.\n"
        f"- 한 줄은 {MAX_CHARS}자 이하. 말이 0.5초 이상 쉬면 새 줄. 화자가 바뀌면 새 줄.\n"
        f"- t = 그 줄 첫 음절이 소리 나기 시작하는 초, e = 마지막 음절 소리가 끝나는 초. {기준}, 소수 둘째 자리까지.\n"
        "- 시각은 추정하지 말고 소리를 듣고 정확히 맞춘다. 줄은 시간 순서대로.\n" + 끝줄 +
        '- 답은 JSON {"lines": [{"t": 0.44, "e": 0.92, "text": "..."}]} 하나만.' + v
    )


# ★출력 한도 초과 → 구간 나눠 전사 (2026-09-28 싱글126 — 원본 214초 통째 전사가 6번 모두 «exceeded the output
#   token limit»). agy 기록 실측: 잘린 답 14건(126·146·166·179·184·188·206·216초 원본)의 본문은 4.0~4.5천 자(74~94줄,
#   원본의 55~80% 지점)였고 생각이 2.5~3.8만 자로 출력의 85~90% — 반복 폭주가 아니라 «길이에 비례하는 생각+답» 이
#   한도를 넘은 것이다(같은 줄 되풀이 0~4개 = 짧은 감탄사). 같은 질문을 되풀이하면 또 넘는다(126: 6/6).
#   그래서 통째 읽기(2026-09-26 사장님 «통째로»)를 먼저 한 번 묻고, 한도를 넘었을 때만 절반씩(겹침 2.5초) 나눠 묻는다.
#   구간마다 답·생각이 절반이라 한도 안에 든다. 모델은 flash-high 그대로(사장님 결정).
겹침 = 2.5            # 이웃 구간이 서로 겹치는 초 — 경계(가운데)에서 가른다
최소구간 = 30.0       # 이보다 짧으면 더 안 나눈다
최대깊이 = 3          # 절반 나누기 최대 3번 = 최대 8구간
끝창 = 40.0           # 끝 확인 전사 창(초) — 로고 아웃트로(싱글벙글 3~10초)를 넘어 마지막 대사까지 들어오게


def _limit(span):
    return int(min(40, 8 + span / 60 * 4))          # 60초에 약 1.5분(high 실측) — 넉넉히


def _자르기(whole, t0, t1, work):
    """360p 전체에서 [t0, t1] 을 재인코딩으로 잘라 낸다(-i 뒤 -ss — 볼트 규칙 «-c copy 금지»)."""
    out = os.path.join(work, f"구간_{t0:07.2f}_{t1:07.2f}.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", whole, "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "64k",
                    "-ac", "1", out], check=True)
    return out


def _묻기(clip, span, vocab, model, log, caller, 부분=None):
    """agy 한 번(형식 오류·시각 늘어남이면 TRIES 번까지) → 첨부 0초 기준 줄 [{"t","e","text"}].
    출력 한도 초과는 agy_gemini.AgyOutputLimit 으로 바로 올라온다(되묻지 않는다)."""
    limit = _limit(span)
    what = "영상 전체" if 부분 is None else f"구간 {부분[0]:.1f}~{부분[1]:.1f}초"
    log(f"agy 전사 — {what} {span:.0f}초를 한 번에 ({model}, 시간 제한 {limit}분)")
    body = {"contents": [{"role": "user", "parts": [
                {"@inline_file": {"path": clip, "mime": "video/mp4"}},
                {"text": _prompt(span, vocab, 부분)}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA}}
    for k in range(TRIES):
        resp = agy_gemini.generate(body, caller=caller, limit_min=limit, model=model, log=log)
        if resp is None:
            log(f"  agy 실패 — 다시 ({k + 1}/{TRIES})")
            continue
        try:
            got = json.loads(agy_gemini.text_of(resp))["lines"]
        except (ValueError, KeyError, TypeError) as e:
            log(f"  답 형식 오류({e}) — 다시 ({k + 1}/{TRIES})")
            continue
        # ★시각 늘어남 관문 (2026-09-26 싱글280 실측): 통째 읽기 답의 시각이 원본보다 길게 세어져
        #   마지막 17줄이 원본 끝(156.5초)을 넘었다 — 잘라 붙이면 끝 1초에 몰려 plan 이 엉뚱한 자리(아웃트로
        #   카드)를 결말로 골랐다. 원본 길이를 넘는 줄이 있으면 틀린 답으로 보고 다시 읽힌다.
        # ★2026-09-27: 조금 늘어난 건(싱글282 — 3번 다 원본보다 2~4% 늘어남) 뒤의 자막띠시각 맞춤이 바로잡는다.
        #   원본 길이의 12% 를 넘게 늘어났을 때만 틀린 답으로 본다(280 1차 — 끝 17줄이 한곳에 몰린 경우).
        #   구간 전사도 같은 자로 잰다(구간 길이 기준).
        넘침 = [float(x.get("t", 0)) for x in got if float(x.get("t", 0)) > span * 1.12]
        if 넘침:
            log(f"  ★시각이 {what}({span:.1f}초)보다 늘어났다 — {len(넘침)}줄이 끝을 넘음(최대 {max(넘침):.1f}초). 다시 ({k + 1}/{TRIES})")
            continue
        lines = []
        for ln in got:
            t, e, tx = float(ln["t"]), float(ln["e"]), str(ln["text"]).strip()
            if not tx:
                continue
            t = max(t, 0.0)                               # 끝을 넘은 시각도 그대로 둔다 — 자막띠시각 맞춤이 옮긴다
            e = max(e, t + 0.2)
            lines.append({"t": t, "e": e, "text": tx})
        lines.sort(key=lambda x: x["t"])
        log(f"  {what}: {len(lines)}줄")
        return lines
    raise RuntimeError(f"agy 전사 실패({what}) — {TRIES}번 시도(답 형식 오류 또는 시각 늘어남)")


def _글(s):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s or "")


def _닮음(a, b):
    """두 줄 글이 같은 말인가 — 한쪽이 다른 쪽을 품거나 글자 두 개씩 겹침(자카드) 0.5 이상. 2자 미만은 비교 안 함."""
    x, y = _글(a), _글(b)
    if len(x) < 2 or len(y) < 2:
        return False
    if x in y or y in x:
        return True
    bx = {x[i:i + 2] for i in range(len(x) - 1)}
    by = {y[i:i + 2] for i in range(len(y) - 1)}
    return len(bx & by) / max(1, len(bx | by)) >= 0.5


def _잇기(A, B, 경계, log=print):
    """이웃 구간 전사 A(앞)·B(뒤) → 하나. 겹침 가운데(경계)에서 가른다 — A 는 경계 앞 줄, B 는 경계부터.
    경계 양쪽 3초 안에서 같은 말(_닮음)이 두 번 나오면 B 쪽을 뺀다(두 구간이 한 줄을 서로 조금 다른 시각으로 들은 경우)."""
    a = [x for x in A if x["t"] < 경계]
    b = [x for x in B if x["t"] >= 경계]
    앞끝 = [x for x in a if x["t"] >= 경계 - 3.0]
    뺌 = [y for y in b if y["t"] < 경계 + 3.0 and any(_닮음(y["text"], x["text"]) for x in 앞끝)]
    if 뺌:
        log(f"  구간 잇기 {경계:.1f}초 — 겹친 줄 {len(뺌)}개 뺌: " + " / ".join(y["text"] for y in 뺌))
    return a + [y for y in b if y not in 뺌]


def _구간전사(whole, t0, t1, dur, vocab, model, log, caller, work, 깊이=0, 나눠=False):
    """원본 [t0, t1] → 원본 시각 기준 줄. 통째(t0=0, t1=dur)면 360p 전체를 그대로 준다.
    출력 한도를 넘으면(AgyOutputLimit) 절반씩 겹쳐 나눠 다시 묻는다 — 최대깊이·최소구간까지."""
    span = t1 - t0
    if not 나눠:
        통째 = t0 <= 0.0 and t1 >= dur - 0.05
        clip = whole if 통째 else _자르기(whole, t0, t1, work)
        try:
            rel = _묻기(clip, span, vocab, model, log, caller, None if 통째 else (t0, t1))
            return [{"t": x["t"] + t0, "e": x["e"] + t0, "text": x["text"]} for x in rel]
        except agy_gemini.AgyOutputLimit:
            if 깊이 >= 최대깊이 or span / 2 < 최소구간:
                raise
            log(f"  ★출력 한도 초과 — {t0:.1f}~{t1:.1f}초를 절반씩(겹침 {겹침}초) 나눠 다시 묻는다")
    mid = (t0 + t1) / 2
    A = _구간전사(whole, t0, min(t1, mid + 겹침 / 2), dur, vocab, model, log, caller, work, 깊이 + 1)
    B = _구간전사(whole, max(t0, mid - 겹침 / 2), t1, dur, vocab, model, log, caller, work, 깊이 + 1)
    return _잇기(A, B, mid, log)


def _끝확인(whole, dur, lines, vocab, model, log, caller, work, 기억=None):
    """전사가 원본 끝까지 닿았는가 — 끝 «끝창» 초를 따로 전사해 글로 대조한다(시각은 늘어나 있을 수 있어 못 믿는다).
    ★2026-09-28 싱글146: 통째 전사가 146초 뒤 대사(~156초)를 통째로 빠뜨렸는데 마지막 줄 시각은 162.05초(원본 162.5초)로
      늘어나 있어 «마지막 줄 시각 ≥ 원본 길이 − 몇 초» 같은 시각 검사로는 안 잡혔다(그 뒤 맞춤 배율 0.710 으로 28초 어긋남).
    돌려주는 것: (줄, 판정) — 판정 "닿음"·"끝없음"(끝 창에 말 없음)·"붙임"(모자란 끝 줄만 붙임)·"다시"(시각이 3초 넘게
    어긋나 붙일 수 없음 → 부르는 쪽이 나눠 다시 전사)."""
    t0 = max(0.0, dur - 끝창)
    if t0 <= 0.0:
        return lines, "닿음"
    if 기억 is not None and "끝" in 기억:
        끝 = 기억["끝"]                                          # 나눠 다시 한 뒤 두 번째 확인 — 끝 전사를 다시 묻지 않는다
    else:
        끝 = _구간전사(whole, t0, dur, dur, vocab, model, log, caller + "#끝확인", work)
        if 기억 is not None:
            기억["끝"] = 끝
    끝말 = [x for x in 끝 if len(_글(x["text"])) >= 3]
    if not 끝말:
        log(f"  끝 확인 — 끝 {끝창:.0f}초에 말 없음(아웃트로)")
        return lines, "끝없음"
    뒤 = lines[len(lines) // 2:]                                  # 시각이 늘어났을 수 있어 뒤 절반 전체에서 찾는다
    맞음 = [i for i, x in enumerate(끝말) if any(_닮음(x["text"], m["text"]) for m in 뒤)]
    모자람 = 끝말[맞음[-1] + 1:] if 맞음 else 끝말
    log(f"  끝 확인 — 끝 {끝창:.0f}초 전사 {len(끝)}줄 중 본 전사에 있는 줄 {len(맞음)}/{len(끝말)}"
        + (f" · 없는 끝 줄 {len(모자람)}개({모자람[0]['t']:.1f}초~)" if 모자람 else ""))
    if len(모자람) < 2:
        return lines, "닿음"
    if not 맞음:
        return lines, "다시"
    닻 = 끝말[맞음[-1]]
    m = max((m for m in 뒤 if _닮음(닻["text"], m["text"])), key=lambda m: m["t"])
    Δ = m["t"] - 닻["t"]
    if abs(Δ) > 3.0:
        log(f"  끝 확인 — 이음 줄 «{닻['text']}» 시각이 본 전사 {m['t']:.1f}초 · 끝 전사 {닻['t']:.1f}초로 {Δ:+.1f}초 어긋나 붙일 수 없다")
        return lines, "다시"
    남김 = [x for x in lines if x["t"] <= m["t"]]
    붙임 = [x for x in 끝 if x["t"] > 닻["t"] + 0.05]
    log(f"  끝 확인 — 모자란 끝 {붙임[0]['t']:.1f}~{붙임[-1]['e']:.1f}초 {len(붙임)}줄을 끝 전사로 붙임"
        f"(본 전사 {len(lines) - len(남김)}줄 교체)")
    return 남김 + 붙임, "붙임"


def transcribe(src, vocab=None, model=None, log=print, caller="스케치코미디/agy_asr", 맞춤=False, 원시=None, 나눠=False):
    """원본 영상 전체 → [{"t","e","text"}]. 먼저 agy 한 번에 통째로 읽힌다(2026-09-26 사장님 «통째로»).
    출력 한도를 넘으면(2026-09-28 싱글126) 그때만 절반씩 나눠 묻고 잇는다 — _구간전사.
    끝에 «끝 확인»(2026-09-28 싱글146) — 끝 40초를 따로 들어 본 전사에 없는 끝 대사가 있으면 그 줄만 붙이고,
    시각이 어긋나 붙일 수 없으면 나눠 다시 전사한다. 나눠 다시 한 뒤에도 끝이 모자라면 RuntimeError(멈춤).
    끝내 실패하면 RuntimeError (또는 agy_gemini.AgyStop — 영상 판정이라 EvoLink 로 넘기지 않는다).
    나눠=True 는 처음부터 절반씩 나눠 묻는다(시험·재실측용).
    맞춤(소리 경계 보정)은 기본 끔 — Deep91 flash-high 에서 가짜 반려를 1→4건으로 늘렸다(2026-09-26 실측)."""
    model = model or MODEL
    work = tempfile.mkdtemp(prefix="agy_asr_")
    aud = os.path.join(work, "원본.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                    "-b:a", "64k", aud], check=True)
    dur = _dur(aud)
    # 영상 전체를 360p 로만 줄인다 — 길이·순서는 그대로, 올리는 용량만 줄인다
    whole = os.path.join(work, "원본_전체_360p.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", "scale=-2:360", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-ac", "1", whole],
                   check=True)
    got = _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=나눠)
    # ★줄 수 관문 (2026-09-28 싱글116 — agy 가 «...» 1줄만 준 전사를 통과시켰고, 끝 확인도 «아웃트로 말 없음» 으로 넘어갔다).
    #   스케치는 대사가 빽빽하다(실측 1줄/1.5~2.5초) — 10초에 1줄도 안 되면 잘못 받은 답이다. 나눠서 한 번 다시, 그래도면 멈춘다.
    최소 = max(5, int(dur / 10))
    if len(got) < 최소:
        log(f"  ★전사가 {len(got)}줄뿐이다(원본 {dur:.0f}초 · 최소 {최소}) — 절반씩 나눠 다시 전사한다")
        got = _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=True)
        if len(got) < 최소:
            raise RuntimeError(f"agy 전사가 {len(got)}줄뿐이다(원본 {dur:.0f}초) — 잘못 받은 답. 준비.sh NNN --다시")
    기억 = {}
    got, 판정 = _끝확인(whole, dur, got, vocab, model, log, caller, work, 기억)
    if 판정 == "다시" and not 나눠:
        log("  ★끝 확인 — 통째 전사가 원본 끝까지 닿지 않았다. 절반씩 나눠 다시 전사한다")
        got = _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=True)
        got, 판정 = _끝확인(whole, dur, got, vocab, model, log, caller, work, 기억)   # 끝 전사는 기억에서 — 다시 안 묻는다
    if 판정 == "다시":
        raise RuntimeError("agy 전사가 원본 끝까지 닿지 않는다 — 나눠 다시 전사해도 끝 40초 대사가 본 전사에 없다")
    lines = [{"t": round(x["t"], 2), "e": round(x["e"], 2), "text": x["text"]} for x in got]
    lines.sort(key=lambda x: x["t"])
    log(f"  {len(lines)}줄 (끝 확인 {판정})")
    if 원시:                                           # 맞춤 전 모델 시각 그대로(시험·대조용)
        write_vtt(lines, 원시, model or agy_gemini.DEFAULT_MODEL)
    if not 맞춤:
        return lines
    # 모델 시각을 실제 말소리 경계에 끌어다 맞춘다 — Deep93 실측: 창 1.0 이 가장 좋았다
    #   (시작 오차 중앙 0.38→0.25초 · 90% 1.71→1.48초. 창 0.5·1.5 는 그보다 못함)
    lines, moved = 소리맞춤(lines, aud, 1.0)
    log(f"  소리 경계 맞춤 — {moved}/{len(lines)}줄 시작을 옮김")
    return lines


def 말소리_지도(path, 프레임=0.05, 이음=0.25):
    """원본 전체의 말소리 구간 [(시작, 끝)] — 말대역(800~3500Hz) 에너지가 주변 8초 바닥(20% 백분위)
    +8dB 를 넘는 프레임. «이음» 초보다 짧은 끊김은 잇고, 0.15초보다 짧은 소리는 버린다."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "s16le", "-"], capture_output=True, check=True)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
    win = int(16000 * 프레임)
    n = len(a) // win
    if n < 20:
        return []
    fr = a[:n * win].reshape(n, win) * np.hanning(win)
    spec = np.abs(np.fft.rfft(fr, axis=1))
    f = np.fft.rfftfreq(win, 1 / 16000)
    e = 20 * np.log10(spec[:, (f > 800) & (f < 3500)].sum(axis=1) + 1e-6)
    half = int(4.0 / 프레임)
    floor = np.array([np.percentile(e[max(0, i - half):i + half], 20) for i in range(0, n, 10)])
    floor = np.repeat(floor, 10)[:n]
    on = e > floor + 8.0
    segs, s = [], None
    for i, v in enumerate(on):
        if v and s is None:
            s = i
        elif not v and s is not None:
            segs.append([s * 프레임, i * 프레임])
            s = None
    if s is not None:
        segs.append([s * 프레임, n * 프레임])
    merged = []
    for g in segs:
        if merged and g[0] - merged[-1][1] < 이음:
            merged[-1][1] = g[1]
        else:
            merged.append(g)
    return [(round(x, 2), round(y, 2)) for x, y in merged if y - x >= 0.15]


def 소리맞춤(lines, path, 창=1.0):
    """agy 줄 시각을 실제 말소리 경계로 끌어다 맞춘다 — 시작은 ±창 안 가장 가까운 말 시작,
    끝은 ±창 안 가장 가까운 말 끝. 가까운 경계가 없으면 모델 시각을 그대로 둔다.
    ★Deep93 실측(2026-09-26): 영상 방식 agy 시작 오차 중앙 0.38·90% 1.71초 → 창 1.0 맞춤 뒤 0.25·1.48초."""
    지도 = 말소리_지도(path)
    if not 지도:
        return lines, 0
    # 끝은 «덩어리» 기준 — 0.55초 이상 쉬면 끊긴 말(Speechmatics to_lines gap 과 같다).
    # ★2026-09-26 Deep90·91·93 실측: 끝을 «가장 가까운 말소리 끝»에 맞췄더니 짧은 틈(0.5~1초) 너머
    #   다음 말까지 한 줄로 늘어나, 편집이 그 틈에서 자른 자리를 make 가 «발화 중간 절단» 으로 반려했다
    #   (승인·납품된 4편 중 3편 가짜 반려). 그래서 끝 = 그 줄이 시작한 덩어리의 끝, 다음 줄 시작 전까지.
    덩어리 = 말소리_지도(path, 이음=0.55)
    starts = [x for x, _ in 지도]
    moved = 0
    for ln in lines:
        t0 = min(starts, key=lambda x: abs(x - ln["t"]))
        if abs(t0 - ln["t"]) <= 창:
            moved += t0 != ln["t"]
            ln["t"] = t0
        e_agy = ln["e"]
        r = next(((x, y) for x, y in 덩어리 if y > ln["t"] + 0.1), None)
        if r is not None:
            e = r[1]
            if e < e_agy - 창:
                # 줄 하나가 쉼을 사이에 둔 덩어리 여럿에 걸친다 — 모델 끝에 가장 가까운 덩어리 끝으로
                cand = [y for _, y in 덩어리 if ln["t"] + 0.2 < y <= e_agy + 창]
                e = min(cand, key=lambda y: abs(y - e_agy)) if cand else e
            ln["e"] = min(e, e_agy + 창)
        ln["e"] = max(ln["e"], ln["t"] + 0.2)
    lines.sort(key=lambda x: x["t"])
    for a, b in zip(lines, lines[1:]):                 # 다음 줄 시작을 넘지 않는다
        if b["t"] > a["t"] + 0.25:
            a["e"] = max(a["t"] + 0.2, min(a["e"], round(b["t"] - 0.05, 2)))
    return lines, moved


def write_vtt(lines, path, model=""):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"WEBVTT\n\n{출처표시} {model}\n\n")
        for ln in lines:
            t, e = ln["t"], ln["e"]
            f.write(f"{int(t//3600):02d}:{int(t%3600//60):02d}:{t%60:06.3f} --> "
                    f"{int(e//3600):02d}:{int(e%3600//60):02d}:{e%60:06.3f}\n{ln['text']}\n\n")


def 원본전사_출처(vtt_path):
    """'agy' | 'speechmatics' — 시각을 정밀하게 쓰는 소비처가 받침(소리 실측)을 켤지 가른다."""
    try:
        with open(vtt_path, encoding="utf-8") as f:
            head = f.read(200)
    except OSError:
        return "speechmatics"
    return "agy" if 출처표시 in head else "speechmatics"


def 말소리_구간(path, t_guess, 창=1.2, 쉼=0.6):
    """agy 시각(t_guess) 언저리에서 실제 말소리 구간을 잰다 → (시작, 끝) 또는 None.
    말대역(800~3500Hz) 에너지가 바닥(창 20% 백분위)+8dB 를 넘으면 말 — make.py 말끝_실측 과 같은 기준.
    시작 = t_guess±창 안의 첫 말 프레임, 끝 = 그 뒤 «쉼» 초 이상 조용해지기 직전."""
    try:
        import numpy as np
    except ImportError:
        return None
    b = max(t_guess - 창 - 3.0, 0.0)
    d = 창 * 2 + 3.0 + 8.0
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{b:.2f}", "-t", f"{d:.2f}", "-i", path,
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
    win = 1600                                     # 0.1초
    if len(a) < win * 8:
        return None
    f = np.fft.rfftfreq(win, 1 / 16000)
    sel = (f > 800) & (f < 3500)
    h = np.hanning(win)
    e = np.array([20 * np.log10(np.abs(np.fft.rfft(a[i:i + win] * h))[sel].sum() + 1e-6)
                  for i in range(0, len(a) - win, win)])
    spk = e > float(np.percentile(e, 20)) + 8.0
    lo = max(0, int((t_guess - 창 - b) / 0.1))
    hi = min(len(spk), int((t_guess + 창 - b) / 0.1) + 1)
    on = next((i for i in range(lo, hi) if spk[i]), None)
    if on is None:
        return None
    last, gap = on, 0
    for i in range(on, len(spk)):
        if spk[i]:
            last, gap = i, 0
        else:
            gap += 1
            if gap >= int(쉼 / 0.1):
                break
    return round(b + on * 0.1, 2), round(b + (last + 1) * 0.1, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--채널", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--나눠", action="store_true", help="처음부터 절반씩 나눠 전사(시험·재실측용)")
    a = ap.parse_args()
    vocab = []
    if a.slug:
        from .asr import load_vocab
        vocab = load_vocab(a.slug, channel=a.채널)
    lines = transcribe(a.src, vocab, a.model, 나눠=a.나눠)
    write_vtt(lines, a.out, a.model or MODEL)
    print(f"전사 {len(lines)}줄 → {a.out}")


if __name__ == "__main__":
    main()
