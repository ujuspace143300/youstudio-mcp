#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""편시작_deep.py — 사장님 지정 소재 폴더(로컬) → 파이프라인 입력 한 벌.

  폴더 규약(2026-09-01 사장님): *.mp4 1개 = 원본(파일명 = 하단 출처 원제) ·
  *댓글*.zip = 완성 댓글 카드 PNG · *추천제목*후보*.txt = 상단 제목 후보.
  ★로고는 편마다 다르다 — --로고 를 안 주면 멈추고 묻는다(린박스 하단 규칙과 같은 사상).

  하는 일: 원본 코덱 검사(AV1/VP9 → H.264 변환) · 원본 전사(기본 agy 구독 — 2026-09-26 사장님 결정 B.
          --전사 speechmatics 면 유료, 사전 승인 필수)
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
    ap.add_argument("--채널", default="띱 Deep", help="하단 크레딧 채널명(예: 싱글벙글). 기본 띱 Deep")
    ap.add_argument("--전사", choices=["agy", "speechmatics"], default="agy",
                    help="원본 전사 엔진 — 기본 agy(구독). speechmatics 는 유료(사전 승인)")
    ap.add_argument("--다시전사", action="store_true",
                    help="work 의 원본 전사(.ko.vtt·.맞춤전·.맞춤.json)를 버리고 새로 묻는다 — 준비.sh --다시 가 준다")
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
    info = {"channel": a.채널, "title": 원제, "comments": []}
    json.dump(info, open(os.path.join(work, f"{vid}.info.json"), "w", encoding="utf-8"), ensure_ascii=False)

    # ③ 원본 전사 — ★2026-09-26 사장님 결정(B): «전사는 agy 로 하고 자막만 스피치매틱스로».
    #   기본은 agy(제미나이 구독, 과금 없음). 자막 시각의 원천인 완성본 재전사(한편 ③ s2pipe.asr)는
    #   그대로 Speechmatics 다. agy 시각은 거칠어서 vtt 머리에 «NOTE 출처 agy» 를 남기고,
    #   make 절단 게이트·준비 배제·sync 복원이 이 표시를 보고 소리 실측으로 받친다.
    #   --전사 speechmatics 를 주면 예전처럼 유료 전사(★사전 승인 필수).
    vtt = os.path.join(work, f"{vid}.ko.vtt")
    # ★낱말사전(2026-09-04 사장님 규칙) — 소재 폴더 *사전*.json 이 있으면 work 로 옮겨
    #   고유명사를 미리 일러 준다. 편 중간에 확정된 이름은 work/<슬러그>_사전.json 에.
    for _사 in glob.glob(os.path.join(d, "*사전*.json")):
        shutil.copy2(_사, os.path.join(work, f"{vid}_사전.json"))
    # ★--다시전사 (2026-09-28 싱글146): 준비.sh --다시 가 편시작을 다시 돌려도 이 vtt 가 있으면 전사를 건너뛰어,
    #   끝 146~157초가 빠진 전사를 그대로 다시 썼다. 자막띠시각의 .맞춤전(«없을 때만» 씀)도 옛 전사로 남는다 — 셋 다 버린다.
    if a.다시전사:
        for _p in (vtt, vtt + ".맞춤전", vtt + ".맞춤.json"):
            if os.path.exists(_p):
                os.remove(_p)
                print(f"  --다시전사: {os.path.basename(_p)} 버림")
    # ★자막띠시각 «멈춤» 기록이 남은 전사는 쓰지 않는다 (2026-09-28 저녁 싱글287) — 멈춘 뒤 --다시 없이 다시 돌리면 vtt 가 있어
    #   전사·맞춤을 건너뛰고 엉킨 전사로 plan 까지 갔을 것이다. --다시전사 가 이 기록(.맞춤.json)도 지운다.
    try:
        _멈춤 = json.load(open(vtt + ".맞춤.json", encoding="utf-8")).get("멈춤") if os.path.exists(vtt) else None
    except (OSError, ValueError):
        _멈춤 = None
    if _멈춤:
        raise SystemExit(f"★자막띠시각 멈춤 기록 — {_멈춤}\n  편시작을 --다시전사 로 다시(싱글벙글은 준비.sh {vid.replace('싱글', '')} --다시) — agy 다시 전사 · 돈 안 듦")
    if not os.path.exists(vtt) and a.전사 == "agy":
        from s2pipe import agy_asr
        vocab = asr.load_vocab(vid, channel=a.채널)
        if vocab:
            print(f"  낱말사전 {len(vocab)}개: {', '.join(e['content'] for e in vocab[:8])}")
        _끝 = {}
        lines = agy_asr.transcribe(dst, vocab, 끝기록=_끝)
        # 머리에 «끝확인 닿음|붙임|끝없음» — 자막띠시각 꼬리 관문 ⑤ 가 «끝 대사까지 닿은 전사» 일 때만 결말 끌어당김을 판정한다
        agy_asr.write_vtt(lines, vtt, agy_asr.MODEL, 끝확인=_끝.get("판정"))
        print(f"전사(agy) {len(lines)}줄 → {os.path.basename(vtt)}")
        # ★박힌 자막 띠로 시각 맞춤 (2026-09-27 사장님 A안 — «확인하는 용도로만»): agy 통째 읽기는 영상마다 시간을
        #   조금씩 늘려 센다(싱글282 끝에서 8초). 박힌 자막이 «언제 떴는가» 만 재서 맞춘다 — 글자는 안 쓴다.
        from s2pipe import 자막띠시각
        _맞 = 자막띠시각.실행(dst, vtt, 반영=True)
        if _맞 and _맞.get("멈춤"):
            # ★꼬리 관문 ⑤ (2026-09-28 저녁 싱글287 1차 전사 — 두 장면 줄이 섞여 맞춤이 결말을 20초 앞으로 당겼고, 맞춤 전도
            #   가운데가 20초 늦었다). 어느 시각도 못 믿어 plan 으로 넘기지 않는다 — 다시 전사하면 풀렸다(287 2차: 참 최대 0.29초).
            raise SystemExit(f"★자막띠시각 멈춤 — {_맞['멈춤']}\n  편시작을 --다시전사 로 다시(싱글벙글은 준비.sh {vid.replace('싱글', '')} --다시) — agy 다시 전사 · 돈 안 듦")
        _, _L = 자막띠시각.읽기(vtt)
        _넘 = [t for t, _e, _x in _L if t > dur_src + 0.5] if (dur_src := float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst],
            capture_output=True, text=True).stdout)) else []
        if _넘:
            raise SystemExit(f"★맞춘 뒤에도 원본({dur_src:.1f}초) 끝을 넘는 줄 {len(_넘)}개 — 전사 시각이 크게 틀렸다. 사장님께 여쭌다")
    if not os.path.exists(vtt):
        aud = os.path.join(work, f"{vid}_asr.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", dst, "-vn",
                        "-ac", "1", "-ar", "16000", "-b:a", "48k", aud], check=True)
        print("전사 제출 (Speechmatics ko — ★유료)…")
        vocab = asr.load_vocab(vid, channel=a.채널)
        if vocab:
            print(f"  낱말사전 {len(vocab)}개: {', '.join(e['content'] for e in vocab[:8])}")
        job = asr.submit(aud, lang="ko", vocab=vocab)
        asr.wait(job)
        words = asr.words_of(job)
        lines = asr.to_lines(words, 28)
        with open(vtt, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for ln in lines:
                t = ln["t"]
                # ★초 단위 절삭 금지(2026-09-03) — 복원 자막의 시각 정밀도가 vtt 를 따른다
                # ★끝시각은 마지막 단어의 실제 끝(2026-09-09 Deep60 «이래서 소개팅 주» — 옛 «시작+0.999»
                #   가짜 끝 때문에 make 의 발화 끝 절단 게이트가 1초 뒤 절단을 못 봤다)
                e = max(ln.get("e", t + 0.999), t + 0.2)
                f.write(f"{int(t//3600):02d}:{int(t%3600//60):02d}:{t%60:06.3f} --> "
                        f"{int(e//3600):02d}:{int(e%3600//60):02d}:{e%60:06.3f}\n{ln['text']}\n\n")
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
