# -*- coding: utf-8 -*-
"""제미나이 호출은 **agy(Google Antigravity CLI) 먼저, EvoLink 는 비상용** — 2026-09-26 사장님 지시.

  «시간이 걸리더라도 전수로 제미나이로 작업하게 변경해줘. 작업이 막히면 안 되니깐
   제미나이로 작업하고 그 이후에 에보링크로 할 수 있도록 해줘.»

  EvoLink(도매 API)가 영상 제작 비용의 큰 몫이었다. agy 는 울트라 구독 계정으로 돌아
  API 키·과금이 없다(볼트 규칙 「제미나이는 agy 로만」 2026-09-24).

  쓰는 법 — 기존 generateContent 요청 본문(body)을 **그대로** 넘긴다:
      import agy_gemini
      resp = agy_gemini.generate(body, caller="분석_판독")
      if resp is None:  ... 원래 EvoLink 길 ...
  돌려주는 resp 는 generateContent 응답과 같은 모양이다
  (candidates[0].content.parts[0].text · finishReason "STOP" · usageMetadata).
  .mjs 실행기는 명령줄로 부른다:
      python agy_gemini.py --body 요청.json --out 응답.json --caller run_select   (성공 0 · 실패 1)

  받는 입력: text · inline_data(base64 사진·영상·소리) · file_data(유튜브 등 공개 URL)
            · 실행기 자리표 @inline_file / @file_uri {path, mime} (로컬 파일을 그대로 보인다)
            · generationConfig.responseSchema → agy --json-schema (구조화 답)
            · responseMimeType application/json → 답에서 JSON 하나를 떼어 검증
  못 받는 입력: 구글 Files API 로 이미 올린 URI(generativelanguage…/files/…) → None(EvoLink 길로)

  2026-09-26 실측(윈도우, agy 1.2.11, gemini-3.8-flash-high) — 첨부는 **절대경로 + 답변 전용 에이전트**:
      글 질문 2초 · 5초 영상 10초 · 60초 대사(영상→그림+소리) flash-low 14초, 중앙 오차 0.31초.
      ★파일 이름만 주면 agy 가 디스크를 헤매 135초·41회 — 절대경로가 핵심이다(_build 주석).
      ★view_file 은 mp4 의 그림만 넘긴다 — 소리는 mp3 로 따로 뽑아 같이 준다(_audio_of).

  끄는 법: 환경변수 YOUSTUDIO_GEMINI_ROUTE=evolink  → agy 를 건너뛰고 예전처럼 EvoLink 만.
  모델:    환경변수 YOUSTUDIO_AGY_MODEL (기본 gemini-3.8-flash-low — DEFAULT_MODEL 주석의 실측)
  기록:    ~/.volcano/logs/gemini_route.jsonl 에 호출마다 한 줄 (route agy / fallback)
           → fallback 줄 수 = EvoLink 로 넘어간 횟수 = 돈이 나간 횟수.
"""
import base64
import re
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ★파이프라인 기본은 flash-low — 60초 대사 받아쓰기 실측(2026-09-26): high 167초·중앙 0.27초·최대 0.97초 /
#   medium 111초·0.38·6.85 / low 14초·0.31·1.88. 생각 시간이 속도를 가른다(EvoLink 호출도 대부분 thinkingBudget 0).
#   대화용 ~/.claude/agy_call.py 의 기본(high)과는 따로다. 바꾸려면 YOUSTUDIO_AGY_MODEL.
DEFAULT_MODEL = "gemini-3.8-flash-low"
RETRIES = 3            # 구글 503(UNAVAILABLE)만 다시 한다 — 2026-09-24 실측 60~73초 실패 뒤 재시도 7초 성공
DEFAULT_LIMIT_MIN = 10
ARGV_MAX = 24000       # 윈도우 명령줄 한도 32767자 — 넘으면 질문을 파일로 넘긴다
LOG = Path.home() / ".volcano" / "logs" / "gemini_route.jsonl"

EXT = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
       "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp",
       "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
       "audio/aac": ".aac", "audio/mp4": ".m4a", "audio/ogg": ".ogg", "audio/flac": ".flac",
       "application/pdf": ".pdf", "text/plain": ".txt"}


def _agy_exe():
    if os.name == "nt":
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
        if p.exists():
            return str(p)
    return shutil.which("agy")


