#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prproj끝검사.py — 스케치 prproj 의 클립 끝·경계가 «시퀀스 프레임 격자» 위에 있고 «영상 끝»을 넘지 않는가.

왜 (2026-10-02 · 사장님 A안 «추천대로»)
  작업 규칙 12번 — 제목·자막·소리 클립이 영상 끝 프레임을 넘지 않는다. 린박스 키트 `도구/제목끝맞춤.py --확인만`
  을 루키치 290~241 납품 prproj 에 돌리니 8편(290 288 285 283 281 272 253 246)이 «넘는 End [N.5]» 로 걸렸다.
  실측(290): 시퀀스 시간축 = 30fps(VideoTrackGroup FrameRate 8467200000 틱 — 도너 신병4 EP1 과 같다)인데
  조립_prproj_sk.py 가 모든 클립 경계를 60fps 격자(FRAME 4233600000 · 주석 «60fps 시퀀스 (실측)» 이 틀렸다)로
  반올림했다. 그래서 경계가 30fps 의 반 프레임(.5)에 떨어진다 — 총길이 78.746초 → 60fps 4725장 = 30fps 2362.5장.
  V1 마지막 컷·A1·V2 껍데기·제목 두 줄이 모두 2362.5 에서 끝나 «제목만 남는» 꼬리는 없었지만, 영상 끝 자체가
  반 프레임이고 안쪽 경계(컷·대사·나레·효과음)도 반 프레임에 많이 떨어졌다(290: 대사 큐 끝 2013.5·2093.5 …).
  스케치 납품.sh 에는 이 검사가 없어서 지나갔다.

무엇을 재나 (제목끝맞춤.py 와 같은 자 — 단, «영상 끝» 을 빈도 추정 대신 V1 트랙에서 직접 읽는다)
  · 시퀀스 프레임 = VideoTrackGroup <FrameRate> (틱/프레임). 30fps 라고 가정하지 않고 파일에서 읽는다.
  · 영상 끝 = V1(비디오 트랙 그룹 첫 트랙) 클립 End 의 최댓값.
  · 탈 ① 영상 끝을 넘는 End (규칙 12)  ② 영상 끝이 프레임 격자 밖  ③ 격자 밖 Start/End (반 프레임 경계)
  셋 중 하나라도 있으면 종료코드 1. 윈도우판(*_윈도우.prproj)은 경로만 바꾼 사본이라 같은 자로 잰다.

쓰는 법
  python prproj끝검사.py <prproj> [<prproj> …] [--자세히]
  조립_prproj_sk.py 는 저장 직후 재기() 로 되읽어 막고, 검수도구/배치/납품.sh 는 NAS 에 쓰기 전에 이 파일을 부른다.
"""
import gzip
import re
import sys

TPS = 254016000000


def _트랙목록(xml, 그룹):
    m = re.search(rf'^\t<{그룹} ObjectID="\d+"[^>]*>(.*?)^\t</{그룹}>', xml, re.M | re.S)
    assert m, f"{그룹} 없음"
    fr = re.search(r"<FrameRate>(\d+)</FrameRate>", m.group(1))
    return re.findall(r'<Track Index="\d+" ObjectURef="([^"]+)"/>', m.group(1)), (int(fr.group(1)) if fr else None)


def _블록(xml, key, uid=False):
    at = "ObjectUID" if uid else "ObjectID"
    m = re.search(rf'^\t<(\w+) {at}="{re.escape(str(key))}"[^>]*>.*?^\t</\1>', xml, re.M | re.S)
    assert m, f"블록 없음 {key}"
    return m.group(0)


def 재기(xml):
    """xml(풀린 prproj 글) → dict. 탈 = 넘음 + 끝격자밖 + 격자밖."""
    if isinstance(xml, (bytes, bytearray)):
        xml = gzip.decompress(xml).decode("utf-8")
    vt, frame = _트랙목록(xml, "VideoTrackGroup")
    at, _ = _트랙목록(xml, "AudioTrackGroup")
    assert frame and TPS % frame == 0, f"시퀀스 프레임 틱 이상: {frame}"
    트랙 = []                                       # (이름, [(start, end), …])
    for k, (uids, 앞) in enumerate(((vt, "V"), (at, "A"))):
        for i, u in enumerate(uids):
            tb = _블록(xml, u, uid=True)
            cm = re.search(r'<ClipItems Version="3">(.*?)</ClipItems>', tb, re.S)
            refs = re.findall(r'<TrackItem Index="\d+" ObjectRef="(\d+)"/>', cm.group(1)) if cm else []
            쌍 = []
            for r in refs:
                b = _블록(xml, r)
                ti = re.search(r'<TrackItem Version="\d+">(.*?)</TrackItem>', b, re.S)
                s = re.search(r"<Start>(-?\d+)</Start>", ti.group(1)) if ti else None
                e = re.search(r"<End>(-?\d+)</End>", ti.group(1)) if ti else None
                if e:
                    쌍.append((int(s.group(1)) if s else 0, int(e.group(1))))
            트랙.append((f"{앞}{i + 1}", 쌍))
    v1 = 트랙[0][1]
    assert v1, "V1 에 클립이 없다"
    영상끝 = max(e for _s, e in v1)
    넘음, 격자밖 = [], []
    for 이름, 쌍 in 트랙:
        for s, e in 쌍:
            if e > 영상끝:
                넘음.append((이름, e))
            for v in (s, e):
                if v % frame:
                    격자밖.append((이름, v))
    끝격자밖 = 영상끝 % frame != 0
    return {"frame": frame, "fps": TPS / frame, "영상끝": 영상끝, "영상끝_장": 영상끝 / frame,
            "넘음": 넘음, "끝격자밖": 끝격자밖, "격자밖": 격자밖,
            "트랙": [(n, len(c)) for n, c in 트랙],
            "탈": len(넘음) + int(끝격자밖) + len(격자밖)}


def 한줄(r):
    f = r["frame"]
    넘 = sorted({round(e / f, 2) for _n, e in r["넘음"]})
    return (f"시퀀스 {r['fps']:.3f}fps · 영상 끝 {r['영상끝_장']:g}장({r['영상끝'] / TPS:.3f}s)"
            f"{' ★격자 밖' if r['끝격자밖'] else ''} · 넘는 End {len(r['넘음'])}개{(' ' + str(넘)) if 넘 else ''}"
            f" · 격자 밖 경계 {len(r['격자밖'])}개")


def main(argv):
    자세히 = "--자세히" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    나쁨 = 0
    for p in paths:
        r = 재기(open(p, "rb").read())
        print(("[OK] " if not r["탈"] else "[X] ") + f"{p}: " + 한줄(r))
        if 자세히 and r["탈"]:
            f = r["frame"]
            for n, e in r["넘음"][:20]:
                print(f"    넘음 {n} End {e / f:g}장")
            for n, v in r["격자밖"][:20]:
                print(f"    격자 밖 {n} {v / f:g}장")
        나쁨 += bool(r["탈"])
    return 1 if 나쁨 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
