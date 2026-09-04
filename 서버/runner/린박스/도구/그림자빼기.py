# -*- coding: utf-8 -*-
"""자막 그래픽의 **그림자만** 끈다. 다른 값은 손대지 않는다.

무엇을 만지나
  덩어리(플랫버퍼) root/12 = 그림자 불투명도. 0 으로 쓰면 그림자가 사라진다.
  root/14(크기)·15(흐림)·16(방향)·20(거리) 는 **그대로 둔다** — 불투명도가 0 이면
  어차피 안 보이고, 모르는 자리를 덜 건드릴수록 안전하다 (규격 §44).

  ★곳간 본 자체가 그림자를 갖고 있어서(둘레 [100,3,6,12,10]) 꾸미기.py 의
    `--그림자없이` 만으로는 안 없어진다. 그래서 0 을 **직접 써야** 한다.

쓰는 법
  python 그림자빼기.py <prproj> <ass> [층이름 …]
    층을 안 주면 headline_l1 headline_l2 band_narr band_dlg band_emph 를 끈다.
"""
import base64
import gzip
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))        # 도구/ 안의 형제 모듈
import 소스텍스트 as S  # noqa: E402
import 플랫버퍼 as F  # noqa: E402

덩어리찾기 = r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>'
불투명도칸 = 12


def 글줄들(raw):
    buf, _ = S.unwrap(raw)
    f = S._fields(buf, S._root0(buf))
    if 0 not in f:
        return []
    p = f[0]; v = p + F.u32(buf, p); n = F.u32(buf, v)
    out = []
    for i in range(n):
        ep = v + 4 + 4 * i
        e = ep + F.u32(buf, ep)
        g = S._fields(buf, e)
        if 0 not in g:
            continue
        t = g[0] + F.u32(buf, g[0])
        out.append(bytes(buf[t + 4:t + 4 + F.u32(buf, t)]).decode('utf-8', 'replace'))
    return out


prproj, ass = sys.argv[1], sys.argv[2]
층목록 = sys.argv[3:] or ['headline_l1', 'headline_l2',
                          'band_narr', 'band_dlg', 'band_emph']

# ass 에서 «그 층에 속한 글자» 를 모은다
대상글 = set()
for 줄 in open(ass, encoding='utf-8'):
    if not 줄.startswith('Dialogue:'):
        continue
    f = 줄.split(',', 9)
    if f[3].strip() not in 층목록:
        continue
    g = re.sub(r'\{[^}]*\}', '', f[9]).strip()
    if g:
        대상글.add(g)
print('끌 층 %s · 대상 글자 %d개' % (','.join(층목록), len(대상글)))

쪽 = gzip.open(prproj, 'rb').read().decode('utf-8')
표 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', 쪽)]
칸 = [(표[i], 표[i + 1] if i + 1 < len(표) else len(쪽)) for i in range(len(표))]

조각, 앞, 끈것, 이미 = [], 0, [], 0
for a, b in 칸:
    도막 = 쪽[a:b]
    끝 = 도막.find('<Name>', 1)
    m = re.search(덩어리찾기, 도막 if 끝 < 0 else 도막[:끝])
    if m:
        raw = base64.b64decode(m.group(1))
        글 = ''.join(글줄들(raw)).strip()
        if 글 in 대상글:
            buf, _ = S.unwrap(raw)
            f = S._fields(buf, S._root0(buf))
            if 불투명도칸 in f:
                옛 = F.f32(buf, f[불투명도칸])
                if 옛 != 0.0:
                    struct.pack_into('<f', buf, f[불투명도칸], 0.0)
                    도막 = 도막.replace(
                        m.group(1),
                        base64.b64encode(S.wrap(buf)).decode('ascii'), 1)
                    끈것.append((글, 옛))
                else:
                    이미 += 1
    조각.append(쪽[앞:a]); 조각.append(도막); 앞 = b
조각.append(쪽[앞:])
gzip.open(prproj, 'wb').write(''.join(조각).encode('utf-8'))

# 되읽어 확인한다 — 성공 메시지를 믿지 않는다
확 = gzip.open(prproj, 'rb').read().decode('utf-8')
표2 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', 확)]
남음 = 0
for i in range(len(표2)):
    a2 = 표2[i]; b2 = 표2[i + 1] if i + 1 < len(표2) else len(확)
    도 = 확[a2:b2]; 끝 = 도.find('<Name>', 1)
    mm = re.search(덩어리찾기, 도 if 끝 < 0 else 도[:끝])
    if not mm:
        continue
    raw = base64.b64decode(mm.group(1))
    글 = ''.join(글줄들(raw)).strip()
    if 글 in 대상글:
        buf, _ = S.unwrap(raw)
        f = S._fields(buf, S._root0(buf))
        if 불투명도칸 in f and F.f32(buf, f[불투명도칸]) != 0.0:
            남음 += 1
print('그림자 끈 것 %d장 · 이미 0 이던 것 %d장 · **아직 남은 것 %d장**'
      % (len(끈것), 이미, 남음))
print('소스 텍스트 칸 %d' % len(표2))
