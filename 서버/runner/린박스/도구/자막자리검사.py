# -*- coding: utf-8 -*-
"""**프로젝트에 든 자막이 화면 안에 있는지** 되읽어 검사한다. (납품 전 관문)

왜 이 관문이 필요한가
  ass 만 검사하면 «ass 는 멀쩡한데 프로젝트만 어긋난» 것을 못 잡는다.
  실제로 「?!」 는 ass 에서 제자리였지만, 도구가 그 줄을 조용히 건너뛰어
  프로젝트에서는 상자 왼쪽 540 에 남아 **화면 오른쪽으로 잘려 나갔다**
  (2026-08-27 사장님 지적). 그때 «못 찾음 0장» 이라고 찍혀 아무도 몰랐다.

무엇을 보나 — prproj 의 자막 낱장마다
  ① 글자를 읽는다 (구조로 — 한글이 없어도 읽힌다)
  ② 그 글자가 ass 에 있나 (없으면 ★)
  ③ 「위치」가 ass 자리에서 나온 값과 맞나 (어긋나면 ★)
  ④ 글자 상자가 화면(0~1080) 밖으로 나가지 않나 (나가면 ★)

쓰는 법  python 자막자리게이트.py <prproj> <ass>
"""
import base64
import gzip
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))        # 도구/ 안의 형제 모듈
import 소스텍스트 as S  # noqa: E402

상자폭 = 1040.0
줄높이배수 = 1.0
찾 = r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>'

prproj, ass = sys.argv[1], sys.argv[2]


def 초(x):
    h, m, s = x.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


# ── ass 에서 «글자 → 자리» ─────────────────────────────────────
스타일 = {}
for 줄 in open(ass, encoding='utf-8'):
    if 줄.startswith('Style:'):
        칸 = 줄[6:].split(',')
        스타일[칸[0].strip()] = float(칸[2])
ass자리 = {}
for 줄 in open(ass, encoding='utf-8'):
    if not 줄.startswith('Dialogue:'):
        continue
    f = 줄.split(',', 9)
    층 = f[3].strip()
    글 = re.sub(r'\{[^}]*\}', '', f[9]).strip()
    if not 글:
        continue
    m = re.search(r'\\pos\(\s*([\d.]+)\s*,\s*([\d.]+)\)', f[9])
    an = re.search(r'\\an(\d)', f[9])
    if not m:
        continue
    x, y = float(m.group(1)), float(m.group(2))
    an = int(an.group(1)) if an else 8
    크기 = 스타일.get(층, 90.0)
    줄수 = 1
    높이 = 줄수 * 크기 * 줄높이배수
    위 = y if an in (7, 8, 9) else (y - 높이 / 2 if an in (4, 5, 6) else y - 높이)
    ass자리[글] = (x - 상자폭 / 2, 위, 층, x)

# ── prproj 를 되읽는다 ────────────────────────────────────────
쪽 = gzip.open(prproj, 'rb').read().decode('utf-8', errors='replace')
표 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', 쪽)]
탈, 잰것 = [], 0
for i in range(len(표)):
    a = 표[i]
    b = 표[i + 1] if i + 1 < len(표) else len(쪽)
    도 = 쪽[a:b]
    끝 = 도.find('<Name>', 1)
    m = re.search(찾, 도 if 끝 < 0 else 도[:끝])
    if not m:
        continue
    글목 = S.글자만(base64.b64decode(m.group(1)))
    글 = ' '.join(t for t in 글목 if t.strip()).strip()
    if not 글:
        탈.append(('(글자 못 읽음)', '', '덩어리를 못 읽는다'))
        continue
    잰것 += 1
    mm = re.search(r'<Name>위치</Name>\s*<StartKeyframe>([^<]*)</StartKeyframe>', 도)
    if not mm:
        탈.append((글, '', '「위치」 칸이 없다'))
        continue
    v = mm.group(1).split(',')[1]
    px, py = (float(q) for q in v.split(':'))
    px *= 1080.0
    py *= 1920.0
    있 = ass자리.get(글)
    if 있 is None:
        # 여러 줄이 한 장에 담긴 경우 첫 줄로 찾아본다
        있 = next((ass자리[q] for q in ass자리 if q.startswith(글목[0])), None)
    if 있 is None:
        탈.append((글, f'{px:.0f},{py:.0f}', 'ass 에 없는 글자'))
        continue
    기x, 기y, 층, 중심x = 있
    # ★가로는 글꼴 지표와 무관하게 «ass x − 상자폭/2» 로 딱 떨어진다 → 엄격히 본다.
    #   세로는 도구가 글줄 높이에 환산비를 곱하므로 몇 px 차이는 정상 → 넉넉히 본다.
    if abs(px - 기x) > 2.5:
        탈.append((글, f'{px:.0f},{py:.0f}',
                   f'가로가 ass 자리({기x:.0f})와 다르다 [{층}]'))
        continue
    if abs(py - 기y) > 14:
        탈.append((글, f'{px:.0f},{py:.0f}',
                   f'세로가 ass 자리({기y:.0f})와 너무 다르다 [{층}]'))
        continue
    # 글자 상자가 화면 밖으로?
    왼 = px
    오 = px + 상자폭
    if 중심x - 상자폭 / 2 < -상자폭 or 오 > 1080 + 상자폭:
        탈.append((글, f'{px:.0f},{py:.0f}', '상자가 화면 밖'))

print('되읽은 자막 %d장 · **탈 %d장**' % (잰것, len(탈)))
if 탈:
    print()
    print('%-20s %-14s %s' % ('글자', '프로젝트 위치', '무엇이 탈인가'))
    print('-' * 88)
    for 글, 자리, 왜 in 탈:
        print('%-20s %-14s %s' % (글[:20], 자리, 왜))
    sys.exit(1)
print('자막이 모두 ass 자리와 같다 — 화면 밖으로 나간 것 없음')
