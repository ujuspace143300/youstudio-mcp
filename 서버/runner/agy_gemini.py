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
  모델:    환경변수 YOUSTUDIO_AGY_MODEL (기본 gemini-3.8-flash-high — 사장님 결정, 실측은 DEFAULT_MODEL 주석)
  기록:    ~/.volcano/logs/gemini_route.jsonl 에 호출마다 한 줄 (route agy / fallback)
           → fallback 줄 수 = EvoLink 로 넘어간 횟수 = 돈이 나간 횟수.
           route agy 줄의 reason 이 비어 있지 않으면 «받긴 했는데 사정이 있었다» 는 표시다
           (Malformed 인데 답 칸이 온전해 받음 · 다시 N번 뒤 받음).

  2026-09-26 저녁 맥2 수리 — 볼트 제안/스크립트/제미나이점검_20260926 반박 9·10·14·16·17·20 · 파악전사 실측.md 8절
    찾기     agy: AGY_EXE → 윈도우 %LOCALAPPDATA%\\agy\\bin\\agy.exe → ~/.local/bin/agy → PATH
             (볼트 스크립트/환경검사.py agy_찾기 와 같은 순서 · _agy_find). 맥 설치기는 ~/.local/bin 에 두는데 설치 전에 켠
             창·LaunchAgent 는 PATH 에 그 자리가 없어, which 만 보던 예전 판은 «agy 없음» → EvoLink 로 샜다(반박 9).
             ffmpeg: PATH → /opt/homebrew/bin · /usr/local/bin …(_ffmpeg_exe). 못 찾거나 소리를 못 뽑으면 **실패**다 —
             예전 판은 소리를 조용히 빼고 그림만 보낸 답을 «agy 성공» 으로 적었다(반박 20).
    Malformed agy 가 status=ERROR «Malformed function call» 을 내도 stdout 의 response 칸에 온전한 답이 있는 일이 있다
             (파악전사 실측 agy 실패 11 중 6 · 원답 _agy_원답/agy_165217.json — 4349자 JSON 이 통째로 있었다).
             답 칸이 **통째로** 한 JSON 값이고 스키마가 있으면 스키마까지 맞을 때만 받는다(_malformed_ok) — route agy,
             reason 에 표시. 아니면 한 번 다시. 글(자유 문장) 답은 끝까지 왔는지 잴 수 없어 받지 않고 다시 한다.
    다시     503 은 전처럼 RETRIES 번까지, Malformed·일시 오류(500·504·429·빈 답·«볼 수 없»)는 한 번 — 모두 처음 시간 제한
             (limit_min) **안에서만**(남은 시간이 MIN_RETRY_SEC 보다 짧으면 다시 하지 않는다). 필터 차단·인증 실패·모르는
             오류·JSON/스키마 어긋남은 다시 하지 않는다(다시 해도 같다 — 사용량만 준다). 예전 판은 503 만 다시 해서,
             Malformed 한 번에 곧장 EvoLink 로 갔다(반박 10 · 2026-09-26 15:54 파악전사 102초 뒤 실패).
             ★부르는 쪽이 따로 다시 하면 곱해진다(파악전사 «다시 1번» · agy_asr TRIES 3) — 몫은 부르는 쪽이 정한다.
    «볼 수 없» JSON 을 요구했고 답이 유효한 JSON(스키마까지 통과)이면 이 정규식을 대지 않는다 —
             {"speaker":"?","reason":"얼굴을 볼 수 없음"} 같은 정상 답이 실패 → EvoLink 가 됐다(반박 14).
    정리     시간 초과·중단(Ctrl-C) 때 agy 와 그 자식을 함께 끈다 — 맥은 새 세션(프로세스 그룹)으로 띄워 그룹째 끄고,
             윈도우는 taskkill /T. 예전 판은 맥에서 proc.kill() 로 agy 하나만 껐다(반박 16).
    순정 키  agy 자식 환경에서 GEMINI_API_KEY·GOOGLE_API_KEY 류와 Vertex·ADC 스위치를 뺀다(_agy_env) — agy 가 구독 대신
             키 모드로 가 과금되지 않게. 한편.py 가 keys 폴더를 전부 <이름>_API_KEY 로 자식에게 넘긴다(반박 17 ·
             사장님 결정 ④ 2026-09-26 «순정 구글 키 길은 막는다»).

  2026-09-27 맥2 — 맥1 판(d822dd5 «agy 비상 길 누수 막기»)과 합침 + 동시 16
    멈춤     영상·소리 첨부(has_media) 요청이 끝내 실패하면 None 대신 AgyStop(BaseException)을 던진다 — EvoLink 금지
             (사장님 결정 2번). 명령줄(main)은 종료코드 3 · agy_gemini.mjs 도 3 을 멈춤으로 받는다. judge_run.agy_먼저 는
             판정멈춤(종료코드 3)으로, 파악전사는 «agy 실패»(한 번 더 → 멈춤)로 받는다. 기록 route 는 agy_fail_stop.
    형식     JSON 없음·스키마 다름·까닭 모를 헛출력은 FORMAT_TRIES(3)번까지 다시 묻는다(싱글286 실측 누수 — 맥1 판).
             필터 차단·인증 실패는 다시 하지 않는다(다시 해도 같다 — 이 맥 판 판단 유지).
    동시 16  볼케이노 3D쇼츠 팩 규격(info3d/flow/agy_review.py · AGY_MAX 16 · 다시 묻기 4초·8초)을 기본값으로 —
             ~/.volcano/agy_slots/ 파일 잠금 16칸을 볼트 설치/agy_call.py 와 같이 쓴다(이 컴퓨터의 agy 호출이 합쳐 16개).
             빈자리를 기다린 시간은 시간 제한에 넣지 않는다. 환경변수 AGY_MAX 로 바꿀 수 있다. (사장님 지시 2026-09-27)
