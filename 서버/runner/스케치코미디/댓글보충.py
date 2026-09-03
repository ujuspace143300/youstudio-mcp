#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""댓글보충.py — 댓글 카드가 10장 미만일 때 같은 형태로 부족분을 만들어 채운다.

  2026-09-03 사장님: «너가 같은 형태로 내용에 맞게 제작해서 진행해줘. 앞으로도 이런
  경우가 있으면 형태 맞춰서 알아서 내용 맞춰서 제작할 수 있게 해줘» (Deep04 — 7장뿐).

  형태 = 기존 카드 실측(510px 폭 · 아바타 원 블러 · 닉네임 블러 바 · 본문 검정 ·
  좋아요 줄). 좋아요 아이콘 줄은 **기존 카드에서 잘라 붙여** 형태를 정확히 맞춘다.
  내용 = 모델이 logline 에 맞는 시청자 댓글을 쓴다(EvoLink 무료). 실패하면 무난한
  감상 댓글 기본 문구를 쓴다.
"""
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

폭 = 510
글x, 글크기, 줄높이 = 64, 16, 23
본문색 = (15, 15, 15)
메타색 = (96, 96, 96)


def _폰트(size):
    from PIL import ImageFont
    for p in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
              "C:/Windows/Fonts/malgun.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _줄바꿈(draw, text, font, maxw):
    lines, cur = [], ""
    for tok in text.split():
        시도 = (cur + " " + tok).strip()
        if draw.textlength(시도, font=font) <= maxw:
            cur = 시도
        else:
            if cur:
                lines.append(cur)
            cur = tok
    if cur:
        lines.append(cur)
    return lines[:3]


def 카드생성(text, 예시들, out_path, 좋아요=None):
    """★원본 본뜨기(2026-09-03 사장님 «기존 형태랑 완전히 똑같게») — 원본 카드에서
    본문 글자 영역만 하얗게 지우고 새 문구를 실측 위치(x70·첫줄 y36·줄간 22px·
    글자색 진회색)에 그린다. 아바타·닉네임 블러·좋아요 줄은 원본 픽셀 그대로다."""
    from PIL import Image, ImageDraw
    font = _폰트(19)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = _줄바꿈(tmp, text, font, 폭 - 70 - 20)
    필요h = {1: 95, 2: 117, 3: 140}[max(1, min(3, len(lines)))]
    # 줄 수에 맞는 높이의 원본을 본으로 고른다 (없으면 가장 가까운 것)
    후보 = sorted(예시들, key=lambda p: (abs(Image.open(p).height - 필요h), random.random()))
    본 = Image.open(후보[0]).convert("RGB")     # 같은 높이 본이 여럿이면 무작위 순환(아바타 다양화)
    im = 본.copy()
    d = ImageDraw.Draw(im)
    d.rectangle((64, 30, im.width - 4, im.height - 32), fill="white")   # 본문만 지움
    y = 36
    for ln in lines[:3]:
        d.text((70, y), ln, font=font, fill=(47, 47, 47))
        y += 22
    # ★좋아요 숫자 — 카드마다 랜덤 (2026-09-03 사장님: 고정 536 은 이상하다).
    #   본의 숫자 자리만 지우고 새 숫자를 그린 뒤, 싫어요 아이콘(원본 픽셀)을
    #   새 숫자 폭에 맞춰 다시 붙인다. (실측: 엄지 x64~92 · 숫자 x99~ · 싫어요 그 뒤)
    import numpy as _np
    row0, row1 = im.height - 32, im.height - 4
    band = _np.asarray(im.crop((0, row0, im.width, row1)).convert("RGB")).astype(int)
    # ★문턱 150 — 싫어요 아이콘의 연한 회색 선까지 포함해야 통째로 잘린다
    #   (120 이었을 때 왼쪽 절반이 빠져 아이콘이 조각났다 — 2026-09-03 캡쳐)
    어둠 = band.mean(axis=2) < 150
    cols = _np.where(어둠[:, 95:].sum(axis=0) > 0)[0] + 95
    if len(cols):
        덩어리, cur = [], [int(cols[0]), int(cols[0])]
        for x in cols[1:]:
            if x - cur[1] > 6:
                덩어리.append(cur)
                cur = [int(x), int(x)]
            else:
                cur[1] = int(x)
        덩어리.append(cur)
        dx0, dx1 = 덩어리[-1]                       # 마지막 덩어리 = 싫어요 아이콘
        싫어요 = im.crop((max(0, dx0 - 10), row0, min(im.width, dx1 + 12), row1)).copy()
        d.rectangle((95, row0, im.width - 4, row1), fill="white")
        r = random.random()
        if r < 0.35:
            수 = str(random.randint(87, 947))
        elif r < 0.75:
            수 = f"{random.choice([1.1, 1.4, 2.3, 3.2, 4.7, 5.2, 6.8, 8.1])}천"
        else:
            수 = random.choice([f"{random.randint(10, 68)}천",
                                f"{random.choice([1.2, 2.4, 3.1])}만"])
        f13 = _폰트(14)
        d.text((100, row0 + 4), 수, font=f13, fill=(96, 96, 96))
        tw = int(d.textlength(수, font=f13))
        im.paste(싫어요, (100 + tw + 16, row0))
    im.save(out_path)
    return out_path


def 댓글문구(logline, n):
    """편 내용에 맞는 시청자 댓글 n개 (EvoLink 무료). 실패하면 기본 문구."""
    try:
        from s2pipe import gem
        from s2pipe.cfg import CFG as _C
        models = _C.get("gemini", {}).get("models", ["gemini-3.5-flash"])
        payload = {"contents": [{"role": "user", "parts": [{"text":
            (f"숏폼 내용: {logline}\n이 영상에 달릴 법한 유튜브 댓글 {n}개를 써라.\n"
             f"- 실제 시청자처럼 자연스럽게(웃음 ㅋㅋ·공감·경험담·드립). 한 개 20~60자.\n"
             f"- 이모지 남발 금지. JSON 만: {{\"comments\":[\"...\"]}}")}]}],
            "generationConfig": {"maxOutputTokens": 1500, "responseMimeType": "application/json"}}
        txt, _r, _m = gem.ask(payload, models, timeout=300)
        out = [str(c).strip() for c in json.loads(txt)["comments"] if str(c).strip()]
        assert len(out) >= n
        return out[:n]
    except Exception as e:
        print("댓글 문구 생성 실패 — 기본 문구 사용:", str(e)[:50])
        기본 = ["아니 이거 완전 내 얘기잖아 ㅋㅋㅋ", "마지막에 현웃 터졌네 ㅋㅋㅋㅋ",
                "이 채널 왜 이제 알았지", "연기 너무 자연스러운데 ㅋㅋ",
                "보다가 숨넘어갈 뻔 ㅋㅋㅋ 공유했다", "3번째 다시 보는 중 ㅋㅋㅋ"]
        return 기본[:n]


def 보충(cdir, logline, 최소=10, 여유=2):
    """폴더의 카드가 최소 미만이면 부족분+여유 만큼 같은 형태로 만들어 채운다."""
    pngs = sorted(glob.glob(os.path.join(cdir, "**", "*.png"), recursive=True))
    if len(pngs) >= 최소:
        return pngs
    n = 최소 - len(pngs) + 여유
    print(f"댓글 카드 {len(pngs)}장 < {최소}장 — 같은 형태로 {n}장 제작해 보충한다 (2026-09-03 사장님)")
    문구들 = 댓글문구(logline, n)
    카운트 = ["1.2천", "487", "2.1만", "893", "3.4천", "1.1만", "652", "9백"]
    out = []
    for k, 문구 in enumerate(문구들):
        p = os.path.join(cdir, f"댓글_보충{k + 1:02d}.png")
        카드생성(문구, pngs, p)
        out.append(p)
        print(f"  + {os.path.basename(p)}  「{문구[:30]}」")
    return sorted(glob.glob(os.path.join(cdir, "**", "*.png"), recursive=True))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cdir")
    ap.add_argument("--logline", default="")
    a = ap.parse_args()
    r = 보충(a.cdir, a.logline)
    print(f"총 {len(r)}장")
