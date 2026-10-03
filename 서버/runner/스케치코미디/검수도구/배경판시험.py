#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배경판시험.py [--편 루키치158,루키치160] [--보기] — 화면 캡션 «배경판» 재기를 실제 표본으로 채점한다(무료 · 굽기 없음 · agy 안 부름).

★2026-10-03 오후 — 수리② (94e1b4b · 말풍선·알림·삽입 그림 판을 피함) 뒤 배치에서 판 재기가 두 번 틀렸다:
  루키치158 음성메시지 재생판(판 안 노란 재생 칸·일시정지 막대에서 판이 끊김 · 굽기 캐시 판과 관문이 다시 잰 판이 달라 관문만 걸림)
  루키치160 카톡 PC 알림판(작은 글 5줄이라 캡션 후보조차 아님 · 굽기도 관문도 «잴 것 없음» → 판 끝 12px 비침을 «걸림 0»).
  수리② 는 163·265·161 세 편을 구도모의로 손 확인만 했고 판 재기를 지키는 시험이 없었다 — 판 재기는 굽기(가림)와 관문(판재기)이
  «같이» 쓰는 한 결과라(화면글자.캡션판), 재기가 틀리면 둘이 같이 틀린다. 그 자를 이 시험이 지킨다.

채점(표본마다):
  판   — 그 캡션 자취의 캡션판["판"] 이 실제 판(사람이 프레임으로 잰 테두리)을 덮고(안쪽 3px), 실제 판보다 넘침 이하로만 크다.
  없음 — 판이 없는 글자(큰 시간 캡션 «3분 뒤» · 벽 위 글자 · 장면 글자)는 캡션판["판"] 이 None 이어야 한다(헛걸림 — 얼굴 덮는 큰 상자).
  후보 — 판무리 표본은 캡션후보 에 «판무리» 로 올라와야 한다.
  둘레 — 판이 있는 모든 자취에서 «피할 사각형»(굽기 가림) ⊇ «잰 판»(관문) + 3px (굽기가 관문보다 늘 넉넉해야 반올림으로 안 걸린다).
