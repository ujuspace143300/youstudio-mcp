# -*- coding: utf-8 -*-
r"""prproj 에 **부품을 베껴 심은 뒤**, 프리미어로 열어 보기 전에 미리 잰다.

왜 필요한가 (2026-08-25)
  프리미어는 망가진 prproj 를 열 때 **오류창도 없이 그냥 멎는다.** 반환값도 안 준다.
  한 번 시험하는 데 5분이 날아가고 강제 종료해야 한다. 그러니 **열기 전에 파일에서 재야** 한다.

  실제로 세 가지가 겹쳐 있었다(더 글로리 2화 자막 주입):
    ① PremiereFilterPrivateData 가 빈 껍데기뿐   → 사설자료고침.py
    ② 한 MasterClip·한 ClipID 를 자막 40장이 공유 → 본은 SubClip:MasterClip 이 1:1, ClipID 중복 0
    ③ 베낀 MasterClip 이 **남의 프로젝트 번호**를 물고 있다
       (LoggingInfo→1752 가 본에선 ClipLoggingInfo, 우리 파일에선 SubClip)

쓰는 법
  python 주입검사.py <우리.prproj> [--본 <본보기.prproj>]
    본을 주면 «어떤 자리가 어떤 태그를 물어야 하는가» 를 본에서 배워 ③ 을 잡는다.
    탈이 있으면 exit 1 — 검수에 물릴 수 있다.
"""
import argparse
import os
import collections
import gzip
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def 열기(p):
    return gzip.open(p, 'rb').read().decode('utf-8')


def 오브(d):
    """{ObjectID 또는 ObjectUID: (태그, 시작, 끝)}

    ★ObjectUID 로만 사는 것(MasterClip·Media 등)도 넣어야 한다 — 안 넣으면
      그것이 무는 자리를 검사 ⑤ 가 통째로 건너뛴다(2026-08-25 에 이 구멍으로 놓쳤다).
    """
    out = {}
    for m in re.finditer(r'<(\w+) Object(U?)ID="([0-9a-f-]+)"[^>]*>', d):
        tag, key = m.group(1), m.group(3)
        c = d.find('</%s>' % tag, m.end())
        if c >= 0:
            out[key] = (tag, m.start(), c + len(tag) + 3)
    return out


def 기대표(d, objs):
    """{(품은태그, 자리이름): {물어야 할 태그들}} — 본에서 배운다"""
    표 = collections.defaultdict(set)
    for oid, (tag, a, b) in objs.items():
        for m in re.finditer(r'<(\w+)(?:\s+\w+="[^"]*")*?\s+ObjectU?Ref="([0-9a-f-]+)"[^>]*/>', d[a:b]):
            자리, 대상 = m.group(1), m.group(2)
            if 대상 in objs:
                표[(tag, 자리)].add(objs[대상][0])
    return 표


P = argparse.ArgumentParser()
P.add_argument('우리')
P.add_argument('--본', default=None)
P.add_argument('--기준', default=None,
               help='심기 전 판(.심기전). 주면 «심기 전에도 있던 탈» 은 빼고 센다 — '
                    '프리미어가 스스로 만든 짜임을 우리 탈로 잘못 세지 않으려고.')
A = P.parse_args()

d = 열기(A.우리)
objs = 오브(d)
탈 = []
알림 = []

# ★심기 전 판이 있으면 «원래 그랬던 것» 을 빼고 센다.
#   프리미어가 스스로 만든 짜임(MasterClip 을 둘이 나눠 쓰기, 캡션의 TranscriptClip 등)을
#   우리 탈로 잘못 세면 진짜 탈이 묻힌다 (2026-08-25 에 41곳을 헛짚었다).
기준objs = 기준d = None
if A.기준:
    기준d = 열기(A.기준)
    기준objs = 오브(기준d)
    print('  (심기 전 판과 견준다 — 원래 있던 탈은 빼고 센다)')

print('%s · 오브젝트 %d개' % (os.path.basename(A.우리), len(objs)))

# ── ① 끊긴 참조 ────────────────────────────────────────────────────
ids = set(objs)
refs = set(re.findall(r'ObjectRef="(\d+)"', d))
uids = set(re.findall(r'ObjectUID="([0-9a-f-]+)"', d))
urefs = set(re.findall(r'ObjectURef="([0-9a-f-]+)"', d))
if refs - ids:
    탈.append('끊긴 ObjectRef %d개: %s' % (len(refs - ids), sorted(refs - ids)[:8]))
if urefs - uids:
    탈.append('끊긴 ObjectURef %d개' % len(urefs - uids))
print('  ① 끊긴 참조 — Ref %d · URef %d' % (len(refs - ids), len(urefs - uids)))

# ── ② PremiereFilterPrivateData 해시 첫 등장 규칙 ──────────────────
첫 = {}
for m in re.finditer(r'<PremiereFilterPrivateData[^>]*?>', d):
    h = re.search(r'BinaryHash="([^"]+)"', m.group(0))
    if h and h.group(1) not in 첫:
        첫[h.group(1)] = not m.group(0).endswith('/>')
빈해시 = [h for h, ok in 첫.items() if not ok]
if 빈해시:
    탈.append('PremiereFilterPrivateData 해시 %d개의 내용이 없다 (사설자료고침.py 로 고쳐라)' % len(빈해시))
print('  ② 사설자료 해시 %d종 · 내용 없는 것 %d' % (len(첫), len(빈해시)))

