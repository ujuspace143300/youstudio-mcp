#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도너/왕복.py — 계단 2 왕복 실험 준비물.

도너 prproj 를 풀고(gzip) 아무것도 안 바꾸고 다시 싸서 _왕복_그대로.prproj 를 만들고,
시퀀스 이름 끝에 "_왕복" 만 붙인 _왕복_이름변경.prproj 도 만든다. 둘 다 사람이
프리미어(새 빈 프로젝트가 아니라 파일 자체를 연다)에서 열어 확인한다.
사용: python 도너/왕복.py 도너/볼케이노_FullTime_v26_b05_ppro-v45.prproj
"""
import gzip, sys, os, hashlib, re

src = sys.argv[1]
raw = open(src, "rb").read()
assert raw[:2] == b"\x1f\x8b", "gzip 이 아니다"
xml = gzip.decompress(raw)
out_dir = os.path.dirname(src) or "."
base = os.path.splitext(os.path.basename(src))[0]

# 1) 그대로
same = gzip.compress(xml, 9, mtime=0)
p1 = os.path.join(out_dir, "_왕복_그대로.prproj")
open(p1, "wb").write(same)
# 2) 시퀀스 이름만
name_m = re.search(rb"<Sequence ObjectUID=[^>]+>(?:(?!</Sequence>).)*?<Name>([^<]*)</Name>", xml, re.S)
seq_name = name_m.group(1)
xml2 = xml.replace(b"<Name>" + seq_name + b"</Name>", b"<Name>" + seq_name + "_왕복".encode() + b"</Name>", 1)
p2 = os.path.join(out_dir, "_왕복_이름변경.prproj")
open(p2, "wb").write(gzip.compress(xml2, 9, mtime=0))

# 검산
back = gzip.decompress(open(p1, "rb").read())
print("원본 gz", len(raw), "B / xml", len(xml), "B / 재압축 gz", len(same), "B")
print("XML 바이트 동일:", back == xml, " md5", hashlib.md5(xml).hexdigest())
print("gz 바이트 동일(원본 vs 재압축):", same == raw, "(달라도 정상 — 압축기·mtime 차이)")
print("시퀀스 이름:", seq_name.decode("utf-8"), "→", (seq_name + "_왕복".encode()).decode("utf-8"))
print("생성:", p1, p2)
