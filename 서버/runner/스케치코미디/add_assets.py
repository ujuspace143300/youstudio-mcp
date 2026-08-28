# -*- coding: utf-8 -*-
"""효과음을 반입하고 목록(assets/catalog.json)을 만든다.

    python tools/add_assets.py sfx <파일들...> --tag 쿵
    python tools/add_assets.py sfx "C:/받은것/impact" --tag 쿵      폴더도 된다
    python tools/add_assets.py catalog                             목록만 다시

★**손으로 복사해 넣지 마라.** catalog.json 이 갱신되지 않으면 코드가 그 자산이
  있는 줄도 모른다. 대본에서 효과음은 `@꼬리표` 로 부르는데, 그 꼬리표를 잇는 것이
  이 목록이다.

★shortform 의 같은 이름 도구를 그대로 가져오면 안 된다 — 그쪽은 `vpipe` 모듈에
  기대고 있다. sketch2 는 혼자 굴러가야 하므로 필요한 것만 다시 썼다.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
CATALOG = os.path.join(ROOT, "assets", "catalog.json")
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".ogg", ".flac")

# ★shortform 과 같은 8종을 쓴다. 자산을 나눠 갖기 때문에 꼬리표가 어긋나면 안 된다.
SFX_TAGS = ("뿅", "딸깍", "쿵", "띵", "휙", "삐", "뿌엥", "두구")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def sfx_dir():
    return os.path.join(ROOT, CFG["assets"]["sfx_dir"])


def gather(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p))
                    if f.lower().endswith(AUDIO_EXT)]
        elif os.path.isfile(p) and p.lower().endswith(AUDIO_EXT):
            out.append(p)
        else:
            print(f"  건너뜀(소리 파일이 아니다): {p}")
    return out


def dur_of(p):
    o = subprocess.run([CFG["ffmpeg"]["ffprobe"], "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    try:
        return round(float(o.stdout.strip()), 2)
    except ValueError:
        return None


def next_index(d, tag):
    n = 0
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.startswith(tag + "_"):
                try:
                    n = max(n, int(os.path.splitext(f)[0].split("_")[-1]))
                except ValueError:
                    pass
    return n + 1


def cmd_sfx(a):
    if a.tag not in SFX_TAGS:
        print(f"꼬리표가 목록에 없다: {a.tag}\n  쓸 수 있는 것: {' '.join(SFX_TAGS)}")
        return 1
    d = sfx_dir()
    os.makedirs(d, exist_ok=True)
    files = gather(a.paths)
    if not files:
        print("반입할 파일이 없다")
        return 1
    i = next_index(d, a.tag)
    for src in files:
        ext = os.path.splitext(src)[1].lower()
        dst = os.path.join(d, f"{a.tag}_{i:02d}{ext}")
        shutil.copy2(src, dst)
        i += 1
    print(f"  {a.tag}: {len(files)}개 반입")
    return 0


def build_catalog():
    d = sfx_dir()
    sfx, unknown = [], 0
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(AUDIO_EXT):
                continue
            tag = f.split("_")[0] if "_" in f else None
            if tag not in SFX_TAGS:
                tag, unknown = None, unknown + 1
            sfx.append({"file": f, "tag": tag, "sec": dur_of(os.path.join(d, f))})
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    json.dump({"sfx_tags": list(SFX_TAGS), "sfx": sfx,
               "쓰는법": "config.sfx.map 에서 '@꼬리표' 로 부르면 그 꼬리표 중 하나를 쓴다."},
              open(CATALOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by = {}
    for s in sfx:
        by[s["tag"]] = by.get(s["tag"], 0) + 1
    print(f"\ncatalog.json 갱신 — 효과음 {len(sfx)}개")
    for t in SFX_TAGS:
        if by.get(t):
            secs = [s["sec"] for s in sfx if s["tag"] == t and s["sec"]]
            print(f"  {t:<4} {by[t]:2d}개  {min(secs):.2f}~{max(secs):.2f}초")
    if unknown:
        print(f"  ★꼬리표를 못 붙인 파일 {unknown}개 — 이름이 '<꼬리표>_NN' 이어야 한다")
    # ★config 가 부르는 꼬리표가 실제로 있는지 본다. 없으면 굽다가 멈춘다.
    miss = [k for k, v in (CFG.get("sfx", {}).get("map") or {}).items()
            if v.startswith("@") and not by.get(v[1:])]
    if miss:
        print(f"  ★config.sfx.map 이 부르는데 없는 것: {', '.join(miss)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sfx", help="효과음 반입")
    p.add_argument("paths", nargs="+")
    p.add_argument("--tag", required=True)
    p.set_defaults(fn=cmd_sfx)
    sub.add_parser("catalog", help="목록만 다시 만들기").set_defaults(fn=lambda a: build_catalog())
    a = ap.parse_args()
    rc = a.fn(a)
    if a.cmd == "sfx":
        build_catalog()
    return rc


if __name__ == "__main__":
    sys.exit(main())
