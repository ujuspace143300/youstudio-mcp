#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""안쪽경계시험.py — 검은 테두리 판정(s2pipe/안쪽경계.py)의 영구 시험. 종료코드 0 = 전부 맞음.

★2026-10-03 수리(루키치206·172·171 — 어두운 밤 장면·흑백 오프닝을 «화면 속 화면/레터박스»로 오판)와 함께 만들었다.
  s2pipe/안쪽경계.py 를 고치면 반드시 이 시험을 돌린다. 하나라도 틀리면 고친 판정을 쓰지 않는다.

시험 표본(실제 납품·작업 편의 원본 구간 — 사람이 프레임으로 정답을 확인한 것):
  가짜(테두리 없음이 정답) — 206 밤 운동장 · 171 밤 골목 · 172 흑백 오프닝 · 싱글208 어두운 실내 · 싱글199 어두운 방 ·
    싱글20 비네팅 · 싱글180·51·58·10 어두운 가장자리 · 싱글115 차 거울 · 점심이네1 차 천장 · Deep61(1920x960 원본) ·
    Deep10 끝 로고 카드(검은 바탕 글자 카드)
  진짜 — Deep79 156.8·189.4초 어두운 그림 위 띠(한 장 · RGB) · Deep10 화면 속 화면 960x540 · 루키치225 화면 속 화면 · Deep14·76·79·91 위아래 띠 · 루키치224·241 세로 영상 양옆 띠