"""
import base64
import re
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# 모델별 실측 — 60초 대사 받아쓰기 실측(2026-09-26): high 167초·중앙 0.27초·최대 0.97초 /
#   medium 111초·0.38·6.85 / low 14초·0.31·1.88. 생각 시간이 속도를 가른다(EvoLink 호출도 대부분 thinkingBudget 0).
#   ★사장님 결정(2026-09-26): 기본은 high — 볼트 규칙 기본값과 같게. 바꾸려면 YOUSTUDIO_AGY_MODEL.
DEFAULT_MODEL = "gemini-3.8-flash-high"
RETRIES = 3            # 모두 합친 시도 수 상한. 503 은 여기까지 — 2026-09-24 실측 60~73초 실패 뒤 재시도 7초 성공
ONCE = 1               # Malformed·일시 오류는 한 번만 다시 (머리 주석 「다시」)
MIN_RETRY_SEC = 30     # 시간 제한까지 이보다 덜 남았으면 다시 하지 않는다
KILL_GRACE_SEC = 60    # agy 자체 --print-timeout 뒤 이만큼 더 기다리고 프로세스 나무째 끈다
STALL_SEC = float(os.environ.get("AGY_STALL_SEC") or 300)   # agy 기록·출력이 이만큼 조용하면 멈춘 것(_run 주석 · 2026-10-04)
SHUTDOWN_GRACE_SEC = 30  # 답을 낸 뒤(«shutting down») 이만큼 지나도 안 끝나면 나무째 끈다(정상 5초 · _run 주석)
DEFAULT_LIMIT_MIN = 10
ARGV_MAX = 24000       # 윈도우 명령줄 한도 32767자 — 넘으면 질문을 파일로 넘긴다
LOG = Path.home() / ".volcano" / "logs" / "gemini_route.jsonl"
FORMAT_TRIES = 3       # 답 형식이 틀리면(JSON 없음·스키마 다름·agy 출력이 JSON 아님) agy 로 다시 묻는 횟수 (맥1 d822dd5)
RETRY_GAP_SEC = 4      # 다시 묻기 간격 — 볼케이노 3D쇼츠 팩 agy_review.agy_json 의 4초·8초 (머리 주석 「동시 16」)
AGY_MAX = 16           # agy 동시 호출 상한 — 3D쇼츠 팩 agy_review.AGY_MAX. 볼트 설치/agy_call.py 와 같은 잠금 칸을 쓴다
SLOT_DIR = Path.home() / ".volcano" / "agy_slots"

# agy 자식 환경에서 뺄 이름 (머리 주석 「순정 키」). agy 1.2.11 실행 파일 안 문자열로 확인한 이름 + 같은 꼴의 키 이름.
_KEY_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI",
            "GOOGLE_GENAI_USE_ENTERPRISE", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_GEMINI_BASE_URL", "AGY_ADC_AUTH")

# agy 실패 가르기 (머리 주석 「다시」) — 오류 칸·표준오류에만 댄다(모델 답 글에 «UNAVAILABLE» 이 있어도 다시 하지 않게)
_FILTER = re.compile(r"blocked by Gemini'?s filters|PROHIBITED_CONTENT|\bSAFETY\b|blockReason", re.I)
_FILTER_RESP = re.compile(r"This request was blocked by Gemini'?s filters", re.I)   # agy 가 답 글 끝에 붙이는 문구
_AUTH = re.compile(r"not (logged|signed) in|not authenticated|UNAUTHENTICATED|PERMISSION_DENIED|login required|"
                   r"please (log|sign) ?in|invalid_grant|reauth|\b40[13]\b", re.I)
_UNAVAILABLE = re.compile(r"UNAVAILABLE|\b503\b|overloaded", re.I)
_MALFORMED = re.compile(r"Malformed function call|improperly formatted function call", re.I)
_TRANSIENT = re.compile(r"\bINTERNAL\b|\b50[024]\b|DEADLINE_EXCEEDED|RESOURCE_EXHAUSTED|\b429\b|rate.?limit|"
                        r"connection (reset|refused|closed)|broken pipe|\bEOF\b|i/o timeout|temporar|"
                        r"network issue|stream was interrupted|operation timed out|read tcp|stream reading error|"
                        r"멈춤\(죽은 연결", re.I)   # 끝 셋 — 2026-10-04 루키치70·76 네트워크 끊김(다시 한 번 묻는다)
_CANNOT_SEE = re.compile(r"볼 수 없|볼수없|cannot (view|access|watch|see)|unable to (view|access|watch)", re.I)

EXT = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
       "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp",
       "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
       "audio/aac": ".aac", "audio/mp4": ".m4a", "audio/ogg": ".ogg", "audio/flac": ".flac",
       "application/pdf": ".pdf", "text/plain": ".txt"}


class AgyStop(BaseException):
    """영상·소리 판정이 agy 로 끝내 안 됐다 — EvoLink 로 넘기지 않고 멈춘다(2026-09-26 사장님 결정 2번).
    ★BaseException 이다: 부르는 쪽의 «except Exception» 이 삼켜 조용히 계속하지 못하게(싱글286 실측 —
    준비·댓글 선별 등 3곳이 except Exception 으로 실패를 삼킨다). Ctrl-C 처럼 끝까지 올라가 체인을 멈춘다.
    judge_run.agy_먼저 는 이것을 판정멈춤(종료코드 3)으로, 파악전사는 «agy 실패»(한 번 더 → 멈춤)로 받는다."""


class AgyOutputLimit(AgyStop):
    """agy 답이 출력 토큰 한도를 넘어 잘렸다 — 같은 질문을 되풀이해도 또 넘는다(부르는 쪽이 질문을 줄여야 한다).
    ★2026-09-28 싱글126(원본 214초 통째 전사): 6번 모두 «exceeded the output token limit». agy 기록(brain/…/transcript_full)
      실측 — 잘린 답 14건의 본문은 4.0~4.5천 자(74~94줄)뿐이고 생각(thinking)이 2.5~3.8만 자로 출력의 85~90% 를 먹었다.
      반복 폭주가 아니다(같은 줄 되풀이 0~4개 — 짧은 감탄사). 같은 질문 3번 = 약 11분을 버리고 멈췄다.
    AgyStop 의 하위라 이 예외를 따로 안 잡는 곳에서는 예전처럼 멈춘다. 영상 전사(agy_asr)는 잡아서 구간을 나눠 다시 묻는다."""


def has_media(body):
    """요청에 영상·소리 첨부가 있는가 — 있으면 agy 실패 시 EvoLink 로 가지 않고 멈춘다."""
    def media_mime(m, path=""):
        m = (m or "").lower()
        return m.startswith(("video/", "audio/")) or Path(path).suffix.lower() in (
            ".mp4", ".mov", ".webm", ".mkv", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
    for c in body.get("contents", []):
        for p in c.get("parts", []):
            inl = p.get("inline_data") or p.get("inlineData")
            if inl and media_mime(inl.get("mime_type") or inl.get("mimeType")):
                return True
            for key in ("@inline_file", "@file_uri"):
                if p.get(key) and media_mime(p[key].get("mime", ""), p[key].get("path", "")):
                    return True
            fd = p.get("file_data") or p.get("fileData")
            if fd:                                   # 유튜브 등 주소 = 영상
                return True
    return False


def _lock_nb(f):
    """파일 잠금을 기다리지 않고 잡는다 — 못 잡으면 OSError. 프로세스가 죽으면 운영체제가 풀어 준다."""
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


class _agy_slot:
    """agy 동시 호출 문(머리 주석 「동시 16」) — 빈 칸 하나를 잡을 때까지 기다리고, 나가면 푼다. waited = 기다린 초."""

    def __init__(self, log=print):
        self.n = max(1, int(os.environ.get("AGY_MAX") or AGY_MAX))
        self.f, self.waited, self.log = None, 0.0, log

    def __enter__(self):
        SLOT_DIR.mkdir(parents=True, exist_ok=True)
        t0, told = time.time(), False
        while True:
            for i in range(self.n):
                f = open(SLOT_DIR / f"slot_{i:02d}.lock", "a+")
                try:
                    _lock_nb(f)
                    self.f, self.waited = f, time.time() - t0
                    return self
                except OSError:
                    f.close()
            if not told:
                self.log(f"  agy 동시 {self.n}개가 다 차 있다 — 빈자리를 기다린다")
                told = True
            time.sleep(0.5)

    def __exit__(self, *exc):
        if os.name == "nt":
            try:
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        self.f.close()      # 맥·리눅스는 닫으면 풀린다
        return False


def _agy_find():
    """(경로, 찾은 길) · 못 찾으면 (None, 까닭). 순서는 볼트 스크립트/환경검사.py agy_찾기 와 같다(머리 주석 「찾기」):
    AGY_EXE → 윈도우 %LOCALAPPDATA%\\agy\\bin\\agy.exe → ~/.local/bin/agy → PATH(which)."""
    env = os.environ.get("AGY_EXE", "").strip()
    if env:
        # 적어 둔 자리가 틀렸으면 다음 후보로 조용히 넘어가지 않는다 — 도구마다 다른 agy 를 잡게 된다
        p = os.path.expanduser(env)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p, "AGY_EXE"
        return None, f"AGY_EXE={env} 가 가리키는 실행 파일이 없다"
    cands = []
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        if la:
            cands.append((os.path.join(la, "agy", "bin", "agy.exe"), "LOCALAPPDATA"))
    cands.append((os.path.join(os.path.expanduser("~"), ".local", "bin",
                               "agy.exe" if os.name == "nt" else "agy"), "~/.local/bin"))
    for p, how in cands:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p, how
    w = shutil.which("agy")
    if w:
        return w, "PATH"
    return None, "agy 실행 파일을 못 찾았다 (AGY_EXE · LOCALAPPDATA · ~/.local/bin · PATH 다 봄)"


def _agy_exe():
    """agy 실행 파일 경로, 없으면 None (judge_run·파악전사가 부르는 이름 — 모양을 바꾸지 않는다)."""
    return _agy_find()[0]


def _ffmpeg_exe():
    """ffmpeg 경로, 없으면 None. PATH 를 먼저 보고, 없으면 흔한 설치 자리(머리 주석 「찾기」 · judge_run 과 같은 후보)."""
    w = shutil.which("ffmpeg")
    if w:
        return w
    if os.name == "nt":
        cands = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"),
                 r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin",
                 os.path.join(os.environ.get("USERPROFILE", ""), "scoop", "shims"), r"C:\ProgramData\chocolatey\bin"]
    else:
        cands = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/usr/bin"]
    for d in cands:
        p = os.path.join(d, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if d and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _agy_env():
    """agy 자식에게 줄 환경 — 순정 구글 키·키 모드 스위치를 뺀다(머리 주석 「순정 키」). 값은 어디에도 적지 않는다."""
    env = dict(os.environ)
    for k in list(env):
        K = k.upper()
        if K in _KEY_ENV or (K.startswith(("GEMINI_", "GOOGLE_")) and K.endswith("_KEY")):
            del env[k]
    return env


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


def _whole_json(text):
    """답 글 **전체**가 JSON 값 하나일 때만 그 값(객체·배열), 아니면 None. _first_json 과 달리 조각을 떼어 오지 않는다 —
    잘린 답 안의 앞쪽 객체 하나를 «온전한 답» 으로 잘못 받지 않게(Malformed 받기 전용 · 머리 주석 「Malformed」)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t[:4].lower() == "json":
            t = t[4:].strip()
    try:
        obj = json.loads(t)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, (dict, list)) else None


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
    영상에 «소리는 없습니다»). 영상에 소리 줄기가 없으면 None(그림만 보내도 된다).
    ffmpeg 를 못 찾거나 소리를 못 뽑으면 _Unsupported — **소리 없이 그림만 보내지 않는다**(머리 주석 「찾기」 · 반박 20)."""
    ff = _ffmpeg_exe()
    if not ff:
        raise _Unsupported("ffmpeg 를 못 찾는다(PATH · /opt/homebrew/bin · /usr/local/bin …) — 영상의 소리를 못 뽑아 "
                           "그림만 보게 된다. 소리 없이 보내지 않는다")
    dst = work / name
    try:
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vn",
                            "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(dst)],
                           capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise _Unsupported(f"영상의 소리를 못 뽑았다({type(e).__name__}) — 소리 없이 보내지 않는다")
    msg = (r.stderr or b"").decode("utf-8", "replace")
    if r.returncode != 0:
        if re.search(r"does not contain any stream|matches no streams", msg):
            return None     # 소리 줄기가 없는 영상 — 그림만 보낸다
        raise _Unsupported(f"영상의 소리를 못 뽑았다(ffmpeg 종료 {r.returncode}: {msg.strip()[-160:]}) — 소리 없이 보내지 않는다")
    return dst if dst.exists() and dst.stat().st_size > 1024 else None


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


def 출력한도(reason):
    """agy 실패 사유가 «출력 토큰 한도 초과» 인가 (agy status=ERROR 문구 — 2026-09-28 싱글126 실측)."""
    return "exceeded the output token limit" in (reason or "")


def _kill_tree(proc):
    """agy 와 그 자식을 함께 끈다(머리 주석 「정리」). agy 는 스스로 agy 를 또 띄운다(2026-09-24 실측)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        return
    # 맥·리눅스: _run 이 새 세션으로 띄웠으니 프로세스 그룹 번호 = agy 의 pid. 먼저 점잖게, 3초 뒤 강제로.
    for sig, wait in ((signal.SIGTERM, 3), (signal.SIGKILL, 0)):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            break           # 그룹이 이미 다 끝났다
        if wait:
            try:
                proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass


