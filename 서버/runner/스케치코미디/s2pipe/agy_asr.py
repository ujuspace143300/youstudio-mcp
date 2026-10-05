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
#
# ★2026-09-29 밤 «구간 시각 대조» (점심이네 64편 배치 — 통째 전사 시각이 틀렸는데 편시작 관문이 못 잡음):
#   실측(완성본 Speechmatics 를 keep 조각으로 되돌린 참 시작 대조 · 편마다 참 9~40줄):
#     · 3 첫 전사: 뒤로 갈수록 늘어나 «야 튀어» 참 206.4초 → 247.9초(참 대조 중앙 37.9·최대 42.3초). 마지막 줄이 원본 256초 안이라
#       «원본 × 1.12 넘는 줄» 관문을 지났고, 끝 40초 창은 말이 없어(아웃트로) «끝없음» 으로 지났다 — 본 전사는 그 창에 줄이 여럿 있었는데.
#     · 10: 통째 3번 다 1.5배(마지막 줄 436.2·436.45·436.5초 / 원본 290.5초) → 3번 다 버리고 멈춤. 절반 전사(146.5초씩)는 참 최대 0.65초.
#     · 53: 끝 110초가 +16~21초(참 최대 22.9초) — 끝 확인은 «글이 본 전사 뒤 절반에 있나» 만 봐서 12/12 닿음.
#     · 맞춤 전 참 대조에서 2초 넘게 틀린 줄이 있는 편 25/64(2·9·13·15·22·23·32·35·38·44·47·49·53·62…) — 틀림은 거의 다 «뒤로 갈수록 커지는
#       늘어남» 이고(9: 0~120초 0.1~0.8 → 150~210초 5.3~5.8) 몇 편은 가운데 한 덩어리만(22 90~120초 +2.5~3.0 · 62 210초 +5.2 · 44 330초 +4.5).
#     · 짧은 창(40초)은 믿을 만하다: agy 기록에 남은 끝 창 답 49개의 참 대조 — 창마다 최대 오차의 중앙 0.65초(아래 창 정확도 표는
#       검수도구/시각대조평가.py). 150초 절반은 가끔 2~4초 틀린 덩어리가 있었다(15 뒤 절반 최대 4.08초).
#   클래스: «전사 시각을 원본 기준 독립 자로 구간마다 재는 관문이 없다». 끝 확인은 끝 한 창에서 글만(시각은 안) 봤고, 늘어남 관문은 원본 길이
#     한 점만 봤고, 자막띠시각은 박힌 카드와의 상대 비교라 거부되면(점심이네 64편 중 32편) 맞춤 전 시각이 맞는지 아무도 안 쟀다 —
#     박힌 자막 카드는 점심이네에서 맞춤 자로도 못 썼다(새 맞춤이 참 대조 최대 13~74초로 틀린 편 5/12).
#   수리(_대조): 원본 전체를 40초 창(겹침 2.5초)으로 빈틈없이 따로 전사해(창마다 시각이 믿을 만함) 본 전사 줄과 글로 맞추고,
#     이웃 닻 어긋남이 2초 넘는 자리만 창 시각으로 옮긴다(그 안이면 통째 시각 그대로 — 통째가 맞을 때는 창보다 정확하다).
#     옮길 근거가 창 하나뿐인 덩어리는 그 자리를 한 번 더 따로 들어(두 창 확인) 더 가까운 쪽을 쓴다 — 창도 한 창 안에서 늘어날 때가
#     있다(45 36~76초 창 1.16배). 글은 통째 읽기 그대로다(2026-09-26 사장님 «통째로» — 창은 시각 자).
#     본 전사가 창들과 거의 안 맞으면(대조율·닻 모자람) 절반씩 나눠 다시 전사해 같은 창으로 다시 잰다(창은 다시 안 묻는다). 그래도면 멈춘다.
#     창 답·통째 답·절반 답은 원본 옆 캐시(<원본>.agy전사/)에 저장한다 — 한도·시간으로 끊겨도 다시 돌리면 받은 것은 다시 안 묻는다.
#   agy 글자는 여기서도 자막 재료가 아니다(파악용) — 자막은 여전히 완성본 Speechmatics.
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import agy_gemini  # noqa: E402  서버/runner/agy_gemini.py
try:  # ffmpeg·ffprobe 스레드 상한은 ff.명령 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
    from . import ff
except ImportError:  # 단독 실행(python s2pipe/x.py)
    import ff  # type: ignore

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
                # ★e 는 없어도 받는다 (2026-09-29 점심이네28 — 통째 답 3번 중 마지막이 «$.lines[70].e 가 없다» 한 칸 때문에
                #   183줄 답 전체를 버리고 멈췄다). 빠진 끝은 _묻기 가 다음 줄 시작 앞으로 채운다.
                "required": ["t", "text"],
            },
        }
    },
    "required": ["lines"],
}


def _dur(path):
    o = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path]), capture_output=True, text=True, check=True)
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
    subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", whole, "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "64k",
                    "-ac", "1", out]), check=True)
    return out


class 시각늘어남(RuntimeError):
    """통째·절반 답이 TRIES 번 다 원본(구간) 길이의 12% 넘게 늘어났다 — _구간전사 가 절반씩 나눠 다시 묻는다.
    ★2026-09-29 점심이네10: 통째 3번 다 1.5배(436/290초)라 RuntimeError 로 멈췄고, 에이전트가 임시 스크립트로 절반씩 나눠 전사했다
      (참 최대 0.65초). 출력 한도 초과(AgyOutputLimit)와 같은 길로 보낸다."""


