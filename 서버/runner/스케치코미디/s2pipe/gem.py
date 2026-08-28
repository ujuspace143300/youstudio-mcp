# Gemini 호출을 한 곳에 모은다. **EvoLink 를 먼저 쓰고 순정으로 물러난다.**
#
# ★★2026-08-18 실측 — 같은 그림·같은 모델로 견줬다:
#     EvoLink 3.4~4.6초 · 순정 24.8초. **5~7배 빠르고 503 이 없다.**
#     (그날 순정은 503 을 11회 냈다. 30초씩 기다려 5분 넘게 날렸다.)
#     답과 토큰은 같았다(prompt 1092 vs 1093) — 품질 손해가 없다.
#
# ★★**User-Agent 를 반드시 준다.** 없으면 **멀티모달만** `403 error code: 1010` 으로
#   막힌다. 텍스트는 통과해서 더 헷갈린다. vault 가 「EvoLink 는 막힌 길」로 적어 둔
#   것이 실은 이 헤더를 빠뜨린 탓이었다 — linbox/runner/vision.py 가 2026-08-13 에
#   이미 짚어 둔 것을 우리가 몰랐다.
#
# ★**EvoLink 에는 Files API 가 없다.** 큰 미디어는 순정 키로만 올릴 수 있다.
#   그래서 덩치가 크면 EvoLink 를 건너뛴다(BIG_MB).
import json
import os
import time
import urllib.error
import urllib.request

EVO_BASE = "https://api.evolink.ai/v1beta/models"
GOO_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
USER_AGENT = "script-engine/1.1"        # ★정본 상수. 바꾸면 멀티모달이 403 이다
BIG_MB = 18.0                           # 이보다 크면 EvoLink 를 건너뛴다


def _read_key(p):
    try:
        return open(os.path.expanduser(p), encoding="utf-8").read().strip()
    except OSError:
        return ""


def routes(big=False):
    """쓸 수 있는 경로를 좋은 순서로. EvoLink → 순정."""
    out = []
    if not big:
        k = os.environ.get("EVOLINK_API_KEY", "").strip() or \
            _read_key("~/.volcano/keys/evolink")
        if k:
            out.append(("EvoLink", EVO_BASE, k))
    g = _read_key("~/.volcano/keys/gemini")
    if g:
        out.append(("순정", GOO_BASE, g))
    return out


def ask(payload, models, timeout=900, tries=3, log=print):
    """돌려주는 것: (파싱된 본문 텍스트, 경로이름, 모델) — 다 막히면 (None, "", "").

    ★503 은 서버 혼잡이라 기다리면 풀린다. 429 는 한도 소진이니 바로 다음 모델로.
      403 은 대개 User-Agent 문제다 — 재시도해도 소용없다.
    """
    # ★★**EvoLink 는 `contents` 에 `role` 이 없으면 응답을 아예 주지 않는다.**
    #   에러도 안 내고 그냥 멈춘다 — 타임아웃까지 기다리게 된다(실측: role 있으면
    #   3.4초, 없으면 45초 타임아웃). 순정 Gemini 는 role 없이도 받아 주므로
    #   **순정에서 잘 돌던 payload 를 그대로 EvoLink 로 보내면 여기서 걸린다.**
    #   실제로 jump_why 가 14분을 헛돌았다.
    payload = dict(payload)
    payload["contents"] = [{**c, "role": c.get("role", "user")}
                           for c in payload.get("contents", [])]

    body = json.dumps(payload).encode()
    big = len(body) / 1024 / 1024 > BIG_MB
    rs = routes(big)
    if not rs:
        log("  쓸 수 있는 키가 없다 — EVOLINK_API_KEY 나 ~/.volcano/keys/gemini")
        return None, "", ""
    if big:
        log(f"  {len(body)/1024/1024:.0f}MB — EvoLink 는 건너뛴다(Files API 가 없다)")

    for name, base, key in rs:
        for model in models:
            for t in range(tries):
                try:
                    req = urllib.request.Request(
                        f"{base}/{model}:generateContent", data=body, method="POST",
                        headers={"Content-Type": "application/json",
                                 "x-goog-api-key": key,
                                 "User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        d = json.loads(r.read().decode())
                    txt = "".join(p.get("text", "")
                                  for p in d["candidates"][0]["content"]["parts"])
                    u = d.get("usageMetadata", {})
                    log(f"  ({name} · {model} · prompt {u.get('promptTokenCount')}토큰)")
                    return txt, name, model
                except urllib.error.HTTPError as e:
                    if e.code == 429:
                        log(f"  {name}/{model} 한도 소진 → 다음 모델")
                        break
                    if e.code == 403:
                        log(f"  {name}/{model} 403 — User-Agent 를 확인하라")
                        break
                    wait = 20 if e.code == 503 else 10
                    log(f"  {name}/{model} HTTP {e.code} ({t+1}/{tries}) — {wait}초 뒤")
                    time.sleep(wait)
                except Exception as e:                   # noqa: BLE001
                    log(f"  {name}/{model} {type(e).__name__} {e}")
                    break
        log(f"  {name} 경로가 다 막혔다" + (" → 다음 경로" if name != rs[-1][0] else ""))
    return None, "", ""