class AgyStall(Exception):
    """agy 가 «아무 기록도 없이» STALL_SEC 넘게 멈춰(죽은 TCP 를 읽고 앉음) 나무째 끊었다 — 일시 오류로 한 번 다시 묻는다."""


class AgyWallTimeout(AgyStall):
    """벽시계 한도(시간 제한+KILL_GRACE_SEC)를 넘어 나무째 끊었다 — 시간이 다 갔으니 다시 묻지 않는다."""


def _agy_logfile():
    """agy 한 번마다 따로 쓰는 기록 파일 — agy 기본 기록과 같은 폴더(사람이 찾던 자리)에 pid 를 붙여 겹치지 않게.
    (기본 기록은 «시작 초» 로 이름을 지어 같은 초에 뜬 agy 들이 한 파일에 섞어 쓴다 — 2026-10-04 실측.)"""
    d = Path.home() / ".gemini" / "antigravity-cli" / "log"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path(tempfile.gettempdir())
    return d / f"cli-{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{os.urandom(3).hex()}.log"


_LOGFLAG = {}


def _log_flag_ok(exe):
    """이 agy 가 --log-file 을 아는가(1.2.16 맥 확인). 옛 판이면 침묵 감시 없이 벽시계 한도만 쓴다."""
    if exe not in _LOGFLAG:
        try:
            h = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=30)
            _LOGFLAG[exe] = "--log-file" in (h.stdout or "") + (h.stderr or "")
        except (OSError, subprocess.TimeoutExpired):
            _LOGFLAG[exe] = False
    return _LOGFLAG[exe]


