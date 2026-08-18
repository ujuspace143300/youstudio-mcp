#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_판독.py — 제미나이 판독 자동화 (분석 단계 (b)).

  `분석/지무비/링크.json` 의 편들을 순회하며 **유튜브 URL 을 그대로** 제미나이에 넣고
  `분석/지무비/제미나이_지침서.md` 의 **C절 프롬프트 전문**으로 판독을 받아
  `분석/지무비/NN/gemini.json` 으로 저장한 뒤 `분석_판독검사.py` 로 곧바로 검사한다.

  실측 근거(2026-08-18 탐침, `서버/runner/분석_탐침.mjs`)
    · EvoLink `v1beta/…:generateContent` 는 `file_data.file_uri` 에 유튜브 URL 을 받는다.
      단 **`mime_type` 이 비면 400** — `video/mp4` 를 붙인다.
    · 15분짜리 한 편 = 프롬프트 토큰 **약 211K**(VIDEO 153K + AUDIO 58K). 비용은 여기서 나온다.
    · 구글 순정 키는 **429(선불 크레딧 소진)** — 폴백으로만 남긴다.

  프롬프트는 지침서에서 **읽어 쓴다**(한 벌만 둔다 — 사람이 수동으로 할 때와 같은 글이어야 비교가 된다).
  키는 환경변수에서만 읽는다(서버 무보관).

사용:
  python 서버/runner/분석_판독.py --n 1              # 1편만 (먼저 품질 확인)
  python 서버/runner/분석_판독.py --전체              # 남은 편 전부
  python 서버/runner/분석_판독.py --n 3 --덮어쓰기    # 이미 있는 것도 다시