def _캐시파일(캐시, 부분, span, model, prompt):
    """창·통째·절반 답 저장 자리 — 같은 원본·구간·모델·질문이면 같은 파일(질문이 바뀌면 이름도 바뀐다)."""
    if not 캐시:
        return None
    h = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]
    what = "전체" if 부분 is None else f"{부분[0]:08.2f}_{부분[1]:08.2f}"
    return os.path.join(캐시, f"{what}_{span:.2f}_{model}_{h}.json")


def _줄다듬기(got):
    """agy 답 줄 → [{"t","e","text"}] (첨부 0초 기준). 빠진 끝(e)은 다음 줄 시작 앞 · 없으면 시작 + 글자당 0.15초(0.2초 이상)."""
    rows = []
    for ln in got:
        try:
            t = float(ln["t"])
        except (KeyError, TypeError, ValueError):
            continue
        tx = str(ln.get("text", "")).strip()
        if not tx:
            continue
        e = ln.get("e")
        try:
            e = float(e) if e is not None else None
        except (TypeError, ValueError):
            e = None
        rows.append([max(t, 0.0), e, tx])                 # 끝을 넘은 시각도 그대로 둔다 — 구간 대조가 옮긴다
    rows.sort(key=lambda x: x[0])
    for i, r in enumerate(rows):
        if r[1] is None:
            nxt = next((x[0] for x in rows[i + 1:] if x[0] > r[0] + 0.25), None)
            guess = r[0] + max(0.2, 0.15 * len(_글(r[2])))
            r[1] = min(guess, nxt - 0.05) if nxt is not None else guess
        r[1] = max(r[1], r[0] + 0.2)
    return [{"t": t, "e": e, "text": tx} for t, e, tx in rows]


