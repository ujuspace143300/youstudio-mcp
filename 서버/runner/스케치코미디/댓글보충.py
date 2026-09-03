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


def 카드생성(text, 예시png, out_path, 좋아요="1.2천"):
    """기존 카드와 같은 형태의 댓글 카드 하나를 그린다."""
    from PIL import Image, ImageDraw, ImageFilter
    font = _폰트(글크기)
    tmp = Image.new("RGB", (폭, 200), "white")
    d0 = ImageDraw.Draw(tmp)
    lines = _줄바꿈(d0, text, font, 폭 - 글x - 14)
    h = 95 + 줄높이 * (len(lines) - 1) if lines else 95
    im = Image.new("RGB", (폭, h), "white")
    d = ImageDraw.Draw(im)
    # 아바타 — 흐린 원 (기존 카드처럼 뭉갠 색)
    색 = random.choice([(196, 148, 108), (150, 150, 156), (170, 140, 170), (140, 160, 150)])
    av = Image.new("RGB", (36, 36), "white")
    ImageDraw.Draw(av).ellipse((0, 0, 35, 35), fill=색)
    av = av.filter(ImageFilter.GaussianBlur(2.2))
    mask = Image.new("L", (36, 36), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 35, 35), fill=255)
    im.paste(av, (14, 8), mask)
    # 닉네임 — 블러 바 (개인정보 뭉갬 형태 그대로)
    nw = random.randint(90, 150)
    bar = Image.new("RGB", (nw, 12), (208, 205, 200))
    bar = bar.filter(ImageFilter.GaussianBlur(2.5))
    im.paste(bar, (글x, 10))
    # 본문
    y = 32
    for ln in lines:
        d.text((글x, y), ln, font=font, fill=본문색)
        y += 줄높이
    # 좋아요 줄 — 기존 카드 하단 아이콘 줄을 잘라 붙이고 숫자만 새로
    try:
        ex = Image.open(예시png).convert("RGB")
        아이콘 = ex.crop((글x, ex.height - 30, 글x + 26, ex.height - 6))   # 엄지 아이콘
        싫어요 = ex.crop((ex.width - 380, ex.height - 30, ex.width - 356, ex.height - 6))
        im.paste(아이콘, (글x, h - 30))
        d.text((글x + 32, h - 28), 좋아요, font=_폰트(13), fill=메타색)
        im.paste(싫어요, (글x + 32 + int(d.textlength(좋아요, font=_폰트(13))) + 18, h - 30))
    except Exception:
        d.text((글x, h - 28), f"👍 {좋아요}", font=_폰트(13), fill=메타색)
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
        카드생성(문구, pngs[k % len(pngs)], p, 좋아요=카운트[k % len(카운트)])
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