"""
import argparse, json, os, re, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
링크_기본 = os.path.join(ROOT, "분석/지무비/링크.json")
지침서 = os.path.join(ROOT, "분석/지무비/제미나이_지침서.md")
검사기 = os.path.join(ROOT, "서버/runner/분석_판독검사.py")


def 키(env):
    v = os.environ.get(env)
    if v: return v.strip()
    r = subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetEnvironmentVariable('{env}','User')"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def 프롬프트_읽기(path=지침서):
    """지침서 C절의 코드블록 = 제미나이에게 주는 글. 사람 절차와 자동화가 **같은 글**을 쓴다."""
    s = open(path, encoding="utf-8").read()
    i = s.index("## C. 프롬프트 전문")
    m = re.search(r"```\n(.*?)\n```", s[i:], re.S)
    if not m: raise SystemExit("지침서 C절에서 프롬프트 코드블록을 찾지 못했다")
    return m.group(1).strip()


def 호출(url_video, prompt, model, 최대토큰, 백엔드):
    """generateContent 한 번. 돌려주는 것: (status, 답 텍스트, usage, finishReason, 원문, 걸린초)"""
    body = {
        "contents": [{"role": "user", "parts": [
            {"file_data": {"mime_type": "video/mp4", "file_uri": url_video}},
            {"text": prompt}]}],
        # brief 때 교훈: JSON 을 말로 부탁하지 말고 **응답 형식으로 강제**한다. 잘림(MAX_TOKENS)은 finishReason 으로 본다.
        "generationConfig": {"temperature": 0, "maxOutputTokens": 최대토큰,
                             "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}},
    }
    # UA 실측(2026-08-18): 기본 Python-urllib 로 부르면 **403 code 1010**(Cloudflare 차단) — 보통 UA 를 붙인다
    UA = "youstudio-mcp/0.8 (analysis runner)"
    if 백엔드 == "evolink":
        url = f"https://api.evolink.ai/v1beta/models/{model}:generateContent"
        headers = {"content-type": "application/json", "user-agent": UA, "accept": "application/json", "authorization": f"Bearer {키('EVOLINK_API_KEY')}"}
    else:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"content-type": "application/json", "user-agent": UA, "accept": "application/json", "x-goog-api-key": 키("GEMINI_API_KEY")}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:
        raw, status = json.dumps({"error": {"message": str(e)}}), 0
    초 = round(time.time() - t0, 1)
    답, usage, finish = "", None, None
    try:
        j = json.loads(raw)
        cand = (j.get("candidates") or [{}])[0]
        답 = "".join(p.get("text", "") for p in (cand.get("content", {}).get("parts") or []))
        finish = cand.get("finishReason")
        usage = j.get("usageMetadata")
    except Exception:
        pass
    return status, 답.strip(), usage, finish, raw, 초


def 판독(row, prompt, 인자):
    n = row["n"]
    폴더 = os.path.join(ROOT, "분석/지무비", f"{n:02d}")
    out = os.path.join(폴더, "gemini.json")
    if os.path.exists(out) and not 인자.덮어쓰기:
        print(f"· {n:02d} 이미 있음 — 건너뜀(--덮어쓰기 로 다시)")
        return None
    os.makedirs(폴더, exist_ok=True)
    최대 = 인자.최대토큰
    for 시도 in range(1, 3):
        print(f"→ {n:02d} 판독 (모델 {인자.모델} · 최대토큰 {최대} · {시도}차)", flush=True)
        status, 답, usage, finish, raw, 초 = 호출(row["url"], prompt, 인자.모델, 최대, 인자.백엔드)
        open(os.path.join(폴더, "_원응답.json"), "w", encoding="utf-8").write(raw[:200000])
        if status != 200 or not 답:
            print(f"  ✗ HTTP {status} · {초}s — {raw[:200].replace(chr(10), ' ')}")
            return {"n": n, "상태": f"실패 HTTP {status}", "초": 초}
        if finish == "MAX_TOKENS" and 시도 == 1:
            print(f"  ! 답이 잘렸다(MAX_TOKENS, {초}s) — 최대토큰을 늘려 다시 부른다")
            최대 = 최대 * 2
            continue
        try:
            doc = json.loads(답)
        except Exception as e:
            print(f"  ✗ JSON 파싱 실패({e}) — 원응답은 {폴더}/_원응답.json")
            return {"n": n, "상태": "JSON 파싱 실패", "초": 초}
        # 실측(2026-08-18): 제미나이가 편.url 에 자리표시자("v_v_v_v_v_v")를 넣는다 — **우리가 아는 값**으로 덮는다
        doc.setdefault("편", {})
        doc["편"]["url"] = row["url"]
        doc["편"]["n"] = n
        json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        meta = {"n": n, "url": row["url"], "모델": 인자.모델, "백엔드": 인자.백엔드, "걸린_s": 초,
                "finishReason": finish, "usage": usage, "받은_시각": time.strftime("%Y-%m-%d %H:%M:%S")}
        json.dump(meta, open(os.path.join(폴더, "_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        tok = (usage or {}).get("totalTokenCount")
        print(f"  ✓ 저장 {out} · {초}s · 토큰 {tok}")
        r = subprocess.run([sys.executable, 검사기, "--판독", out], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r.stdout or "").rstrip())
        return {"n": n, "상태": "통과" if r.returncode == 0 else "검사 불통", "초": 초, "토큰": tok, "usage": usage}
    return {"n": n, "상태": "잘림 반복", "초": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, help="이 번호 한 편만")
    ap.add_argument("--전체", action="store_true")
    ap.add_argument("--덮어쓰기", action="store_true")
    ap.add_argument("--링크", default=링크_기본)
    ap.add_argument("--모델", default="gemini-3.5-flash")
    ap.add_argument("--백엔드", default="evolink", choices=["evolink", "google"])
    ap.add_argument("--최대토큰", type=int, default=32768)
    ap.add_argument("--쉼_s", type=float, default=3.0, help="편 사이 쉬는 시간")
    a = ap.parse_args()
    링크 = json.load(open(a.링크, encoding="utf-8"))
    표본 = [r for r in 링크["표본"] if (a.n is None or r["n"] == a.n)]
    if not a.전체 and a.n is None:
        ap.error("--n <번호> 또는 --전체 중 하나가 필요하다 (먼저 1편으로 품질을 본다)")
    prompt = 프롬프트_읽기()
    print(f"프롬프트 {len(prompt)}자 · 대상 {len(표본)}편 · 백엔드 {a.백엔드}")
    결과 = []
    for i, row in enumerate(표본):
        r = 판독(row, prompt, a)
        if r: 결과.append(r)
        if i + 1 < len(표본): time.sleep(a.쉼_s)
    if 결과:
        tot = sum(x.get("토큰") or 0 for x in 결과)
        sec = sum(x.get("초") or 0 for x in 결과)
        print(f"\n합계 {len(결과)}편 · 통과 {sum(1 for x in 결과 if x['상태'] == '통과')} · 총 토큰 {tot} · 총 {round(sec, 1)}s")
        json.dump(결과, open(os.path.join(ROOT, "분석/지무비/_판독기록.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
