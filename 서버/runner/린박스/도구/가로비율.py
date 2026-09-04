# -*- coding: utf-8 -*-
"""ass 에서 «\\fscx» 로 좁힌 줄을 프로젝트의 「가로 비율」에 옮긴다.

ass 의 `\\fscx` 는 프로젝트로 안 넘어간다. 그대로 두면 완성본에서는 좁혀진 줄이
프리미어에서는 안 좁혀져 화면 밖으로 나간다.
"""
import base64
import gzip
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))        # 도구/ 안의 형제 모듈
import 소스텍스트 as S  # noqa: E402
import 플랫버퍼 as F  # noqa: E402

찾 = r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>'


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
목표 = {}
for l in open(ass, encoding='utf-8'):
    if not l.startswith('Dialogue:'):
        continue
    f = l.split(',', 9)
    m = re.search(r'\\fscx(\d+)', f[9])
    if m:
        목표[re.sub(r'\{[^}]*\}', '', f[9]).strip()] = float(m.group(1))

쪽 = gzip.open(prproj, 'rb').read().decode('utf-8')
표 = [m.start() for m in re.finditer(r'<Name>소스 텍스트</Name>', 쪽)]
칸 = [(표[i], 표[i + 1] if i + 1 < len(표) else len(쪽)) for i in range(len(표))]
조각, 앞, n = [], 0, 0
for a, b in 칸:
    도막 = 쪽[a:b]
    끝 = 도막.find('<Name>', 1)
    m = re.search(찾, 도막 if 끝 < 0 else 도막[:끝])
    글 = ''.join(글줄들(base64.b64decode(m.group(1)))).strip() if m else ''
    if 글 in 목표:
        mm = re.search(r'(<Name>가로 비율</Name>\s*<StartKeyframe>)([^<]*)(</StartKeyframe>)', 도막)
        if mm:
            값 = mm.group(2).split(',')
            값[1] = '%.6f' % 목표[글]
            도막 = 도막[:mm.start(2)] + ','.join(값) + 도막[mm.end(2):]
            n += 1
    조각.append(쪽[앞:a]); 조각.append(도막); 앞 = b
조각.append(쪽[앞:])
gzip.open(prproj, 'wb').write(''.join(조각).encode('utf-8'))
확 = gzip.open(prproj, 'rb').read().decode('utf-8')
print('  가로비율 %d곳 (ass 에 좁힌 줄 %d개) · 소스 텍스트 칸 %d'
      % (n, len(목표), len(re.findall(r'<Name>소스 텍스트</Name>', 확))))
