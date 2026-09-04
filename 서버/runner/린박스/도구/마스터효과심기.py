# -*- coding: utf-8 -*-
"""prproj 의 **마스터(혼합) 트랙**에 오디오 효과를 도너에서 베껴 심는다.

왜 (2026-08-28 사장님 지시 · 작업규칙 「완성 보고」 11번)
  prproj 는 마스터 트랙에 **멀티밴드 압축기 «브로드캐스트» + 선택적 제한 «−3dB로 제한»** 이
  걸려 있어야 한다. 프리미어 스크립트(QE)는 마스터 트랙을 못 잡고, 프리셋을 코드로 못 건다.
  그래서 사장님이 프리미어에서 손으로 걸어 저장한 prproj 를 **도너**로 삼아 그 컴포넌트를
  파라미터까지 통째로 베낀다 — 값이 1비트도 안 틀린다.

무엇을 베끼나
  도너 마스터 체인(AudioMixTrack → Components → AudioComponentChain)의 AudioFilterComponent 와
  그 Param 이 가리키는 AudioComponentParam 전부. 새 ObjectID 를 받아 대상에 넣고,
  대상 마스터 체인 맨 앞(Index 0,1…)에 끼운다. 페이더·미터는 뒤로 밀린다 (도너와 같은 순서).

이미 있으면 (FilterMatchName 이 같은 컴포넌트가 마스터에 있으면) 건드리지 않는다.

쓰는 법
  python 마스터효과심기.py <대상.prproj> [--도너 <도너.prproj>] [--확인만]
    --도너 기본값: 볼트 프리셋 카드에 적힌 견본 (없으면 필수)
    --확인만     심지 않고 마스터에 무엇이 걸려 있는지만 보인다 (종료코드 1 = 없다)
  심은 뒤:  python 주입검사.py <대상> --기준 <갓지은판>  ·  프리미어로 열어 오프라인 0 확인
"""
import argparse
import gzip
import io
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = argparse.ArgumentParser()
P.add_argument('대상')
P.add_argument('--도너', default=os.path.expanduser('~/Desktop/볼케이노 린박스/신병/완성/EP1/신병4_EP1.prproj'))
P.add_argument('--확인만', action='store_true')
A = P.parse_args()

# 효과 이름표 — 프리미어는 이름을 안 적고 GUID(FilterMatchName)만 적는다 (2026-08-28 실측)
이름표 = {
    '3981e750-c8ae-40a2-889f-41a01c7efa03': '멀티밴드 압축기',
    'e0b23f05-f1a7-4ef7-9b50-7ec3e3002058': '선택적 제한',
}


def 읽기(p):
    return gzip.open(p, 'rb').read().decode('utf-8')


def 객체(s, oid):
    m = re.search(r'<(\w+) ObjectID="%s"[^>]*>.*?</\1>' % oid, s, re.S)
    if not m:
        raise SystemExit('★ObjectID %s 를 못 찾았다' % oid)
    return m.group(0)


def 마스터체인(s):
    mt = re.search(r'<AudioMixTrack ObjectID="(\d+)".*?<Components ObjectRef="(\d+)"/>', s, re.S)
    if not mt:
        raise SystemExit('★마스터 트랙(AudioMixTrack)이 없다')
    return mt.group(1), mt.group(2)


def 체인컴포넌트(s, 체인id):
    ch = 객체(s, 체인id)
    return [(int(i), r) for i, r in re.findall(r'<Component Index="(\d+)" ObjectRef="(\d+)"/>', ch)]


def 효과목록(s):
    _, 체인 = 마스터체인(s)
    out = []
    for _, r in 체인컴포넌트(s, 체인):
        b = 객체(s, r)
        if not b.startswith('<AudioFilterComponent'):
            continue
        fm = re.search(r'<FilterMatchName>([^<]+)</FilterMatchName>', b)
        pr = re.search(r'<FilterPreset>([^<]+)</FilterPreset>', b)
        out.append((r, fm.group(1) if fm else '?', pr.group(1) if pr else '?',
                    len(re.findall(r'<Param Index=', b))))
    return out


def 보이기(제목, s):
    print('■ %s' % 제목)
    lst = 효과목록(s)
    if not lst:
        print('  (마스터에 효과 없음)')
    for r, fm, pr, n in lst:
        print('  %-6s %-14s 프리셋 %-3s 파라미터 %3d  [%s]' % (r, 이름표.get(fm, '?'), pr, n, fm))
    return lst


대상 = 읽기(A.대상)
있는 = 보이기('대상 마스터 · %s' % os.path.basename(A.대상), 대상)
있는GUID = {fm for _, fm, _, _ in 있는}
if A.확인만:
    sys.exit(0 if 있는GUID >= set(이름표) else 1)

if not os.path.exists(A.도너):
    raise SystemExit('★도너가 없다: %s' % A.도너)
