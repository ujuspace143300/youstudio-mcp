# -*- coding: utf-8 -*-
r"""프리미어 프로젝트의 자막에 **그림자와 등장 팝**을 넣는다.

★이 도구는 «부품을 새로 만들지 않는다». 그게 핵심이다.
  사장님 프로젝트는 자막마다 효과가 세 겹이다 —
      벡터 모션(기본자막·아모르) + 그림자 효과 + 텍스트
  그 부품을 밖에서 만들어 달아 봤더니 **프리미어가 파일을 거부했다**(두 번).
  XML 은 멀쩡한데 프리미어 내부 규칙에 걸린다. 밖에서는 어느 규칙인지 못 좁힌다.

  대신 **이미 있는 매개변수만 고친다.** 그건 열리는 것이 확인됐다.
      · 등장 팝  → 텍스트의 «비율 조정» 에 키프레임 (부품 없이)
      · 그림자   → 덩어리 안의 둘레 값 (root/10 색 · /12 /14 /15 /16 /20)

  사장님 사전설정과 속 배선은 다르지만 **보이는 결과는 같고, 파일이 안 깨진다.**

값의 출처 — 미안해형.prproj 에서 읽은 사장님 사전설정
  「2. 팝업자막_아모르」 비율 조정 150% → 175% (0.182초)
      최종 크기가 안 변하게 옮기면 85.7% → 100%
  「4. 글자에 그림자넣기」 검정 · 불투명도 100 · 크기 3 · 흐림 6 · 방향 12 · 거리 10

쓰는 법
  python <키트>/꾸미기.py <prproj>
  python <키트>/꾸미기.py <prproj> --팝없이      그림자만
"""
import argparse
import base64
import gzip
import os
import re
import shutil
import struct
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '도구'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import 소스텍스트 as S      # noqa: E402
import 플랫버퍼 as F        # noqa: E402

틱 = 254016000000.0
# ── 등장 팝 ──────────────────────────────────────────────
# ★2026-08-25 사장님: «모션이 빠진 것 같아»
#   전에는 미안해형 사전설정(150%→175%, 즉 85.7%→100%)만 넣었다. 폭이 14% 뿐이라
#   **눈에 거의 안 보인다.** 완성본(ass)의 팝은 훨씬 크고 되튐이 있다 —
#       scx62 → 	(0,85,118) → 	(85,160,93) → 	(160,235,100)
#   완성본과 같아야 하므로 그 네 점을 그대로 쓴다. (초, 배율%)
팝점 = [(0.000, 62.0), (0.085, 118.0), (0.160, 93.0), (0.235, 100.0)]
팝점_옛 = [(0.000, 150.0 / 175.0 * 100), (0.182, 100.0)]   # 미안해형 사전설정
그림자 = {12: 100.0, 14: 3.0, 15: 6.0, 16: 12.0, 20: 10.0}
덩어리찾기 = r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>'

P = argparse.ArgumentParser()
P.add_argument('prproj')
P.add_argument('--팝없이', action='store_true', dest='팝없이')
P.add_argument('--팝자리보정', action='store_true', dest='팝자리보정',
               help='팝과 함께 «위치» 키프레임도 넣는다. 린박스에서는 넣지 마라 — 1편에 없다')
P.add_argument('--그림자없이', action='store_true', dest='그림자없이')
P.add_argument('--옛팝', action='store_true', dest='옛팝',
               help='미안해형 사전설정(85.7→100)으로. 기본은 완성본과 같은 말랑 팝')
P.add_argument('자막', nargs='?', default=None,
               help='완성본을 구운 ass. 주면 **줄마다** 그 줄의 팝을 그대로 쓴다 (권장)')
A = P.parse_args()
자리보정 = bool(getattr(A, '팝자리보정', False))

무팝 = set()


def ass팝(경로):
    """ass 한 줄에서 팝 네 점을 읽는다 — {글자: [(초, 배율%), ...]}

    ★2026-08-25 옆자리(타짜)가 잡아 준 것 — **줄마다 봉우리가 다르다.**
      긴 줄일수록 굽는 쪽이 봉우리를 낮춘다(118 대신 111~116). 팝이 튈 때 글자가 화면
      밖으로 나가지 않게 하는 안전장치로 보인다. 붙박이 118 을 넣으면 그게 풀린다.
      5%라 눈엔 안 보이지만 «완성본과 같다» 가 아니다.
    """
    표 = {}
    for ln in open(경로, encoding='utf-8').read().split(chr(10)):
        if not ln.startswith('Dialogue:'):
            continue
        칸 = ln.split(',', 9)
        본문 = 칸[9]
        태그 = 본문.split('}')[0] if '}' in 본문 else ''
        글 = re.sub(r'\{[^}]*\}', '', 본문).replace(chr(92) + 'N', ' ').strip()
        시작 = re.search(r'\\fscx([\d.]+)', 태그)
        if not 시작:
            continue
        점 = [(0.0, float(시작.group(1)))]
        for m in re.finditer(r'\\t\((\d+),(\d+),\\fscx([\d.]+)', 태그):
            점.append((int(m.group(2)) / 1000.0, float(m.group(3))))
        if len(점) > 1:
            표[글] = 점
        else:
            무팝.add(글)      # ★팝이 «없는» 줄이다 — 모션자막처럼 제 움직임을 가진 층
    return 표


