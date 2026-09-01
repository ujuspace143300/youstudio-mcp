# -*- coding: utf-8 -*-
"""공용 config 로더 — 모든 모듈이 여기서 CFG 를 가져온다.

config.json 은 손으로 만들지 않는다: 정본은 스타일/스케치코미디/{규격,정답지,우리실측}.json
이고 규격조립.py 가 작업 폴더에 생성한다. 경로 우선순위:

    1) 명령줄 인자 `--config <경로>`  (어느 모듈이든 공통 — argparse 전에 걷어낸다)
    2) 환경변수 `S2_CONFIG`
    3) 러너 폴더의 config.json  (sketch2 시절 호환 — 저장소에는 커밋하지 않는다)

sketch2(윈도우) 시절에는 모듈마다 HERE/config.json 을 읽었다. MCP 이식(2026-08-28)에서
작업 폴더가 저장소 밖으로 나가면서 로더를 한 곳으로 모았다.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_path():
    # 1) --config <경로> — 뒤 모듈들의 인자 해석을 깨지 않게 sys.argv 에서 걷어낸다
    argv = sys.argv
    if "--config" in argv:
        i = argv.index("--config")
        if i + 1 >= len(argv):
            raise SystemExit("--config 뒤에 경로가 없다")
        path = argv[i + 1]
        del argv[i:i + 2]
        return path
    # 2) 환경변수
    env = os.environ.get("S2_CONFIG", "").strip()
    if env:
        return env
    # 3) 러너 폴더 (구버전 호환)
    return os.path.join(HERE, "config.json")


CONFIG_PATH = os.path.abspath(os.path.expanduser(_config_path()))
if not os.path.isfile(CONFIG_PATH):
    raise SystemExit(
        f"config 가 없다: {CONFIG_PATH}\n"
        "  먼저 생성하라: python 규격조립.py --workdir <작업 폴더>\n"
        "  그리고 --config <작업 폴더>/config.json 인자(또는 S2_CONFIG)로 알려 달라."
    )
with open(CONFIG_PATH, encoding="utf-8") as _f:
    CFG = json.load(_f)


def strip_punct(text):
    """★절대 규칙(2026-09-01 사장님) — 나레이션·자막에서 금지 구두점을 걷어낸다.

    목록은 규격 layout.subtitle.구두점_금지 (마침표·쉼표·말줄임·가운뎃점).
    쉼표는 공백으로(단어가 붙지 않게), 나머지는 지운다. 물음표·느낌표는 남긴다.
    plan(모델 출력)·subs(재추출)가 저장 전에 부른다. 판정은 정답지 G-구두점.
    """
    banned = (CFG.get("layout", {}).get("subtitle", {}) or {}).get("구두점_금지") or []
    t = str(text or "")
    for ch in banned:
        t = t.replace(ch, " " if ch == "," else "")
    return " ".join(t.split())