# ── ③ ClipID 중복 ──────────────────────────────────────────────────
cid = collections.Counter(re.findall(r'<ClipID>([^<]+)</ClipID>', d))
중복 = [(k, v) for k, v in cid.most_common() if v > 1]
if 중복:
    탈.append('ClipID 중복 %d종 (가장 심한 것 %s x%d) — 베낄 때마다 새 GUID 를 줘라'
              % (len(중복), 중복[0][0][:13], 중복[0][1]))
print('  ③ ClipID %d개 · 서로 다른 %d · 중복 %d종' % (sum(cid.values()), len(cid), len(중복)))

# ── ④ SubClip 과 MasterClip 이 1:1 인가 ────────────────────────────
짝 = re.findall(r'<SubClip ObjectID="\d+"[^>]*>\s*<Clip ObjectRef="\d+"/>\s*<MasterClip ObjectURef="([0-9a-f-]+)"/>', d)
공유 = [(k, v) for k, v in collections.Counter(짝).most_common() if v > 1]
if 기준d:
    옛짝 = re.findall(r'<SubClip ObjectID="\d+"[^>]*>\s*<Clip ObjectRef="\d+"/>\s*<MasterClip ObjectURef="([0-9a-f-]+)"/>', 기준d)
    옛 = collections.Counter(옛짝)
    공유 = [(k, v) for k, v in 공유 if 옛.get(k, 0) != v]
# ★2026-08-26 — 이 규칙은 «손으로 만든 본보기» 에서 얻은 것이라
#   **FCP7 XML 을 가져와 만든 프로젝트에는 안 맞는다.**
#   XML 은 한 소재(구간.mp4·효과음)를 여러 컷이 나눠 쓰는 것이 정상이라
#   SubClip 여럿이 같은 MasterClip 을 가리킨다. 사장님이 이미 잘 여신
#   포헨즈 1화 프로젝트도 똑같이 «6장이 나눠 쓴다» 로 걸렸다 — 헛경보다.
#   그러니 **막힘이 아니라 알림**으로 낮춘다. `--본` 을 준 자리(부품을 손으로
#   베껴 심은 경우)에서만 막힘으로 본다.
if 공유 and not A.본:
    알림.append('MasterClip 을 여럿이 나눠 쓴다 %d종 — XML 로 가져온 프로젝트에선 정상이다'
                % len(공유))
elif 공유:
    탈.append('MasterClip 을 여럿이 나눠 쓴다 %d종 (가장 심한 것 %s 를 %d장이) — 본은 1:1 이다'
              % (len(공유), 공유[0][0][:8], 공유[0][1]))
print('  ④ SubClip %d개 · MasterClip %d종 · 나눠 쓰는 것 %d종' % (len(짝), len(set(짝)), len(공유)))

# ── ⑤ 무는 자리의 태그 종류가 맞나 (본이 있어야 잰다) ──────────────
if A.본:
    본 = 열기(A.본)
    본objs = 오브(본)
    표 = 기대표(본, 본objs)
    # ★뭉뚱그려 보면 안 된다 — 멀쩡한 MasterClip 150개가 어긋난 1개를 가려 버린다.
    #   참조를 **하나하나** 짚어야 한다 (2026-08-25 에 이 실수로 한 번 놓쳤다).
    어긋 = []
    for oid, (tag, a, b) in objs.items():
        for m in re.finditer(r'<(\w+)(?:\s+\w+="[^"]*")*?\s+ObjectU?Ref="([0-9a-f-]+)"[^>]*/>', d[a:b]):
            자리, 대상 = m.group(1), m.group(2)
            if 대상 not in objs:
                continue
            기대 = 표.get((tag, 자리))
            실제 = objs[대상][0]
            if 기대 and 실제 not in 기대:
                어긋.append((oid, tag, 자리, 대상, sorted(기대), 실제))
    if 기준d and 기준objs:
        옛 = set()
        for oid, (tag, a, b) in 기준objs.items():
            for m in re.finditer(r'<(\w+)(?:\s+\w+="[^"]*")*?\s+ObjectU?Ref="([0-9a-f-]+)"[^>]*/>', 기준d[a:b]):
                if m.group(2) in 기준objs:
                    옛.add((tag, m.group(1), 기준objs[m.group(2)][0]))
        어긋 = [x for x in 어긋 if (x[1], x[2], x[5]) not in 옛]
    if 어긋:
        탈.append('무는 태그 종류가 어긋난 참조 %d개 — 베낀 도막의 ObjectRef 를 새 번호로 안 바꿨다'
                  % len(어긋))
        본때 = collections.Counter((x[1], x[2], x[5]) for x in 어긋)
        for (tag, 자리, 실제), n in 본때.most_common(8):
            기대 = '/'.join(sorted(표[(tag, 자리)]))
            print('     <%s> 의 <%s> → %s 여야 하는데 %s 를 문다 (%d곳)'
                  % (tag, 자리, 기대, 실제, n))
    print('  ⑤ 참조 검사 · 어긋난 곳 %d' % len(어긋))
else:
    print('  ⑤ 건너뜀 (--본 을 주면 «무는 태그 종류» 까지 잰다)')

print()
for t in 알림:
    print('  ! %s' % t)
if 탈:
    print('★탈 %d가지 — 프리미어는 이 파일을 못 연다' % len(탈))
    for t in 탈:
        print('  ✗ %s' % t)
    sys.exit(1)
print('탈 없다 — 열어 봐도 좋다')
