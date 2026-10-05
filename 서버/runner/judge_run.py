# -*- coding: utf-8 -*-
"""서버/runner/judge_run.py — 서버 judge 일감 한 개를 **사장님 규칙대로** 처리하는 문 하나 (2026-09-26).

  python 서버/runner/judge_run.py --job <일감.json> [--out <응답.json>] [--limit 분]      (맥은 python3)

  왜: 서버가 원시 request(EvoLink 주소·키 자리)를 세션에 넘기고 «그대로 보내라» 고만 하면, 받는 쪽(세션·실행기)
      마다 규칙이 빠진다 — 영화롱폼 judge 4종이 agy 를 건너뛰고 EvoLink 로 곧장 가게 짜여 있었다
      (볼트 제안/스크립트/제미나이점검_20260926 점검_계획 표 ② · 클래스 3). 규칙을 받는 쪽마다 걸면 새 길이
      또 우회하므로(2026-09-03 «14자 규칙을 복원 경로가 우회») judge 는 전부 이 파일 하나를 지난다.

  순서
    ① 일감 검사 — provider 가 google 이거나, 주소가 generativelanguage.googleapis.com 이거나, 키 자리가
       GEMINI_API_KEY·GOOGLE_API_KEY 면 **거절**(종료 2). 순정 구글 키 길은 막는다 — 키 파일은 지우지 않고
       코드에서 안 쓴다(사장님 결정 ④ 2026-09-26).
    ② inputs 치환 — 파일 내용을 바디의 자리표에 문자열로 넣는다(전사 본문은 파일→요청으로만 흐른다).
    ②' 모양 검사 — **아는 모양만** 받는다(아래 「아는 모양만」). 모르는 모양이면 agy 에도 EvoLink 에도 안 보이고 멈춤(종료 3).
    ③ agy(구독) 먼저 — agy_gemini.generate. 답이 오면 그것이 결과다.
    ④ agy 가 답을 못 주면
       · 본문이 «글만» 이 아니면 **멈춤**(종료 3) — «글만» = 아는 모양 + 조각이 전부 text 하나짜리 + 주소가 …:generateContent.
         글이 아닌 조각(영상·소리·그림·주소 — inline_data · file_data · @inline_file · @file_uri)이 하나라도 있으면
         EvoLink 로 넘기지 않는다 — 사장님 결정 ② «영상·소리가 들어가는 판정은 agy 가 실패하면 멈추고 여쭙기 ·
         짧은 글만 보내는 판정만 EvoLink 비상 길». 그림(프레임)도 «글만» 이 아니다.
       · agy 를 아예 못 쓰면(설치 안 됨·AGY_EXE 가 없는 파일·실행 권한 없음·띄우다 OSError) 글만이어도 **멈춤**(종료 3) — 일시 실패가 아니라
         설치 문제라 그대로 두면 모든 호출이 유료로 샌다(사장님 결정 ③ · 반박 9). 설치·로그인이 먼저다.
       · ★글만이어도 **멈춤**(종료 3) — 2026-10-05 사장님 «글판정도 에보링크 사용하지 않도록 막아 … 못하는경우가 있다? 그러면
         나한테 물어봐». 사장님이 그 자리에서 허락하신 때만 YOUSTUDIO_EVOLINK_APPROVED=1 을 붙여 다시 돌리면 아래 비상 길로 간다.
       · (허락받은 때) 글만이면 일감의 request 로 EvoLink 비상 길 **한 번**(재시도 없음 — 기록 한 줄 = 보낸 요청 한 건).
         키: 환경변수 EVOLINK_API_KEY → (윈도우) 사용자 환경변수 → ~/.volcano/keys/evolink. 없으면 멈춤(종료 3).
         주소는 api.evolink.ai 만(시험용 가짜 서버 127.0.0.1·localhost 허용). 다른 주소면 종료 2.
         보내기 **직전에** «글만» 을 한 번 더 잰다(본문·주소) — 마지막 관문. 어긋나면 안 보내고 종료 3.

  아는 모양만 (2026-09-26 검증 FAIL 뒤 — 땜질 금지 원칙 2)
    처음엔 «글만» 을 미디어 칸 이름을 **찾아서**(검출) 정했다. 그러자 모르는 모양은 전부 «글만» 으로 지나갔다 —
    OpenAI chat/completions 본문의 image_url(그림 8KB), cachedContent(구글에 올려 둔 영상을 가리킴)가 가짜 EvoLink
    서버로 나갔다(검증 재현). 검출은 새 모양이 올 때마다 뚫린다(2026-09-03 «검출로 유무를 판정하는 구조 자체가
    새 스타일마다 뚫림»). 그래서 **허용 목록**으로 바꿨다:
      · 본문 칸은 contents · systemInstruction(system_instruction) · generationConfig(generation_config) 만
      · contents·systemInstruction 의 항목은 {role(user·model), parts} 만 · parts 는 비지 않은 목록
      · 조각은 **칸 하나짜리** 객체 — text(글) 또는 inline_data·inlineData·file_data·fileData·@inline_file·@file_uri
      · 비상 길 주소는 경로가 :generateContent 로 끝나야 한다
    모르는 모양은 agy 에도 안 보인다 — agy_gemini._build 는 모르는 본문 칸을 조용히 버리고, text 가 든 조각은
    나머지 칸(그림)을 버린 채 글만 읽는다. 그림을 안 보고 한 답이 «agy 성공» 으로 돌아오게 두지 않는다.
    새 생산자가 새 모양을 쓰려면 여기 목록에 **사람이 더한다** — 그 전에는 멈춘다.
    ⑤ 결과는 generateContent 응답 모양으로 --out(없으면 일감의 out)에 쓴다. 실패한 EvoLink 응답은 out 에
       쓰지 않고 <out>.실패.json 에 남긴다 — measure 가 실패 응답을 답으로 읽지 않게.

  종료코드  0 답 받음 · 2 일감이 잘못됐거나 막힌 길(순정) · 3 멈춤(사람에게 여쭙기) · 4 EvoLink 비상 길도 실패(HTTP 오류·잘림)

  기록  ~/.volcano/logs/gemini_route.jsonl — agy_gemini 규약 그대로 한 줄 {t, caller, route, sec, model, reason}
        route  agy            agy 가 답함 (agy_gemini 가 적는다)
               fallback       EvoLink 로 **보낸** 요청 1건 = 돈이 나갈 수 있는 건 (재시도 없음 — 줄 수 = 보낸 수)
               agy_fail_stop  agy 가 못 줬고 EvoLink 로 안 보내고 멈춤 (파악전사.py 와 같은 이름)
               blocked        막힌 길 거절 — 순정 구글 길 · 모르는 본문 모양(agy 에도 안 보냄) · 돈 0
        ★agy_gemini.generate 는 실패를 스스로 «fallback» 으로 적는다. 멈춘 호출까지 «돈 나간 횟수» 에 섞이지 않게
          (반박 19) 그 줄을 맡아 두었다가 실제로 간 길로 적는다 — _record 감싸기. agy_gemini.py 는 고치지 않는다.

  PATH 빈틈 (반박 9·20)
    · 맥은 agy_gemini 가 shutil.which 로만 agy 를 찾는다. agy 를 설치하기 전에 켠 셸·세션·LaunchAgent 는 PATH 에
      ~/.local/bin(공식 설치 자리)이 없어 «agy 없음» 이 된다 → import 전에 그 자리를 PATH 앞에 넣는다.
      AGY_EXE 환경변수가 있으면 그 파일의 폴더를 앞에 넣는다(없는 파일이면 «agy 없음» 으로 멈춘다).
    · ffmpeg 도 이름으로 부른다. PATH 에 없으면 agy_gemini 가 영상의 소리를 **조용히 빼고** 그림만 보낸다 —
      흔한 설치 자리(/opt/homebrew/bin · /usr/local/bin · 윈도우 WinGet·C:\\ffmpeg\\bin 등)를 PATH 뒤에 보태고,
      그래도 없으면 영상 판정은 멈춘다(소리 없이 본 답을 «agy 성공» 으로 받지 않는다). 이 검사는 agy_먼저 안에
      있다 — gem.py·분석 판독 3종처럼 agy_먼저 를 곧장 부르는 쪽도 같은 관문을 지난다.
      «영상» 은 agy_gemini 와 같은 잣대로 잰다 — mime 이 video/* 이거나 **파일 확장자**가 .mp4·.mov·.webm·.mkv.
      agy_gemini 는 확장자만 보고도 ffmpeg 로 소리를 뽑으려 든다. mime 만 보던 때는 mime 이 application/octet-stream
      인 .mp4 가 관문을 비켜 가 소리 없이 agy 로 갔다(재검증 2026-09-26).

  generate 의 예외 (재검증 2026-09-26 — 반박 18 의 연장)
    agy_gemini.generate 는 실패를 None 으로 돌려주지만 **예외도 던진다** — Popen 의 PermissionError(실행 권한 없음)·
    FileNotFoundError·OSError(실행 파일 아님), base64 오류, KeyError(자리표에 path 없음), agy 답 모양이 바뀐 AttributeError.
    try/finally 로만 감쌌을 때는 예외가 그대로 빠져나가 비상길_검사·판정멈춤·route 기록을 건너뛰었고, 호출처
    (준비_prproj_sk 댓글선별·화자판정·댓글보충)의 `except Exception` 이 삼켜 «앞 12장 사용»·빈 화자로 계속 갔다
    (재현: AGY_EXE 를 실행 권한 없는 파일로 — rc 1·route 0줄·호출처는 조용히 계속).
    그래서 agy_먼저 는 generate 의 **모든 예외**(Exception)를 «agy 실패» 로 돌린다(까닭 = 예외 이름과 글) — 그 뒤는
    None 과 똑같이 비상길_검사를 지난다. KeyboardInterrupt 같은 BaseException 은 그대로 올린다(사람이 끈 것).
    · OSError(띄우기·임시 폴더 실패)는 **이 컴퓨터에서 agy 를 못 돌리는 것** — 일시 실패가 아니라 설치·권한 문제라
      글만이어도 멈춘다(결정 ③). 한 번 못 띄운 agy 는 이 프로세스 안에서 다시 안 부른다(agy_문제).
    · 실행 권한 없는 파일은 부르기 전에 가린다(agy_문제 — os.access). 예외 길은 그래도 남겨 둔다(ENOEXEC 등).

  agy 자식의 환경 (부가 · 결정 ④)
    agy_gemini 가 띄우는 자식(agy·ffmpeg)에는 GEMINI_API_KEY·GOOGLE_API_KEY 를 **빼고** 넘긴다 — 한편.py 가 keys 폴더를
    모든 자식에게 넘기므로(반박 17) agy 가 구독 대신 순정 키로 붙을 틈을 닫는다. 이 프로세스의 os.environ 은 안 건드린다.
    agy_gemini.py 는 안 고치고 그 모듈이 쓰는 subprocess 만 이 프로세스 안에서 감싼다(_자식은_순정키없이).

  다른 파이썬에서 쓰기 (스케치 s2pipe/gem.py · 분석 판독 3종 — 규칙을 여기 한 곳에 둔다):
      import judge_run
      resp, 까닭 = judge_run.agy_먼저(body, caller, limit_min, log)   # 모르는 모양·ffmpeg 없는 영상은 여기서 판정멈춤
      if resp is None:
          judge_run.비상길_검사(body, caller, 까닭, log)   # 멈출 자리면 판정멈춤(SystemExit 3) 을 던진다
          ... 글만일 때만 여기 온다 — EvoLink 로 보낼 때마다 judge_run.기록(caller, "fallback", …) ...
    판정멈춤 은 SystemExit 이라 호출처의 넓은 `except Exception` 에 안 잡힌다(반박 18 — 삼키면 기본값으로 계속 간다).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = os.name == "nt"


# ── PATH 빈틈 막기 (머리 주석 「PATH 빈틈」) — agy_gemini 를 import 하기 전에 ──
def _길_보태기():
    sep = os.pathsep
    parts = [p for p in os.environ.get("PATH", "").split(sep) if p]
    앞, 뒤 = [], []
    agy_exe = os.environ.get("AGY_EXE", "").strip()
    if agy_exe:
        if os.path.isfile(agy_exe):
            앞.append(os.path.dirname(os.path.abspath(agy_exe)))
    elif not IS_WIN:
        앞.append(os.path.join(os.path.expanduser("~"), ".local", "bin"))
    if shutil.which("ffmpeg", path=sep.join(앞 + parts)) is None:
        if IS_WIN:
            후보 = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"),
                  r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin",
                  os.path.join(os.environ.get("USERPROFILE", ""), "scoop", "shims"), r"C:\ProgramData\chocolatey\bin"]
        else:
            후보 = ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/usr/bin"]
        for d in 후보:
            if os.path.isfile(os.path.join(d, "ffmpeg.exe" if IS_WIN else "ffmpeg")):
                뒤.append(d)
                break
    새 = [d for d in 앞 if os.path.isdir(d) and d not in parts] + parts + [d for d in 뒤 if d not in parts]
    os.environ["PATH"] = sep.join(새)


_길_보태기()
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import agy_gemini  # noqa: E402  같은 폴더의 agy_gemini.py — 고치지 않는다 (다른 작업이 쓰는 중)

EVOLINK_HOSTS = ("api.evolink.ai",)
시험_HOSTS = ("127.0.0.1", "localhost", "::1")              # 시험용 가짜 서버 — 돈이 안 나간다
순정_HOSTS = ("generativelanguage.googleapis.com",)
순정_키 = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
# 아는 모양 (머리 주석 「아는 모양만」) — 허용 목록. 여기 없는 칸은 전부 «모르는 모양» 이다.
본문_칸 = ("contents", "systemInstruction", "system_instruction", "generationConfig", "generation_config")
내용_칸 = ("role", "parts")
역할_칸 = ("user", "model")
글_칸 = "text"
미디어_칸 = ("inline_data", "inlineData", "file_data", "fileData", "@inline_file", "@file_uri")
비상길_주소_끝 = ":generateContent"
UA = "youstudio-mcp/judge_run"   # UA 가 없으면(Python-urllib) EvoLink 가 403 code 1010 — 분석_판독 2026-08-18 실측
사용량_확인 = "python ~/.claude/agy_call.py --usage"
규칙_날짜 = "사장님 규칙 2026-09-26"
승인_날짜 = "사장님 규칙 2026-10-05"
승인_변수 = "YOUSTUDIO_EVOLINK_APPROVED"   # 사장님이 그 자리에서 «이번엔 EvoLink 써» 하신 때만 1 (비상길_검사)


class 판정멈춤(SystemExit):
    """멈춤 — 사람에게 여쭐 자리. SystemExit 이라 `except Exception` 에 안 잡힌다(반박 18). 잡히지 않으면 종료코드 3."""

    def __init__(self, 글):
        super().__init__(3)
        self.글 = 글

    def __str__(self):
        return self.글


# ── 기록 (머리 주석 「기록」) ──
_원래기록 = agy_gemini._record
_보류 = threading.local()


def _기록_감싸기(caller, route, sec, reason="", model=""):
    box = getattr(_보류, "box", None)
    if box is not None and route == "fallback":
        box.update(caller=caller, sec=sec, reason=reason or "", model=model or "")   # 아직 안 적는다 — 길이 정해진 뒤 적는다
        return
    _원래기록(caller, route, sec, reason, model)


agy_gemini._record = _기록_감싸기


def 기록(caller, route, sec, reason="", model=""):
    """gemini_route.jsonl 에 한 줄 (agy_gemini 규약). route = agy · fallback · agy_fail_stop · blocked."""
    _원래기록(caller, route, sec, reason, model)


_원래찾기 = agy_gemini._agy_exe
_못띄운 = {}   # agy 자리 → 까닭. 이 프로세스에서 generate 가 OSError 를 낸 agy(머리 주석 「generate 의 예외」)


def _agy_자리():
    exe = os.environ.get("AGY_EXE", "").strip()
    return exe if exe else _원래찾기()


def agy_문제():
    """agy 를 이 컴퓨터에서 쓸 수 없는 까닭(설치·권한 문제), 쓸 수 있으면 "". 일시 실패(503·시간 제한·빈 답)는 여기 안 든다."""
    exe = _agy_자리()
    if not exe:
        return "agy 가 설치돼 있지 않다(찾는 자리: AGY_EXE · ~/.local/bin · PATH · %LOCALAPPDATA%\\agy)"
    if not os.path.isfile(exe):
        return f"AGY_EXE 가 가리키는 파일이 없다({exe})"
    if not IS_WIN and not os.access(exe, os.X_OK):
        return f"agy 파일에 실행 권한이 없다({exe} — chmod +x)"
    if exe in _못띄운:
        return f"agy 를 띄우지 못했다({_못띄운[exe][:200]})"
    return ""


def agy_있나():
    """agy 실행 파일 자리, 쓸 수 없으면 None(agy_문제). AGY_EXE 가 있으면 그것만 본다 — 점검_계획 클래스 1 의
    찾는 순서(AGY_EXE → %LOCALAPPDATA% → ~/.local/bin → PATH). generate 도 이 함수로 찾게 한다(아래) — 미리 본 것과
    실제로 부르는 것이 갈리지 않게. 이 프로세스 안에서만 바꾸고 agy_gemini.py 파일은 안 고친다."""
    return None if agy_문제() else _agy_자리()


agy_gemini._agy_exe = agy_있나


# ── agy 자식 환경 (머리 주석 「agy 자식의 환경」) ──
class _자식은_순정키없이:
    """agy_gemini 모듈이 쓰는 subprocess 자리에 끼운다. Popen·run 에 순정 키를 뺀 env 를 주고, 나머지(PIPE·DEVNULL·
    TimeoutExpired …)는 진짜 subprocess 를 그대로 보인다."""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def _env(kw):
        base = os.environ if kw.get("env") is None else kw["env"]
        kw["env"] = {k: v for k, v in base.items() if k.upper() not in 순정_키}
        return kw

    def Popen(self, *a, **kw):
        return subprocess.Popen(*a, **self._env(kw))

    def run(self, *a, **kw):
        return subprocess.run(*a, **self._env(kw))


_지금 = getattr(agy_gemini, "subprocess", None)
if type(_지금).__name__ == _자식은_순정키없이.__name__:
    pass   # 이미 감쌌다 — judge_run 을 한 프로세스에서 두 번 불러온 경우(__main__ 과 import)
elif _지금 is not subprocess or hasattr(agy_gemini, "Popen"):
    # agy_gemini 가 subprocess 를 다르게 부르게 바뀌면 이 감싸기가 조용히 헛돈다 — 여기서 멈춰 사람이 보게 한다
    raise ImportError("judge_run: agy_gemini 가 자식을 띄우는 방식이 바뀌었다(subprocess 모듈 속성이 아님) — "
                      "순정 키 빼기(_자식은_순정키없이)를 새 방식에 맞게 고쳐라")
else:
    agy_gemini.subprocess = _자식은_순정키없이()


def agy_꺼둠():
    return os.environ.get("YOUSTUDIO_GEMINI_ROUTE", "").strip().lower() == "evolink"


def 본문_모양(body):
    """허용 목록(머리 주석 「아는 모양만」)으로 본문을 잰다. 돌려주는 것: (모르는 모양 목록, 글 아닌 조각 [(칸, mime)]).
    모르는 모양이 하나라도 있으면 이 문은 그 본문을 다루지 않는다 — «글만» 도 아니고 agy 에도 안 보인다."""
    모름, 조각 = [], []
    if not isinstance(body, dict):
        return [f"본문이 객체가 아니다({type(body).__name__})"], 조각
    for k in body:
        if k not in 본문_칸:
            모름.append(f"모르는 본문 칸 {k}")
    contents = body.get("contents")
    if not isinstance(contents, list) or not contents:
        모름.append("contents 가 비었거나 목록이 아니다")
        contents = []
    blocks = [(f"contents[{i}]", c) for i, c in enumerate(contents)]
    blocks += [(k, body[k]) for k in ("systemInstruction", "system_instruction") if k in body]
    for where, c in blocks:
        if not isinstance(c, dict):
            모름.append(f"{where} 가 객체가 아니다")
            continue
        모름 += [f"{where} 의 모르는 칸 {k}" for k in c if k not in 내용_칸]
        if "role" in c and c["role"] not in 역할_칸:
            모름.append(f"{where} 의 모르는 role {c['role']!r}")
        parts = c.get("parts")
        if not isinstance(parts, list) or not parts:
            모름.append(f"{where}.parts 가 비었거나 목록이 아니다")
            continue
        for j, p in enumerate(parts):
            here = f"{where}.parts[{j}]"
            if not isinstance(p, dict) or len(p) != 1:
                # 칸 둘 이상({text, inline_data} · {text, image_url})이면 agy_gemini 는 text 만 읽고 나머지를 버린다
                모름.append(f"{here} 는 칸 하나짜리 조각이 아니다({'+'.join(map(str, p)) if isinstance(p, dict) else type(p).__name__})")
                continue
            (k, v), = p.items()
            if k == 글_칸:
                if not isinstance(v, str):
                    모름.append(f"{here}.text 가 글이 아니다({type(v).__name__})")
            elif k in 미디어_칸:
                if not isinstance(v, dict):
                    모름.append(f"{here}.{k} 가 객체가 아니다")
                    continue
                mime = v.get("mime_type") or v.get("mimeType") or v.get("mime") or ""
                if not mime and v.get("path"):
                    ext = Path(str(v["path"])).suffix.lower()
                    mime = next((m for m, e in agy_gemini.EXT.items() if e == ext), ext)
                조각.append((k, str(mime)))
            else:
                모름.append(f"{here} 의 모르는 조각 칸 {k}")
    for k in ("generationConfig", "generation_config"):
        if k in body and not isinstance(body[k], dict):
            모름.append(f"{k} 가 객체가 아니다")
    return 모름, 조각


def 글_아닌_조각(body):
    """본문에서 글(text)이 아닌 조각 목록 — [(칸, mime)]. 모양이 맞는지는 본문_모양 이 따로 본다."""
    return 본문_모양(body)[1]


def 주소_문제(url):
    """비상 길 주소의 경로가 …:generateContent 로 끝나지 않으면 그 까닭, 맞으면 ""."""
    try:
        path = urllib.parse.urlsplit(url or "").path
    except ValueError:
        path = ""
    return "" if path.endswith(비상길_주소_끝) else f"비상 길 주소가 …{비상길_주소_끝} 가 아니다({(path or url or '없음')[-80:]})"


def 글만_아닌_까닭(body, url=None):
    """«글만» 이 아닌 까닭 목록 — 비었으면 글만. 아는 모양 + 조각이 전부 text + (주소를 주면) …:generateContent."""
    모름, 조각 = 본문_모양(body)
    까닭 = list(모름)
    if 조각:
        까닭.append(f"글 아닌 조각 {len(조각)}개: {', '.join(sorted({m or k for k, m in 조각}))[:200]}")
    if url is not None and 주소_문제(url):
        까닭.append(주소_문제(url))
    return 까닭


def 모양_검사(body, caller, log=print, model=""):
    """아는 모양이 아니면 기록하고 판정멈춤 — agy 에도 EvoLink 에도 안 보인다(머리 주석 「아는 모양만」)."""
    모름 = 본문_모양(body)[0]
    if not 모름:
        return
    글 = (f"본문이 아는 모양이 아니다 — agy 에도 EvoLink 에도 보내지 않고 멈춘다({규칙_날짜} · judge_run 허용 목록).\n"
         f"  까닭: {' · '.join(모름[:5])[:400]}{' …' if len(모름) > 5 else ''}\n"
         f"  아는 모양: contents[{{role, parts}}] · systemInstruction · generationConfig · 조각은 칸 하나"
         f"(text · inline_data · file_data · @inline_file · @file_uri). 새 모양은 사람이 judge_run.py 목록에 더한다.")
    기록(caller, "blocked", 0, "모르는 본문 모양 — agy·EvoLink 안 보냄(멈춤) — " + " · ".join(모름[:3]), model)
    log("★" + 글)
    raise 판정멈춤(글)


_영상_확장자 = (".mp4", ".mov", ".webm", ".mkv")   # agy_gemini._build 의 local() 이 소리를 따로 뽑는 확장자와 같게


def _로컬영상_조각(body):
    """agy_gemini 가 ffmpeg 로 소리를 따로 뽑으려 드는 조각 목록 — mime 이 video/* 이거나 **파일 확장자**가 영상인 것
    (머리 주석 「PATH 빈틈」). 주소(file_data)는 agy 가 직접 보므로 뺀다. 대문자 mime 도 영상으로 친다(더 엄하게)."""
    out = []
    blocks = list(body.get("contents") or []) + [body.get(k) for k in ("systemInstruction", "system_instruction")]
    for c in blocks:
        if not isinstance(c, dict):
            continue
        for p in c.get("parts") or []:
            if not isinstance(p, dict):
                continue
            for k, v in p.items():
                if k not in 미디어_칸 or k in ("file_data", "fileData") or not isinstance(v, dict):
                    continue
                mimes = [str(v.get(x) or "").lower() for x in ("mime_type", "mimeType", "mime")]
                path = str(v.get("path") or "")
                if any(m.startswith("video/") for m in mimes) or Path(path).suffix.lower() in _영상_확장자:
                    out.append(f"{k} {path or '/'.join(m for m in mimes if m)}")
    return out


def agy_먼저(body, caller, limit_min=agy_gemini.DEFAULT_LIMIT_MIN, log=print, model=None):
    """agy 로 한 번. 돌려주는 것: (generateContent 응답 또는 None, agy 가 못 준 까닭).
    실패 줄은 여기서 안 적는다 — 부른 쪽이 길을 정한 뒤 적는다(비상길_검사 · 기록).
    멈추는 관문 둘은 여기 있다(판정멈춤) — agy_먼저 를 곧장 부르는 gem.py·분석 판독 3종도 같이 지난다:
      · 모르는 본문 모양 (머리 주석 「아는 모양만」)
      · 로컬 영상인데 ffmpeg 없음 (머리 주석 「PATH 빈틈」 — 소리 없이 본 답을 받지 않는다)"""
    def 로그(m):
        log(str(m).replace("→ EvoLink 로 넘어간다", "→ 다음 길은 judge_run 규칙이 정한다"))

    모양_검사(body, caller, log)
    문제 = "" if agy_꺼둠() else agy_문제()
    if 문제:
        return None, 문제          # 설치·권한 문제 — 비상길_검사가 글만이어도 멈춘다(결정 ③)
    영상 = [] if agy_꺼둠() else _로컬영상_조각(body)
    if 영상 and not shutil.which("ffmpeg"):
        글 = ("ffmpeg 를 못 찾는다 — agy 에 영상의 소리를 못 넣는다(그림만 보고 답한다). 소리 없이 본 판정은 받지 않고 멈춘다.\n"
             f"  영상 조각: {', '.join(영상[:3])[:200]}\n"
             "  ffmpeg 를 PATH 에 두고 다시 하라(맥 /opt/homebrew/bin · 윈도우 winget install ffmpeg).")
        기록(caller, "agy_fail_stop", 0, "ffmpeg 없음 — 영상 소리 못 넣음(멈춤)", model or "")
        log("★" + 글)
        raise 판정멈춤(글)
    _보류.box = {}
    예외 = ""
    try:
        resp = agy_gemini.generate(body, caller=caller, limit_min=limit_min, model=model, log=로그)
    except agy_gemini.AgyStop as e:
        # 영상·소리 판정이 agy 로 끝내 안 됨(2026-09-27 맥1 d822dd5 합침) — agy_gemini 가 agy_fail_stop 으로 이미 적었다.
        #   BaseException 이라 아래 except Exception 에 안 잡힌다 — 여기서 판정멈춤(종료코드 3)으로 바꿔 올린다.
        글 = f"{e}\n  확인: {사용량_확인}  (남은 양이 찍히는가 · 로그인 상태)"
        log("★" + 글)
        raise 판정멈춤(글)
    except Exception as e:    # 모든 예외 → «agy 실패»(머리 주석 「generate 의 예외」). BaseException(사람이 끔)은 그대로 올린다
        이름 = type(e).__qualname__ if type(e).__module__ == "builtins" else f"{type(e).__module__}.{type(e).__qualname__}"
        resp, 예외 = None, f"{이름}: {e}"
        if isinstance(e, OSError):
            _못띄운[_agy_자리() or ""] = 예외     # 이 컴퓨터에서 agy 를 못 돌린다 — 이 뒤로 agy_문제 가 설치 문제로 본다
    finally:
        box, _보류.box = _보류.box, None
    if resp is not None:
        return resp, ""
    if 예외:
        까닭 = f"agy 호출 중 예외 {예외[:240]}"
        if agy_문제():
            까닭 += " — 이 컴퓨터에서 agy 를 띄우지 못함(설치·권한 문제)"
        로그(f"  agy 실패({까닭[:200]}) → 다음 길은 judge_run 규칙이 정한다")
        return None, 까닭
    return None, box.get("reason") or "agy 실패(까닭 모름)"


def 비상길_검사(body, caller, 까닭, log=print, sec=0.0, model="", url=None):
    """agy 가 답을 못 준 뒤 — EvoLink 비상 길로 가도 되는지. «글만»(허용 목록 — 머리 주석 「아는 모양만」)이 아니면
    기록하고 판정멈춤 을 던진다. url 을 주면 경로가 …:generateContent 인지도 본다.
    글만이어도 2026-10-05 부터 멈춘다 — YOUSTUDIO_EVOLINK_APPROVED=1(사장님이 그 자리에서 허락)일 때만 돌아오고,
    그때 부른 쪽이 EvoLink 로 보낸다 — 보낼 때마다 기록(caller, "fallback", …)."""
    모름, 조각 = 본문_모양(body)
    if 조각:
        종류 = sorted({m or k for k, m in 조각})
        글 = (f"agy 실패 — 영상·소리·그림 판정은 EvoLink 로 넘기지 않음({규칙_날짜}). 멈추고 사장님께 여쭙는다.\n"
             f"  agy 가 못 준 까닭: {까닭}\n  본문의 글 아닌 조각 {len(조각)}개: {', '.join(종류)[:200]}\n"
             f"  확인: {사용량_확인}  (남은 양이 찍히는가 · 로그인 상태)")
        기록(caller, "agy_fail_stop", sec, "영상·소리·그림 판정은 EvoLink 로 안 넘김(멈춤) — " + 까닭, model)
        log(글)
        raise 판정멈춤(글)
    어긋남 = 모름 + ([주소_문제(url)] if url is not None and 주소_문제(url) else [])
    if 어긋남:
        글 = (f"agy 실패 — 본문·주소가 «글만»(글 조각만 든 …{비상길_주소_끝})이 아니라 EvoLink 로 넘기지 않음({규칙_날짜}). "
             f"멈추고 사장님께 여쭙는다.\n  agy 가 못 준 까닭: {까닭}\n  어긋난 것: {' · '.join(어긋남[:5])[:400]}\n"
             f"  확인: {사용량_확인}")
        기록(caller, "agy_fail_stop", sec, "글만 아님(모르는 모양·주소) — EvoLink 로 안 넘김(멈춤) — " + " · ".join(어긋남[:3]), model)
        log(글)
        raise 판정멈춤(글)
    문제 = "" if agy_꺼둠() else agy_문제()
    if 문제:
        글 = (f"agy 를 이 컴퓨터에서 쓸 수 없다 — 일시 실패가 아니라 설치 문제라 EvoLink 로 넘기지 않는다({규칙_날짜} 결정 ③).\n"
             f"  까닭: {문제}\n  설치·로그인이 먼저다(볼트 설치/). 확인: {사용량_확인}")
        기록(caller, "agy_fail_stop", sec, f"agy 못 씀(설치 문제: {문제[:140]}) — EvoLink 로 안 넘김(멈춤)", model)
        log(글)
        raise 판정멈춤(글)
    # 글만이어도 EvoLink 로 안 간다 — 멈추고 사장님께 여쭙는다 (2026-10-05 사장님 «글판정도 에보링크 사용하지 않도록 막아.
    #   근데 제미나이가 절대로 못하는경우가 있다? 그러면 나한테 물어봐. 그때 내가 판단해줄께»).
    #   사건: 10-04 19:07 스케치코미디 글 판정 3건이 구글 필터(«sensitive words») 거절 → 이 자리를 지나 EvoLink 로 나갔다.
    #   9-26 «막히면 에보링크로» 의 글 판정 허용을 대신한다. 사장님이 그 자리에서 허락하신 때만 승인 변수를 붙여 다시 돌린다.
    if os.environ.get(승인_변수, "").strip() == "1":
        log(f"  ★{승인_변수}=1 — 사장님이 허락하신 EvoLink 비상 길(글만)로 보낸다")
        return
    글 = (f"agy(제미나이)가 이 판정을 못 했다 — 글 판정도 EvoLink 로 넘기지 않음({승인_날짜}). 멈추고 사장님께 여쭙는다.\n"
         f"  agy 가 못 준 까닭: {까닭}\n  부른 곳: {caller}\n"
         f"  사장님께 여쭐 것: 까닭(구글 필터 거절이면 질문 글의 어느 낱말인지 · 한도·장애면 남은 양 {사용량_확인}) 과\n"
         f"    갈 길 — ① 질문 글을 고쳐 agy 로 다시 ② 이번만 EvoLink(유료) ③ 그 편 건너뜀.\n"
         f"  ②는 사장님이 그 자리에서 허락하신 때만 {승인_변수}=1 을 붙여 이 단계만 다시 돌린다(세션이 스스로 넣지 않는다).")
    기록(caller, "agy_fail_stop", sec, "글 판정 — EvoLink 로 안 넘김(멈춤 · 사장님께 여쭘) — " + 까닭, model)
    log(글)
    raise 판정멈춤(글)


# ── EvoLink 비상 길 (글만) ──
def _evolink_키():
    v = os.environ.get("EVOLINK_API_KEY", "").strip()
    if v:
        return v
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = str(winreg.QueryValueEx(k, "EVOLINK_API_KEY")[0] or "").strip()
            if v:
                return v
        except OSError:
            pass
    try:
        return (Path.home() / ".volcano" / "keys" / "evolink").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _evolink_보내기(job, body, caller, 까닭, log):
    """EvoLink 로 한 번(재시도 없음). 돌려주는 것: (종료코드, 응답 dict 또는 None, 원문)."""
    req = job.get("request") or {}
    url = req.get("url") or ""
    host = _host(url)
    if host not in EVOLINK_HOSTS + 시험_HOSTS:
        log(f"★비상 길 주소가 EvoLink 가 아니다: {host or url[:80]} — 보내지 않는다")
        기록(caller, "agy_fail_stop", 0, f"비상 길 주소가 EvoLink 가 아님({host}) — 안 보냄", job.get("model", ""))
        return 2, None, ""
    # 마지막 관문 — 보내기 직전에 «글만» 을 한 번 더(본문 허용 목록 + 주소 경로). 앞 단계를 우회한 길도 여기서 선다.
    어긋남 = 글만_아닌_까닭(body, url)
    if 어긋남:
        log(f"★보내기 직전 관문: «글만» 이 아니다 — EvoLink 로 보내지 않고 멈춘다({규칙_날짜}).\n"
            f"  어긋난 것: {' · '.join(어긋남[:5])[:400]}\n  확인: {사용량_확인}")
        기록(caller, "agy_fail_stop", 0, "보내기 직전 관문: 글만 아님 — 안 보냄(멈춤) — " + " · ".join(어긋남[:3]), job.get("model", ""))
        return 3, None, ""
    key = _evolink_키()
    if not key:
        글 = (f"agy 실패 · EvoLink 키도 없다(EVOLINK_API_KEY · ~/.volcano/keys/evolink) — 멈춘다.\n"
             f"  agy 가 못 준 까닭: {까닭}\n  확인: {사용량_확인}")
        기록(caller, "agy_fail_stop", 0, "EvoLink 키 없음 — 멈춤 — " + 까닭, job.get("model", ""))
        log(글)
        return 3, None, ""
    hdr = {k: v for k, v in (req.get("headers") or {}).items() if k.lower() not in ("authorization", "x-goog-api-key")}
    hdr.setdefault("Content-Type", "application/json")
    hdr["User-Agent"] = UA
    hdr["Authorization"] = "Bearer " + key          # 키 값은 화면·파일·기록에 안 쓴다
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    log(f"  agy 실패 → EvoLink 비상 길 한 번(글만 · {job.get('model', '')} · {len(data) // 1024}KB)")
    t0 = time.time()
    status, raw, 사정 = 0, "", ""
    try:
        rq = urllib.request.Request(url, data=data, headers=hdr, method=req.get("method", "POST"))
        with urllib.request.urlopen(rq, timeout=600) as r:
            status, raw = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError) as e:
        사정 = f"{type(e).__name__}: {e}"
    sec = time.time() - t0
    결과 = f"HTTP {status}" if status else f"연결 실패({사정[:120]})"
    기록(caller, "fallback", sec, f"agy: {까닭[:160]} → EvoLink {host} {결과}", job.get("model", ""))
    if not status:
        log(f"★EvoLink 연결 실패 — {사정[:200]}")
        return 4, None, json.dumps({"error": {"message": 사정}}, ensure_ascii=False)
    try:
        resp = json.loads(raw)
    except json.JSONDecodeError:
        log(f"★EvoLink 응답이 JSON 이 아니다(HTTP {status}): {raw[:200]}")
        return 4, None, raw
    if status != 200 or not isinstance(resp, dict) or resp.get("error"):
        log(f"★EvoLink 오류 HTTP {status}: {json.dumps((resp or {}).get('error') if isinstance(resp, dict) else resp, ensure_ascii=False)[:300]}")
        return 4, None, raw
    cand = (resp.get("candidates") or [{}])[0]
    if cand.get("finishReason") != "STOP":
        log(f"★EvoLink 답이 잘렸다/비정상 finishReason={cand.get('finishReason')} — 멈추고 보고")
        return 4, None, raw
    resp.setdefault("route", "evolink_fallback")
    log(f"  (EvoLink 비상 · HTTP 200 · {sec:.0f}초 · 토큰 {(resp.get('usageMetadata') or {}).get('totalTokenCount')})")
    return 0, resp, raw


# ── 일감 한 개 ──
class 일감오류(Exception):
    pass


def _순정인가(job):
    req = job.get("request") or {}
    auth = job.get("auth") or {}
    if str(job.get("provider", "")).lower() == "google":
        return "provider google"
    if _host(req.get("url") or "") in 순정_HOSTS:
        return "주소 " + _host(req.get("url") or "")
    if str(auth.get("env", "")).upper() in 순정_키:
        return "키 자리 " + str(auth.get("env"))
    if "x-goog-api-key" in str(auth.get("header", "")).lower():
        return "키 머리 x-goog-api-key"
    return ""


def 치환한_바디(job, base_dir="."):
    """inputs 대로 파일 내용을 바디의 자리표에 문자열로 넣는다. 자리표가 바디에 없거나 파일이 없으면 일감오류."""
    req = job.get("request") or {}
    body = req.get("body")
    if not isinstance(body, dict):
        raise 일감오류("request.body 가 객체가 아니다")
    s = json.dumps(body, ensure_ascii=False)
    for inp in job.get("inputs") or []:
        ph, path = inp.get("placeholder"), inp.get("path")
        if not ph or not path:
            raise 일감오류(f"inputs 칸이 비었다: {inp}")
        esc = json.dumps(ph, ensure_ascii=False)[1:-1]
        if esc not in s:
            raise 일감오류(f"자리표 {ph} 가 바디에 없다")
        p = Path(path) if os.path.isabs(path) else Path(base_dir) / path
        try:
            content = p.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise 일감오류(f"inputs 파일을 못 읽는다: {path} ({e})")
        s = s.replace(esc, json.dumps(content, ensure_ascii=False)[1:-1])
    return json.loads(s)


def 처리(job, out, limit_min=None, caller=None, log=None):
    """일감 한 개 → 종료코드. 성공이면 out 에 generateContent 응답 모양을 쓴다."""
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    name = job.get("name") or "judge"
    caller = caller or f"judge_run/{name}"
    model = job.get("model", "")
    막힘 = _순정인가(job)
    if 막힘:
        글 = (f"순정 구글 길은 막혔다({막힘}) — 사장님 결정 ④ 2026-09-26. 키 파일은 안 지우지만 코드에서 안 쓴다.\n"
             f"  규격 판정.*.backend 를 evolink 로 되돌려라(판정은 어차피 agy 가 먼저 한다).")
        기록(caller, "blocked", 0, "순정 구글 길 거절 — " + 막힘, model)
        log("★" + 글)
        return 2
    try:
        body = 치환한_바디(job)
    except 일감오류 as e:
        log(f"★일감이 잘못됐다({name}): {e}")
        return 2
    if limit_min is None:
        limit_min = 15 if 글_아닌_조각(body) else agy_gemini.DEFAULT_LIMIT_MIN
    t0 = time.time()
    url = (job.get("request") or {}).get("url") or ""
    try:
        resp, 까닭 = agy_먼저(body, caller, limit_min=limit_min, log=log)    # 모르는 모양·ffmpeg 없는 영상 → 판정멈춤
        if resp is None:
            비상길_검사(body, caller, 까닭, log=lambda m: log("★" + m), sec=time.time() - t0, model=model, url=url)
    except 판정멈춤:
        return 3
    if resp is None:
        if str(job.get("provider", "")).lower() != "evolink":
            log(f"★비상 길은 EvoLink 만 — 이 일감의 provider 는 {job.get('provider')!r}. 보내지 않는다.")
            기록(caller, "agy_fail_stop", time.time() - t0, f"provider {job.get('provider')!r} — 비상 길 없음(멈춤) — " + 까닭, model)
            return 3
        rc, resp, raw = _evolink_보내기(job, body, caller, 까닭, log)
        if rc != 0:
            if raw:
                bad = str(out) + ".실패.json"
                Path(bad).parent.mkdir(parents=True, exist_ok=True)
                Path(bad).write_text(raw, encoding="utf-8")
                log(f"  실패 응답 원문 → {bad}")
            return rc
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
    route = resp.get("route") or "?"
    print(f"judge_run: {name} ← {route} ({time.time() - t0:.1f}초) → {out}", flush=True)
    return 0


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")   # 윈도우 기본 cp949 로 나가면 한글이 깨진다
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="서버 judge 일감 한 개를 agy 먼저 · 사장님 규칙대로 처리한다")
    ap.add_argument("--job", required=True, help="서버가 준 judge 일감(jobs[i]) 하나를 그대로 저장한 JSON 파일")
    ap.add_argument("--out", default=None, help="응답을 쓸 자리 (없으면 일감의 out)")
    ap.add_argument("--limit", type=int, default=None, help="agy 시간 제한(분). 기본: 글만 10 · 미디어 15")
    ap.add_argument("--caller", default=None, help="기록에 남길 이름 (기본 judge_run/<일감 이름>)")
    a = ap.parse_args(argv)
    try:
        job = json.loads(Path(a.job).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"★일감 파일을 못 읽는다: {a.job} ({e})", file=sys.stderr)
        return 2
    if not isinstance(job, dict) or "request" not in job:
        print("★일감 모양이 아니다 — 서버 응답의 jobs[i] 객체 하나를 통째로 저장해야 한다(request·out 칸).", file=sys.stderr)
        return 2
    out = a.out or job.get("out")
    if not out:
        print("★응답을 쓸 자리가 없다 — --out 을 주거나 일감에 out 칸이 있어야 한다.", file=sys.stderr)
        return 2
    return 처리(job, out, limit_min=a.limit, caller=a.caller)


if __name__ == "__main__":
    sys.exit(main())
