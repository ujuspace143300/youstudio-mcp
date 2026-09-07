# -*- coding: utf-8 -*-
"""스케치코미디 prproj → NAS 편 폴더 + 두 판(맥·윈도우 UNC).

린박스 `키트/도구/prproj이관.py`(신병4·불륜 실증: 사장님 윈도우 «유실 0»)의 원칙을
스케치 폴더 규약(`소스/`)에 맞춘 판:
  · 경로는 처음부터 순수 NFC (맥 SMB listdir 의 NFD 를 절대 박지 않는다)
  · 윈도우 UNC 는 **서버 이름**(GALAXYSTORE-NAS) — IP 는 «미디어 없음» (2026-09-04 실측)
  · 미디어는 md5 대조 복사, 두 판은 태그 수·NFC·실존 되읽기 검증

사용: python NAS이관_sk.py <완성 prproj> <NAS 편 폴더> [UNC_HOST]
결과: <편 폴더>/소스/… · <prproj 이름>.prproj(맥판) · *_윈도우.prproj
"""
import gzip
import hashlib
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter

NFC = lambda s: unicodedata.normalize("NFC", s)

SRC = sys.argv[1]
PKG = NFC(sys.argv[2])
UNC_HOST = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("VOLCANO_UNC_HOST", "GALAXYSTORE-NAS")
assert "galaxy" in PKG, "NAS 편 폴더는 /Volumes/galaxy/… 안이어야 한다: " + PKG

xml = gzip.decompress(open(SRC, "rb").read()).decode("utf-8")

# ① prproj 가 실제로 무는 파일만 — /Users/…/소스/<이름> 꼴 (내장 그래픽 자리표 오인 방지:
#    prproj이관.py 와 같은 원칙으로 /Users/ 로 시작하는 실존 파일만)
paths = sorted(set(re.findall(r"/+Users/[^<]+", xml)), key=len, reverse=True)
os.makedirs(os.path.join(PKG, "소스"), exist_ok=True)
매핑 = {}
복사 = 0
for p in paths:
    실경로 = "/" + p.lstrip("/")
    if not os.path.isfile(실경로):
        # 폴더(도너의 스크래치 자리 흔적)나 없는 경로는 미디어가 아니다 — 그대로 둔다
        continue
    이름 = NFC(os.path.basename(실경로))
    새 = os.path.join(PKG, "소스", 이름)
    if not os.path.exists(새) or os.path.getsize(새) != os.path.getsize(실경로):
        shutil.copy2(실경로, 새)
        복사 += 1
    h1 = hashlib.md5(open(실경로, "rb").read()).hexdigest()
    h2 = hashlib.md5(open(새, "rb").read()).hexdigest()
    assert h1 == h2, "md5 불일치: " + 이름
    lead = len(p) - len(p.lstrip("/"))
    매핑[p] = ("/" * (lead - 1)) + 새 if lead > 1 else 새

assert 매핑, "무는 미디어를 하나도 못 찾았다 — prproj 를 확인하라"

# ② 두 판 생성
base = NFC(os.path.splitext(os.path.basename(SRC))[0])
OUT_MAC = os.path.join(PKG, base + ".prproj")
OUT_WIN = os.path.join(PKG, base + "_윈도우.prproj")
mac, win = xml, xml
for old, new in 매핑.items():
    mac = mac.replace(old, new)
    unc = "\\\\" + UNC_HOST + "\\galaxy\\" + new.lstrip("/").split("galaxy/", 1)[1].replace("/", "\\")
    win = win.replace(old, unc)
for out, body in ((OUT_MAC, mac), (OUT_WIN, win)):
    open(out, "wb").write(gzip.compress(body.encode("utf-8")))

# ③ 검증 — 태그 수 3판 일치 · 경로 NFC · 맥판 실존 · 맥 작업 경로 잔존 0
def tags(t):
    return Counter(re.findall(r"<([A-Za-z]+)[ >]", t))
t0, tm, tw = tags(xml), tags(mac), tags(win)
assert t0 == tm == tw, "태그 수 불일치"
탈 = 0
for lab, t in (("맥판", mac), ("윈판", win)):
    for _tag, val in re.findall(r"<(FilePath|ActualMediaFilePath)>([^<]+)</", t):
        if ("galaxy" in val or UNC_HOST in val) and val != NFC(val):
            print("✗", lab, "NFC 아님:", val[-50:]); 탈 += 1
    잔존 = [v for _t2, v in re.findall(r"<(FilePath|ActualMediaFilePath)>([^<]+)</", t)
            if v.startswith("/Users") or v.startswith("//Users")]
    if 잔존:
        print("✗", lab, "맥 작업 경로 잔존:", len(잔존), "건", 잔존[:2]); 탈 += len(잔존)
for _tag, val in re.findall(r"<(FilePath|ActualMediaFilePath)>([^<]+)</", mac):
    if val.startswith("/Volumes") and not os.path.exists(val):
        print("✗ 실존 안 함:", val[-60:]); 탈 += 1
assert 탈 == 0, f"검증 탈 {탈}건 — 위 목록"
print(f"경로 {len(매핑)}개 재작성 · 복사 {복사}개(md5 대조) · 태그 3판 일치 · NFC/실존/잔존 탈 0"
      f" · UNC \\\\{UNC_HOST}")
print("→", OUT_MAC)
print("→", OUT_WIN)