def _묻기(clip, span, vocab, model, log, caller, 부분=None, 캐시=None, 늘어남받음=False):
    """agy 한 번(형식 오류·시각 늘어남이면 TRIES 번까지) → 첨부 0초 기준 줄 [{"t","e","text"}].
    출력 한도 초과는 agy_gemini.AgyOutputLimit 으로 바로 올라온다(되묻지 않는다). 늘어남이 TRIES 번이면 시각늘어남.
    캐시(폴더)를 주면 받은 답을 저장하고, 같은 질문은 저장본을 쓴다(2026-09-29 — 점심이네10 절반 전사가 한도로 끊겨 받은 절반을 버림).
    늘어남받음=True 면 늘어난 답도 받는다 — 뒤의 구간 시각 대조가 창 시각으로 옮긴다(2026-09-29 점심이네10 — 1.5배 늘어난 통째 답도
      글은 멀쩡했다: 91·87·97줄 / 절반 전사 94줄). 시각 대조의 자가 되는 창 전사(늘어남받음=False)는 예전처럼 버리고 다시 묻는다."""
    limit = _limit(span)
    what = "영상 전체" if 부분 is None else f"구간 {부분[0]:.1f}~{부분[1]:.1f}초"
    prompt = _prompt(span, vocab, 부분)
    cf = _캐시파일(캐시, 부분, span, model, prompt)
    if cf and os.path.exists(cf):
        try:
            lines = json.load(open(cf, encoding="utf-8"))["lines"]
            log(f"agy 전사 — {what}: 저장본 {len(lines)}줄 씀({os.path.basename(cf)})")
            return lines
        except (OSError, ValueError, KeyError):
            pass
    log(f"agy 전사 — {what} {span:.0f}초를 한 번에 ({model}, 시간 제한 {limit}분)")
    body = {"contents": [{"role": "user", "parts": [
                {"@inline_file": {"path": clip, "mime": "video/mp4"}},
                {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA}}
    늘어 = 0
    for k in range(TRIES):
        resp = agy_gemini.generate(body, caller=caller, limit_min=limit, model=model, log=log)
        if resp is None:
            log(f"  agy 실패 — 다시 ({k + 1}/{TRIES})")
            continue
        try:
            got = json.loads(agy_gemini.text_of(resp))["lines"]
            lines = _줄다듬기(got)
        except (ValueError, KeyError, TypeError) as e:
            log(f"  답 형식 오류({e}) — 다시 ({k + 1}/{TRIES})")
            continue
        # ★시각 늘어남 관문 (2026-09-26 싱글280 실측): 통째 읽기 답의 시각이 원본보다 길게 세어져
        #   마지막 17줄이 원본 끝(156.5초)을 넘었다 — 잘라 붙이면 끝 1초에 몰려 plan 이 엉뚱한 자리(아웃트로
        #   카드)를 결말로 골랐다. 원본 길이를 넘는 줄이 있으면 틀린 답으로 보고 다시 읽힌다.
        # ★2026-09-27: 조금 늘어난 건(싱글282 — 3번 다 원본보다 2~4% 늘어남) 뒤의 자막띠시각 맞춤이 바로잡는다.
        #   원본 길이의 12% 를 넘게 늘어났을 때만 틀린 답으로 본다(280 1차 — 끝 17줄이 한곳에 몰린 경우).
        #   구간 전사도 같은 자로 잰다(구간 길이 기준).
        # ★2026-09-29: 통째·절반 답(늘어남받음)은 늘어나도 받는다 — 시각은 구간 시각 대조가 창으로 바로잡는다(위 머리 주석).
        #   이 관문은 원본 길이 한 점만 봐서 3 첫 전사(1.2배 늘었는데 아웃트로 40초 덕에 마지막 줄 247.9 < 256초)를 못 잡았다.
        넘침 = [x["t"] for x in lines if x["t"] > span * 1.12]
        if 넘침 and not 늘어남받음:
            늘어 += 1
            log(f"  ★시각이 {what}({span:.1f}초)보다 늘어났다 — {len(넘침)}줄이 끝을 넘음(최대 {max(넘침):.1f}초). 다시 ({k + 1}/{TRIES})")
            continue
        if 넘침:
            log(f"  ★시각이 {what}({span:.1f}초)보다 늘어났다 — {len(넘침)}줄이 끝을 넘음(최대 {max(넘침):.1f}초). "
                "받고 구간 시각 대조로 바로잡는다")
        u = resp.get("usageMetadata") or {}
        log(f"  {what}: {len(lines)}줄 · agy 토큰 {u.get('totalTokenCount') or '-'}")
        if cf:
            try:
                os.makedirs(캐시, exist_ok=True)
                tmp = f"{cf}.{os.getpid()}.{time.time_ns()}"
                json.dump({"lines": lines, "what": what, "model": model, "tokens": u.get("totalTokenCount")},
                          open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                os.replace(tmp, cf)
            except OSError:
                pass
        return lines
    if 늘어 == TRIES:
        raise 시각늘어남(f"agy 전사 실패({what}) — {TRIES}번 다 시각이 늘어남")
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


def _구간전사(whole, t0, t1, dur, vocab, model, log, caller, work, 깊이=0, 나눠=False, 캐시=None, 늘어남받음=False):
    """원본 [t0, t1] → 원본 시각 기준 줄. 통째(t0=0, t1=dur)면 360p 전체를 그대로 준다.
    출력 한도를 넘거나(AgyOutputLimit) TRIES 번 다 늘어나면(시각늘어남) 절반씩 겹쳐 나눠 다시 묻는다 — 최대깊이·최소구간까지."""
    span = t1 - t0
    if not 나눠:
        통째 = t0 <= 0.0 and t1 >= dur - 0.05
        부분 = None if 통째 else (t0, t1)
        cf = _캐시파일(캐시, 부분, span, model, _prompt(span, vocab, 부분))
        clip = whole if 통째 or (cf and os.path.exists(cf)) else _자르기(whole, t0, t1, work)
        try:
            rel = _묻기(clip, span, vocab, model, log, caller, 부분, 캐시=캐시, 늘어남받음=늘어남받음)
            return [{"t": x["t"] + t0, "e": x["e"] + t0, "text": x["text"]} for x in rel]
        except (agy_gemini.AgyOutputLimit, 시각늘어남) as ex:
            if 깊이 >= 최대깊이 or span / 2 < 최소구간:
                raise
            왜 = "출력 한도 초과" if isinstance(ex, agy_gemini.AgyOutputLimit) else f"{TRIES}번 다 시각 늘어남"
            log(f"  ★{왜} — {t0:.1f}~{t1:.1f}초를 절반씩(겹침 {겹침}초) 나눠 다시 묻는다")
    mid = (t0 + t1) / 2
    A = _구간전사(whole, t0, min(t1, mid + 겹침 / 2), dur, vocab, model, log, caller, work, 깊이 + 1,
              캐시=캐시, 늘어남받음=늘어남받음)
    B = _구간전사(whole, max(t0, mid - 겹침 / 2), t1, dur, vocab, model, log, caller, work, 깊이 + 1,
              캐시=캐시, 늘어남받음=늘어남받음)
    return _잇기(A, B, mid, log)


def _끝확인(whole, dur, lines, vocab, model, log, caller, work, 기억=None, 캐시=None):
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
        끝 = _구간전사(whole, t0, dur, dur, vocab, model, log, caller + "#끝확인", work, 캐시=캐시)
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


# ── 구간 시각 대조 (2026-09-29 밤 — 머리 주석 «구간 시각 대조») ─────────────────────────────────────────
대조창 = 끝창          # 창 길이(초) — 끝 확인 창과 같다(마지막 창 = 끝 확인 창이라 한 번만 묻는다)
대조병렬 = 4           # 창을 동시에 몇 개 묻나 — agy 문 16칸을 다른 편·다른 일과 같이 쓴다
대조닻점수 = 0.6        # 닻(글이 뚜렷이 같은 줄) 최소 닮음
대조맞춤점수 = 0.5      # 닻 사이 줄을 예상 자리(±대조찾기폭)에서 맞출 때 최소 닮음
대조찾기폭 = 2.0
대조최소율 = 0.5        # 본 전사 줄(3자 이상) 가운데 창 전사에서 찾은 비율이 이보다 낮으면 본 전사를 못 믿는다 → 나눠 다시
대조틀림 = 2.0          # 닻 어긋남이 이보다 크면 «틀린 줄» (보고용)
대조고침 = 2.0          # 이웃 닻 어긋남 중앙값이 이보다 크면 그 자리 줄을 창 시각으로 옮긴다 — 창 전사 떨림(45: 한 창 중앙 −1.65초)보다 크게
대조외톨 = 4.0          # 뚜렷한 닻 하나가 이웃과 이만큼 넘게 다르면 그 줄만 옮긴다(순서 섞인 줄)
대조확인최소 = 3          # 두 창 확인: 창 하나만 근거인 덩어리가 이 줄 수 이상이면 확인 창을 하나 더 듣는다


def _창들(dur, 창=None):
    """원본 [0, dur] 를 빈틈없이 덮는 창 [(t0, t1)] — 길이 «창», 이웃끼리 «겹침» 초 이상 겹치고, 마지막 창은 끝 확인 창([dur − 창, dur])과 같다."""
    창 = 창 or 대조창
    if dur <= 창 + 0.05:
        return [(0.0, dur)]
    n = int(np.ceil((dur - 창) / (창 - 겹침))) + 1
    return [(round(float(s), 2), round(float(s) + 창, 2) if k < n - 1 else dur)
            for k, s in enumerate(np.linspace(0.0, dur - 창, n))]


def _창전사(whole, dur, vocab, model, log, caller, work, 캐시=None, 창목록=None):
    """창마다 따로 전사(동시 대조병렬 개) → [(t0, t1, 줄)] (원본 시각). 하나라도 끝내 실패하면 그 예외를 올린다
    (받은 창은 캐시에 남아 다시 돌리면 다시 안 묻는다)."""
    창목록 = 창목록 or _창들(dur)
    log(f"  구간 시각 대조 — 원본 {dur:.1f}초를 {len(창목록)}개 창({대조창:.0f}초·겹침 {겹침}초 이상)으로 따로 전사")

    def one(w):
        return w[0], w[1], _구간전사(whole, w[0], w[1], dur, vocab, model, log, caller + "#시각대조", work, 캐시=캐시)

    with ThreadPoolExecutor(max_workers=대조병렬) as ex:
        futs = [ex.submit(one, w) for w in 창목록]
        out, err = [], None
        for f in futs:
            try:
                out.append(f.result())
            except BaseException as e:                       # noqa: BLE001 — 다른 창은 끝까지 받아 캐시에 남긴다
                err = err or e
    if err is not None:
        raise err
    return out


def _창이음(창답):
    """창 전사들을 겹침 가운데에서 이어 하나로 — 창마다 믿을 만한 시각의 «조각 전사»."""
    창답 = sorted(창답, key=lambda x: x[0])
    창답 = [(a, b, [dict(x, 창=k) for x in L]) for k, (a, b, L) in enumerate(창답)]   # 줄마다 어느 창에서 왔나(두 창 확인에 쓴다)
    got = list(창답[0][2])
    for (a0, a1, _A), (b0, _b1, B) in zip(창답, 창답[1:]):
        got = _잇기(got, B, (b0 + a1) / 2, log=lambda *_: None)
    return sorted(got, key=lambda x: x["t"])


def _비슷(a, b):
    """두 줄 글의 닮음 0~1 — 글자 두 개씩 묶음(겹침 허용 개수)의 다이스 계수. 한쪽이 다른 쪽 «앞머리» 이고 길이가 절반 이상이면 0.8.
    (앞머리만 본다: 대조는 줄 «시작» 시각을 옮기므로 뒤쪽이 같은 줄은 시작이 다르다.)"""
    x, y = _글(a), _글(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    if len(x) < 2 or len(y) < 2:
        return 0.0
    bx = Counter(x[i:i + 2] for i in range(len(x) - 1))
    by = Counter(y[i:i + 2] for i in range(len(y) - 1))
    d = 2 * sum((bx & by).values()) / (sum(bx.values()) + sum(by.values()))
    s, l = (x, y) if len(x) <= len(y) else (y, x)
    if l.startswith(s) and len(s) >= 3 and len(s) / len(l) >= 0.5:
        d = max(d, 0.8)
    return d


def _대조(M, C, dur, 창목록=None, 확인=None):
    """본 전사 M(통째 읽기) ↔ 조각 전사 C(창 이음) — 줄마다 창 시각을 찾아 옮긴다. 반환 (새 줄, 기록 dict).
    ① 닻: 글 4자 이상 · 가장 닮은 C 줄이 대조닻점수 이상 · 4초 넘게 떨어진 다른 C 줄과 뚜렷이 갈림(0.15) · 본 전사 안에 같은 말이 또 없음.
       C 줄 하나에 닻 하나(가장 닮은 것). 이웃 닻 7개의 어긋남 중앙값에서 5초 넘게 벗어나고 닮음 0.85 미만인 닻은 버린다(엉뚱한 짝).
    ② 닻 사이 줄: 이웃 닻 어긋남을 이어 잡은 예상 자리 ±대조찾기폭 안에서 대조맞춤점수 이상 닮은 C 줄(안 쓴 것) — 짧은 감탄은 글이 같아야.
    ③ 옮기기: 이웃 닻 어긋남 중앙값이 대조고침(2초)을 넘는 자리만 — 맞은 줄은 창 시각, 못 맞춘 줄은 그 중앙값만큼. 뚜렷한 닻 하나가
       이웃과 대조외톨(4초) 넘게 다르면 그 줄만(순서 섞인 줄). 나머지는 본 전사 시각 그대로(통째 읽기가 맞을 때는 창보다 정확하다).
    ④ 두 창 확인: 옮기려는 덩어리(3줄 이상)의 근거가 창 하나뿐이면 확인(a0, a1) → 그 구간 따로 전사한 줄 로 한 번 더 듣고, 본 전사와 옮긴 시각 중 더 가까운 쪽을 쓴다.
    판정: 다시(대조율 < 대조최소율 · 닻 모자람 — 본 전사 글이 들리는 말과 안 맞음) · 바로잡음(옮긴 줄 있음) · 맞음.
    기록: 대조율·닻 수·어긋남(닻의 본 전사 시각 − 창 시각) 중앙/최대·틀린 닻 수·옮긴 줄·두 창 확인·창별 어긋남·줄별 [본, 창, 새]."""
    n = len(M)
    if n == 0 or not C:
        return list(M), {"판정": "다시", "까닭": "본 전사나 창 전사가 비었다", "대조율": 0.0, "닻": 0}
    ct = np.array([c["t"] for c in C], dtype=float)
    S = np.zeros((n, len(C)))
    for i, m in enumerate(M):
        for j, c in enumerate(C):
            S[i, j] = _비슷(m["text"], c["text"])
    길이 = [len(_글(m["text"])) for m in M]
    닻 = {}
    for i in range(n):
        if 길이[i] < 4:
            continue
        j = int(np.argmax(S[i]))
        s = S[i, j]
        if s < 대조닻점수:
            continue
        먼 = np.abs(ct - ct[j]) > 4.0
        if 먼.any() and S[i][먼].max() >= s - 0.15:
            continue
        if any(k != i and _비슷(M[k]["text"], M[i]["text"]) >= 0.8 for k in range(n)):
            continue
        if j in {v for v in 닻.values()}:
            k0 = next(k for k, v in 닻.items() if v == j)
            if S[k0, j] >= s:
                continue
            del 닻[k0]
        닻[i] = j
    ks = sorted(닻)
    Δ = {i: M[i]["t"] - ct[닻[i]] for i in ks}
    좋은 = []
    for p, i in enumerate(ks):
        이웃 = [Δ[k] for k in ks[max(0, p - 3):p] + ks[p + 1:p + 4]]
        if len(이웃) >= 3 and abs(Δ[i] - float(np.median(이웃))) > 5.0 and S[i, 닻[i]] < 0.85:
            continue
        좋은.append(i)
    닻 = {i: 닻[i] for i in 좋은}
    ks = sorted(닻)
    대상 = [i for i in range(n) if 길이[i] >= 3]
    기록 = {"줄": n, "대상줄": len(대상), "닻": len(ks), "창줄": len(C)}
    if len(ks) < 2:
        기록.update(판정="다시", 까닭=f"닻 {len(ks)}개 — 본 전사가 창 전사와 거의 안 맞는다", 대조율=0.0)
        return list(M), 기록
    xs = np.array(ks, dtype=float)
    ds = np.array([M[i]["t"] - ct[닻[i]] for i in ks])

    def 예상(i):
        return M[i]["t"] - float(np.interp(i, xs, ds))

    쓴 = set(닻.values())
    짝 = dict(닻)
    for i in range(n):
        if i in 짝:
            continue
        τ = 예상(i)
        후보 = [j for j in np.nonzero(np.abs(ct - τ) <= 대조찾기폭)[0] if j not in 쓴]
        if 길이[i] < 3:
            후보 = [j for j in 후보 if _글(C[j]["text"]) == _글(M[i]["text"]) and _글(M[i]["text"])]
        else:
            후보 = [j for j in 후보 if S[i, j] >= 대조맞춤점수]
        if 후보:
            j = max(후보, key=lambda j: (S[i, j], -abs(ct[j] - τ)))
            짝[i] = j
            쓴.add(j)
    # 옮길 줄 고르기 — 창 전사도 떨린다(45: 본 전사가 맞는 36~76초 창에서 창이 −1.65초 · 본 전사가 카드와 76% 맞고 창은 59%).
    #   그래서 두 전사가 «대조고침» 초 안에서 같으면 본 전사 시각을 그대로 둔다(통째 읽기가 맞을 때는 창보다 정확하다).
    #   옮기는 것: ⓐ 이웃 닻(앞뒤 3개씩)의 어긋남 중앙값이 대조고침을 넘는 자리(늘어남·덩어리 밀림) — 맞은 줄은 창 시각, 못 맞춘 줄은 그 중앙값만큼
    #   ⓑ 제 닻이 뚜렷한데(닮음 0.9 이상 · 6자 이상) 제 어긋남이 이웃 중앙값에서 대조외톨 초 넘게 벗어난 줄(순서가 섞인 줄 — 53 끝).
    국소 = {}
    for p, i in enumerate(ks):
        국소[i] = float(np.median(ds[max(0, p - 3):p + 4]))
    kx = np.array(ks, dtype=float)
    kd = np.array([국소[i] for i in ks])
    새, 줄별, 옮긴 = [], [], 0
    for i, m in enumerate(M):
        d = m["e"] - m["t"]
        g = float(np.interp(i, kx, kd))                   # 이 줄 자리의 어긋남(이웃 닻 중앙값을 줄 순서로 이음)
        자기 = m["t"] - float(ct[짝[i]]) if i in 짝 else None
        t = m["t"]
        if abs(g) > 대조고침:
            t = float(ct[짝[i]]) if i in 짝 and abs(자기 - g) <= 대조외톨 else m["t"] - g
        elif (i in 닻 and 자기 is not None and abs(자기 - g) > 대조외톨 and S[i, 닻[i]] >= 0.9 and 길이[i] >= 6):
            t = float(ct[닻[i]])
        t = min(max(t, 0.0), max(0.0, dur - 0.2))
        옮긴 += abs(t - m["t"]) > 0.05
        줄별.append([round(m["t"], 2), None if i not in 짝 else round(float(ct[짝[i]]), 2), round(t, 2)])
        새.append({"t": round(t, 2), "e": round(min(dur, t + max(0.2, d)), 2), "text": m["text"]})
    # ★두 창 확인 — 창 전사도 한 창 안에서 늘어날 때가 있다(45 36~76초 창: 본 36.8→62.2초 줄들이 창에서 36.7→66.4초 · 1.16배 ·
    #   앞뒤 창은 본 전사와 −0.28·+0.39초로 맞았다). 옮기려는 덩어리(이어진 줄 3개 이상)의 «옮긴 근거»(본 전사와 2초 넘게 다른 창 줄)가
    #   창 하나에서만 왔으면 그 창 하나의 말이라 못 믿는다 — 덩어리 가운데에 창을 하나 더(확인 창) 따로 들어, 본 전사와 옮긴 시각 가운데
    #   확인 창에 더 가까운 쪽을 쓴다. 근거가 창 둘 이상에서 왔으면(늘어남이 여러 창에 걸침 — 3·10·53) 이미 두 번 들은 것이라 그대로 옮긴다.
    #   ☓ 박힌 카드를 심판으로 쓰는 길은 시험하고 버렸다(2026-09-29): 45 는 맞혔지만(카드 맞음 본 0.67 · 창 0.50) 11 첫 전사는 틀렸다
    #     (본 0.32 · 창 0.21 로 본 전사 편을 들었는데 참은 창 쪽 — 43.62초에 본 49.75 · 창 43.99). 점심이네 카드는 우연 수준에 가깝다.
    확인들 = []
    i = 0
    while i < n:
        if abs(새[i]["t"] - M[i]["t"]) <= 0.05:
            i += 1
            continue
        j = i
        while j + 1 < n and abs(새[j + 1]["t"] - M[j + 1]["t"]) > 0.05:
            j += 1
        덩 = list(range(i, j + 1))
        근거창 = {C[짝[k]].get("창") for k in 덩 if k in 짝 and abs(M[k]["t"] - ct[짝[k]]) > 대조고침}
        if len(덩) >= 대조확인최소 and len(근거창) <= 1:
            c = float(np.median([새[k]["t"] for k in 덩]))
            a0 = max(0.0, min(c - 대조창 / 2, dur - 대조창))
            a1 = min(dur, a0 + 대조창)
            록1 = {"줄": [i, j], "본": [round(M[i]["t"], 1), round(M[j]["t"], 1)], "근거창": sorted(x for x in 근거창 if x is not None),
                   "확인창": [round(a0, 2), round(a1, 2)]}
            T = 확인(a0, a1) if 확인 is not None else None
            if T:
                d본, d새 = [], []
                for k in 덩:
                    s_ = [(_비슷(M[k]["text"], x["text"]), x["t"]) for x in T]
                    s_ = [x for x in s_ if x[0] >= 대조닻점수]
                    if s_:
                        tt = max(s_)[1]
                        d본.append(abs(M[k]["t"] - tt))
                        d새.append(abs(새[k]["t"] - tt))
                if len(d본) >= 3:
                    m본, m새 = float(np.median(d본)), float(np.median(d새))
                    록1.update(찾은줄=len(d본), 본거리=round(m본, 2), 새거리=round(m새, 2), 되돌림=m본 < m새)
                    if m본 < m새:
                        for k in 덩:
                            새[k] = {"t": round(M[k]["t"], 2), "e": round(M[k]["e"], 2), "text": M[k]["text"]}
                            줄별[k][2] = round(M[k]["t"], 2)
                            옮긴 -= 1
                else:
                    록1.update(찾은줄=len(d본), 되돌림=False, 까닭="확인 창에서 덩어리 줄을 3개 못 찾음 — 옮긴 대로 둔다")
            확인들.append(록1)
        i = j + 1
    순서 = sorted(range(n), key=lambda i: 새[i]["t"])
    뒤집힘 = sum(1 for a, b in zip(순서, 순서[1:]) if a > b)
    새.sort(key=lambda x: x["t"])
    for a, b in zip(새, 새[1:]):                          # 다음 줄 시작을 넘지 않게
        if b["t"] > a["t"] + 0.25:
            a["e"] = round(max(a["t"] + 0.2, min(a["e"], b["t"] - 0.05)), 2)
    맞은 = sum(1 for i in 대상 if i in 짝)
    율 = 맞은 / max(1, len(대상))
    ad = np.abs(ds)
    창별 = []
    for (w0, w1) in (창목록 or []):
        sel = [k for k, i in enumerate(ks) if w0 <= ct[닻[i]] < w1]
        if sel:
            창별.append({"창": [w0, w1], "닻": len(sel), "어긋남중앙": round(float(np.median(ds[sel])), 2),
                       "어긋남최대": round(float(ds[sel][np.argmax(np.abs(ds[sel]))]), 2)})
        else:
            창별.append({"창": [w0, w1], "닻": 0, "본전사줄": sum(1 for m in M if w0 <= m["t"] < w1),
                       "창줄": sum(1 for c in C if w0 <= c["t"] < w1)})
    기록.update(대조율=round(율, 3), 맞은줄=맞은, 어긋남중앙=round(float(np.median(ad)), 2),
              어긋남최대=round(float(ad.max()), 2), 틀린닻=int((ad > 대조틀림).sum()), 뒤집힘=뒤집힘, 옮긴줄=옮긴,
              국소최대=round(float(np.max(np.abs(kd))), 2), 두창확인=확인들, 창별=창별, 줄별=줄별)
    if len(ks) < max(5, 0.2 * len(대상)) or 율 < 대조최소율:
        기록.update(판정="다시", 까닭=f"본 전사 줄 {len(대상)}개 가운데 창 전사에서 찾은 줄 {맞은}개({율:.0%}) · 닻 {len(ks)}개 — "
                                   "본 전사 글이 들리는 말과 안 맞는다")
        return 새, 기록
    기록["판정"] = "바로잡음" if 옮긴 else "맞음"
    return 새, 기록


def transcribe(src, vocab=None, model=None, log=print, caller="스케치코미디/agy_asr", 맞춤=False, 원시=None, 나눠=False,
               끝기록=None, 캐시=None, 대조=True, 대조기록=None, 본전사=None, 확인창=True):
    """원본 영상 전체 → [{"t","e","text"}]. 먼저 agy 한 번에 통째로 읽힌다(2026-09-26 사장님 «통째로»).
    출력 한도를 넘으면(2026-09-28 싱글126) 그때만 절반씩 나눠 묻고 잇는다 — _구간전사.
    끝에 «끝 확인»(2026-09-28 싱글146) — 끝 40초를 따로 들어 본 전사에 없는 끝 대사가 있으면 그 줄만 붙이고,
    시각이 어긋나 붙일 수 없으면 나눠 다시 전사한다. 나눠 다시 한 뒤에도 끝이 모자라면 RuntimeError(멈춤).
    끝내 실패하면 RuntimeError (또는 agy_gemini.AgyStop — 영상 판정이라 EvoLink 로 넘기지 않는다).
    나눠=True 는 처음부터 절반씩 나눠 묻는다(준비.sh --나눠 · 시험·재실측용).
    대조=True(기본)면 «구간 시각 대조»(2026-09-29 — 머리 주석) — 원본을 40초 창으로 따로 전사해 줄마다 시각을 창에 맞춘다.
      본 전사가 창과 안 맞으면(판정 «다시») 절반씩 나눠 다시 전사해 같은 창으로 다시 잰다 — 그래도면 RuntimeError(멈춤).
      대조기록(dict)을 주면 판정·지표를 담아 준다(편시작이 vtt 머리 «시각대조 …» 와 <vtt>.시각대조.json 으로 남긴다).
    캐시(폴더)를 주면 통째·절반·창 답을 거기 저장하고 다시 쓴다 — 편시작은 <원본>.agy전사/ (--다시전사 가 지운다).
    본전사(줄 목록)를 주면 통째 전사를 묻지 않고 그것을 쓴다(재실측용 — 옛 전사를 새 관문에 넣어 본다).
    확인창=True 면 대조가 창 하나만 근거로 옮기려는 덩어리에 확인 창을 하나 더 묻는다(_대조 «두 창 확인» — 창 하나의 말만 믿지 않는다).
    맞춤(소리 경계 보정)은 기본 끔 — Deep91 flash-high 에서 가짜 반려를 1→4건으로 늘렸다(2026-09-26 실측)."""
    model = model or MODEL
    work = tempfile.mkdtemp(prefix="agy_asr_")
    aud = os.path.join(work, "원본.mp3")
    subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                    "-b:a", "64k", aud]), check=True)
    dur = _dur(aud)
    # 영상 전체를 360p 로만 줄인다 — 길이·순서는 그대로, 올리는 용량만 줄인다
    whole = os.path.join(work, "원본_전체_360p.mp4")
    subprocess.run(ff.명령(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", "scale=-2:360", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-ac", "1", whole]),
                   check=True)
    대조 = 대조 and dur > 대조창 * 1.5                   # 창이 원본 하나뿐이면 본 전사와 같은 답이라 잴 게 없다
    묻 = dict(캐시=캐시, 늘어남받음=대조)               # 대조가 있으면 늘어난 통째 답도 받는다(시각은 창이 정한다)
    got = [dict(x) for x in 본전사] if 본전사 is not None else \
        _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=나눠, **묻)
    나뉨 = 나눠
    # ★줄 수 관문 (2026-09-28 싱글116 — agy 가 «...» 1줄만 준 전사를 통과시켰고, 끝 확인도 «아웃트로 말 없음» 으로 넘어갔다).
    #   스케치는 대사가 빽빽하다(실측 1줄/1.5~2.5초) — 10초에 1줄도 안 되면 잘못 받은 답이다. 나눠서 한 번 다시, 그래도면 멈춘다.
    최소 = max(5, int(dur / 10))
    if len(got) < 최소:
        log(f"  ★전사가 {len(got)}줄뿐이다(원본 {dur:.0f}초 · 최소 {최소}) — 절반씩 나눠 다시 전사한다")
        got = _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=True, **묻)
        나뉨 = True
        if len(got) < 최소:
            raise RuntimeError(f"agy 전사가 {len(got)}줄뿐이다(원본 {dur:.0f}초) — 잘못 받은 답. 준비.sh NNN --다시")
    기억 = {}
    C, 창목록, 기록 = None, None, {"판정": "안 함"}
    if 대조:
        # ★구간 시각 대조 (2026-09-29 밤 — 머리 주석). 마지막 창 = 끝 확인 창이라 끝 확인은 그 답을 쓴다(다시 안 묻는다).
        창목록 = _창들(dur)
        창답 = _창전사(whole, dur, vocab, model, log, caller, work, 캐시=캐시, 창목록=창목록)
        C = _창이음(창답)
        기억["끝"] = next(x[2] for x in 창답 if abs(x[1] - dur) < 0.05)

        def 확인(a0, a1):                               # 두 창 확인 — 창 하나만 근거인 덩어리 자리를 한 번 더 따로 듣는다(캐시에 남는다)
            return _구간전사(whole, a0, a1, dur, vocab, model, log, caller + "#두창확인", work, 캐시=캐시)
        if not 확인창:
            확인 = None

        def 재기(g, 어느):
            새, 록 = _대조(g, C, dur, 창목록, 확인=확인)
            틀린창 = [f"{w['창'][0]:.0f}~{w['창'][1]:.0f}초 {w['어긋남중앙']:+.1f}" for w in 록.get("창별", [])
                   if w.get("닻") and abs(w["어긋남중앙"]) > 대조틀림]
            log(f"  구간 시각 대조({어느}) — 본 전사 {록.get('대상줄')}줄 중 창에서 찾은 줄 {록.get('맞은줄', 0)}"
                f"({록.get('대조율', 0):.0%}) · 닻 {록.get('닻')}개 · 어긋남 중앙 {록.get('어긋남중앙', '-')}·최대 "
                f"{록.get('어긋남최대', '-')}초 · {대조틀림}초 넘게 틀린 닻 {록.get('틀린닻', '-')}개"
                + (f" · 틀린 창 {' / '.join(틀린창)}" if 틀린창 else "") + f" → {록['판정']}")
            return 새, 록

        새, 기록 = 재기(got, "통째" if not 나뉨 else "나눠")
        if 기록["판정"] == "다시" and not 나뉨:
            log(f"  ★구간 시각 대조 — {기록['까닭']}. 절반씩 나눠 다시 전사해 같은 창으로 다시 잰다")
            got = _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=True, **묻)
            나뉨 = True
            새, 기록 = 재기(got, "나눠")
        if 기록["판정"] == "다시":
            if 대조기록 is not None:
                대조기록.update(기록)
            raise RuntimeError(f"agy 전사 시각을 못 믿는다 — {기록['까닭']}(나눠 다시 전사해도). 준비.sh NNN --다시")
        got = 새
    got, 판정 = _끝확인(whole, dur, got, vocab, model, log, caller, work, 기억, 캐시=캐시)
    if 판정 == "다시" and not 나뉨:
        log("  ★끝 확인 — 통째 전사가 원본 끝까지 닿지 않았다. 절반씩 나눠 다시 전사한다")
        got = _구간전사(whole, 0.0, dur, dur, vocab, model, log, caller, work, 나눠=True, **묻)
        나뉨 = True
        if C is not None:
            got, 기록 = _대조(got, C, dur, 창목록, 확인=확인)
            if 기록["판정"] == "다시":
                raise RuntimeError(f"agy 전사 시각을 못 믿는다 — {기록['까닭']}(끝 확인 뒤 나눠 다시 전사해도)")
        got, 판정 = _끝확인(whole, dur, got, vocab, model, log, caller, work, 기억)   # 끝 전사는 기억에서 — 다시 안 묻는다
    if 판정 == "다시":
        raise RuntimeError("agy 전사가 원본 끝까지 닿지 않는다 — 나눠 다시 전사해도 끝 40초 대사가 본 전사에 없다")
    lines = [{"t": round(x["t"], 2), "e": round(x["e"], 2), "text": x["text"]} for x in got]
    lines.sort(key=lambda x: x["t"])
    log(f"  {len(lines)}줄 (끝 확인 {판정} · 시각 대조 {기록['판정']}{' · 나눠 전사' if 나뉨 else ''})")
    if 대조기록 is not None:
        기록["나눠"] = 나뉨
        대조기록.update(기록)
    if 끝기록 is not None:                             # ★끝 확인 판정을 부르는 쪽에 넘긴다 — 편시작이 vtt 머리에 «끝확인 …» 으로 적고
        끝기록["판정"] = 판정                           #   자막띠시각 꼬리 관문 ⑤ 가 읽는다(2026-09-28 저녁 싱글287)
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
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "s16le", "-"]), capture_output=True, check=True)
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