도너 = 읽기(A.도너)
도너효과 = [(r, fm) for r, fm, _, _ in 보이기('도너 마스터 · %s' % os.path.basename(A.도너), 도너)]
심을 = [(r, fm) for r, fm in 도너효과 if fm not in 있는GUID]
if not 심을:
    print('\n이미 다 걸려 있다 — 손대지 않는다')
    sys.exit(0)

# ── 새 ObjectID 는 대상 최대값 다음부터 ──────────────────────────────
다음id = max(int(i) for i in re.findall(r'ObjectID="(\d+)"', 대상)) + 1
시작id = 다음id
새덩어리 = []
새컴포넌트 = []
for r, fm in 심을:
    comp = 객체(도너, r)
    파람 = re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', comp)
    # 도너 안에서 다른 객체를 가리키는 건 Param 뿐이어야 한다 (2026-08-28 실측: 105/8 = Param 수)
    if len(re.findall(r'ObjectRef="\d+"', comp)) != len(파람) or 'URef' in comp:
        raise SystemExit('★도너 컴포넌트 %s 가 Param 밖의 것을 가리킨다 — 이 도구로는 못 베낀다' % r)
    바꿈 = {}
    for p in 파람:
        바꿈[p] = str(다음id); 다음id += 1
    새comp_id = str(다음id); 다음id += 1
    comp2 = re.sub(r'ObjectID="%s"' % r, 'ObjectID="%s"' % 새comp_id, comp, count=1)
    comp2 = re.sub(r'ObjectRef="(\d+)"', lambda m: 'ObjectRef="%s"' % 바꿈[m.group(1)], comp2)
    새덩어리.append(comp2)
    for p in 파람:
        pb = 객체(도너, p)
        if re.search(r'Object(Ref|URef)=', pb):
            raise SystemExit('★파라미터 %s 가 다른 객체를 가리킨다' % p)
        새덩어리.append(re.sub(r'ObjectID="%s"' % p, 'ObjectID="%s"' % 바꿈[p], pb, count=1))
    새컴포넌트.append((새comp_id, fm))

# ── 대상 마스터 체인 맨 앞에 끼운다 ──────────────────────────────────
_, 체인id = 마스터체인(대상)
체인 = 객체(대상, 체인id)
기존 = 체인컴포넌트(대상, 체인id)
줄 = ['<Component Index="%d" ObjectRef="%s"/>' % (i, cid) for i, (cid, _) in enumerate(새컴포넌트)]
줄 += ['<Component Index="%d" ObjectRef="%s"/>' % (i + len(새컴포넌트), r) for i, (_, r) in enumerate(기존)]
체인2 = re.sub(r'<Components Version="1">.*?</Components>',
              '<Components Version="1">\n\t\t\t\t' + '\n\t\t\t\t'.join(줄) + '\n\t\t\t</Components>',
              체인, count=1, flags=re.S)
대상2 = 대상.replace(체인, 체인2, 1)
# 새 객체는 파일 끝 </PremiereData> 앞에 붙인다
끝 = 대상2.rfind('</PremiereData>')
대상2 = 대상2[:끝] + '\n'.join('\t' + d for d in 새덩어리) + '\n' + 대상2[끝:]

사본 = A.대상 + '.마스터효과전'
if not os.path.exists(사본):
    shutil.copy2(A.대상, 사본)
with gzip.open(A.대상, 'wb') as fh:
    fh.write(대상2.encode('utf-8'))

# ── 되읽어 확인 ────────────────────────────────────────────────────
되 = 읽기(A.대상)
print()
뒤 = 보이기('심은 뒤 대상 마스터', 되)
뒤GUID = {fm for _, fm, _, _ in 뒤}
빠짐 = set(이름표) - 뒤GUID
# 파라미터 값이 도너와 같은가
def 값들(s, cid):
    out = []
    for p in re.findall(r'<Param Index="\d+" ObjectRef="(\d+)"/>', 객체(s, cid)):
        pb = 객체(s, p)
        v = re.search(r'<CurrentValue>([^<]*)<', pb); k = re.search(r'<StartKeyframe>([^<]*)<', pb)
        out.append((v.group(1) if v else None, k.group(1) if k else None))
    return out
틀림 = 0
for (새cid, fm), (옛r, _) in zip(새컴포넌트, 심을):
    if 값들(되, 새cid) != 값들(도너, 옛r):
        틀림 += 1
print('  새 객체 %d개 · ObjectID %d~%d · 사본 %s' % (len(새덩어리), 시작id, 다음id - 1, os.path.basename(사본)))
if 빠짐 or 틀림:
    print('★탈 — 빠진 효과 %s · 값 다른 컴포넌트 %d' % ([이름표[g] for g in 빠짐], 틀림))
    sys.exit(1)
print('  파라미터 값 도너와 동일 ✓')
