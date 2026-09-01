#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""준비_prproj_sk.py — 조립_prproj_sk 의 입력 한 벌을 만든다.

  ① 납품 폴더(<workdir>/프리미어_<슬러그>/소스/)에 미디어 복사
     원본.mp4(그대로) · 나레_00.wav(모노 48k s16 변환) · 그래픽_템플릿.mov(껍데기, qtrle argb 30fps)
  ② 껍데기 = build.draw_frame(제목 비움) → 영상 상자(y0~y1)에 알파 구멍 → mov
     제목은 굽지 않는다 — V3 텍스트 그래픽으로 들어가 프리미어에서 수정 가능해야 하므로.
  ③ timeline_sk.json — 컷·나레·자막 큐·상자 배치(모션 값)

사용: python 준비_prproj_sk.py <편.json> --config <config.json>
"""
import argparse, json, os, subprocess, sys, wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG  # noqa: E402  (--config 인자를 걷어간다)
from s2pipe import build    # noqa: E402
from prproj_lib_probe import ffprobe_info  # noqa: E402


def run(argv):
    subprocess.run(argv, check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    a = ap.parse_args()
    proj = json.load(open(a.project, encoding="utf-8"))
    slug = proj["slug"]
    workdir = os.path.dirname(os.path.dirname(os.path.abspath(a.project)))
    wdir = os.path.join(workdir, "work", slug)
    src_orig = os.path.join(workdir, "work", proj["source"]["id"] + ".mp4")
    out_root = os.path.join(workdir, f"프리미어_{slug}")
    sdir = os.path.join(out_root, "소스")
    os.makedirs(sdir, exist_ok=True)

    segs = [s for s in proj["segments"] if s.get("keep")]
    total = sum(s["t1"] - s["t0"] for s in segs)

    # ① 미디어 — ★프리미어가 읽는 코덱만 넣는다 (2026-09-01 실측: 유튜브 AV1 원본 → 비디오만
    #   미디어 오프라인, 소리(AAC)는 정상. 경로·메타가 아니라 코덱이 원인이었다)
    지원코덱 = {"h264", "hevc", "prores", "qtrle", "mpeg4", "mjpeg", "dnxhd"}

    def vcodec(path):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                             check=True, capture_output=True)
        return out.stdout.decode().strip()

    dst_src = os.path.join(sdir, "원본.mp4")
    if os.path.exists(dst_src) and vcodec(dst_src) not in 지원코덱:
        os.remove(dst_src)                     # 이전에 복사된 미지원 코덱본 폐기
    if not os.path.exists(dst_src):
        if vcodec(src_orig) in 지원코덱:
            import shutil
            shutil.copy2(src_orig, dst_src)
        else:
            print(f"원본 코덱 {vcodec(src_orig)} — 프리미어 미지원 → H.264 변환 (수 분)")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src_orig,
                            "-vf", "fps=24000/1001", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "16", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst_src], check=True)
    assert vcodec(dst_src) in 지원코덱, "원본 변환 실패 — 코덱 " + vcodec(dst_src)
    dst_nar = os.path.join(sdir, "나레_00.wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(wdir, "narr01.wav"),
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", dst_nar])

    # ② 껍데기 — 제목 비운 frame → 알파 구멍 → mov
    import copy
    from PIL import Image
    p2 = copy.deepcopy(proj)
    p2["title"] = ["", ""]
    frame_png = os.path.join(sdir, "_frame_notitle.png")
    build.draw_frame(p2, frame_png)
    im = Image.open(frame_png).convert("RGBA")
    b = CFG["layout"]["video_box"]
    hole = Image.new("RGBA", (b["w"], b["y1"] - b["y0"]), (0, 0, 0, 0))
    im.paste(hole, (0, b["y0"]))
    rgba = os.path.join(sdir, "_frame_hole.png")
    im.save(rgba)
    dst_tpl = os.path.join(sdir, "그래픽_템플릿.mov")
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", rgba, "-t", f"{total + 1:.3f}",
         "-r", "30", "-c:v", "qtrle", "-pix_fmt", "argb", dst_tpl])

    # ③ timeline
    picture, cum = [], 0.0
    for i, s in enumerate(segs):
        d = s["t1"] - s["t0"]
        picture.append({"t0": round(cum, 4), "t1": round(cum + d, 4), "src_in": s["t0"],
                        "name": f'{i + 1:02d} P{s["phase"]} {s["what"][:24]}'})
        cum += d

    subs = sorted(proj["subs"], key=lambda x: x["t"])
    nar_seg = next(s for s in segs if s.get("narration"))
    nar_sub = next((x for x in subs if x.get("kind") == "narr"), None)
    w = wave.open(dst_nar)
    nar_dur = w.getnframes() / w.getframerate()
    w.close()
    nar_t0 = nar_sub["t"] if nar_sub else picture[segs.index(nar_seg)]["t0"] + 0.3
    narration = [{"t0": round(nar_t0, 3), "t1": round(nar_t0 + nar_dur, 3),
                  "wav": dst_nar, "text": nar_seg["narration"]}]

    cues = [{"lane": "title", "t0": 0.0, "t1": round(total, 3), "text": proj["title"][0] + "\r" + proj["title"][1]}]
    cues.append({"lane": "narr", "t0": narration[0]["t0"], "t1": narration[0]["t1"], "text": nar_seg["narration"]})
    # 대사 큐 — 60fps 격자에서 끝 = min(시작+6초, 다음 시작) 로 겹침 0 을 보장한다
    F = 60
    lines = [x for x in subs if x.get("kind") != "narr"]
    for i, x in enumerate(lines):
        t0f = round(x["t"] * F)
        nxtf = round((lines[i + 1]["t"] if i + 1 < len(lines) else total) * F)
        t1f = min(t0f + 6 * F, nxtf, round(total * F))
        if t1f <= t0f:
            t1f = t0f + 1
        cues.append({"lane": "dlg", "t0": round(t0f / F, 4), "t1": round(t1f / F, 4), "text": x["text"]})

    # 상자 배치 — 1920×1080 원본을 상자(높이 y1-y0)에 세로 맞춤
    box_h = b["y1"] - b["y0"]
    scale = round(box_h / 1080 * 100, 3)
    cy = round((b["y0"] + b["y1"]) / 2 / CFG["video"]["h"], 6)
    src_info = ffprobe_info(dst_src)

    tl = {"title": f"스케치 {slug}", "total_s": round(total, 4),
          "source": dst_src, "source_dur_s": src_info["dur"],
          "src_audio_tickrate": src_info["audio_tickrate"],
          "template": dst_tpl,
          "box": {"scale": scale, "pos": f"0.5:{cy}"},
          "picture": picture, "narration": narration, "cues": cues}
    out = os.path.join(out_root, "timeline_sk.json")
    json.dump(tl, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("생성:", out)
    print(f"컷 {len(picture)} · 나레 {len(narration)} · 큐 {len(cues)} (제목1·나레1·대사 {len(lines)}) · 총 {total:.1f}s")
    print(f"상자: scale {scale}% · pos 0.5:{cy}")


if __name__ == "__main__":
    main()