def write_vtt(lines, path, model="", 끝확인=None, 시각대조=None):
    """끝확인 — transcribe 의 «끝 확인» 판정(닿음·붙임·끝없음). 머리에 «· 끝확인 …» 으로 적는다: 전사가 원본 끝 대사까지
    닿았다는 표시라 자막띠시각 꼬리 관문 ⑤ 가 «맞춤이 결말을 앞으로 끌어당김» 을 이것이 있을 때만 판정한다(2026-09-28 저녁).
    시각대조 — transcribe 의 «구간 시각 대조» 판정(맞음·바로잡음). 머리에 «· 시각대조 …»: 줄 시각이 40초 창 전사로 확인된 전사라
    자막띠시각 맞춤이 그 시각에서 크게 옮기면 그 줄을 되돌린다(2026-09-29 밤 — 자막띠시각 대조관문)."""
    틀 = [(i, ln["t"], ln["e"]) for i, ln in enumerate(lines) if ln["t"] < 0 or ln["e"] < 0 or ln["e"] <= ln["t"]]
    if 틀:                                             # 관문 — 뒤집힌 시각을 vtt 에 쓰지 않는다(2026-10-05 루키치8 «-1:59:59.850»)
        raise ValueError(f"agy 전사 쓰기 멈춤: 시각이 음수이거나 끝 ≤ 시작인 줄 {len(틀)}개 — 처음 {틀[:3]}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"WEBVTT\n\n{출처표시} {model}" + (f" · 끝확인 {끝확인}" if 끝확인 else "")
                + (f" · 시각대조 {시각대조}" if 시각대조 in ("맞음", "바로잡음") else "") + "\n\n")
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
    r = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{b:.2f}", "-t", f"{d:.2f}", "-i", path,
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]), capture_output=True)
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
    ap.add_argument("--캐시", default=None, help="통째·절반·창 답 저장 폴더(같은 질문은 다시 안 묻는다)")
    ap.add_argument("--본전사", default=None, help="통째 전사 대신 이 vtt 를 본 전사로(재실측 — 옛 전사를 새 관문에)")
    ap.add_argument("--대조끔", action="store_true", help="구간 시각 대조를 안 한다(옛 동작 — 재실측 비교용)")
    a = ap.parse_args()
    vocab = []
    if a.slug:
        from .asr import load_vocab
        vocab = load_vocab(a.slug, channel=a.채널)
    본 = None
    if a.본전사:
        txt = open(a.본전사, encoding="utf-8").read()
        본 = [{"t": int(h) * 3600 + int(m) * 60 + float(s), "e": int(h2) * 3600 + int(m2) * 60 + float(s2), "text": x}
             for h, m, s, h2, m2, s2, x in re.findall(r"(\d+):(\d+):([\d.]+) --> (\d+):(\d+):([\d.]+)\n(.+)", txt)]
    끝, 록 = {}, {}
    lines = transcribe(a.src, vocab, a.model, 나눠=a.나눠, 캐시=a.캐시, 대조=not a.대조끔, 본전사=본, 끝기록=끝, 대조기록=록)
    write_vtt(lines, a.out, a.model or MODEL, 끝확인=끝.get("판정"), 시각대조=록.get("판정"))
    json.dump(록, open(a.out + ".시각대조.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"전사 {len(lines)}줄 → {a.out}")


if __name__ == "__main__":
    main()