def _record(caller, route, sec, reason="", model=""):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "caller": caller,
                                "route": route, "sec": round(sec, 1), "model": model,
                                "reason": reason[:300]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _to_json_schema(s):
    """Gemini responseSchema(OpenAPI 부분집합, 대문자 type) → JSON Schema."""
    if isinstance(s, list):
        return [_to_json_schema(x) for x in s]
    if not isinstance(s, dict):
        return s
    out = {}
    for k, v in s.items():
        if k in ("propertyOrdering", "nullable", "format"):
            continue
        if k == "type" and isinstance(v, str):
            out[k] = v.lower()
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: _to_json_schema(pv) for pk, pv in v.items()}
        else:
            out[k] = _to_json_schema(v)
    if s.get("nullable") and isinstance(out.get("type"), str):
        out["type"] = [out["type"], "null"]
    return out


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool,
          "number": (int, float), "integer": int}


def _schema_errors(v, s, where="$"):
    """EvoLink responseSchema 가 서버에서 강제하던 것을 여기서 잰다 — 타입과 required 칸. 틀린 곳 목록."""
    if not isinstance(s, dict):
        return []
    t = s.get("type")
    ts = t if isinstance(t, list) else [t] if t else []
    if v is None:
        return [] if "null" in ts or not ts else [f"{where} 가 비었다"]
    ok = [x for x in ts if x in _TYPES and isinstance(v, _TYPES[x])
          and not (x in ("number", "integer") and isinstance(v, bool))]
    if ts and not ok:
        return [f"{where} 는 {t} 여야 한다({type(v).__name__})"]
    errs = []
    if isinstance(v, dict):
        errs += [f"{where}.{k} 가 없다" for k in s.get("required", []) if k not in v]
        for k, sub in (s.get("properties") or {}).items():
            if k in v:
                errs += _schema_errors(v[k], sub, f"{where}.{k}")
    elif isinstance(v, list) and isinstance(s.get("items"), dict):
        for i, x in enumerate(v):
            errs += _schema_errors(x, s["items"], f"{where}[{i}]")
    return errs