def _run(cmd, cwd, env, timeout, stall=None, log=print):
    """agy 한 번 → (종료코드, stdout, stderr). 벽시계 timeout 을 넘기거나 기록 침묵이 stall 초를 넘으면 나무째 끄고 AgyStall.
    Ctrl-C 등으로 끊겨도 나무째 끈다 — 새 세션이라 터미널의 Ctrl-C 가 agy 에 직접 안 간다.

    ★2026-10-04 루키치70·72·76 — agy 가 네트워크 끊김 뒤 CPU 0% 로 15~25분 매달렸다. agy 기록(~/.gemini/antigravity-cli/log)
      실측 두 갈래:
      (가) 죽은 연결 읽기 — 마지막 streamGenerateContent 뒤 기록이 한 줄도 없이 17분(10:13:51 → 10:31:18 «read: connection
           reset» · 10:13:56 → 10:31:07 «operation timed out»). 운영체제 TCP 시간 초과(약 17분)까지 기다린다. agy 의
           --print-timeout 은 막힌 읽기를 못 깨고, 우리 communicate(timeout=남은 시간+60) 는 시간 제한 «끝» 에서야 끊어
           다시 물을 시간이 0 이었다(«시간 제한까지 0초라 다시 하지 않는다» — 오늘 gem.ask 실패 30여 건이 955~2176초).
           3일치 기록 1만 6902개 침묵 중 정상(다음 턴·끝으로 깨짐) 99.9% = 228초 · 최대 627초 / 오류로 깨진 침묵 69개는
           대부분 1000~1089초. 그래서 «기록 침묵 STALL_SEC(300초)» 이면 멈춘 것으로 보고 끊는다 — 다시 묻기는 부르는 쪽(한 번).
      (나) 끝맺음 멈춤 — 답을 stdout 에 다 쓰고 «CLI store manager shutting down» 뒤 언어 서버 종료가 매달려 프로세스가
           안 끝났다(10:31:53 → 10:49:33 · 3410번 중 5번 902~1060초 · 정상은 5초). communicate 는 프로세스가 끝나야 돌아온다.
           그래서 끝맺음 줄 뒤 SHUTDOWN_GRACE_SEC(30초) 지나도 살아 있으면 나무째 끄고 이미 받은 답을 쓴다.
      기록은 호출마다 따로 쓰게 --log-file 로 정한다(_agy_logfile)."""
    import threading
    stall = STALL_SEC if stall is None else stall
    lf = None
    if stall and _log_flag_ok(cmd[0]):
        lf = _agy_logfile()
        cmd = [cmd[0], "--log-file", str(lf)] + list(cmd[1:])
    extra = {} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, env=env, **extra)
    bufs = {"out": [], "err": []}
    seen = [time.time()]                 # 마지막 움직임(stdout·stderr·기록 파일이 자란 때)

    def pump(stream, key):
        for chunk in iter(lambda: stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536), b""):
            bufs[key].append(chunk)
            seen[0] = time.time()
    th = [threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True),
          threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True)]
    for t in th:
        t.start()

    def text(key):
        return b"".join(bufs[key]).decode("utf-8", "replace")

    def finish(kill):
        if kill:
            _kill_tree(proc)
        for t in th:
            t.join(15)
        if any(t.is_alive() for t in th):        # 파이프를 쥔 손주가 남았다 — 그룹째 한 번 더 끄고 파이프를 닫는다
            _kill_tree(proc)
            for st in (proc.stdout, proc.stderr):
                try:
                    st.close()
                except (OSError, AttributeError):
                    pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    t0 = time.time()
    size, shut_at = -1, None
    try:
        while True:
            if proc.poll() is not None:
                finish(False)
                return proc.returncode, text("out"), text("err")
            now = time.time()
            if lf is not None:
                try:
                    sz = lf.stat().st_size
                except OSError:
                    sz = -1
                if sz != size:
                    if sz > max(size, 0) and shut_at is None:
                        with open(lf, "rb") as f:
                            f.seek(max(0, size - 64))
                            if b"CLI store manager shutting down" in f.read():
                                shut_at = now
                    size, seen[0] = sz, now
            if shut_at is not None and now - shut_at > SHUTDOWN_GRACE_SEC:
                finish(True)
                out = text("out")
                log(f"  agy 끝맺음 멈춤 — 답을 낸 뒤 {SHUTDOWN_GRACE_SEC}초 넘게 안 끝나 나무째 끔(받은 답은 씀)")
                return (0 if out.strip() else -9), out, text("err")
            if now - t0 > timeout:
                finish(True)
                raise AgyWallTimeout(f"벽시계 한도 {timeout:.0f}초 넘음 — 나무째 끊음")
            if stall and lf is not None and shut_at is None and now - seen[0] > stall:   # 끝맺음 뒤 침묵은 위 30초가 맡는다
                finish(True)
                raise AgyStall(f"agy 가 {stall:.0f}초 동안 아무 기록·출력 없이 멈춤(죽은 연결 추정 — 기록 {lf.name}) — 나무째 끊음")
            time.sleep(1.0)
    except AgyStall:
        raise
    except BaseException:
        finish(True)
        raise


