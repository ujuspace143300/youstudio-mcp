# -*- coding: utf-8 -*-
r"""프리미어를 띄워 CEP 확장(auto_prproj.jsx)이 FCP7 XML 을 .prproj 로 만들게 한다 — 정본 맥 사슬 `한번에.sh` ③ 의 유스튜디오판.

한번에.sh ③ 이 하던 것 그대로 (2026-09-04)
  · 잠금(키트 도구/프리미어잠금.sh 원리 — mkdir 은 원자적이라 한 컴퓨터에서 **한 번에 하나만**; 주인 pid 가 죽었으면 걷어낸다)
  · 프리미어를 끄고 → 옛 prproj·_갓지은판 지우고 → 대기줄(~/.volcano/prproj_queue.txt)에 XML 줄을 **없을 때만** 보태고
    (남이 세워 둔 줄은 그대로 둔다) → 프리미어 실행 → 확장이 그 줄을 지울 때까지 기다린다(8초 × 60 = 8분)
  · prproj 가 생겼는지 보고 → 프리미어 끄고 → _갓지은판.prproj 사본 → 잠금 해제
  · ★파일이 «생기면» 바로 돌아오지 않는다 — 프리미어가 몇 초 더 저장한다. 크기·시각이 3초간 잠잠할 때까지 기다린다
    (키트 프리미어내기.py 교훈 2026-08-27: 그 틈에 편집 도구가 달려들면 자막 0장짜리가 나온다)

쓰는 법
  python 프리미어돌리기.py <xml> <prproj> --누구 <표시이름> [--기다림 480] [--ppro <프리미어 실행파일>]
  프리미어 자리: --ppro > 환경변수 PPRO > 기본(맥 /Applications/Adobe Premiere Pro 2026/… · 윈도우 C:/Program Files/Adobe/Adobe Premiere Pro */Adobe Premiere Pro.exe)
  표준출력 마지막 줄: 「✓ prproj <바이트> <경로>」 또는 「✗ …」 (종료코드 1)
"""
import argparse
import glob
import io
import os
import shutil
import subprocess
import sys
import time

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

P = argparse.ArgumentParser()
P.add_argument('xml')
P.add_argument('prproj')
P.add_argument('--누구', default='유스튜디오', dest='누구')
P.add_argument('--기다림', type=int, default=480, dest='기다림')
P.add_argument('--ppro', default=None)
P.add_argument('--잠금기다림', type=int, default=3600, dest='잠금기다림')
A = P.parse_args()

XML = os.path.abspath(A.xml)
PROJ = os.path.abspath(A.prproj)
EP_DIR = os.path.dirname(PROJ)
HOME = os.path.expanduser('~')
VOL = os.path.join(HOME, '.volcano')
QUEUE = os.path.join(VOL, 'prproj_queue.txt')
PLOG = os.path.join(VOL, 'prproj_log.txt')
LOCK = os.environ.get('PPRO_LOCK') or os.path.join(VOL, 'prproj.lock')
WIN = sys.platform == 'win32'


def 프리미어():
    if A.ppro:
        return A.ppro
    if os.environ.get('PPRO'):
        return os.environ['PPRO']
    if WIN:
        후 = sorted(glob.glob('C:/Program Files/Adobe/Adobe Premiere Pro */Adobe Premiere Pro.exe'))
        return 후[-1] if 후 else None
    후 = sorted(glob.glob('/Applications/Adobe Premiere Pro */Adobe Premiere Pro *.app/Contents/MacOS/Adobe Premiere Pro *'))
    return 후[-1] if 후 else None


def 살아있나(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if WIN:
        r = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid], capture_output=True, text=True)
        return str(pid) in (r.stdout or '')
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def 프리미어끄기():
    if WIN:
        subprocess.run(['taskkill', '/IM', 'Adobe Premiere Pro.exe', '/F'], capture_output=True)
    else:
        subprocess.run(['pkill', '-f', 'Adobe Premiere Pro'], capture_output=True)
    for _ in range(12):
        if not 프리미어떠있나():
            return
        time.sleep(2)


def 프리미어떠있나():
    if WIN:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Adobe Premiere Pro.exe'], capture_output=True, text=True)
        return 'Adobe Premiere Pro.exe' in (r.stdout or '')
    r = subprocess.run(['pgrep', '-f', 'Adobe Premiere Pro'], capture_output=True)
    return r.returncode == 0


