# -*- coding: utf-8 -*-
r"""자막 클립에 **「팝업자막_아모르」의 벡터 모션**을 달아 튀는 팝을 만든다.

왜 부품을 새로 다는가 (다른 길이 없다)
  사장님 프리셋 「2. 팝업자막_아모르」의 정체는 `AE.ADBE Graphic Group`(벡터 모션) 부품이다.
  우리 자막 클립에는 `AE.ADBE Text` 하나뿐이라 그 겹이 **비어 있다.**

  Text 의 «기준점» 으로 흉내 낼 수 없다 — 본보기를 재 보니 Text 쪽 기준점은
  **0:0 그대로**이고(우리와 같다), 0.5:0.9453125 는 **Graphic Group 쪽**에 있다.
  두 겹의 좌표계가 달라서 아래층 값을 위층에 옮겨 적을 수 없다.

  ★부품을 새로 다는 것은 2026-08-24 에 프로젝트를 두 번 깨뜨린 일이다. 그래서
    [[premiere-clone-objects-rules]] 의 네 규칙을 전부 지킨다:
      ① 닫힘은 ObjectRef·ObjectURef 를 **둘 다** 따라간다 (여기선 7개 · 2770바이트 · URef 없음)
      ② 베낀 도막의 ID·UID·Ref·URef 를 **한 번에 훑으며 전부** 갈아 끼운다
      ③ ClipID 는 이 부품엔 없다
      ④ `PremiereFilterPrivateData` 는 **첫 등장만 내용, 나머지는 해시 참조**

본보기에서 잰 값 (미안해형.prproj · Graphic Group 을 가진 자막 56장)
      위치        0.5:0.65104168653488159   49/56 장이 이 값 — 붙박이다
      기준점       0.5:0.9453125             51/56
      비율 조정     StartKeyframe 100 · 팝은 Keyframes 로 (50/56 장)
      폭 비율 조정   100 · 회전 0
  ★키프레임 시각은 **소재 시간** 기준이다. 본보기 자막은 소재가 3600초(01:00:00:00)에서
    시작해 키프레임도 3600초대에 있다. 우리 자막은 소재가 **0초**에서 시작하므로
    키프레임도 0초대에 넣는다. 클립마다 제자리에서 돈다.

팝 값은 어디서 오나
  **그 편의 ass 에서 줄마다 읽는다.** 본보기의 150→175 를 붙박이로 쓰지 않는다 —
  ass 의 봉우리는 줄마다 다르고(118·113·115·111·116) **긴 줄일수록 낮다.**
  붙박이를 넣으면 그 안전장치가 풀린다. 그리고 끝값이 100% 가 되게 옮겨 넣으므로
  최종 크기는 안 변한다(우리는 이미 `서식입히기.py` 로 완성본과 같은 크기를 맞춰 뒀다).

쓰는 법
  python 아모르입히기.py <프로젝트.prproj> <원본.ass> [--본 <본보기.prproj>] [--보기만]
    --텍스트팝지우기   Text 쪽에 들어 있던 옛 팝(비율 조정·위치 키프레임)을 지운다 (기본 켬)
  ★사본에서 먼저 하고, 프리미어로 열어 눈으로 본 뒤 진본에 옮겨라.
"""
import argparse
import base64
import collections
import gzip
import io
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TICK = 254016000000
NL = chr(10)
BS = chr(92)
# ★본보기는 **키트 안**에 있다 (2026-08-25).
#   전에는 사장님 A: 드라이브의 미안해형.prproj(5MB, 사장님 작업물)를 물었다.
#   **다른 컴퓨터엔 없으니 이 단계가 통째로 죽는다.** 그래서 Graphic Group 한 벌
#   (닫힘 7개 · 2770바이트)만 떠서 키트에 넣었다 — 992바이트다.
#   미안해형이 있으면 `--본` 으로 그걸 줘도 된다. 값은 같다.
# ★«위로 두 단계» 로 못 박으면 안 된다 (2026-08-26).
#   새편.py 는 도구를 **편 폴더 바로 밑**에 편다. 그러면 두 단계 위는 편 모음 폴더라
#   스타일/아모르_부품.prproj 가 없어 이 단계가 통째로 죽는다(FileNotFoundError).
#   있는 데를 **찾아 올라간다.** 못 찾으면 왜 못 찾았는지 말한다.
def _본찾기():
    본 = os.path.abspath(__file__)
    본 = os.path.dirname(본)
    길 = 본
    for _ in range(6):
        for 뒤 in (os.path.join(길, '스타일', '아모르_부품.prproj'),
                   os.path.join(길, '린박스_배포키트', '스타일', '아모르_부품.prproj')):
            if os.path.exists(뒤):
                return 뒤
        위 = os.path.dirname(길)
        if 위 == 길:
            break
        길 = 위
    return None