def _kind(t):
    """실패 글(오류 칸·표준오류) → (종류, 이름). 종류: stop(다시 안 함) · 503(RETRIES 번까지) · once(한 번 다시)."""
    if _FILTER.search(t):
        return "stop", "필터 차단"
    if _AUTH.search(t):
        return "stop", "인증 실패"
    if _UNAVAILABLE.search(t):
        return "503", "구글 서버 일시 장애(503)"
    if _MALFORMED.search(t):
        return "once", "Malformed function call"
    if _TRANSIENT.search(t):
        return "once", "일시 오류"
    return "stop", ""


def _malformed_ok(res, want_json, js, use_flag):
    """status=ERROR «Malformed function call» 인데 답 칸이 요청한 형식으로 온전한가(머리 주석 「Malformed」).
    글(자유 문장) 답은 끝까지 왔는지 잴 수 없어 False — JSON 을 요구했든 안 했든 답 전체가 JSON 값 하나여야 한다."""
    if use_flag:
        return res.get("structured_output") not in (None, {}, [])
    text = (res.get("response") or "").strip()
    if not text or _FILTER_RESP.search(text):
        return False
    obj = _whole_json(text)
    if obj is None:
        return False
    return not (js and _schema_errors(obj, js))


def _read(rc, out, err, n, want_json, js, use_flag):
    """agy 한 번의 결과를 가른다 → ("ok", 답 글, 표시, res) 또는 (종류, 까닭, "", res). 종류는 _kind 와 같다."""
    res = _first_json(out or "")
    if not isinstance(res, dict) or "response" not in res and "structured_output" not in res:
        res = None
    errtxt = " ".join(x for x in (err or "", str((res or {}).get("error") or "")) if x.strip())
    if res is None:
        kind, name = _kind(errtxt + " " + (out or ""))
        if kind == "stop" and not name:
            kind = "format"     # 까닭 모를 헛출력·종료코드≠0 — FORMAT_TRIES 까지 다시 묻는다(맥1 d822dd5·903a3d7)
        if rc != 0:
            return kind, f"{name + ' — ' if name else ''}종료코드 {rc}: {((out or '') + (err or '')).strip()[-200:]}", "", None
        return kind, f"{name + ' — ' if name else ''}agy 출력이 JSON 이 아니다: " + (out or "").strip()[:160], "", None
    note = ""
    status = res.get("status")
    if status not in (None, "SUCCESS"):
        if _MALFORMED.search(errtxt) and not _FILTER.search(errtxt) and _malformed_ok(res, want_json, js, use_flag):
            note = "Malformed function call(status=ERROR) — 답 칸이 온전해 받음"
        else:
            kind, name = _kind(errtxt)
            if kind == "stop" and not name:
                kind = "format"     # 까닭 모를 실패도 FORMAT_TRIES 까지 다시 묻는다(아래 rc≠0 주석 · 맥1 903a3d7)
            if kind == "once" and name == "Malformed function call":
                name += " — 답 칸이 온전하지 않다"
            return kind, f"{name + ' — ' if name else ''}agy status={status}: {str(res.get('error') or '')[:200]}", "", res
    elif rc != 0:
        kind, name = _kind(errtxt)
        if kind == "stop" and not name:
            # ★까닭 모를 종료코드≠0 도 FORMAT_TRIES 까지 다시 묻는다 (맥1 903a3d7 · 2026-09-27 100편 배치 — 동시 체인
            #   8~10개로 부하 33 일 때 싱글252·284·267 ⑦ 화자 판정이 «broken pipe»·«빈 답» 한 번에 AgyStop 으로 죽었다.
            #   FROM=7 로 다시 돌리면 다 통과했다 = 일시 실패.) 필터 차단·인증 실패는 여전히 다시 하지 않는다.
            kind = "format"
        return kind, f"{name + ' — ' if name else ''}종료코드 {rc}: {errtxt.strip()[-200:]}", "", res
    if use_flag:
        so = res.get("structured_output")
        if so in (None, {}, []):
            return "once", "구조화 답이 비었다", "", res
        return "ok", json.dumps(so, ensure_ascii=False), note, res
    text = (res.get("response") or "").strip()
    if not text:
        # agy 는 --print-timeout 에 걸려도 빈 답에 종료코드 0 을 낸다(2026-09-24 실측) — 시간이 남았으면 한 번 다시
        return "once", "빈 답 — 시간 제한에 걸렸을 가능성이 크다", "", res
    # ★유튜브 주소는 agy 가 들쭉날쭉하다 — 같은 질문에 82~244초, 가끔 «영상을 볼 수 없음»(2026-09-26 실측 5회).
    #   못 봤다는 답을 성공으로 넘기지 않는다. 단 JSON 을 요구했고 답이 유효한 JSON 이면 대지 않는다(반박 14).
    see = bool(n) and len(text) < 200 and bool(_CANNOT_SEE.search(text))
    if want_json:
        if _FILTER_RESP.search(text):
            # 필터가 답 중간을 막으면 JSON 이 잘린다 — 잘린 답의 앞쪽 조각을 답으로 받지 않는다(다시 해도 같은 자리에서 막힌다)
            return "stop", "필터 차단 — 답이 잘렸다: " + text[-120:], "", res
        obj = _first_json(text)
        # ★객체를 요구했는데 [ {…} ] 로 한 겹 싸서 낸 답은 벗겨 받는다 (2026-09-29 점심이네50·싱글116·204·269 plan —
        #   «스키마와 다르다: $ 는 object 여야 한다(list)» 로 영상 plan 을 통째로 다시 물어 한 번에 3~8분을 버렸다.
        #   내용은 온전한 답 하나였다). 원소가 둘 이상이면 어느 것이 답인지 모르니 그대로 형식 오류로 둔다.
        if js and js.get("type") == "object" and isinstance(obj, list) and len(obj) == 1 and isinstance(obj[0], dict):
            obj = obj[0]
            note = "; ".join(x for x in (note, "답이 [ {…} ] 로 한 겹 싸여 있어 벗겨 받음") if x)
        bad = ["JSON 이 없다"] if obj is None else (_schema_errors(obj, js) if js else [])
        if bad:
            if see:
                return "once", "첨부를 못 봤다고 답했다: " + text[:80], "", res
            # 답 형식 문제는 FORMAT_TRIES 까지 agy 로 다시 묻는다 — 싱글286 20:24:40 실측: 영상 작표 한 번이
            #   «JSON 을 요구했는데 답에 JSON 이 없다: ]» 로 떨어져 곧장 EvoLink 로 샜다(같은 편 다른 13건은 정상 · 맥1 d822dd5)
            if obj is None:
                return "format", "JSON 을 요구했는데 답에 JSON 이 없다: " + text[:120], "", res
            return "format", "스키마와 다르다: " + "; ".join(bad[:3]), "", res
        return "ok", json.dumps(obj, ensure_ascii=False), note, res
    if see:
        return "once", "첨부를 못 봤다고 답했다: " + text[:80], "", res
    return "ok", text, note, res


