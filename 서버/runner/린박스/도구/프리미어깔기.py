# -*- coding: utf-8 -*-
r"""프리미어로 프로젝트를 뽑을 수 있게 **깔고 확인한다** — 볼케이노 키트 프리미어깔기.py 의 유스튜디오판 (2026-09-04).

무엇이 있어야 프리미어 길이 열리나
  ① 확장 폴더   윈도우 %APPDATA%\Adobe\CEP\extensions\com.volcano.prproj\
                맥     ~/Library/Application Support/Adobe/CEP/extensions/com.volcano.prproj/
                (원본은 저장소 서버/runner/린박스/프리미어확장/)
  ② 서명 없는 확장 허용  PlayerDebugMode = "1"
                윈도우 레지스트리 HKCU\Software\Adobe\CSXS.9~13 · 맥 defaults write com.adobe.CSXS.9~13 PlayerDebugMode 1
                — 없으면 확장이 **조용히 안 뜬다**
  ③ 프리미어를 **껐다 켜야** 확장이 읽힌다
  ④ 자막 서식 재료 — 서버/runner/린박스/스타일/ 의 곳간·아모르 부품·마스터효과 도너

쓰는 법
  python 프리미어깔기.py          재보기만 한다 (종료코드 1 = 빠진 것 있음)
  python 프리미어깔기.py --쓰기    확장을 복사하고 PlayerDebugMode 를 넣는다
"""
import os
import shutil
import subprocess
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

쓰기 = '--쓰기' in sys.argv
러너 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # 서버/runner/린박스
확장본 = os.path.join(러너, '프리미어확장')
탈 = []

print('=' * 62)
print('  프리미어 길 깔기 · 확인 (유스튜디오)')
print('=' * 62)

맥 = sys.platform == 'darwin'
if os.name != 'nt' and not 맥:
    raise SystemExit('  이 도구는 윈도우·맥용이다')

# ── ① 확장 폴더 ────────────────────────────────────────────────
if 맥:
    자리 = os.path.expanduser('~/Library/Application Support/Adobe/CEP/extensions/com.volcano.prproj')
else:
    자리 = os.path.join(os.environ.get('APPDATA', ''), 'Adobe', 'CEP', 'extensions', 'com.volcano.prproj')
print()
print('■ ① 확장')
if not os.path.isdir(확장본):
    탈.append('러너에 프리미어확장 폴더가 없다: %s' % 확장본)
    print('  ★러너에 없다:', 확장본)
elif 쓰기:
    os.makedirs(자리, exist_ok=True)
    센 = 0
    for 방, _, 파일들 in os.walk(확장본):
        상 = os.path.relpath(방, 확장본)
        목 = 자리 if 상 == '.' else os.path.join(자리, 상)
        os.makedirs(목, exist_ok=True)
        for f in 파일들:
            shutil.copyfile(os.path.join(방, f), os.path.join(목, f))
            센 += 1
    print('  파일 %d개를 넣었다 → %s' % (센, 자리))
else:
    있 = os.path.isdir(자리) and os.path.exists(os.path.join(자리, 'index.html'))
    print('  %s %s' % ('있다' if 있 else '★없다', 자리))
    if not 있:
        탈.append('확장이 안 깔렸다 — python 프리미어깔기.py --쓰기')

# ── ② PlayerDebugMode ─────────────────────────────────────────
print()
print('■ ② 서명 없는 확장 허용 (PlayerDebugMode)')
없는판 = []
for n in range(9, 14):
    if 맥:
        r = subprocess.run(['defaults', 'read', 'com.adobe.CSXS.%d' % n, 'PlayerDebugMode'], capture_output=True, text=True)
        켜짐 = r.returncode == 0 and r.stdout.strip() == '1'
    else:
        키 = r'HKCU\Software\Adobe\CSXS.%d' % n
        r = subprocess.run(['reg', 'query', 키, '/v', 'PlayerDebugMode'], capture_output=True, text=True)
        켜짐 = r.returncode == 0 and '1' in r.stdout
    if 켜짐:
        print('  CSXS.%-2d 켜져 있다' % n)
        continue
    없는판.append(n)
    if 쓰기:
        if 맥:
            subprocess.run(['defaults', 'write', 'com.adobe.CSXS.%d' % n, 'PlayerDebugMode', '1'], capture_output=True, text=True)
        else:
            subprocess.run(['reg', 'add', 키, '/v', 'PlayerDebugMode', '/t', 'REG_SZ', '/d', '1', '/f'], capture_output=True, text=True)
        print('  CSXS.%-2d 넣었다' % n)
    else:
        print('  CSXS.%-2d ★꺼져 있다' % n)
if 없는판 and not 쓰기:
    탈.append('PlayerDebugMode 가 %s 에 없다 — python 프리미어깔기.py --쓰기' % 없는판)

# ── ③ 프리미어 ────────────────────────────────────────────────
print()
print('■ ③ 프리미어')
찾음 = []
if 맥:
    if os.path.isdir('/Applications'):
        for 이름 in sorted(os.listdir('/Applications')):
            if 이름.startswith('Adobe Premiere Pro'):
                d = os.path.join('/Applications', 이름)
                if os.path.isdir(d):
                    for 안 in sorted(os.listdir(d)):
                        if 안.endswith('.app'):
                            찾음.append(os.path.join(d, 안))
else:
    for 뿌리 in (os.environ.get('ProgramFiles', r'C:\Program Files'), os.environ.get('ProgramW6432', r'C:\Program Files')):
        d = os.path.join(뿌리, 'Adobe')
        if not os.path.isdir(d):
            continue
        for 이름 in sorted(os.listdir(d)):
            exe = os.path.join(d, 이름, 'Adobe Premiere Pro.exe')
            if os.path.exists(exe):
                찾음.append(exe)
if 찾음:
    for e in 찾음:
        print('  있다:', e)
else:
    print('  ★못 찾았다 — 프리미어가 안 깔렸거나 다른 자리에 있다(다른 자리면 환경변수 PPRO 로 알려 준다)')
    탈.append('프리미어를 못 찾았다')

# ── ④ 자막 서식 재료 ───────────────────────────────────────────
print()
print('■ ④ 자막 서식 재료 (서버/runner/린박스/스타일)')
for 이름, 길 in (('곳간 신병4', '스타일/신병4_본.json'), ('아모르 부품', '스타일/아모르_부품.prproj'), ('마스터효과 도너', '스타일/마스터효과_도너.prproj'), ('얼굴 모델', '자산/yunet.onnx')):
    p = os.path.join(러너, *길.split('/'))
    있 = os.path.exists(p)
    print('  %s %s (%s)' % ('있다' if 있 else '★없다', 이름, 길))
    if not 있:
        탈.append('%s 가 없다 — 저장소를 다시 받아라: %s' % (이름, 길))

print()
if 탈:
    print('★빠진 것 %d' % len(탈))
    for t in 탈:
        print('  · ' + t)
    if 쓰기:
        print('  (--쓰기 로 넣은 것은 프리미어를 껐다 켜야 읽힌다)')
    raise SystemExit(1)
print('프리미어 길 열려 있다 ✓ %s' % ('(프리미어를 껐다 켜라)' if 쓰기 else ''))