기본본 = _본찾기()
# ★붙박이 값을 쓰지 마라. 본보기(미안해형)의 0.5:0.651 / 0.5:0.9453 은
#   **그 프로젝트의 글자 자리에 맞춘 값**이다. 그대로 베끼면 자막이 통째로 밀린다
#   (2026-08-25: 565px 위로 솟아 사장님이 «위치가 기존과 달라졌어» 하셨다).
#
#   벡터 모션은 **소재의 «기준점» 이 화면의 «위치» 에 놓이도록** 그린다.
#   그러니 밀림이 0 이려면  **위치 == 기준점**  이어야 한다.
#   그 값은 **그 자막 글자의 한가운데** 로 잡는다 — 그래야 팝이 글자를 붙잡고 튄다.
#
#       가운데x = Text위치.x + (상자가로/2)/1080
#       가운데y = Text위치.y + (상자세로/2)/1920
#
#   규격 §53 「본보기 값과 이 편의 값이 다르면 이 편 것이 이긴다」의 세 번째 사례다.
프레임가로, 프레임세로 = 1080.0, 1920.0


def 열기(p):
    return gzip.open(p, 'rb').read().decode('utf-8')


def 쓰기(p, s):
    with open(p, 'wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as f:
            f.write(s.encode('utf-8'))


def 오브(d):
    out = {}
    for m in re.finditer(r'<(\w+) Object(U?)ID="([0-9a-f-]+)"[^>]*>', d):
        tag, key = m.group(1), m.group(3)
        c = d.find('</%s>' % tag, m.end())
        if c >= 0:
            out[key] = (tag, m.start(), c + len(tag) + 3)
    return out


def 닫힘(d, objs, 뿌리, 깊이=30):
    본 = {}

    def 걷기(k, dep):
        if k in 본 or dep > 깊이 or k not in objs:
            return
        본[k] = objs[k]
        t, a, b = objs[k]
        for r in set(re.findall(r'ObjectU?Ref="([0-9a-f-]+)"', d[a:b])):
            걷기(r, dep + 1)

    걷기(뿌리, 0)
    return 본


층표 = {}
자리표 = {}   # 글자 → (an, x, y) — 클립에 «위치» 가 없을 때(모션 컴포넌트 없는 클립) 한가운데를 ass 로 잡는다


def ass팝(경로):
    """{글자: ([(초, 배율), …], 층이름)} — 줄마다 제 값"""
    표 = {}
    for l in io.open(경로, encoding='utf-8').read().split(NL):
        if not l.startswith('Dialogue:'):
            continue
        f = l.split(',', 9)
        본문 = f[9]
        글자 = re.sub(r'\{[^}]*\}', '', 본문).replace(BS + 'N', ' ').strip()
        if not 글자:
            continue
        점 = []
        m0 = re.search(BS + BS + 'fscx([0-9.]+)', 본문)
        if m0:
            점.append((0.0, float(m0.group(1))))
        for mm in re.finditer(BS + BS + r't\((\d+),(\d+),' + BS + BS + 'fscx([0-9.]+)', 본문):
            점.append((int(mm.group(2)) / 1000.0, float(mm.group(3))))
        # ★층은 **모든 줄**에서 읽는다. 팝이 있는 줄만 담으면 모션자막처럼
        #   제 움직임(\move)만 있고 \fscx 팝이 없는 층을 «층을 모르는 것» 으로 잘못 다룬다
        #   (2026-08-25 포헨즈: 모션자막 36장이 «못 찾은 것» 으로 잡혀 도구가 멈췄다).
        층표[글자] = f[3].strip()
        _an = re.search(BS + BS + r'an(\d)', 본문); _pos = re.search(BS + BS + r'pos\((-?[\d.]+),(-?[\d.]+)\)', 본문)
        if _pos:
            자리표[글자] = (int(_an.group(1)) if _an else 5, float(_pos.group(1)), float(_pos.group(2)))
        if len(점) >= 2:
            표[글자] = (점, f[3].strip())
    return 표


P = argparse.ArgumentParser()
P.add_argument('우리')
P.add_argument('자막')
P.add_argument('--본', default=기본본)
P.add_argument('--보기만', action='store_true', dest='보기만')
P.add_argument('--텍스트팝두기', action='store_true', dest='팝두기')
P.add_argument('--팝', default='',
               help='ass 에 \\fscx 팝이 없는 편(신병4 같은 정적 자막)에 쓸 팝 모양. '
                    '«부품» 이면 본보기 부품의 «비율 조정» 키프레임을 끝값 100%% 로 환산해 쓴다 '
                    '(아모르 프리셋 원래 모양: 150→175 / 0.18초 = 85.7→100). '
                    '아니면 "초:배율,초:배율" 로 직접. ass 에 팝이 있는 줄은 ass 값이 이긴다.')
P.add_argument('--층', default='band_narr,band_dlg',
               help='아모르를 달 층. 기본은 나레·대사만이다. '
                    '★모션자막(effect_float)에는 달지 마라 — ass 에서 이미 제 움직임(\\move·\\t)을 '
                    '가지므로 팝을 또 얹으면 두 움직임이 겹쳐 완성본과 달라진다(규격 §53).')
A = P.parse_args()

import 소스텍스트 as S  # noqa: E402

d = 열기(A.우리)
objs = 오브(d)
팝표 = ass팝(A.자막)
달층 = set(x.strip() for x in A.층.split(',') if x.strip())
print('아모르를 달 층: %s' % ' · '.join(sorted(달층)))

# ── 본보기에서 Graphic Group 한 벌을 뜬다 ──────────────────────────
본 = 열기(A.본)
본objs = 오브(본)
본GG = None
for m in re.finditer(r'<VideoFilterComponent ObjectID="(\d+)"[^>]*>', 본):
    c = 본.find('</VideoFilterComponent>', m.end())
    if 'AE.ADBE Graphic Group' in 본[m.end():c]:
        본GG = m.group(1)
        break
if not 본GG:
    raise SystemExit('본보기에서 AE.ADBE Graphic Group 을 못 찾았다')
본닫 = 닫힘(본, 본objs, 본GG)
print('본보기 %s · Graphic Group %s · 닫힘 %d개 · %d바이트'
      % (os.path.basename(A.본), 본GG, len(본닫), sum(b - a for _, (t, a, b) in 본닫.items())))

# ── 붙박이 팝 (--팝) — ass 에 팝이 없는 편용 (2026-08-28 신병4) ─────────
붙박이팝 = None
if A.팝 == '부품':
    for k, (t2, a2, b2) in 본닫.items():
        도막0 = 본[a2:b2]
        nm0 = re.search(r'<Name>([^<]*)</Name>', 도막0)
        if nm0 and nm0.group(1).strip().startswith('비율 조정') and '<Keyframes>' in 도막0:
            kf = re.search(r'<Keyframes>([^<]*)</Keyframes>', 도막0).group(1)
            점0 = [(int(x.split(',')[0]), float(x.split(',')[1].rstrip('.'))) for x in kf.split(';') if x.strip()]
            t0 = 점0[0][0]
            붙박이팝 = [((tk - t0) / float(TICK), v) for tk, v in 점0]
            break
    if not 붙박이팝:
        raise SystemExit('★부품의 «비율 조정» 에 키프레임이 없다 — --팝 을 초:배율 로 직접 줘라')
elif A.팝:
    붙박이팝 = [(float(x.split(':')[0]), float(x.split(':')[1])) for x in A.팝.split(',')]
if 붙박이팝:
    print('  붙박이 팝(--팝 %s): %s  (끝값 100%% 로 환산해 넣는다)'
          % (A.팝, ' → '.join('%.3fs %g' % (t3, v) for t3, v in 붙박이팝)))
if any(not k.isdigit() for k in 본닫):
    raise SystemExit('★닫힘에 ObjectUID 로 사는 것이 있다 — 이 도구는 그 경우를 안 다룬다')

# 사설자료 해시
해시 = None
t, a, b = 본objs[본GG]
mm = re.search(r'<PremiereFilterPrivateData[^>]*BinaryHash="([^"]+)"[^>]*>([^<]*)</PremiereFilterPrivateData>', 본[a:b])
if mm:
    해시, 내용 = mm.group(1), mm.group(2).strip()
    print('  사설자료 해시 %s · 내용 %d자' % (해시[:13], len(내용)))
    이미 = re.search(r'<PremiereFilterPrivateData[^>]*BinaryHash="%s"[^>]*>[^<]' % re.escape(해시), d)
    print('  우리 파일에 그 해시의 내용이 이미 있나: %s' % ('예' if 이미 else '아니오 — 첫 장에 넣는다'))

# ── 자막 클립 찾기 ─────────────────────────────────────────────────
클립 = []
for m in re.finditer(r'<VideoClipTrackItem ObjectID="(\d+)"[^>]*>', d):
    ti = m.group(1)
    cl = 닫힘(d, objs, ti)
    글칸 = [k for k, (t, a, b) in cl.items() if '<Name>소스 텍스트</Name>' in d[a:b]]
    if not 글칸:
        continue
    이미GG = any('AE.ADBE Graphic Group' in d[a:b] for k, (t, a, b) in cl.items()
                 if t == 'VideoFilterComponent')
    t, a, b = objs[ti]
    체인 = re.search(r'<Components ObjectRef="(\d+)"/>', d[a:b])
    클립.append({'ti': ti, '글칸': 글칸[0], '체인': 체인.group(1) if 체인 else None,
                 '이미GG': 이미GG, '닫힘': cl})
print('자막 클립 %d장 · 이미 벡터 모션이 있는 것 %d장'
      % (len(클립), sum(1 for c in 클립 if c['이미GG'])))

할것 = [c for c in 클립 if not c['이미GG'] and c['체인']]
if not 할것:
    raise SystemExit('달 자막이 없다')

# ★해시 무리별 «내용 담은 덩어리» — 껍데기가 글자를 빌려 쓴다
#   같은 문구를 여러 번 띄우는 층(모션자막)은 덩어리를 나눠 쓰므로 껍데기가 나온다.
#   껍데기도 **어느 층인지**는 알아야 «달 것이냐 건너뛸 것이냐»를 가릴 수 있다.
무리글 = {}
for c0 in 클립:
    t0, a0, b0 = objs[c0['글칸']]
    도0 = d[a0:b0]
    h0 = re.search(r'<StartKeyframeValue[^>]*BinaryHash="([^"]+)"', 도0)
    m0 = re.search(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>', 도0)
    if h0 and m0 and h0.group(1) not in 무리글:
        무리글[h0.group(1)] = base64.b64decode(re.sub(r'\s', '', m0.group(1)))

# 글자 → 팝 짝짓기
짝 = []
못 = []
건너뜀 = {}
for c in 할것:
    t, a, b = objs[c['글칸']]
    # ★도막이 이미 그 ArbVideoComponentParam **하나**다. 여기서 «다음 <Name> 까지» 로
    #   자르면 제 덩어리 앞에서 끊긴다 (본떠서만들기.py 는 도막이 <Name> 에서 시작해 사정이 다르다).
    도막 = d[a:b]
    m = re.search(r'<StartKeyframeValue Encoding="base64"[^>]*>\s*([A-Za-z0-9+/=\s]+?)\s*</StartKeyframeValue>',
                  도막)
    # ★껍데기면 제 무리의 «내용 담은 덩어리» 를 빌려 온다 — 같은 문구이므로 글자·상자가 같다
    if m:
        raw본 = base64.b64decode(re.sub(r'\s', '', m.group(1)))
    else:
        h = re.search(r'<StartKeyframeValue[^>]*BinaryHash="([^"]+)"', 도막)
        raw본 = 무리글.get(h.group(1)) if h else None
    글자 = None
    if raw본:
        try:
            # ★글자만() 이 먼저 — read_text 는 한글 없는 자막(「?!」)을 못 읽는다 (제안 2026-08-27_맥2_한글없는자막)
            글줄 = S.글자만(raw본)
            글자 = ' '.join(x.strip() for x in 글줄 if x.strip()) if 글줄 else None
            if not 글자:
                글자 = S.read_text(raw본)[0][1].replace('\r', ' ').replace(NL, ' ').strip()
        except Exception:
            pass
    # 그 자막의 한가운데를 잰다 (상자 크기는 덩어리, 자리는 Text 의 «위치»)
    가운데 = None
    if raw본:
        try:
            raw = raw본
            import struct as _st
            buf = bytearray(raw[12:12 + _st.unpack_from('<Q', raw, 0)[0]])
            u32 = lambda o: _st.unpack_from('<I', buf, o)[0]      # noqa: E731
            i32 = lambda o: _st.unpack_from('<i', buf, o)[0]      # noqa: E731
            u16 = lambda o: _st.unpack_from('<H', buf, o)[0]      # noqa: E731
            t2 = S._root0(buf)
            vt = t2 - i32(t2)
            nn = (u16(vt) - 4) // 2
            FF = {k: t2 + u16(vt + 4 + k * 2) for k in range(nn) if u16(vt + 4 + k * 2)}
            상자w = _st.unpack_from('<f', buf, FF[2])[0]
            상자h = _st.unpack_from('<f', buf, FF[3])[0]
            자리 = None
            for k2, (t3, a3, b3) in c['닫힘'].items():
                if t3 != 'PointComponentParam':
                    continue
                nm2 = re.search(r'<Name>([^<]*)</Name>', d[a3:b3])
                if nm2 and re.sub(r'\s*\([A-Za-z][^)]*\)$', '', nm2.group(1)).strip() == '위치':
                    sk = re.search(r'<StartKeyframe>[^,]*,([0-9.]+):([0-9.]+),', d[a3:b3])
                    if sk:
                        자리 = (float(sk.group(1)), float(sk.group(2)))
                        break
            if 자리:
                가운데 = (자리[0] + (상자w / 2.0) / 프레임가로,
                          자리[1] + (상자h / 2.0) / 프레임세로)
            elif 글자 in 자리표:
                # 모션 컴포넌트가 없는 클립 — ass 의 \pos 와 정렬로 한가운데를 잡는다 (2026-08-28 신병4 EP1 「목소리 터짐」)
                an, px, py = 자리표[글자]
                cx = px + {1: 1, 4: 1, 7: 1, 3: -1, 6: -1, 9: -1}.get(an, 0) * 상자w / 2.0
                cy = py + {7: 1, 8: 1, 9: 1, 1: -1, 2: -1, 3: -1}.get(an, 0) * 상자h / 2.0
                가운데 = (cx / 프레임가로, cy / 프레임세로)
        except Exception as _e가:
            가운데 = None
            print('  (한가운데 못 잼: %s — %s)' % (글자, _e가))
    if raw본 and not 글자:
        # 글자가 빈 텍스트 그래픽 (프리미어에서 손본 빈 장) — 달 것이 없다
        건너뜀['(빈 글자)'] = 건너뜀.get('(빈 글자)', 0) + 1
        continue
    층 = 층표.get(글자)
    if 층 is not None and 층 not in 달층:
        # 달 층이 아니면 한가운데를 못 재도 상관없다 — 건너뛴다
        건너뜀[층] = 건너뜀.get(층, 0) + 1
        continue
    if 글자 and 글자 in 팝표 and 가운데:
        짝.append((c, 글자, 팝표[글자][0], 가운데))
    elif 글자 and 붙박이팝 and 가운데:
        # ★글자가 ass 와 조금 달라 층을 모르는 장(줄바꿈·폭맞춤)도 단다 — 달 층이 아닌 층은 위에서 이미 걸렀다
        짝.append((c, 글자, 붙박이팝, 가운데))
    else:
        못.append(글자 if 가운데 else ((글자 or '?') + ' (한가운데를 못 쟀다)'))
print('  아모르를 달 것 %d장 · 못 찾은 것 %d장 %s'
      % (len(짝), len(못), 못[:3] if 못 else ''))
if 건너뜀:
    print('  건너뛴 층: %s (그 층은 제 움직임이 있다)'
          % ' · '.join('%s %d장' % (k, v) for k, v in sorted(건너뜀.items())))
if 못:
    raise SystemExit('★팝을 못 찾은 장이 있다 — ass 가 그 편 것이 맞는지 봐라')

꼴 = collections.Counter(tuple(v for _, v in p) for _, _, p, _g in 짝)
가운데꼴 = collections.Counter('%.5f:%.5f' % g for _, _, _p, g in 짝)
print('  팝 꼴 %d가지: %s' % (len(꼴), [('→'.join('%g' % x for x in k), v) for k, v in 꼴.most_common(3)]))
print('  위치=기준점 (자막 한가운데) %d가지: %s' % (len(가운데꼴), 가운데꼴.most_common(3)))

if A.보기만:
    print(NL + '(--보기만)')
    raise SystemExit(0)

# ── 달기 ───────────────────────────────────────────────────────────
다음ID = max(int(x) for x in objs if x.isdigit()) + 1
차례 = sorted(본닫, key=lambda k: 본닫[k][1])
새조각 = []
체인고침 = {}
텍스트고침 = []
내용넣음 = bool(re.search(r'<PremiereFilterPrivateData[^>]*BinaryHash="%s"[^>]*>[^<]' % re.escape(해시), d)) if 해시 else True

for c, 글자, 점, 가운데 in 짝:
    맵 = {}
    for k in 차례:
        맵[k] = str(다음ID)
        다음ID += 1
    # 그 체인에서 안 쓰는 컴포넌트 ID
    t, a, b = objs[c['체인']]
    쓰인ID = set(re.findall(r'<ID>(\d+)</ID>', ''.join(
        d[objs[r][1]:objs[r][2]] for r in re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', d[a:b])
        if r in objs)))
    새компID = next(str(i) for i in range(4, 40) if str(i) not in 쓰인ID)

    for k in 차례:
        t2, a2, b2 = 본닫[k]
        도막 = 본[a2:b2]

        def 갈기(mm2):
            return '%s"%s"' % (mm2.group(1), 맵.get(mm2.group(2), mm2.group(2)))
        도막 = re.sub(r'(Object(?:U?)(?:ID|Ref)=)"([^"]+)"', 갈기, 도막)

        nm = re.search(r'<Name>([^<]*)</Name>', 도막)
        이름 = nm.group(1).strip() if nm else ''
        # ★prfpset 에서 뜬 부품은 이름이 «위치 (Position)» 처럼 영어 꼬리를 단다 (2026-08-28 윈도우 아모르부품뜨기).
        #   꼬리를 떼고 견준다 — 안 떼면 위치·기준점·비율을 하나도 못 바꿔 자막이 175% 로 위로 튄다.
        이름 = re.sub(r'\s*\([A-Za-z][^)]*\)$', '', 이름).strip()
        if k == 본GG:
            도막 = re.sub(r'<ID>\d+</ID>', '<ID>%s</ID>' % 새компID, 도막, count=1)
            # 사설자료 — 첫 장만 내용, 나머지는 해시 참조
            if 해시:
                if 내용넣음:
                    도막 = re.sub(r'<PremiereFilterPrivateData[^>]*>[^<]*</PremiereFilterPrivateData>',
                                  '<PremiereFilterPrivateData Encoding="base64" BinaryHash="%s"/>' % 해시, 도막)
                else:
                    내용넣음 = True
        if 이름 in ('위치', '기준점'):
            # ★둘을 **같게** 둔다 — 그래야 밀림이 0 이다
            값 = '%.9f:%.9f' % 가운데
            도막 = re.sub(r'(<StartKeyframe>)(-?\d+),([^,]*)(,)',
                          lambda z: z.group(1) + z.group(2) + ',' + 값 + z.group(4), 도막, count=1)
            도막 = re.sub(r'<Keyframes>[^<]*</Keyframes>', '', 도막)
        elif 이름 == '비율 조정':
            끝값 = 점[-1][1]
            def _수(x):
                # ★프리미어 숫자 꼴은 «100.» · «85.714302» — 소수 뒤에 점을 또 붙이면(«85.7143.») 그 키프레임부터 버린다 (2026-08-28 실측)
                s_ = '%.6g' % x
                return s_ if '.' in s_ or 'e' in s_ else s_ + '.'
            줄 = ''.join('%d,%s,0,0,0,0.16666666666666666,0,0.16666666666666666;'
                         % (int(round(t3 * TICK)), _수(v * 100.0 / 끝값)) for t3, v in 점)
            도막 = re.sub(r'(<StartKeyframe>)(-?\d+),([^,]*)(,)',
                          lambda z: z.group(1) + z.group(2) + ',100.' + z.group(4), 도막, count=1)
            if '<Keyframes>' in 도막:
                도막 = re.sub(r'<Keyframes>[^<]*</Keyframes>', '<Keyframes>%s</Keyframes>' % 줄, 도막)
            else:
                도막 = 도막.replace('</StartKeyframe>', '</StartKeyframe><Keyframes>%s</Keyframes>' % 줄, 1)
            if '<IsTimeVarying>' not in 도막:
                도막 = 도막.replace('<ParameterID>', '<IsTimeVarying>true</IsTimeVarying><ParameterID>', 1)
        elif 이름 in ('폭 비율 조정', '회전'):
            도막 = re.sub(r'<Keyframes>[^<]*</Keyframes>', '', 도막)
        새조각.append(도막)

    체인고침[c['체인']] = 맵[본GG]
    if not A.팝두기:
        텍스트고침.append(c)

# ── 고칠 자리를 **한 자루에 모은다** ──────────────────────────────
#   ★두 번에 나눠 넣으면 안 된다. 앞 고침이 길이를 바꿔 놓아서 뒤 고침의 자리가 밀린다
#     (2026-08-25 에 여기서 끊긴 참조 80개가 났다). 모아서 **뒤에서부터 한 번에** 넣는다.
고칠 = []

# 체인 — Graphic Group 을 Index 0 으로, 있던 것은 한 칸씩 뒤로
for 체인, 새ref in 체인고침.items():
    t, a, b = objs[체인]
    도막 = d[a:b]
    옛 = re.findall(r'<Component Index="\d+" ObjectRef="(\d+)"/>', 도막)
    줄 = '<Component Index="0" ObjectRef="%s"/>' % 새ref
    줄 += ''.join('<Component Index="%d" ObjectRef="%s"/>' % (i + 1, r) for i, r in enumerate(옛))
    도막2 = re.sub(r'<Components Version="1">.*?</Components>',
                   '<Components Version="1">%s</Components>' % 줄, 도막, count=1, flags=re.S)
    if 도막2 != 도막:
        고칠.append((a, b, 도막2))

# Text 쪽 옛 팝 지우기 (비율 조정·위치의 키프레임) — 벡터 모션과 겹쳐 돌지 않게
지움 = 0
for c in 텍스트고침:
    for k, (t, a, b) in c['닫힘'].items():
        if t not in ('VideoComponentParam', 'PointComponentParam'):
            continue
        도막 = d[a:b]
        nm = re.search(r'<Name>([^<]*)</Name>', 도막)
        if not nm or nm.group(1).strip() not in ('비율 조정', '위치'):
            continue
        if '<Keyframes>' not in 도막:
            continue
        도막2 = re.sub(r'<Keyframes>[^<]*</Keyframes>', '', 도막)
        도막2 = 도막2.replace('<IsTimeVarying>true</IsTimeVarying>', '')
        고칠.append((a, b, 도막2))
        지움 += 1

# 겹치는 자리가 없어야 한다
고칠.sort(key=lambda x: x[0])
for (a1, b1, _), (a2, b2, _) in zip(고칠, 고칠[1:]):
    if b1 > a2:
        raise SystemExit('★고칠 자리가 겹친다 (%d~%d 와 %d~%d) — 멈춘다' % (a1, b1, a2, b2))

새d = d
for a, b, 도막 in sorted(고칠, key=lambda x: -x[0]):
    새d = 새d[:a] + 도막 + 새d[b:]

끝자리 = 새d.rfind('</PremiereData>')
새d = 새d[:끝자리] + ''.join(새조각) + 새d[끝자리:]

bak = A.우리 + '.아모르전'
if not os.path.exists(bak):
    shutil.copyfile(A.우리, bak)
쓰기(A.우리, 새d)
print()
print('달았다 — 벡터 모션 %d장 (오브젝트 %d개)' % (len(짝), len(새조각)))
if 지움:
    print('  Text 쪽 옛 키프레임 %d군데 지웠다 (겹쳐 도는 것을 막는다)' % 지움)
print('  %d -> %d바이트 (압축 풀어서)' % (len(d), len(새d)))
print('  달기 전 판은 %s' % os.path.basename(bak))
print('★반드시: python 주입검사.py "%s" --본 "%s" --기준 "%s"' % (A.우리, A.본, bak))
