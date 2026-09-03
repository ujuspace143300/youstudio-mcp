#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""편시작_deep.py — 사장님 지정 소재 폴더(로컬) → 파이프라인 입력 한 벌.

  폴더 규약(2026-09-01 사장님): *.mp4 1개 = 원본(파일명 = 하단 출처 원제) ·
  *댓글*.zip = 완성 댓글 카드 PNG · *추천제목*후보*.txt = 상단 제목 후보.
  ★로고는 편마다 다르다 — --로고 를 안 주면 멈추고 묻는다(린박스 하단 규칙과 같은 사상).

  하는 일: 원본 코덱 검사(AV1/VP9 → H.264 변환) · Speechmatics 전사(유료, 사전 승인 필수)
  → work/<슬러그>.mp4 · .ko.vtt · .info.json · _댓글/ · _로고.png · _제목후보.txt

사용: python 편시작_deep.py <소재폴더> --slug Deep01 --로고 <로고.png> --config <config.json>
"""
import argparse, glob, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s2pipe.cfg import CFG  # noqa: E402
from s2pipe import asr      # noqa: E402

지원코덱 = {"h264", "hevc", "prores", "qtrle", "mpeg4", "mjpeg", "dnxhd"}


def vcodec(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                         check=True, capture_output=True)
    return out.stdout.decode().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--로고", default=None)
    a = ap.parse_args()
    d = a.folder
    assert os.path.isdir(d), "소재 폴더 없음: " + d
    assert a.로고 and os.path.exists(a.로고), (
        "★로고가 지정되지 않았다(또는 없다) — 편마다 로고·문구가 다르므로 사장님께 묻고 시작한다 (2026-09-01 규칙)")

    # ★맥은 한글 파일명을 NFD(자모 분해)로 준다 — NFC 로 정규화해 비교한다 (볼트 메모리 규칙)
    import unicodedata
    def nfc(s):
        return unicodedata.normalize("NFC", s)
    names = [(n, nfc(n)) for n in os.listdir(d)]
    mp4s = [os.path.join(d, n) for n, c in names if c.lower().endswith(".mp4")]
    zips = [os.path.join(d, n) for n, c in names if "댓글" in c and c.endswith(".zip")]
    titles = [os.path.join(d, n) for n, c in names if "추천제목" in c and "후보" in c and c.endswith(".txt")]
    assert len(mp4s) == 1, f"원본 mp4 가 1개여야 한다: {len(mp4s)}개"
    assert zips, "댓글 zip 이 없다"
    assert titles, "추천제목 후보 txt 가 없다"
    src, zp, tt = mp4s[0], zips[0], titles[0]

    work = os.path.join(HERE, CFG["paths"]["work"])
    os.makedirs(work, exist_ok=True)
    vid = a.slug

    # ① 원본 — 코덱 검사 후 반입 (프리미어 미지원 코덱은 H.264 변환. 2026-09-01 AV1 실측 규칙)
    dst = os.path.join(work, f"{vid}.mp4")
    if not os.path.exists(dst):
        if vcodec(src) in 지원코덱:
            shutil.copy2(src, dst)
        else:
            print(f"원본 코덱 {vcodec(src)} — H.264 변환")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src,
                            "-vf", "fps=24000/1001", "-c:v", "libx264", "-preset", "fast",
                            "-crf", "16", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst], check=True)
    assert vcodec(dst) in 지원코덱

    # ② 원제·출처 — 파일명에서 (규약: <채널접두>_<원제>.mp4). 채널 표기는 본래 방식(#띱 Deep)
    base = os.path.splitext(os.path.basename(src))[0]
    base = unicodedata.normalize("NFC", base)     # ★NFD 원제는 폰트가 못 그린다(출처 줄 실측)
    원제 = base.split("_", 1)[1] if "_" in base else base
    info = {"channel": "띱 Deep", "title": 원제, "comments": []}
    json.dump(info, open(os.path.join(work, f"{vid}.info.json"), "w", encoding="utf-8"), ensure_ascii=False)

    # ③ 전사 (Speechmatics ko — ★유료. 부르기 전에 승인받았어야 한다)
    vtt = os.path.join(work, f"{vid}.ko.vtt")
    if not os.path.exists(vtt):
        aud = os.path.join(work, f"{vid}_asr.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", dst, "-vn",
                        "-ac", "1", "-ar", "16000", "-b:a", "48k", aud], check=True)
        print("전사 제출 (Speechmatics ko)…")
        job = asr.submit(aud, lang="ko")
        asr.wait(job)
        words = asr.words_of(job)
        lines = asr.to_lines(words, 28)
        with open(vtt, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for ln in lines:
                t = ln["t"]
                f.write(f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d}.000 --> "
                        f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d}.999\n{ln['text']}\n\n")
        os.remove(aud)
        print(f"전사 {len(lines)}줄 → {os.path.basename(vtt)}")

    # ④ 댓글 PNG — cp949 파일명 복원 해제
    cdir = os.path.join(work, f"{vid}_댓글")
    if not os.path.isdir(cdir):
        os.makedirs(cdir, exist_ok=True)
        r = subprocess.run(["ditto", "-x", "-k", zp, cdir], capture_output=True)
        if r.returncode != 0 or not glob.glob(os.path.join(cdir, "**", "*.png"), recursive=True):
            subprocess.run(["unzip", "-qq", "-O", "cp949", zp, "-d", cdir], check=True)
    pngs = sorted(glob.glob(os.path.join(cdir, "**", "*.png"), recursive=True))
    if len(pngs) < 10:
        # ★2026-09-03 사장님: 카드가 모자라면 같은 형태로 내용 맞춰 제작해 채운다 (Deep04 7장 사건)
        from 댓글보충 import 보충
        logline = ""
        pj = os.path.join(HERE, "..", "..", "..")  # logline 은 아직 없을 수 있다(계획 전) — 빈 값 허용
        pngs = 보충(cdir, logline)
    assert len(pngs) >= 10, f"댓글 PNG 가 10장 미만이다(보충 후에도): {len(pngs)}"

    # ⑤ 로고·제목 후보
    shutil.copy2(a.로고, os.path.join(work, f"{vid}_로고.png"))
    shutil.copy2(tt, os.path.join(work, f"{vid}_제목후보.txt"))

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", dst], check=True, capture_output=True).stdout)
    print(f"편시작 완료 — {vid}: 원본 {dur:.0f}s · 댓글 PNG {len(pngs)}장 · 원제 「{원제}」")


if __name__ == "__main__":
    main()
