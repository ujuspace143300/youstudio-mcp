# -*- coding: utf-8 -*-
r"""린박스 실행기 — 유스튜디오 MCP 서버가 돌려주는 지시(do · jobs · post · write_files · measure · carry)를 **그대로** 실행하고
next_step 을 따라간다. 서버가 판정하고 이것은 손발이다 (설계 「방법이 아닌 조건 · 숫자 반환」).

  python 실행기.py --url http://127.0.0.1:8787 --state <상태.json> \
      --source "<드라마.mp4>" --title 신병4 --workdir "<드라마 폴더>" --ep EP19 --start 1495 --end 1635 --repo <저장소 루트> \
      [--answers <사람이 줄 값.json>] [--approve-paid] [--until lb_check] [--from setup]

  · 상태(payload)는 --state 파일에 매 호출 뒤 저장한다 — 다시 돌리면 이어서 간다.
  · need_input 이 오면 --answers 의 값(키 = need_input.keys 또는 payload 칸)을 실어 다시 부르고, 없으면 멈춘다(종료코드 2).
  · ★유료(jobs_kind synthesize · 전사.py · narr_align.py) 는 --approve-paid 없이는 멈춘다(종료코드 3) — 규칙: 비용 보고 → 승인 → 실행.
  · error 면 멈춘다(종료코드 1). done 이면 0.
  · measure unit: json_stdout · stdout · stdout_first_line · stderr · seconds(ffprobe 길이 — job 의 out, 없으면 argv 의 마지막 .mp4/.wav) · bytes
  · argv 첫 토막 «python» 은 이 실행기의 파이썬(러너 venv)으로 바꾼다. 나머지는 한 글자도 안 고친다.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

P = argparse.ArgumentParser()
P.add_argument('--url', default='http://127.0.0.1:8787')
P.add_argument('--state', required=True)
P.add_argument('--source')
P.add_argument('--title', default='린박스')
P.add_argument('--workdir')
P.add_argument('--ep')
P.add_argument('--start', type=float)
P.add_argument('--end', type=float)
P.add_argument('--repo')
P.add_argument('--answers', default=None)
P.add_argument('--approve-paid', action='store_true', dest='approve_paid')
P.add_argument('--until', default=None, help='이 단계에 들어가기 전에 멈춘다')
P.add_argument('--from', dest='from_step', default=None)
P.add_argument('--max-calls', type=int, default=60, dest='max_calls')
P.add_argument('--preset', default='린박스')
A = P.parse_args()

PY = sys.executable
_id = 0


def device_id():
    """이 컴퓨터의 설치 id — 기기.mjs deviceId() 와 같은 파일(~/.youstudio/device). 없으면 만든다(랜덤 16바이트 hex)."""
    d = os.path.join(os.path.expanduser('~'), '.youstudio'); f = os.path.join(d, 'device')
    try:
        v = io.open(f, encoding='utf-8').read().strip()
        if v:
            return v
    except OSError:
        pass
    import secrets
    v = secrets.token_hex(16)
    try:
        os.makedirs(d, exist_ok=True); io.open(f, 'w', encoding='utf-8').write(v)
    except OSError:
        pass
    return v


def rpc(method, params):
    global _id
    _id += 1
    body = json.dumps({'jsonrpc': '2.0', 'id': _id, 'method': method, 'params': params}, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(A.url.rstrip('/'), data=body, headers={
        'content-type': 'application/json', 'accept': 'application/json, text/event-stream', 'mcp-protocol-version': '2025-11-25'})
    # 인증 헤더 — 서버/runner/기기.mjs authHeaders() 와 같은 규칙(같은 ~/.youstudio/device 파일 = 같은 기기 id).
    req.add_header('X-Youstudio-Device', device_id())
    tok = os.environ.get('YOUSTUDIO_TOKEN')
    if tok:
        req.add_header('authorization', 'Bearer ' + tok)
    with urllib.request.urlopen(req, timeout=120) as r:
        ct = r.headers.get('content-type', '')
        text = r.read().decode('utf-8')
    if 'text/event-stream' in ct:
        datas = [l[5:].strip() for l in text.split('\n') if l.startswith('data:')]
        j = json.loads(datas[-1])
    else:
        j = json.loads(text)
    if j.get('error'):
        raise SystemExit('★RPC 오류: %s' % json.dumps(j['error'], ensure_ascii=False)[:500])
    return j['result']


def call_step(step, payload, source=None):
    args = {'step': step, 'preset': A.preset, 'payload': payload}
    if source:
        args['source'] = source
    res = rpc('tools/call', {'name': 'youstudio_video', 'arguments': args})
    sc = res.get('structuredContent')
    if sc is None:
        txt = ''.join(c.get('text', '') for c in res.get('content', []))
        try:
            sc = json.loads(txt)
        except Exception:
            raise SystemExit('★응답에 structuredContent 가 없다: %s' % txt[:300])
    return sc


def key_from(name):
    v = os.environ.get(name)
    if v:
        return v
    p = os.path.expanduser('~/.volcano/keys/' + name.replace('_API_KEY', '').lower())
    if os.path.exists(p):
        return io.open(p, encoding='utf-8').read().strip()
    envf = os.path.expanduser('~/.volcano/.env')
    if os.path.exists(envf):
        for l in io.open(envf, encoding='utf-8'):
            if l.startswith(name + '='):
                return l.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def fix_argv(argv):
    a = list(argv)
    if a and a[0] in ('python', 'python3'):
        a[0] = PY
    return a


def run_argv(job, cwd, results, optional_default=False):
    name = job['name']
    argv = fix_argv(job['argv'])
    t0 = time.time()
    r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    dt = time.time() - t0
    out = job.get('out')
    if out:
        os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
        io.open(out, 'w', encoding='utf-8').write(r.stdout or '')
    results[name] = {'rc': r.returncode, 'stdout': r.stdout or '', 'stderr': r.stderr or '', 'argv': argv, 'out': out}
    tail = [l for l in (r.stdout or '').splitlines() if l.strip()][-1:] or ['']
    print('    %-14s rc=%d %5.1fs  %s' % (name, r.returncode, dt, tail[0][:90]))
    if r.returncode != 0 and not job.get('optional', optional_default):
        print((r.stdout or '')[-1200:])
        print((r.stderr or '')[-1200:])
        raise SystemExit('★필수 일감 %s 가 실패했다 (rc %d)' % (name, r.returncode))


def run_synth(job, cwd, results):
    name = job['name']
    out = job['out']
    skip = job.get('skip_if') or {}
    if skip.get('path') and os.path.exists(skip['path']) and os.path.getsize(skip['path']) >= int(skip.get('min_bytes', 1)):
        results[name] = {'rc': 0, 'stdout': 'cache', 'stderr': '', 'out': out}
        print('    %-14s 캐시 있음 — 요청 안 보냄' % name)
        return
    key = key_from(job['auth']['env'])
    if not key:
        raise SystemExit('★키가 없다: %s (~/.volcano/keys/ 또는 환경변수)' % job['auth']['env'])
    req = job['request']
    hdr = dict(req.get('headers') or {})
    hdr[job['auth']['header']] = key
    data = json.dumps(req['body'], ensure_ascii=False).encode('utf-8')
    for attempt in range(4):
        try:
            rq = urllib.request.Request(req['url'], data=data, headers=hdr, method=req.get('method', 'POST'))
            with urllib.request.urlopen(rq, timeout=180) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', 'replace')[:300]
            if e.code == 429 and attempt < 3:
                print('    %s 429 — %d초 뒤 다시' % (name, 5 * (attempt + 1)))
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit('★합성 실패 %s: HTTP %d %s' % (name, e.code, detail))
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    io.open(out, 'wb').write(body)
    results[name] = {'rc': 0, 'stdout': '', 'stderr': '', 'out': out, 'bytes': len(body)}
    print('    %-14s 합성 %d바이트 → %s' % (name, len(body), os.path.basename(out)))


def ffdur(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True)
    try:
        return float((r.stdout or '').split()[0])
    except (ValueError, IndexError):
        return None


def measure(rule, results):
    src = rule['from']
    if not src.startswith('job:'):
        raise SystemExit('★measure from 을 모른다: %s' % src)
    name = src[4:]
    res = results.get(name)
    if res is None:
        return None
    u = rule['unit']
    if u == 'json_stdout':
        try:
            return json.loads(res['stdout'])
        except Exception:
            return None
    if u == 'stdout':
        return res['stdout']
    if u == 'stdout_first_line':
        return (res['stdout'].splitlines() or [''])[0]
    if u == 'stderr':
        return res['stderr']
    if u == 'bytes':
        return res.get('bytes') or (os.path.getsize(res['out']) if res.get('out') and os.path.exists(res['out']) else 0)
    if u == 'seconds':
        path = res.get('out')
        if not path or not (path.endswith('.mp4') or path.endswith('.wav')):
            cand = [x for x in res.get('argv', []) if x.endswith('.mp4') or x.endswith('.wav')]
            path = cand[-1] if cand else None
        return ffdur(path) if path and os.path.exists(path) else None
    raise SystemExit('★measure unit 을 모른다: %s' % u)


PAID_MARK = ('전사.py', 'narr_align.py')


def is_paid(sc):
    if sc.get('jobs_kind') == 'synthesize':
        return True
    for j in sc.get('jobs') or []:
        for x in j.get('argv') or []:
            if any(x.endswith(m) for m in PAID_MARK):
                return True
    return False


def execute(sc):
    cwd = sc.get('jobs_cwd') or os.getcwd()
    os.makedirs(cwd, exist_ok=True)
    results = {}
    for j in sc.get('do') or []:
        run_argv(j, cwd, results)
    kind = sc.get('jobs_kind')
    for j in sc.get('jobs') or []:
        if kind == 'synthesize' or j.get('provider'):
            run_synth(j, cwd, results)
        elif 'argv' in j:
            run_argv(j, cwd, results)
        else:
            raise SystemExit('★이 실행기가 모르는 일감 종류: %s %s' % (kind, j.get('name')))
    for j in sc.get('post') or []:
        run_argv(j, cwd, results)
    for wf in sc.get('write_files') or []:
        p = wf['path']
        os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
        c = wf['content']
        io.open(p, 'w', encoding='utf-8').write(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False, indent=2))
        print('    write %s (%d)' % (os.path.basename(p), os.path.getsize(p)))
    measured = {}
    for rule in sc.get('measure') or []:
        measured[rule['as']] = measure(rule, results)
    return measured


def main():
    st = json.load(io.open(A.state, encoding='utf-8')) if os.path.exists(A.state) else {}
    payload = st.get('payload') or {}
    step = A.from_step or st.get('next_step') or 'setup'
    answers = json.load(io.open(A.answers, encoding='utf-8')) if A.answers and os.path.exists(A.answers) else {}
    source = st.get('source')
    if A.source:
        source = {'kind': 'local_video', 'path': os.path.abspath(A.source), 'title': A.title, 'lang': 'ko'}
    if A.workdir:
        payload.setdefault('workdir', os.path.abspath(A.workdir))
    if A.ep:
        payload.setdefault('ep', A.ep)
    if A.start is not None:
        payload.setdefault('start_s', A.start)
    if A.end is not None:
        payload.setdefault('end_s', A.end)
    if A.repo:
        payload['repo'] = os.path.abspath(A.repo)
    # ★기본 칸(workdir·ep·start_s·end_s·repo)은 carry 에 없어도 늘 싣는다 — setup 처럼 carry 가 빈 응답 뒤에 잃어버리지 않게
    base = st.get('base') or {k: payload.get(k) for k in ('workdir', 'ep', 'start_s', 'end_s', 'repo') if payload.get(k) is not None}
    st['base'] = base

    def save(next_step, sc=None):
        st.update({'payload': payload, 'next_step': next_step, 'source': source, 'last': {k: sc.get(k) for k in ('status', 'message', 'metrics', 'warnings', 'need_input')} if sc else st.get('last')})
        io.open(A.state, 'w', encoding='utf-8').write(json.dumps(st, ensure_ascii=False, indent=1))

    for n in range(A.max_calls):
        if A.until and step == A.until and st.get('next_step') == step and n > 0:
            print('■ %s 앞에서 멈춤 (--until)' % step)
            save(step)
            return 0
        # need_input 답을 실어 준다 (키가 «편정보.로고» 처럼 점으로 오면 겹친 사전으로)
        for k, v in answers.items():
            if '.' in k:
                a, b = k.split('.', 1)
                payload.setdefault(a, {})
                if isinstance(payload[a], dict):
                    payload[a][b] = v
            else:
                payload[k] = v
        print('▶ %s (%d)' % (step, n + 1))
        sc = call_step(step, payload, source if step in ('setup', 'start') else None)
        status = sc.get('status')
        print('   %s → %s · %s' % (status, sc.get('next_step'), (sc.get('message') or '')[:160]))
        for w in sc.get('warnings') or []:
            print('   ▲ ' + w[:200])
        if status == 'error':
            print('★ ' + (sc.get('message') or ''))
            print('   → ' + str(sc.get('hint') or sc.get('fix') or sc.get('instructions') or '')[:1200])
            save(step, sc)
            return 1
        if status == 'need_input':
            keys = (sc.get('need_input') or {}).get('keys') or []
            missing = [k for k in keys if k not in answers and not (('.' in k) and answers.get(k) is not None)]
            print('■ need_input: %s' % keys)
            for i, l in enumerate(sc.get('instructions') or []):
                print('   ' + str(l)[:300])
            if missing:
                print('★ --answers 에 없는 값: %s' % missing)
                save(step, sc)
                return 2
            # 답이 다 있으면 같은 단계를 다시 부른다 (carry 는 응답에서)
        if status == 'execute' and is_paid(sc) and not A.approve_paid:
            print('★ 유료 단계다 — 예상 분량: %s' % (sc.get('message') or '')[:300])
            print('   승인되면 --approve-paid 로 다시 돌려라.')
            save(step, sc)
            return 3
        if status == 'done':
            save(None, sc)
            print('■ done — %s' % (sc.get('message') or '')[:300])
            return 0
        measured = execute(sc) if status == 'execute' else {}
        # carry — 응답이 실어 준 값을 다음 payload 로
        new_payload = {}
        for k in sc.get('carry') or []:
            if k in sc:
                new_payload[k] = sc[k]
            elif k in payload:
                new_payload[k] = payload[k]
        for k, v in base.items():
            new_payload.setdefault(k, v)
        if 'source' not in new_payload and source:
            new_payload['source'] = source
        new_payload.update({k: v for k, v in measured.items() if v is not None})
        if status == 'need_input':
            new_payload.update(payload)  # 답은 다음 호출 직전에 다시 얹는다
        payload = new_payload
        step = sc.get('next_step') or step
        save(step, sc)
        if not sc.get('next_step'):
            return 0
    print('★ 호출 상한 %d 에 닿았다' % A.max_calls)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
