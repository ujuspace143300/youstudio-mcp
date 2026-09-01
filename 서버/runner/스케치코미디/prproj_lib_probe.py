# -*- coding: utf-8 -*-
"""prproj_lib_probe.py — 미디어 물성 실측 (조립 준비용). ffprobe 로 잰다 — 추정하지 않는다."""
import json, subprocess

TPS = 254016000000


def ffprobe_info(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json",
                          "-show_streams", "-show_format", path],
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
