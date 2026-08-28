# -*- coding: utf-8 -*-
"""스타일 3파일(규격·정답지·우리실측)에서 러너용 config.json 을 생성한다.

    python 규격조립.py --workdir <작업 폴더 절대경로> [--out <파일>]

러너 코드(s2pipe·make.py)는 sketch2 시절의 config.json 모양을 읽는다. 그 모양은
여기서 **생성**된다 — 손으로 만들지 않는다(정본은 스타일/스케치코미디/ 3파일).
경로 규칙: 저장소 안 위치는 이 파일 기준 상대로 알아내고, 작업 폴더만 인자로 받는다.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
STYLE = os.path.join(REPO, "스타일", "스케치코미디")
ASSETS = os.path.join(REPO, "자산", "스케치코미디")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(name):
    with open(os.path.join(STYLE, name), encoding="utf-8") as f:
        return json.load(f)


def build_config(workdir):
    spec = load("규격.json")
    ours = load("우리실측.json")

    cfg = {k: v for k, v in spec.items()}
    cfg["_"] = "생성된 파일 — 고치지 마라. 정본은 스타일/스케치코미디/{규격,정답지,우리실측}.json 이고 규격조립.py 가 만든다."
    # 판정 대역 — make.py 의 이중 빗장(유료 렌더 직전 검사)이 이 값을 읽는다.
    # 판정의 정본은 서버(sk_check)지만, 상수의 원천은 똑같이 정답지 한 곳이다.
    cfg["_정답지"] = load("정답지.json")

    # 저장소 자산 경로를 실제 절대경로로 푼다 (규격에는 저장소 기준 경로가 적혀 있다)
    def asset_path(p):
        rel = p.replace("자산/스케치코미디/", "")
        return os.path.join(ASSETS, *rel.split("/"))

    cfg["channel"] = dict(spec["channel"], icon=asset_path(spec["channel"]["icon"]))
    cfg["layout"] = json.loads(json.dumps(spec["layout"]))  # 깊은 복사
    cfg["layout"]["title"]["font"] = asset_path(spec["layout"]["title"]["font"])
    cfg["layout"]["subtitle"]["font"] = asset_path(spec["layout"]["subtitle"]["font"])
    cfg["sfx"] = dict(spec["sfx"], dir=asset_path(spec["sfx"]["dir"]))
    cfg["bgm"] = dict(spec["bgm"], dir=asset_path(spec["bgm"]["dir"]))

    # 실측 물성은 우리실측에서 온다
    cfg["narration"] = dict(spec["narration"], sec_per_char=ours["tts"]["sec_per_char"])

    # 러너가 기대하는 경로 칸 — 전부 작업 폴더 안 (원본 sketch2 는 저장소 안에 뒀지만
    # 우리 규칙은 산출물을 저장소 밖 작업 폴더로 낸다)
    cfg["paths"] = {
        "projects": os.path.join(workdir, "projects"),
        "work": os.path.join(workdir, "work"),
        "out": os.path.join(workdir, "out"),
        "assets": ASSETS,
    }
    cfg["assets"] = {
        "sfx_dir": os.path.join(ASSETS, "sfx"),
        "meme_dir": os.path.join(ASSETS, "meme"),
        "fonts_dir": os.path.join(ASSETS, "fonts"),
    }
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True, help="작업 폴더 루트 절대경로")
    ap.add_argument("--out", default=None, help="생성할 config.json 경로 (기본: <workdir>/config.json)")
    a = ap.parse_args()

    workdir = os.path.abspath(a.workdir)
    out = a.out or os.path.join(workdir, "config.json")
    cfg = build_config(workdir)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"생성: {out}")
    # 되읽어 확인 — 스크립트의 성공 메시지를 믿지 않는다
    with open(out, encoding="utf-8") as f:
        back = json.load(f)
    assert back["narration"]["sec_per_char"] == cfg["narration"]["sec_per_char"]
    print(f"되읽기 확인: 키 {len(back)}개 · sec_per_char {back['narration']['sec_per_char']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
