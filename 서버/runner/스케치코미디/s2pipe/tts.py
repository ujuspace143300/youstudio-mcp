# -*- coding: utf-8 -*-
"""나레이션 합성 — Typecast. ★요금이 나간다.

■ 후처리를 왜 두 단계로 하나
    tamjeongcat 에서 검증된 순서를 그대로 옮겼다(볼케이노 배급 실행기에서 온 것).
    한 단계로 줄이면 앞뒤 무음이 남아 **컷 슬롯을 넘긴다.** 순서를 바꾸지 마라.
      1) loudnorm  → 48k mono
      2) 앞뒤 무음 제거 + loudnorm → 48k stereo

■ 캐시
    같은 (문구·목소리·감정·속도) 는 다시 굽지 않는다. 과금이 붙는 API 다.

■ ★volume 은 config 가 100 으로 못박는다
    실측(2026-08-18): 150·200 이나 intensity 2.0 은 최대 음량이 0.0dB 에 닿아
    피크가 잘렸다. 음량은 여기가 아니라 믹싱 gain 으로 올린다.
"""
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
try:  # ffmpeg·ffprobe 스레드 상한은 ff.명령 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
    from . import ff
except ImportError:  # 단독 실행(python s2pipe/x.py)
    import ff  # type: ignore

ENDPOINT = "https://api.typecast.ai/v1/text-to-speech"


def _api_key():
    p = os.path.expanduser("~/.volcano/keys/typecast")
    if not os.path.exists(p):
        raise SystemExit("Typecast 키가 없다: ~/.volcano/keys/typecast")
    return open(p, encoding="utf-8").read().strip()


def _run(argv, what):
    p = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"{what} 실패:\n{(p.stderr or '')[-600:]}")
    return p.stdout


def wav_seconds(path):
    o = _run(ff.명령(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", path]), "wav_seconds")
    return float(o.strip())


def _본문(text, narr):
    return {
        "voice_id": narr["voice_id"],
        "text": text,
        "model": narr.get("model", "ssfm-v30"),
        "language": narr.get("language", "KOR"),
        "prompt": {
            "emotion_type": "preset",
            "emotion_preset": narr.get("emotion", "normal"),
            "emotion_intensity": narr.get("intensity", 1.0),
        },
        "output": {
            "volume": narr.get("volume", 100),
            "audio_pitch": narr.get("pitch", 0),
            "audio_tempo": narr.get("tempo", 1.0),
            "audio_format": "wav",
        },
    }


def _캐시자리(body, cache_dir):
    sig = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True)
                         .encode()).hexdigest()[:16]
    return os.path.join(cache_dir, f"{sig}.raw.wav")


def _후처리(raw, out_wav):
    """원음(raw) → 나레 wav — 두 단계 후처리(위 «후처리를 왜 두 단계로 하나»). synth 와 캐시길이 가 같이 쓴다."""
    os.makedirs(os.path.dirname(out_wav) or ".", exist_ok=True)
    mid = out_wav + ".norm.wav"
    _run(ff.명령(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
          "-af", "loudnorm=I=-23.0:TP=-3:LRA=9", "-ar", "48000", "-ac", "1", mid]),
         "narr loudnorm")
    _run(ff.명령(["ffmpeg", "-y", "-loglevel", "error", "-i", mid,
          "-af", "silenceremove=start_periods=1:start_threshold=-38dB:start_silence=0.02:"
                 "stop_periods=-1:stop_threshold=-38dB:stop_duration=0.20:stop_silence=0.02,"
                 "loudnorm=I=-23:TP=-3:LRA=9",
          "-ar", "48000", "-ac", "2", out_wav]), "narr trim")
    os.remove(mid)


def 캐시길이(text, narr, cache_dir):
    """이 문구를 구웠을 때 나레 wav 길이(초) — TTS 캐시에 원음이 있으면 synth 와 같은 후처리로 임시 파일에 만들어 잰다
    (요금 없음). 캐시에 없으면 None(아직 한 번도 안 구운 문구 — 부르는 쪽이 글자 수로 어림한다).
    ★2026-09-28 저녁: make --check 의 «나레 곁 대사» 관문이 굽기 전에 나레 창 길이를 실측으로 쓰려고 만들었다."""
    import tempfile
    raw = _캐시자리(_본문(text, narr), cache_dir)
    if not (os.path.exists(raw) and os.path.getsize(raw) > 2000):
        return None
    d = tempfile.mkdtemp(prefix="나레길이_")
    try:
        out = os.path.join(d, "n.wav")
        _후처리(raw, out)
        return round(wav_seconds(out), 3)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def synth(text, narr, out_wav, cache_dir, retry=4):
    """문구 하나를 굽고 (경로, 길이)를 준다. `narr` 는 config.narration."""
    body = _본문(text, narr)
    os.makedirs(cache_dir, exist_ok=True)
    raw = _캐시자리(body, cache_dir)

    if not (os.path.exists(raw) and os.path.getsize(raw) > 2000):
        data = json.dumps(body, ensure_ascii=False).encode()
        hdr = {"X-API-KEY": _api_key(), "Content-Type": "application/json",
               "User-Agent": "sketch2/1.0"}
        part, last = raw + ".part", None
        for a in range(retry):
            try:
                req = urllib.request.Request(ENDPOINT, data=data, headers=hdr)
                with urllib.request.urlopen(req, timeout=120) as r:
                    blob = r.read()
                if len(blob) <= 2000:
                    raise RuntimeError(f"응답이 너무 작다 ({len(blob)}B)")
                open(part, "wb").write(blob)
                os.replace(part, raw)
                break
            except Exception as e:                       # noqa: BLE001
                last = e
                detail = ""
                if isinstance(e, urllib.error.HTTPError):
                    try:
                        detail = e.read().decode()[:200]
                    except Exception:                    # noqa: BLE001
                        pass
                print(f"    TTS 재시도 {a+1}/{retry}: {type(e).__name__} "
                      f"{str(e)[:80]} {detail}", flush=True)
                time.sleep(a + 1)
        else:
            raise SystemExit(f"음성 합성 실패: {type(last).__name__} {str(last)[:200]}")

    _후처리(raw, out_wav)
    return out_wav, round(wav_seconds(out_wav), 3)