팝표 = ass팝(A.자막) if A.자막 else {}
if A.자막:
    print('  ass 에서 줄마다 팝을 읽었다 — %d줄' % len(팝표))

d = gzip.open(A.prproj, 'rb').read().decode('utf-8')
표 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', d)]
if not 표:
    raise SystemExit('자막 덩어리가 없다 — 프리미어 프로젝트가 맞는가?')
칸 = [(표[i], 표[i + 1] if i + 1 < len(표) else len(d)) for i in range(len(표))]

조각, 끝, 센, 맞춘것, 팝없는것, 못맞춘 = [], 0, 0, 0, 0, []
for a, b in 칸:
    도막 = d[a:b]
    m = re.search(덩어리찾기, 도막)
    if not m:
        continue
    buf, _ = S.unwrap(base64.b64decode(m.group(1)))
    f = S._fields(buf, S._root0(buf))

    if not A.그림자없이:
        # ★root/10 을 건드리지 마라 — 그건 **둘레색이 아니라 «채움색»** 이다 (2026-08-26).
        #   전에는 여기서 root/10 을 검정으로 칠했다. 그런데 `서식입히기.py` 는 같은 칸을
        #   **글자 칠**로 쓴다(«④ 채움색 — 그래픽 전체 (root/10)»). 꾸미기가 뒤에 도니까
        #   **글자색이 통째로 검정이 됐다.** 포헨즈 1-1 에서 모션자막 분홍(#F070C0)이
        #   사라지고 검정 8장이 생겼다 — 사장님: «외곽선 색이 분홍으로 바뀌었어,
        #   글자의 색이 원본이랑 너무 달라».
        #   둘레색은 **run/4** 에 있고 `서식입히기.py` 가 이미 ass 대로 넣어 뒀다.
        #   여기서는 **그림자 값(12·14·15·16·20)만** 만진다.
        for k, v in 그림자.items():
            if k in f:
                struct.pack_into('<f', buf, f[k], v)
    W = F.f32(buf, f[2]) if 2 in f else 1040.0
    도막 = 도막.replace(m.group(1), base64.b64encode(S.wrap(buf)).decode('ascii'), 1)

    if not A.팝없이:
        위 = re.search(r'<Name>위치</Name>\s*<StartKeyframe>(-?\d+),([^,]+),', 도막)
        if 위:
            x, y = (float(v) for v in 위.group(2).split(':'))
            cx = x * 1080.0 + W / 2.0
            뒤 = '0,0,0,0.16666666666666666,0,0.16666666666666666'
            점들 = 팝점_옛 if A.옛팝 else 팝점
            if 팝표:                                   # 그 줄의 ass 값이 있으면 그것이 이긴다
                # ★S.read_text 는 «(자리, 글자)» 짝 목록을 돌려준다 — 문자열이 아니다.
                #   전에 ''.join() 으로 다뤘다가 40장 다 못 맞췄는데 **예외를 조용히
                #   삼켜서** 그것을 못 봤다. 삼키지 말고 세어서 알린다 (2026-08-25)
                글조각 = S.read_text(base64.b64decode(m.group(1))) or []
                글 = max((t for _, t in 글조각), key=len, default='')
                if 글 in 팝표:
                    점들 = 팝표[글]; 맞춘것 += 1
                elif 글 in 무팝:
                    # ★ass 에 `	(…)` 가 없는 줄 — **팝이 없는 것이 정답이다.**
                    #   모션자막(effect_float)은 `\move` 로 제 움직임을 갖는다.
                    #   여기에 팝을 또 얹으면 두 움직임이 겹쳐 완성본과 달라진다.
                    점들 = None; 팝없는것 += 1
                else:
                    못맞춘.append(글 or '(글자를 못 읽었다)')
            자리조각, 배율조각 = [], []
            for 초, 배 in (점들 or []):
                # 커질 때 글자가 오른쪽으로 딸려가지 않게 x 를 되민다 (기준점이 상자 왼쪽 위라서)
                xk = (cx - (배 / 100.0) * W / 2.0) / 1080.0
                t = int(round(초 * 틱))
                자리조각.append(f'{t},{xk:.9f}:{y:.9f},{뒤},5,4,0,0,0,0;')
                배율조각.append(f'{t},{배:g}.,{뒤};')
            자리키 = ''.join(자리조각)
            배율키 = ''.join(배율조각)
            if 점들 is None:
                자리키 = 배율키 = None

            def 얹기(도막, 이름, 키):
                패 = (r'(<Name>' + 이름 + r'</Name>\s*<StartKeyframe>[^<]*</StartKeyframe>)'
                      r'(\s*<Keyframes>[^<]*</Keyframes>)?')
                return re.sub(패, lambda z: z.group(1) + '\n\t\t<Keyframes>' + 키 + '</Keyframes>',
                              도막, count=1)
            if 자리키 is not None:
                # ★«위치» 되밀기는 기본으로 넣지 않는다 (2026-08-26).
                #   사장님이 확정하신 1편에는 위치 키프레임이 **0장**이고 팝만 39장이다.
                #   자리잡기.py 로 글자상자를 다시 잡은 뒤에는 여기 쓰는 cx·W 가
                #   그 상자와 어긋나서, 팝 도는 동안 자막이 제자리를 벗어난다 —
                #   사장님 눈에는 «팝이 안 들어갔다» 로 보였다.
                #   되밀기가 필요한 채널에서만 --팝자리보정 을 준다.
                if 자리보정:
                    도막 = 얹기(도막, '위치', 자리키)
                도막 = 얹기(도막, '비율 조정', 배율키)
    센 += 1
    조각.append(d[끝:a]); 조각.append(도막); 끝 = b
