# -*- coding: utf-8 -*-
"""prproj_lib_probe.py — 미디어 물성 실측 (조립 준비용). ffprobe 로 잰다 — 추정하지 않는다."""
import json, subprocess
# ffmpeg·ffprobe 스레드 상한은 s2pipe/ff.py 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
import os as _ff_os, sys as _ff_sys  # noqa: E402
_ff_d = _ff_os.path.dirname(_ff_os.path.abspath(__file__))
if _ff_d not in _ff_sys.path:
    _ff_sys.path.append(_ff_d)
from s2pipe import ff  # noqa: E402

TPS = 254016000000


def ffprobe_info(path):
    out = subprocess.run(ff.명령(["ffprobe", "-v", "error", "-print_format", "json",
                          "-show_streams", "-show_format", path]),
                         check=True, capture_output=True).stdout
    d = json.loads(out)
    dur = float(d["format"]["duration"])
    a_rate = None
    for s in d["streams"]:
        if s.get("codec_type") == "audio":
            sr = int(s.get("sample_rate", 0))
            if sr and TPS % sr == 0:
                a_rate = TPS // sr
    return {"dur": dur, "audio_tickrate": a_rate}