원본은 임시 폴더 사본으로 잰다(work 캐시·납품물은 안 건드림) — work 에 없으면 NAS «영화자료/3. 스캐치코미디/루키치/<번호>.*/*.mp4».
화면글자 캐시(글자 인식 훑기)를 같이 복사하고 사본 시각을 캐시 키에 맞춘다(없으면 인식기로 다시 훑는다 — 맥 전용).
종료코드: 0 통과 · 1 틀림 · 2 원본이 없어 건너뛴 표본이 있음(틀림 없을 때).
"""
import glob
import json
import os
import shutil
import sys
import tempfile
import unicodedata

RUN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RUN)
WORK = os.path.expanduser("~/Desktop/스케치코미디/work")
NAS = "/Volumes/galaxy/영화자료/3. 스캐치코미디"
안쪽, 넘침 = 3, 40           # 판 채점 여유(px) — 덮음: 실제 판을 3px 안쪽까지 · 넘침: 그림자(163 ≈25px)·판 밖 머리카락까지 40px

# (편, 글 일부, 자취 시작 초, 종류, 실제 판 x0,y0,x1,y1 · 근거)
표본 = [
    ("루키치158", "0:06", 68.0, "판", (737, 35, 1107, 175), "음성메시지 재생판 — 노란 재생 칸이 761→1060 으로 자람 · 일시정지 막대 x785~818"),
    ("루키치158", "0:06", 141.5, "판", (737, 27, 1107, 168), "재생판(다른 장면) — 판 아래 손 그림자"),
    ("루키치158", "0:07", 95.0, "판", (737, 28, 1107, 168), "재생판 — 재생 삼각형(곧지 않은 덩어리) · 판 아래 머리카락"),
    ("루키치160", "돼지", 29.0, "판무리", (58, 362, 754, 651), "카톡 PC 알림판 — 작은 글 5줄 · 아래 «메시지 입력» 칸"),
    ("루키치160", "송금보내요", 156.5, "판", (178, 162, 699, 777), "카카오페이 송금 카드 — 노란 머리 + 흰 몸"),
    ("루키치163", "근데 누나는", 149.5, "판", (1011, 456, 1786, 594), "흰 말풍선 — 부드러운 그림자 ≈25px (수리② 표본)"),
    ("루키치265", "그러게", 201.0, "판", (1004, 416, 1741, 590), "회색 말풍선 (수리② 표본)"),
    ("루키치265", "첨단호반", 149.0, "판무리", (93, 286, 836, 600), "부동산 앱 캡처 — 작은 글 무리"),
    ("루키치161", "0343", 51.0, "판", (186, 157, 872, 795), "삽입 일정표 (수리② 표본)"),
    ("루키치160", "3분", 36.0, "없음", None, "큰 시간 캡션 — 판 없음(왼쪽 화면 끝 · 오른쪽 검은 옷)"),
    ("루키치160", "2분", 41.0, "없음", None, "큰 시간 캡션"),
    ("루키치160", "그분", 44.5, "없음", None, "큰 시간 캡션"),
    ("루키치160", "내일 식단", 96.5, "없음", None, "판 없는 글자"),
    ("루키치160", "수요일", 115.0, "없음", None, "가운데 큰 글자"),
    ("루키치163", "10분", 34.0, "없음", None, "시간 캡션"),
    ("루키치163", "5분", 50.5, "없음", None, "시간 캡션"),
    ("루키치161", "30분", 80.0, "없음", None, "시간 캡션"),
    ("루키치161", "소중하다", 0.0, "없음", None, "여러 줄 글귀(판 없음)"),
    ("루키치265", "킬고미터", 74.0, "없음", None, "사진 위 작은 글(판 아님)"),
]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def 원본찾기(편):
    p = os.path.join(WORK, 편 + ".mp4")
    if os.path.exists(p):
        return p
    번호 = "".join(ch for ch in 편 if ch.isdigit())
    시리즈 = 편.rstrip("0123456789")
    for d in glob.glob(os.path.join(NAS, 시리즈, "*")):
        if _nfc(os.path.basename(d)).startswith(번호 + "."):
            ms = [m for m in glob.glob(os.path.join(d, "*.mp4")) if "_360p" not in m]
            if ms:
                return ms[0]
    return None


def 사본(편, d):
    """원본 사본 + 화면글자 캐시 사본 → 사본 경로(없으면 None). 캐시 키(크기:시각)가 맞게 사본 시각을 맞춘다."""
    src = 원본찾기(편)
    if not src:
        return None
    dst = os.path.join(d, 편 + ".mp4")
    shutil.copyfile(src, dst)
    cache = os.path.join(WORK, 편 + ".mp4.화면글자.json")
    st = os.stat(src)
    mt = st.st_mtime
    if os.path.exists(cache):
        try:
            k = json.load(open(cache, encoding="utf-8"))["key"].split(":")
            if int(k[1]) == st.st_size:
                mt = float(k[2])
                shutil.copyfile(cache, dst + ".화면글자.json")
        except (OSError, ValueError, KeyError, IndexError):
            pass
    os.utime(dst, (mt, mt))
    for f in glob.glob(os.path.join(WORK, 편 + ".mp4.카드*.json")):       # 자막띠(_띠)가 쓰는 카드 캐시
        shutil.copyfile(f, os.path.join(d, os.path.basename(f)))
    return dst


def 채점(편들=None, 보기=False):
    from s2pipe import 화면글자 as 화
    if 화.인식기() is None:
        print("화면글자 인식기 없음(macOS 전용) — 이 시험은 맥에서 돈다")
        return 2
    d = tempfile.mkdtemp(prefix="배경판시험_")
    틀림, 건너뜀, 통과 = [], [], 0
    try:
        편목록 = sorted({s[0] for s in 표본 if not 편들 or s[0] in 편들})
        for 편 in 편목록:
            src = 사본(편, d)
            if not src:
                건너뜀 += [s for s in 표본 if s[0] == 편]
                print(f"[건너뜀] {편} — 원본 없음(work·NAS)")
                continue
            c = 화._캐시(src)
            후 = 화.캡션후보(src, c)
            판들 = {}
            for a in 후:
                판들[id(a)] = 화.캡션판(src, c, a)
            # 둘레 — 피할 사각형 ⊇ 잰 판 + 3px
            for a in 후:
                r = 판들[id(a)]
                if r["판"]:
                    p, g = r["판"], r["가림"]
                    W, H = c["W"], c["H"]                        # 화면 끝에 붙은 판은 끝에서 잘린다
                    if not (g[0] <= max(0, p[0] - 3) and g[1] <= max(0, p[1] - 3)
                            and g[2] >= min(W, p[2] + 3) and g[3] >= min(H, p[3] + 3)):
                        틀림.append(f"{편} «{a['글'][:16]}» 둘레 — 가림 {g} 가 판 {p} 보다 3px 넉넉하지 않다")
            for 편_, 글, t0, 종류, 실제, 근거 in [s for s in 표본 if s[0] == 편]:
                맞 = [a for a in 후 if 글 in a["글"] and abs(a["t0"] - t0) <= 1.0]
                이름 = f"{편} {t0:.1f}초 «{글}» ({근거})"
                if 종류 == "없음":
                    잡 = [판들[id(a)]["판"] for a in 맞 if 판들[id(a)]["판"]]
                    if 잡:
                        틀림.append(f"{이름} — 판이 없어야 하는데 {잡[0]} 로 잡힘(헛걸림)")
                    else:
                        통과 += 1
                        print(f"  [통과] {이름} — 판 없음" + ("" if 맞 else " (후보 아님)"))
                    continue
                if 종류 == "판무리":
                    맞 = [a for a in 맞 if a.get("판무리")]
                if not 맞:
                    틀림.append(f"{이름} — 캡션 후보에 없음" + (" (판무리로 올라와야 한다)" if 종류 == "판무리" else ""))
                    continue
                p = 판들[id(맞[0])]["판"]
                x0, y0, x1, y1 = 실제
                if not p:
                    틀림.append(f"{이름} — 판을 못 쟀다(실제 {list(실제)})")
                    continue
                덮 = p[0] <= x0 + 안쪽 and p[1] <= y0 + 안쪽 and p[2] >= x1 - 안쪽 and p[3] >= y1 - 안쪽
                작 = p[0] >= x0 - 넘침 and p[1] >= y0 - 넘침 and p[2] <= x1 + 넘침 and p[3] <= y1 + 넘침
                표 = 판들[id(맞[0])]["표본"]
                글_ = f"잰 판 {p} vs 실제 {list(실제)} · 표본 {sum(1 for _t, q in 표 if q)}/{len(표)} 장 판"
                if 덮 and 작:
                    통과 += 1
                    print(f"  [통과] {이름} — {글_}")
                else:
                    틀림.append(f"{이름} — " + ("실제 판을 다 못 덮음 " if not 덮 else "") + ("너무 큼 " if not 작 else "") + 글_)
                if 보기:
                    for t, q in 표:
                        print(f"      표본 {t:7.2f} {q}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for x in 틀림:
        print("  [틀림]", x)
    print(f"배경판 시험 — 통과 {통과} · 틀림 {len(틀림)} · 건너뜀 {len(건너뜀)} (표본 {len(표본) if not 편들 else len([s for s in 표본 if s[0] in 편들])})")
    return 1 if 틀림 else (2 if 건너뜀 else 0)


if __name__ == "__main__":
    a = sys.argv[1:]
    편들 = set(a[a.index("--편") + 1].split(",")) if "--편" in a else None
    sys.exit(채점(편들, "--보기" in a))
