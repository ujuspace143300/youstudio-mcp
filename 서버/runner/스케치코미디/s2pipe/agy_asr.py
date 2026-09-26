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


def _prompt(span, vocab):
    v = ""
    if vocab:
        v = ("\n등장 고유명사(이 표기로 적어라): " +
             ", ".join(x["content"] if isinstance(x, dict) else str(x) for x in vocab))
    return (
        f"첨부한 영상(소리 포함)은 한국어 스케치 코미디 한 편 전체({span:.1f}초)다. 처음부터 끝까지 들리는 말을 전부 받아 적어라.\n"
        "규칙:\n"
        "- 들린 그대로 적는다. 사투리·반말·더듬는 말·짧은 감탄(아, 어, 야)도 그대로. 없는 말을 지어내지 않는다.\n"
        "- 작은 목소리·전화 너머 목소리·겹치는 말도 빠뜨리지 않는다. 노래 가사·효과음은 적지 않는다.\n"
        f"- 한 줄은 {MAX_CHARS}자 이하. 말이 0.5초 이상 쉬면 새 줄. 화자가 바뀌면 새 줄.\n"
        "- t = 그 줄 첫 음절이 소리 나기 시작하는 초, e = 마지막 음절 소리가 끝나는 초. 영상 0초 기준, 소수 둘째 자리까지.\n"
        "- 시각은 추정하지 말고 소리를 듣고 정확히 맞춘다. 줄은 시간 순서대로.\n"
        '- 답은 JSON {"lines": [{"t": 0.44, "e": 0.92, "text": "..."}]} 하나만.' + v
    )


def transcribe(src, vocab=None, model=None, log=print, caller="스케치코미디/agy_asr", 맞춤=False, 원시=None):
    """원본 영상 전체 → [{"t","e","text"}]. agy 한 번에 통째로 읽힌다(조각 금지). 끝내 실패하면 RuntimeError
    (또는 agy_gemini.AgyStop — 영상 판정이라 EvoLink 로 넘기지 않는다).
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
    limit = int(min(40, 8 + dur / 60 * 4))          # 60초에 약 1.5분(high 실측) — 넉넉히
    log(f"agy 전사 — 영상 전체 {dur:.0f}초를 한 번에 ({model}, 시간 제한 {limit}분)")
    body = {"contents": [{"role": "user", "parts": [
                {"@inline_file": {"path": whole, "mime": "video/mp4"}},
                {"text": _prompt(dur, vocab)}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA}}
    got = None
    for k in range(TRIES):
        resp = agy_gemini.generate(body, caller=caller, limit_min=limit, model=model, log=log)
        if resp is not None:
            try:
                got = json.loads(agy_gemini.text_of(resp))["lines"]
            except (ValueError, KeyError, TypeError) as e:
                log(f"  답 형식 오류({e}) — 다시 ({k + 1}/{TRIES})")
                continue
            # ★시각 늘어남 관문 (2026-09-26 싱글280 실측): 통째 읽기 답의 시각이 원본보다 길게 세어져
            #   마지막 17줄이 원본 끝(156.5초)을 넘었다 — 잘라 붙이면 끝 1초에 몰려 plan 이 엉뚱한 자리(아웃트로
            #   카드)를 결말로 골랐다. 원본 길이를 넘는 줄이 있으면 틀린 답으로 보고 통째로 다시 읽힌다(조각 금지).
            # ★2026-09-27: 조금 늘어난 건(싱글282 — 3번 다 원본보다 2~4% 늘어남) 뒤의 자막띠시각 맞춤이 바로잡는다.
            #   원본 길이의 12% 를 넘게 늘어났을 때만 틀린 답으로 본다(280 1차 — 끝 17줄이 한곳에 몰린 경우).
            넘침 = [float(x.get("t", 0)) for x in got if float(x.get("t", 0)) > dur * 1.12]
            if 넘침:
                log(f"  ★시각이 원본({dur:.1f}초)보다 늘어났다 — {len(넘침)}줄이 끝을 넘음(최대 {max(넘침):.1f}초). 다시 ({k + 1}/{TRIES})")
                got = None
                continue
            break
        else:
            log(f"  agy 실패 — 다시 ({k + 1}/{TRIES})")
    if got is None:
        raise RuntimeError(f"agy 전사 실패 — {TRIES}번 시도(답 형식 오류 또는 시각 늘어남)")
    lines = []
    for ln in got:
        t, e, tx = float(ln["t"]), float(ln["e"]), ln["text"].strip()
        if not tx:
            continue
        t = max(t, 0.0)                                   # 끝을 넘은 시각도 그대로 둔다 — 자막띠시각 맞춤이 옮긴다
        e = max(e, t + 0.2)
        lines.append({"t": round(t, 2), "e": round(e, 2), "text": tx})
    log(f"  {len(lines)}줄")
    lines.sort(key=lambda x: x["t"])
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
    a = ap.parse_args()
    vocab = []
    if a.slug:
        from .asr import load_vocab
        vocab = load_vocab(a.slug, channel=a.채널)
    lines = transcribe(a.src, vocab, a.model)
    write_vtt(lines, a.out, a.model or MODEL)
    print(f"전사 {len(lines)}줄 → {a.out}")


if __name__ == "__main__":
    main()