def _first_json(text):
    """답 글에서 완결된 JSON 값 하나를 떼어 낸다(앞에 파일 링크·설명이 붙는 일이 있다). 없으면 None."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    try:
        return json.loads(t)
    except (json.JSONDecodeError, ValueError):
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch not in "{[":
            continue
        try:
            obj, _ = dec.raw_decode(t[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) or (isinstance(obj, list) and not all(isinstance(x, str) for x in obj)):
            return obj
    return None


class _Unsupported(Exception):
    pass


ANSWER_AGENT = """---
name: answer
description: 첨부를 view_file 로 한 번씩 열어 보고 곧바로 답만 한다
mainAgent: true
excludeDefaultComponents: true
tools: [view_file]
---
# answer
너는 질문에 한 번에 답하는 모델이다. 질문에 적힌 첨부 파일(절대경로)만 view_file 로 한 번씩 연다.
다른 파일·폴더는 열지 않는다. 명령을 실행하지 않는다. 첨부를 보고 들은 뒤 곧바로 답한다.
"""


def _audio_of(video, work, name):
    """영상의 소리를 mp3 로 따로 뽑는다. view_file 은 mp4 에서 그림만 넘긴다(2026-09-26 실측 — 소리 있는
    영상에 «소리는 없습니다»). 소리가 없거나 ffmpeg 가 없으면 None."""
    dst = work / name
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn",
                            "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(dst)],
                           capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return dst if r.returncode == 0 and dst.exists() and dst.stat().st_size > 1024 else None


def _build(body, work):
    """요청 본문 → (질문 글, 첨부 수, 주소 첨부 여부). 첨부 파일은 work 폴더에 놓고 **절대경로**로 가리킨다.

    ★2026-09-26 실측 — 파일 이름만 주면 view_file 이 «절대경로만 받는다»로 거절해 agy 가 파일을 찾아
      디스크를 헤맸다(41회 호출·65만 토큰·135초, 클로드 설정·대화 기록까지 열었다).
      절대경로로 주니 5초 영상 12.7초·3회·3.4천 토큰, 60초 대사(mp3) 15.7초·3회.
    """
    n = 0
    has_url = False

    def local(path, mime):
        nonlocal n
        n += 1
        ap = Path(path).resolve().as_posix()
        if mime.startswith("video/") or Path(path).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            snd = _audio_of(path, work, f"첨부{n}_소리.mp3")
            if snd:
                return (f"[첨부 {n} 영상의 그림: {ap}]\n"
                        f"[첨부 {n} 영상의 소리: {snd.resolve().as_posix()}] (같은 영상의 소리 — 시각이 그림과 같다)")
        return f"[첨부 {n}: {ap} ({mime})]"

    def media(part):
        nonlocal n, has_url
        if "text" in part:
            return part["text"]
        inl = part.get("inline_data") or part.get("inlineData")
        if inl:
            mime = inl.get("mime_type") or inl.get("mimeType") or ""
            f = work / f"첨부{n + 1}{EXT.get(mime, '.bin')}"
            f.write_bytes(base64.b64decode(inl["data"]))
            return local(f, mime)
        for key in ("@inline_file", "@file_uri"):
            loc = part.get(key)
            if loc:
                return local(loc["path"], loc.get("mime", ""))
        fd = part.get("file_data") or part.get("fileData")
        if fd:
            uri = fd.get("file_uri") or fd.get("fileUri") or ""
            if "generativelanguage.googleapis.com" in uri or not uri.startswith("http"):
                raise _Unsupported("구글 Files API 로 올린 파일은 agy 가 못 본다: " + uri[:80])
            n += 1
            has_url = True
            return f"[첨부 {n}: 영상 주소 {uri} — 이 주소의 영상을 직접 보라]"
        raise _Unsupported("모르는 part: " + ",".join(part.keys()))

    chunks = []
    si = body.get("systemInstruction") or body.get("system_instruction")
    if si:
        chunks.append("[시스템 지시]\n" + "\n".join(media(p) for p in si.get("parts", [])))
    contents = body.get("contents", [])
    multi = len(contents) > 1
    for c in contents:
        txt = "\n".join(media(p) for p in c.get("parts", []))
        chunks.append(f"[{c.get('role', 'user')}]\n{txt}" if multi else txt)
    prompt = "\n\n".join(chunks)
    if n and not has_url:
        prompt = ("아래 [첨부] 파일을 view_file 로 절대경로 그대로 한 번씩 열어 보고(영상은 그림 파일과 소리 파일을 "
                  "둘 다) 곧바로 답하라. 다른 파일은 열지 마라.\n\n" + prompt)
    elif has_url:
        prompt = "아래 [첨부] 영상 주소의 영상을 직접 보고(화면과 소리 모두) 답하라. 파일을 고치거나 지우지 마라.\n\n" + prompt
    return prompt, n, has_url


def generate(body, caller="", limit_min=DEFAULT_LIMIT_MIN, model=None, log=print):
    """agy 로 generateContent 를 흉내 낸다. 실패하면 None — 호출하는 쪽이 EvoLink 로 간다."""
    t0 = time.time()
    model = model or os.environ.get("YOUSTUDIO_AGY_MODEL") or DEFAULT_MODEL

    def fail(reason):
        log(f"  agy 실패({reason[:160]}) → EvoLink 로 넘어간다")
        _record(caller, "fallback", time.time() - t0, reason, model)
        return None

    if os.environ.get("YOUSTUDIO_GEMINI_ROUTE", "").strip().lower() == "evolink":
        _record(caller, "fallback", 0, "YOUSTUDIO_GEMINI_ROUTE=evolink (agy 꺼 둠)", model)
        return None
    exe = _agy_exe()
    if not exe:
        return fail("agy 가 설치돼 있지 않다")

    work = Path(tempfile.mkdtemp(prefix="agy_"))
    try:
        try:
            prompt, n, has_url = _build(body, work)
        except _Unsupported as e:
            return fail(str(e))
        gc = body.get("generationConfig") or body.get("generation_config") or {}
        schema = gc.get("responseSchema") or gc.get("response_schema")
        want_json = bool(schema) or "json" in str(gc.get("responseMimeType") or gc.get("response_mime_type") or "")
        js = _to_json_schema(schema) if schema else None
        # ★답변 전용 에이전트에는 --json-schema 답을 채우는 «작업 완료» 도구가 없다 — 구조화 답이 늘 빈다
        #   (2026-09-26 실측). 그래서 스키마는 질문 글로 주고, 받은 JSON 을 _schema_errors 로 검사한다.
        #   기본 에이전트(유튜브 주소)만 --json-schema 를 쓴다.
        use_flag = bool(schema) and has_url
        if want_json and not use_flag:
            prompt += "\n\n[출력 형식] JSON 값 하나만 출력하라. 앞뒤 설명·코드블록 금지."
            if js:
                prompt += "\n아래 JSON Schema 를 반드시 따른다(required 칸 전부):\n" + json.dumps(js, ensure_ascii=False)
        cmd = [exe, "--dangerously-skip-permissions", "--disable-slash-commands", "--model", model,
               "--print-timeout", f"{limit_min}m", "--output-format", "json"]
        if not has_url:
            # 답변 전용 에이전트 — 기본 도구·기본 안내문을 빼고 view_file 하나만(글 질문 589토큰·2초).
            #   유튜브 주소는 agy 기본 에이전트가 보러 가야 해서 쓰지 않는다.
            (work / ".agents" / "agents" / "answer").mkdir(parents=True, exist_ok=True)
            (work / ".agents" / "agents" / "answer" / "agent.md").write_text(ANSWER_AGENT, encoding="utf-8")
            cmd += ["--agent", "answer"]
        if use_flag:
            (work / "_schema.json").write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
            cmd += ["--json-schema", str(work / "_schema.json")]
        if len(prompt) > ARGV_MAX:
            (work / "_질문.md").write_text(prompt, encoding="utf-8")
            prompt = (f"{(work / '_질문.md').resolve().as_posix()} 파일 전체가 너의 작업 지시다. view_file 로 끝까지 "
                      "읽고 그대로 수행해 답하라. 파일을 고치거나 지우지 마라.")
        cmd += ["-p", prompt]

        out = err = ""
        for i in range(RETRIES):
            proc = subprocess.Popen(cmd, cwd=str(work), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
            try:
                out, err = proc.communicate(timeout=limit_min * 60 + 60)
            except subprocess.TimeoutExpired:
                # agy 는 스스로 agy 를 또 띄운다(2026-09-24 실측) — 자식까지 같이 끈다
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
                else:
                    proc.kill()
                proc.communicate()
                return fail(f"{limit_min}분 시간 제한")
            both = (out or "") + (err or "")
            if proc.returncode == 0 and "UNAVAILABLE" not in both:
                break
            if "UNAVAILABLE" not in both:
                return fail(f"종료코드 {proc.returncode}: {both.strip()[-200:]}")
            log(f"  agy 구글 서버 일시 장애(503) — {5 * (i + 1)}초 뒤 다시 ({i + 1}/{RETRIES})")
            time.sleep(5 * (i + 1))
        else:
            return fail("구글 서버 일시 장애(503) 반복")

        res = _first_json(out or "")
        if not isinstance(res, dict) or "response" not in res and "structured_output" not in res:
            return fail("agy 출력이 JSON 이 아니다: " + (out or "").strip()[:160])
        if res.get("status") not in (None, "SUCCESS"):
            return fail(f"agy status={res.get('status')}: {str(res.get('error') or '')[:200]}")
        if use_flag:
            so = res.get("structured_output")
            if so in (None, {}, []):
                return fail("구조화 답이 비었다")
            text = json.dumps(so, ensure_ascii=False)
        else:
            text = (res.get("response") or "").strip()
            if not text:
                # agy 는 --print-timeout 에 걸려도 빈 답에 종료코드 0 을 낸다(2026-09-24 실측)
                return fail("빈 답 — 시간 제한에 걸렸을 가능성이 크다")
            # ★유튜브 주소는 agy 가 들쭉날쭉하다 — 같은 질문에 82~244초, 가끔 «영상을 볼 수 없음»(2026-09-26 실측 5회).
            #   못 봤다는 답을 성공으로 넘기지 않는다.
            if n and re.search(r"볼 수 없|볼수없|cannot (view|access|watch|see)|unable to (view|access|watch)", text, re.I) \
                    and len(text) < 200:
                return fail("첨부를 못 봤다고 답했다: " + text[:80])
            if want_json:
                obj = _first_json(text)
                if obj is None:
                    return fail("JSON 을 요구했는데 답에 JSON 이 없다: " + text[:120])
                bad = _schema_errors(obj, js) if js else []
                if bad:
                    return fail("스키마와 다르다: " + "; ".join(bad[:3]))
                text = json.dumps(obj, ensure_ascii=False)
        u = res.get("usage") or {}
        sec = time.time() - t0
        log(f"  (agy · {model} · 첨부 {n} · {sec:.0f}초)")
        _record(caller, "agy", sec, "", model)
        return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]},
                                "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": u.get("input_tokens"),
                                  "candidatesTokenCount": u.get("output_tokens"),
                                  "totalTokenCount": u.get("total_tokens")},
                "modelVersion": f"agy/{model}", "route": "agy"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def text_of(resp):
    return "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])


def main():
    import argparse
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")  # 윈도우 기본 cp949 로 나가면 .mjs 로그가 깨진다
    ap = argparse.ArgumentParser(description="generateContent 요청 파일을 agy 로 처리한다 (.mjs 실행기용)")
    ap.add_argument("--body", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--caller", default="cli")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT_MIN)
    a = ap.parse_args()
    body = json.loads(Path(a.body).read_text(encoding="utf-8"))
    resp = generate(body, caller=a.caller, limit_min=a.limit, log=lambda m: print(m, file=sys.stderr))
    if resp is None:
        sys.exit(1)
    Path(a.out).write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