원본 찾는 차례: --원본 폴더 → 작업 폴더 work/<편>.mp4 → NAS 묶음(<NAS>/<시리즈>/<편>.tar)에서 원본 mp4 하나만 임시로 꺼내 쓰고 지운다.
쓰는 법:  ~/.volcano/venv/bin/python3 검수도구/안쪽경계시험.py [--원본 폴더] [--스케치 ~/Desktop/스케치코미디] [--nas 경로]
"""
import argparse
import os
import shutil
import sys
import tarfile
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from s2pipe import 안쪽경계 as K  # noqa: E402
# ffmpeg·ffprobe 스레드 상한은 s2pipe/ff.py 한 곳에서 (2026-10-04 루키치 14편 과부하 · 검수도구/ffmpeg스레드시험.py)
import os as _ff_os, sys as _ff_sys  # noqa: E402
_ff_d = _ff_os.path.dirname(_ff_os.path.abspath(__file__))
_ff_d = _ff_os.path.dirname(_ff_d)
if _ff_d not in _ff_sys.path:
    _ff_sys.path.append(_ff_d)
from s2pipe import ff  # noqa: E402

# (편, 시리즈, t0, t1, 준비 정답, 굽기 정답, 메모)  정답 None = 테두리 없음 · ("안쪽"|"레터박스", (x, y, w, h))
표본 = [
    ("루키치206", "루키치", 182.3051, 193.1076, None, None, "밤 운동장 — 옛 판정 레터박스 1775x970"),
    ("루키치206", "루키치", 203.7015, 216.5, None, None, "밤 운동장 초록옷 샷 — 옛 판정 안쪽 1674x958 · ⑦ 막혀 6초 뺌"),
    ("루키치171", "루키치", 290.3, 293.6, None, None, "밤 골목 — 옛 판정 레터박스 1161x1080"),
    ("루키치171", "루키치", 297.6, 308.1, None, None, "밤 골목 — 옛 판정 레터박스 1196x1008"),
    ("루키치171", "루키치", 274.2, 276.7, None, None, "밤 재민 샷(배치 보고 구간)"),
    ("루키치171", "루키치", 281.9, 285.2, None, None, "밤 재민 샷(배치 보고 구간)"),
    ("루키치172", "루키치", 0.0, 13.3, None, None, "흑백 오프닝 «오늘은 오빠가 쏜다»"),
    ("루키치172", "루키치", 324.3, 330.9, None, None, "밤 골목 — 옛 판정 레터박스 1633x1080"),
    ("싱글208", "싱글", 179.0, 196.0, None, None, "어두운 실내 — 옛 판정 안쪽 1699x990"),
    ("싱글208", "싱글", 101.5, 108.5, None, None, "어두운 실내 — 옛 판정 레터박스"),
    ("싱글199", "싱글", 165.4, 174.2, None, None, "어두운 방 — 옛 판정 안쪽 1432x847"),
    ("싱글20", "싱글", 11.3, 20.1, None, None, "비네팅(둥근 어둠) — 옛 판정 레터박스"),
    ("싱글180", "싱글", 149.9, 170.0, None, None, "어두운 오른쪽"),
    ("싱글51", "싱글", 128.5, 133.8, None, None, "밤 거리 어두운 양옆"),
    ("싱글10", "싱글", 1.5, 8.7, None, None, "어두운 복도"),
    ("싱글115", "싱글", 137.1, 148.9, None, None, "차 거울 위 천장(움직이는 순흑 — 경계가 곧지 않음)"),
    ("점심이네1", "점심이네", 82.3, 89.8, None, None, "차 천장(밝기 14)"),
    ("점심이네58", "점심이네", 205.3, 213.8, None, None, "밤 어두운 양옆"),
    ("Deep61", "Deep", 235.8, 244.3, None, None, "1920x960 원본 — 옛 판정 안쪽(높이 1080 박음)"),
    ("Deep61", "Deep", 180.3, 187.6, None, None, "1920x960 원본 — 옛 판정 레터박스"),
    ("Deep10", "Deep", 352.5, 358.5, None, None, "검은 바탕 로고 카드 — 확대 금지(2026-09-09 규칙)"),
    ("Deep10", "Deep", 336.0, 350.0, ("안쪽", (480, 270, 960, 540)), (480, 270, 960, 540), "진짜 화면 속 화면(2026-09-07 컷7)"),
    ("루키치225", "루키치", 295.2, 301.5, ("안쪽", (431, 89, 1057, 708)), None, "진짜 화면 속 화면(확대 애니메이션 — 굽기는 세 장 불일치로 안 자름)"),
    ("Deep14", "Deep", 147.1, 160.9, ("레터박스", (0, 130, 1920, 820)), None, "진짜 위아래 띠(2026-09-08 사건 편)"),
    ("Deep76", "Deep", 287.8, 301.7, ("레터박스", (0, 162, 1920, 756)), None, "샷마다 있다 없다 하는 위아래 띠"),
    ("Deep79", "Deep", 41.9, 53.8, ("레터박스", (0, 86, 1920, 908)), None, "위아래 띠 + 어두운 커튼 — 옛 판정은 안쪽(옆까지 좁힘)"),
    ("Deep79", "Deep", 149.6, 159.1, ("레터박스", (0, 86, 1920, 908)), None, "위아래 띠 — 옛 판정은 안쪽 1386x908"),
    ("Deep91", "Deep", 342.5, 353.8, ("레터박스", (0, 108, 1920, 898)), None, "위아래 띠"),
    ("루키치224", "루키치", 239.4, 250.2, ("레터박스", (656, 0, 608, 1080)), None, "세로 영상 양옆 띠"),
    ("루키치241", "루키치", 354.6, 360.5, ("레터박스", (550, 0, 820, 1080)), None, "세로 영상 양옆 띠"),
]
허용 = 6   # 상자 좌표 허용 오차(px)

# 한 장 표본 — 굽기 비트(framing.그림경계 → 안쪽경계.비트경계)처럼 RGB 한 장을 넣어 «위 띠 두께»를 본다.
# (편, 시리즈, 시각, 위 띠 정답 px, 메모) — 2026-10-03 수리③ 실측: 띠 바로 아래 그림이 어두워 띠를 놓쳤던 장면
한장표본 = [
    ("Deep79", "Deep", 156.8, 86, "어두운 무대 위 진짜 위 띠 — 옛 ② 경계몫 0.19 로 놓침 · 상자가 y55 까지 올라 검은 띠 31px"),
    ("Deep79", "Deep", 189.42, 86, "컬러 프레임 — 채널 최대값으로 보면 경계몫 0.03 · 띠 없음(6px 들어감)"),
    ("Deep79", "Deep", 189.33, 86, "컬러 프레임 — 채널 최대값으로 보면 띠 82px 로 짧게 잡힘"),
]


def 꺼내기(tar, 편, 임시):
    want = unicodedata.normalize("NFC", f"work/{편}.mp4")
    with tarfile.open(tar) as t:
        for m in t:
            if unicodedata.normalize("NFC", m.name) == want:
                p = os.path.join(임시, f"{편}.mp4")
                with t.extractfile(m) as f, open(p, "wb") as o:
                    shutil.copyfileobj(f, o, 1 << 20)
                return p
    return None


def 원본찾기(편, 시리즈, a, 임시):
    for d in filter(None, [a.원본, os.path.join(a.스케치, "work")]):
        p = os.path.join(d, f"{편}.mp4")
        if os.path.exists(p):
            return p
    tar = os.path.join(a.nas, 시리즈, f"{편}.tar")
    return 꺼내기(tar, 편, 임시) if os.path.exists(tar) else None


def 같은가(정답, 결과):
    if 정답 is None or 결과 is None:
        return 정답 is None and 결과 is None
    if isinstance(정답[0], str):
        return 정답[0] == 결과[0] and all(abs(p - q) <= 허용 for p, q in zip(정답[1], 결과[1]))
    return all(abs(p - q) <= 허용 for p, q in zip(정답, 결과))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--원본", help="<편>.mp4 들이 이미 있는 폴더(있으면 먼저 쓴다)")
    ap.add_argument("--스케치", default=os.path.expanduser("~/Desktop/스케치코미디"))
    ap.add_argument("--nas", default="/Volumes/galaxy/맥1 작업백업용/스케치코미디")
    a = ap.parse_args()
    임시 = tempfile.mkdtemp(prefix="안쪽경계시험_")
    try:
        편들 = sorted({(p[0], p[1]) for p in 표본} | {(p[0], p[1]) for p in 한장표본})
        with ThreadPoolExecutor(6) as ex:
            자리 = dict(zip(편들, ex.map(lambda x: 원본찾기(x[0], x[1], a, 임시), 편들)))
        없음 = [p for p, v in 자리.items() if not v]
        if 없음:
            print("원본을 못 찾았다(시험 불가):", [p[0] for p in 없음])
            return 2

        def 하나(s):
            편, 시리즈, t0, t1, 준정, 굽정, 메모 = s
            src = 자리[(편, 시리즈)]
            준 = K.판정([K.프레임(src, t0 + (t1 - t0) * f) for f in (0.15, 0.35, 0.5, 0.65, 0.85)])
            굽 = K.굽기판정([K.프레임(src, t0 + (t1 - t0) * f) for f in (0.25, 0.5, 0.75)])
            return s, 준, 굽
        틀림 = 0
        with ThreadPoolExecutor(8) as ex:
            for (편, _, t0, t1, 준정, 굽정, 메모), 준, 굽 in ex.map(하나, 표본):
                ok = 같은가(준정, 준) and 같은가(굽정, 굽)
                틀림 += not ok
                print(f"{'맞음' if ok else '틀림'}  {편} {t0:.1f}~{t1:.1f}초  준비={준} (정답 {준정})  굽기={굽} (정답 {굽정})  · {메모}")
        import subprocess
        import numpy as np
        for 편, 시리즈, t, 정답, 메모 in 한장표본:
            src = 자리[(편, 시리즈)]
            W, H = K._크기(src)
            raw = subprocess.run(ff.명령(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]), capture_output=True).stdout
            rgb = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            위 = K.비트경계(rgb, W, H)[1]
            ok = abs(위 - 정답) <= 2
            틀림 += not ok
            print(f"{'맞음' if ok else '틀림'}  {편} {t:.2f}초 한 장(RGB) 위 띠={위} (정답 {정답})  · {메모}")
        print(f"\n표본 {len(표본) + len(한장표본)}개 중 틀림 {틀림}개")
        return 1 if 틀림 else 0
    finally:
        shutil.rmtree(임시, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
