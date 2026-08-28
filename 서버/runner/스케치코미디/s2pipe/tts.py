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
    o = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", path], "wav_seconds")
    return float(o.strip())


def synth(text, narr, out_wav, cache_dir, retry=4):
    """문구 하나를 굽고 (경로, 길이)를 준다. `narr` 는 config.narration."""
    body = {
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
    sig = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True)
                         .encode()).hexdigest()[:16]
    os.makedirs(cache_dir, exist_ok=True)
    raw = os.path.join(cache_dir, f"{sig}.raw.wav")

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

    os.makedirs(os.path.dirname(out_wav) or ".", exist_ok=True)
    mid = out_wav + ".norm.wav"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
          "-af", "loudnorm=I=-23.0:TP=-3:LRA=9", "-ar", "48000", "-ac", "1", mid],
         "narr loudnorm")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", mid,
          "-af", "silenceremove=start_periods=1:start_threshold=-38dB:start_silence=0.02:"
                 "stop_periods=-1:stop_threshold=-38dB:stop_duration=0.20:stop_silence=0.02,"
                 "loudnorm=I=-23:TP=-3:LRA=9",
          "-ar", "48000", "-ac", "2", out_wav], "narr trim")
    os.remove(mid)
    return out_wav, round(wav_seconds(out_wav), 3)