def generate(body, caller="", limit_min=DEFAULT_LIMIT_MIN, model=None, log=print):
    """agy 로 generateContent 를 흉내 낸다. 실패하면 None — 호출하는 쪽이 EvoLink 로 간다.
    ★단, 영상·소리 첨부 요청은 끝내 실패하면 None 대신 AgyStop 을 던진다 — EvoLink 금지(사장님 결정 2번 · 맥1 d822dd5).
    ★답 형식 오류는 FORMAT_TRIES 번까지 agy 로 다시 묻는다(_read 의 "format")."""
    t0 = time.time()
    model = model or os.environ.get("YOUSTUDIO_AGY_MODEL") or DEFAULT_MODEL
    media = has_media(body)

    def fail(reason):
        if media:
            _record(caller, "agy_fail_stop", time.time() - t0, "영상·소리 판정 — EvoLink 로 안 넘김(멈춤) — " + reason, model)
            log(f"  agy 실패({reason[:160]}) — 영상·소리 판정이라 EvoLink 로 넘기지 않고 멈춘다")
            raise AgyStop(f"agy 실패 · 영상·소리 판정 — EvoLink 금지(사장님 결정 2번)라 멈춤: {reason[:200]}"
                          f" · 부른 곳 {caller}. agy 로그인·사용량(agy_call.py --usage)을 보고 다시 돌린다.")
        log(f"  agy 실패({reason[:160]}) → 다음 길은 judge_run 규칙이 정한다(2026-10-05 부터 글 판정도 멈춤)")
        _record(caller, "fallback", time.time() - t0, reason, model)
        return None

    if os.environ.get("YOUSTUDIO_GEMINI_ROUTE", "").strip().lower() == "evolink":
        _record(caller, "fallback", 0, "YOUSTUDIO_GEMINI_ROUTE=evolink (agy 꺼 둠)", model)
        return None
    exe = _agy_exe()
    if not exe:
        return fail("agy 가 설치돼 있지 않다 — " + _agy_find()[1])

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
        # --print-timeout 은 시도마다 남은 시간으로 붙인다(아래 「다시」 고리)
        cmd = [exe, "--dangerously-skip-permissions", "--disable-slash-commands", "--model", model,
               "--output-format", "json"]
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
        tail = ["-p", prompt]

        # 다시 고리 (머리 주석 「다시」) — 시간 제한은 첫 시도부터 모든 시도를 합쳐 limit_min 이다
        env = _agy_env()
        deadline = time.time() + limit_min * 60
        n503 = nonce = nfmt = 0
        지난 = []           # 버린 시도의 까닭 — 실패·표시 글에 붙인다
        while True:
            # 동시 16 문(머리 주석) — 빈자리를 기다린 시간은 시간 제한에 넣지 않는다(기다리다 시간이 다 가지 않게)
            with _agy_slot(log) as slot:
                deadline += slot.waited
                left = deadline - time.time()
                try:
                    rc, out, err = _run(cmd + ["--print-timeout", f"{max(1, int(left))}s"] + tail, work, env,
                                        max(1.0, left) + KILL_GRACE_SEC, log=log)
                except AgyWallTimeout:
                    return fail(f"{limit_min:g}분 시간 제한" + (f" (앞 시도: {' / '.join(지난)})" if 지난 else ""))
                except AgyStall as e:
                    # ★2026-10-04 — 죽은 연결로 멈춘 시도는 _run 이 STALL_SEC 만에 끊는다. 일시 오류(«once»)로 갈라
                    #   남은 시간 안에서 한 번 다시 묻는다(_TRANSIENT 의 «멈춤(죽은 연결»).
                    log(f"  {e}")
                    rc, out, err = -9, "", str(e)
            got = _read(rc, out, err, n, want_json, js, use_flag)
            if got[0] == "ok":
                break
            kind, reason = got[0], got[1]
            if media and 출력한도(reason):
                # ★출력 한도 초과는 되묻지 않는다 — AgyOutputLimit 참고(2026-09-28 싱글126 · 맥1 b99942d)
                _record(caller, "stop", time.time() - t0, reason, model)
                log(f"  agy 답이 출력 한도를 넘어 잘렸다 — 같은 질문을 되풀이하지 않는다({caller})")
                raise AgyOutputLimit(f"agy 출력 토큰 한도 초과 · 부른 곳 {caller}: {reason[:160]}")
            지난.append(reason[:100])
            # 다시 묻기 간격은 3D쇼츠 팩과 같은 4초·8초(RETRY_GAP_SEC) — 기다리는 동안 문은 비운다(팩과 같다)
            if kind == "503" and n503 + nonce < RETRIES - 1:
                n503 += 1
                wait = RETRY_GAP_SEC * n503
            elif kind == "once" and nonce < ONCE and n503 + nonce < RETRIES - 1:
                nonce += 1
                wait = RETRY_GAP_SEC
            elif kind == "format" and nfmt < FORMAT_TRIES - 1:
                nfmt += 1
                wait = RETRY_GAP_SEC * nfmt
            else:
                if kind == "503":
                    return fail("구글 서버 일시 장애(503) 반복 — " + " / ".join(지난))
                return fail(reason if len(지난) == 1 else f"{reason} (시도 {len(지난)}번: {' / '.join(지난[:-1])})")
            left = deadline - time.time() - wait
            if left < MIN_RETRY_SEC:
                return fail(f"{reason} — 시간 제한까지 {max(0, left):.0f}초라 다시 하지 않는다")
            log(f"  agy {reason[:100]} — {wait}초 뒤 다시 (503·일시 {n503 + nonce}/{RETRIES - 1} · 형식 {nfmt}/{FORMAT_TRIES - 1})")
            time.sleep(wait)

        _, text, note, res = got
        if 지난:
            note = "; ".join(x for x in (note, f"다시 {len(지난)}번 뒤 받음 — " + " / ".join(지난)) if x)
        u = res.get("usage") or {}
        sec = time.time() - t0
        log(f"  (agy · {model} · 첨부 {n} · {sec:.0f}초{' · ' + note[:80] if note else ''})")
        _record(caller, "agy", sec, note, model)
        resp = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]},
                                "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": u.get("input_tokens"),
                                  "candidatesTokenCount": u.get("output_tokens"),
                                  "totalTokenCount": u.get("total_tokens")},
                "modelVersion": f"agy/{model}", "route": "agy"}
        if note:
            resp["agy_note"] = note     # route 는 그대로 agy — 부르는 쪽(파악전사)이 route·modelVersion 으로 가른다
        return resp
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
    try:
        resp = generate(body, caller=a.caller, limit_min=a.limit, log=lambda m: print(m, file=sys.stderr))
    except AgyStop as e:
        print(f"★멈춤 — {e}", file=sys.stderr)
        sys.exit(3)                                  # 3 = 멈춤(영상·소리 판정 · EvoLink 금지) — agy_gemini.mjs 도 멈춘다
    if resp is None:
        sys.exit(1)                                  # 1 = 글 판정 실패 — 부른 쪽이 EvoLink 비상 길로
    Path(a.out).write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
