#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""설정_누룽지독.py — «누룽지독 템플릿» 설정(config_누룽지독.json)을 만든다.

2026-09-29 사장님 결정: 점심이네 64편 = 누룽지독 템플릿(Deep 에 쓰던 틀 · 로고 = 누룽지독(@yellow_dog) 고정 —
볼트 프리셋/스케치코미디/작품/Deep.md). 손으로 만들지 않고 이 도구로 만든다 — config.json 은 규격조립.py 가
다시 만드는 생성 파일이라, 다시 만들어지면 이 도구를 한 번 더 돌린다.

  바탕     = <작업 폴더>/config.json (Deep 틀, 규격조립.py 생성본)
  + 튐완화 = <작업 폴더>/config_숨은기록.json 의 layout.video_box 여섯 값과 그 주석
             (2026-09-10 사장님 «튀는 구간 없게» 는 채널 공통 지시)
  + 머리   = channel 을 누룽지독으로 · 머리를 로고 그림 한 장으로(channel.logo_image — build.로고얹기)
             그림 = 저장소 자산/스케치코미디/channel_logo_누룽지독.png (= work/Deep01_로고.png 와 같은 바이트)
  출처 줄  = layout.credit.format 은 Deep 그대로 «#{channel} - {title}». {channel} 은 편시작 --채널 값이다.

사용: python 설정_누룽지독.py [작업 폴더]   (기본 ~/Desktop/스케치코미디) → <작업 폴더>/config_누룽지독.json
"""
import copy
import json
import os
import sys

튐완화_키 = ["eye_center", "beat_zoom", "beat_shift", "beat_cut_relief", "max_shift", "smooth_win", "_튐완화"]
로고_이름 = "channel_logo_누룽지독.png"
# 최하연님 작업 Deep prproj 실측(준비_prproj_sk 가 쓰던 값 = build.로고_자리·로고_비율). 설정에 적어 두면
# mp4·프리미어가 둘 다 이 값을 읽는다(build.로고얹기).
로고_자리 = [0.19928400218486786, 0.069892480969429016]
로고_비율 = 0.16451612472534


def main():
    wd = os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/스케치코미디"))
    base = json.load(open(os.path.join(wd, "config.json"), encoding="utf-8"))
    hid = json.load(open(os.path.join(wd, "config_숨은기록.json"), encoding="utf-8"))
    cfg = copy.deepcopy(base)

    logo = os.path.join(cfg["paths"]["assets"], 로고_이름)
    assert os.path.isfile(logo), f"로고 그림이 없다: {logo} — work/Deep01_로고.png 를 이 이름으로 복사해 두라"

    cfg["_"] = (
        "★누룽지독 템플릿 설정(2026-09-29 · 검수도구/배치/설정_누룽지독.py 가 만든다 — 손으로 고치지 말고 도구를 다시 돌려라). "
        "사장님 결정 2026-09-29: 점심이네 64편 = «누룽지독 템플릿»(Deep 에 쓰던 틀 · 로고 = 누룽지독(@yellow_dog) 고정 — "
        "볼트 프리셋/스케치코미디/작품/Deep.md). "
        "바탕 = config.json(Deep 틀 · 규격조립.py 생성본 — 그 파일의 _ 는 «생성된 파일, 정본은 스타일/스케치코미디/{규격,정답지,우리실측}.json»). "
        "바꾼 것 셋: ① layout.video_box 튐완화 여섯 값(eye_center·beat_zoom·beat_shift·beat_cut_relief·max_shift·smooth_win)과 "
        "주석 _튐완화 를 config_숨은기록.json 에서 — 2026-09-10 사장님 «튀는 구간 없게» 는 채널 공통 지시. 상자 크기·자리(y0·y1·h)는 Deep 그대로. "
        "② channel = 누룽지독(@yellow_dog) · 머리를 로고 그림 한 장으로(channel.logo_image) — Deep 납품 mp4 머리엔 임시값 "
        "«@sketchsample 스케치샘플» 이 찍혀 나갔고(Deep90 3초 프레임) 프리미어에만 누룽지독 로고가 들어갔다. 이제 mp4(build.draw_frame)와 "
        "프리미어(준비_prproj_sk)가 같은 함수(build.로고얹기)·같은 자리로 그린다. "
        "③ layout.credit 은 Deep 그대로 «#{channel} - {title}» — {channel} 은 편시작 --채널 값(점심이네)이다(_channel 참고). "
        "편시작: python 편시작_deep.py <소재폴더> --slug <슬러그> --채널 점심이네 --로고 " + logo
    )

    cfg["channel"] = {
        "name": "누룽지독",
        "handle": "@yellow_dog",
        "logo_image": logo,
        "logo_pos": list(로고_자리),
        "logo_scale": 로고_비율,
        "_": ("★누룽지독 템플릿(2026-09-29 사장님 결정 — 점심이네 64편). 머리는 로고 그림 한 장이다: logo_image 가 있으면 "
              "build.draw_frame 이 아이콘·핸들·채널명 글자를 그리지 않고 그림을 얹는다(없으면 멈춘다). name·handle 은 화면에 "
              "그리지 않는 기록용."),
        "_logo": ("그림 = work/Deep01_로고.png 사본(2604x1600 · 개 얼굴 원 + @yellow_dog + 누룽지독 · 흰 배경 · Deep 92편 로고와 같은 "
                  "바이트). 자리 logo_pos = 로고 중심 (x/1080, y/1920) · 크기 logo_scale = 프리미어 비율 16.45% — 최하연님 작업 "
                  "Deep prproj 실측(준비_prproj_sk 가 쓰던 값). 흰 배경(250 이상)은 layout.bg 로 바꾼다(배경맞춤)."),
    }

    vb, hv = cfg["layout"]["video_box"], hid["layout"]["video_box"]
    for k in 튐완화_키:
        assert k in hv, f"config_숨은기록.json layout.video_box 에 {k} 가 없다"
        vb[k] = hv[k]

    cr = cfg["layout"]["credit"]
    assert cr["format"] == "#{channel} - {title}", f"Deep 출처 형식이 바뀌었다: {cr['format']!r} — 사장님께 여쭌다"
    cr["_channel"] = ("★{channel} = 편시작_deep.py --채널 값 → work/<슬러그>.info.json channel → plan.origin_of → "
                      "proj.credit.channel → build.draw_frame. 점심이네는 --채널 점심이네 로 준다(주지 않으면 기본값 «띱 Deep» 이 "
                      "찍힌다). {title} = 같은 info.json 의 title(편시작이 정한 원제).")

    dst = os.path.join(wd, "config_누룽지독.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("생성:", dst)


if __name__ == "__main__":
    main()