조각.append(d[끝:])
새d = ''.join(조각)

# ── 확인: 여기서 걸리면 파일을 안 건드린다 ──────────────────────
ET.fromstring(새d)
# ★«내용 담은 덩어리» 수로 잰다 — 칸 수가 아니다. 같은 문구가 되풀이되는 편에서는
#   프리미어가 한 무리에 덩어리를 하나만 두고 나머지는 BinaryHash 로 가리킨다.
전 = re.findall(덩어리찾기, d)
확 = re.findall(덩어리찾기, 새d)
if len(확) != len(전):
    raise SystemExit(f'덩어리 수가 달라졌다 — 전 {len(전)} · 후 {len(확)}')
for q in 확:
    buf, _ = S.unwrap(base64.b64decode(q)); S.runs(buf); S._fields(buf, S._root0(buf))
효과 = set(re.findall(r'<MatchName>([^<]*)</MatchName>', 새d))
print(f'  자막 {센}장에 ' + ('그림자' if not A.그림자없이 else '') +
      ('' if A.팝없이 or A.그림자없이 else ' + ') + ('등장 팝' if not A.팝없이 else '') + ' 넣었다')
if 팝표:
    print('  줄마다 제 팝 %d장' % 맞춘것
          + ('' if not 팝없는것 else ' · 팝이 없는 줄 %d장(모션자막 등 — 제 움직임이 있다)' % 팝없는것)
          + ('' if not 못맞춘 else
          ' · ★ass 에서 못 찾은 것 %d장: %s' % (len(못맞춘), ' / '.join(못맞춘[:3]))))
    # ★제목(headline) 두 장은 팝이 원래 없다 — 그 몫만큼은 경고로 끝낸다 (2026-09-02 제목 텍스트화)
    if 못맞춘 and len(못맞춘) <= 2:
        print('  (제목 %d장은 팝 없이 둔다 — 정상)' % len(못맞춘))
    elif 못맞춘:
        raise SystemExit('  ass 와 짝이 안 맞는 자막이 있다 — 붙박이 값이 들어갔다. 확인해라')
print(f'  확인 — XML 정상 · 덩어리 {len(확)}장 정상 · 효과 부품 {sorted(효과)} (새로 만든 것 없음)')

백업 = A.prproj.replace('.prproj', f'_꾸미기전_{time.strftime("%m%d_%H%M")}.prproj')
shutil.copy2(A.prproj, 백업)
with gzip.open(A.prproj, 'wb') as fh:
    fh.write(새d.encode('utf-8'))
print(f'  전 판은 옆에 두었다: {os.path.basename(백업)}')
print(f'  다 됐다 → {A.prproj}')