def 잠금걸기():
    os.makedirs(VOL, exist_ok=True)
    기다린 = 0
    while True:
        try:
            os.mkdir(LOCK)
            break
        except FileExistsError:
            pass
        누구 = ''
        try:
            누구 = io.open(os.path.join(LOCK, '누구'), encoding='utf-8').read().strip()
        except OSError:
            pass
        hpid = 누구.split(' ')[0] if 누구 else ''
        if hpid and not 살아있나(hpid):
            print('  ↳ 주인 없는 잠금을 걷어낸다 — %s (pid %s 없음)' % (누구, hpid))
            shutil.rmtree(LOCK, ignore_errors=True)
            continue
        if not hpid and time.time() - os.path.getmtime(LOCK) > 60:
            print('  ↳ 주인 표시 없는 오래된 잠금을 걷어낸다')
            shutil.rmtree(LOCK, ignore_errors=True)
            continue
        if 기다린 >= A.잠금기다림:
            print('✗ 프리미어 차례를 %d초 기다렸다 — 아직 「%s」 가 쓰는 중. 그 터미널을 확인하고, 정말 죽었는데 잠금만 남았으면 지워라: %s' % (기다린, 누구 or '?', LOCK))
            sys.exit(1)
        if 기다린 % 60 == 0:
            print('  ↳ 프리미어 차례 기다리는 중 (%d초) — 「%s」 가 쓰는 중' % (기다린, 누구 or '?'))
            sys.stdout.flush()
        time.sleep(5)
        기다린 += 5
    io.open(os.path.join(LOCK, '누구'), 'w', encoding='utf-8').write('%d %s %s\n' % (os.getpid(), A.누구, time.strftime('%F %T')))
    print('  ↳ 프리미어 잠금 걸었다 (%s)' % A.누구)


def 잠금풀기():
    try:
        hpid = io.open(os.path.join(LOCK, '누구'), encoding='utf-8').read().split(' ')[0]
    except OSError:
        hpid = ''
    if hpid in ('', str(os.getpid())):
        shutil.rmtree(LOCK, ignore_errors=True)
        print('  ↳ 프리미어 잠금 풀었다')


def 줄있나():
    try:
        return XML in [l.strip() for l in io.open(QUEUE, encoding='utf-8', errors='replace')]
    except OSError:
        return False


def main():
    if not os.path.exists(XML):
        print('✗ XML 이 없다: %s' % XML)
        return 1
    ppro = 프리미어()
    if not ppro or not os.path.exists(ppro):
        print('✗ 프리미어 실행파일을 못 찾았다 — --ppro 나 환경변수 PPRO 로 알려 줘라 (본 곳: %s)' % (ppro or '기본 자리'))
        return 1
    잠금걸기()
    try:
        프리미어끄기()
        for p in (PROJ, os.path.join(EP_DIR, '_갓지은판.prproj')):
            if os.path.exists(p):
                os.remove(p)
        for p in glob.glob(os.path.join(EP_DIR, '*전_*.prproj')):
            os.remove(p)
        os.makedirs(VOL, exist_ok=True)
        if not os.path.exists(QUEUE):
            io.open(QUEUE, 'w', encoding='utf-8').write('')
        if not 줄있나():
            with io.open(QUEUE, 'a', encoding='utf-8') as f:
                f.write(XML + '\n')
        if os.path.exists(PLOG):
            os.remove(PLOG)
        print('  프리미어 실행 — %s' % ppro)
        sys.stdout.flush()
        subprocess.Popen([ppro], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        번 = max(1, A.기다림 // 8)
        for _ in range(번):
            if not 줄있나():
                break
            time.sleep(8)
        if not os.path.exists(PROJ):
            print('✗ 프리미어가 prproj 를 안 만들었다 — 확장(com.volcano.prproj)이 깔렸나 보라. 확장 로그: %s' % PLOG)
            try:
                print(io.open(PLOG, encoding='utf-8', errors='replace').read()[-800:])
            except OSError:
                pass
            프리미어끄기()
            return 1
        앞 = None
        for _ in range(40):
            지금 = (os.path.getsize(PROJ), os.path.getmtime(PROJ))
            if 지금 == 앞:
                break
            앞 = 지금
            time.sleep(1.5)
        프리미어끄기()
        shutil.copyfile(PROJ, os.path.join(EP_DIR, '_갓지은판.prproj'))
        print('  _갓지은판.prproj 사본 남김')
        print('✓ prproj %d %s' % (os.path.getsize(PROJ), PROJ))
        return 0
    finally:
        잠금풀기()


if __name__ == '__main__':
    raise SystemExit(main())
