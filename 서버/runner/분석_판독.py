#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_판독.py — 제미나이 판독 자동화 (분석 단계 (b)).

  `분석/지무비/링크.json` 의 편들을 순회하며 **유튜브 URL 을 그대로** 제미나이에 넣고
  `분석/지무비/제미나이_지침서.md` 의 **C절 프롬프트 전문**으로 판독을 받아
  `분석/지무비/NN/gemini.json` 으로 저장한 뒤 `분석_판독검사.py` 로 곧바로 검사한다.

  실측 근거(2026-08-18 탐침, `서버/runner/분석_탐침.mjs`)
    · `file_data.file_uri` 에 유튜브 URL 을 받는다. 단 **`mime_type` 이 비면 400** — `video/mp4` 를 붙인다.
    · 15분짜리 한 편 = 프롬프트 토큰 **약 211K**(VIDEO 153K + AUDIO 58K). EvoLink 로 보내면 비용은 여기서 나왔다.

  ★2026-09-26 사장님 결정 ②④ — 판독은 **agy(구독)만**. 유튜브 영상 판독이라 agy 가 막히면 EvoLink 로 넘기지 않고
    **멈춘다**(종료코드 3 — judge_run.판정멈춤). 순정 구글 키 길(`--백엔드 google`)은 막혔다. 규칙은 judge_run.py 한 곳.
    확인: python ~/.claude/agy_call.py --usage

  프롬프트는 지침서에서 **읽어 쓴다**(한 벌만 둔다 — 사람이 수동으로 할 때와 같은 글이어야 비교가 된다).

사용:
  python 서버/runner/분석_판독.py --n 1              # 1편만 (먼저 품질 확인)
  python 서버/runner/분석_판독.py --전체              # 남은 편 전부
  python 서버/runner/분석_판독.py --n 3 --덮어쓰기    # 이미 있는 것도 다시
"""
import argparse, json, os, re, subprocess, sys, time
import judge_run  # 서버/runner/judge_run.py — agy 먼저 · 영상 판정은 막히면 멈춤 (2026-09-26 사장님 결정 ②④)
import agy_gemini  # noqa: E402  judge_run 이 PATH 빈틈을 막은 뒤 import 한 같은 모듈

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
링크_기본 = os.path.join(ROOT, "분석/지무비/링크.json")
지침서 = os.path.join(ROOT, "분석/지무비/제미나이_지침서.md")
검사기 = os.path.join(ROOT, "서버/runner/분석_판독검사.py")


def 프롬프트_읽기(path=지침서):
    """지침서 C절의 코드블록 = 제미나이에게 주는 글. 사람 절차와 자동화가 **같은 글**을 쓴다."""
    s = open(path, encoding="utf-8").read()
    i = s.index("## C. 프롬프트 전문")
    m = re.search(r"```\n(.*?)\n```", s[i:], re.S)
    if not m: raise SystemExit("지침서 C절에서 프롬프트 코드블록을 찾지 못했다")
    return m.group(1).strip()


def 호출(url_video, prompt, model, 최대토큰, 백엔드="agy"):
    """generateContent 한 번 — agy(구독)만. 돌려주는 것: (status, 답 텍스트, usage, finishReason, 원문, 걸린초).
    agy 가 막히면 judge_run.판정멈춤(종료코드 3)으로 멈춘다 — 유튜브 영상 판독이라 EvoLink 로 안 넘긴다(머리 주석)."""
    body = {
        "contents": [{"role": "user", "parts": [
            {"file_data": {"mime_type": "video/mp4", "file_uri": url_video}},
            {"text": prompt}]}],
        # brief 때 교훈: JSON 을 말로 부탁하지 말고 **응답 형식으로 강제**한다. 잘림(MAX_TOKENS)은 finishReason 으로 본다.
        "generationConfig": {"temperature": 0, "maxOutputTokens": 최대토큰,
                             "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}},
    }
    t0 = time.time()
    resp, 까닭 = judge_run.agy_먼저(body, "분석_판독", limit_min=15)
    if resp is None:
        judge_run.비상길_검사(body, "분석_판독", 까닭, sec=time.time() - t0, model=model)   # 영상이라 여기서 멈춘다
        raise judge_run.판정멈춤("분석_판독: 영상 판독인데 비상 길 검사를 지났다 — judge_run 규칙 오류, 멈춘다")
    return 200, agy_gemini.text_of(resp).strip(), resp["usageMetadata"], "STOP", json.dumps(resp, ensure_ascii=False), round(time.time() - t0, 1)


# 제미나이가 **한 항목만 영어 키**로 쓰는 일이 있다(실측 07: "meaning_type": "반전어").
#   값은 멀쩡하므로 재호출하지 않고 **키 이름만** 우리 스키마로 옮긴다 — 값은 손대지 않는다.
별칭 = {"meaning_type": "의미_유형", "confidence": "확신", "time_s": "시각_s", "type": "종류",
        "text": "자막_전문", "words": "강조_단어", "reason": "왜_강조라고_보나", "duration_s": "길이_s",
        "position": "붙은_자리", "color_hex": "색_HEX", "size_ratio": "크기_배수", "lane": "레인"}


def 느슨한파싱(text):
    """제미나이가 JSON 뒤에 군더더기를 붙일 때가 있다(실측 09: 닫는 괄호 하나가 더 붙었다).
       첫 번째 완결된 JSON 값만 떼어 쓴다 — 값을 고치지는 않는다."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json": text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i = text.find("{")
        if i < 0: raise
        obj, _ = json.JSONDecoder().raw_decode(text[i:])
        return obj


def 정규화(o):
    """영어 키를 우리 키로 바꾼다(값은 그대로). 우리 키가 이미 있으면 건드리지 않는다."""
    if isinstance(o, list):
        return [정규화(x) for x in o]
    if not isinstance(o, dict):
        return o
    out = {}
    for k, v in o.items():
        kk = 별칭.get(k, k)
        if kk != k and kk in o:      # 우리 키가 이미 있으면 영어 키는 버린다
            continue
        out[kk] = 정규화(v)
    return out


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
            doc = 느슨한파싱(답)
        except Exception as e:
            print(f"  ✗ JSON 파싱 실패({e}) — 원응답은 {폴더}/_원응답.json")
            return {"n": n, "상태": "JSON 파싱 실패", "초": 초}
        # 실측(2026-08-18): 제미나이가 편.url 에 자리표시자("v_v_v_v_v_v")를 넣는다 — **우리가 아는 값**으로 덮는다
        doc = 정규화(doc)
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
    ap.add_argument("--백엔드", default="agy", choices=["agy", "evolink", "google"],
                    help="agy 만 된다 — evolink·google 은 막혔다(2026-09-26 사장님 결정 ②④). 옛 명령줄이 넘겨도 멈추게 칸은 남긴다")
    ap.add_argument("--최대토큰", type=int, default=32768)
    ap.add_argument("--쉼_s", type=float, default=3.0, help="편 사이 쉬는 시간")
    ap.add_argument("--다시검사", action="store_true", help="API 를 부르지 않고, 이미 받은 판독을 정규화한 뒤 다시 검사만 한다")
    a = ap.parse_args()
    if a.백엔드 == "google":
        ap.error("--백엔드 google(순정 구글 키) 길은 막혔다 — 사장님 결정 ④ 2026-09-26. 판독은 agy 만.")
    if a.백엔드 == "evolink":
        ap.error("--백엔드 evolink 는 막혔다 — 유튜브 영상 판독은 agy 가 막히면 멈춘다(사장님 결정 ② 2026-09-26). "
                 "EvoLink 로 재 보려면 사람이 분석_탐침.mjs --backend evolink 로 따로.")
    링크 = json.load(open(a.링크, encoding="utf-8"))
    표본 = [r for r in 링크["표본"] if (a.n is None or r["n"] == a.n)]
    if not a.전체 and a.n is None and not a.다시검사:
        ap.error("--n <번호> 또는 --전체 중 하나가 필요하다 (먼저 1편으로 품질을 본다)")
    if a.다시검사:
        import glob
        for 원 in sorted(glob.glob(os.path.join(ROOT, "분석/지무비", "*", "_원응답.json"))):
            폴더2 = os.path.dirname(원)
            목표 = os.path.join(폴더2, "gemini.json")
            if os.path.exists(목표): continue
            try:
                j = json.load(open(원, encoding="utf-8"))
                t = "".join(p2.get("text", "") for p2 in (j.get("candidates") or [{}])[0].get("content", {}).get("parts", []))
                doc2 = 정규화(느슨한파싱(t))
                nn2 = int(os.path.basename(폴더2))
                doc2.setdefault("편", {})["n"] = nn2
                row2 = next((r for r in 링크["표본"] if r["n"] == nn2), None)
                if row2: doc2["편"]["url"] = row2["url"]
                json.dump(doc2, open(목표, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print(f"· {nn2:02d} 원응답에서 복구했다(재호출 없음)")
            except Exception as e:
                print(f"· {폴더2}: 복구 실패 — {e}")
        for path in sorted(glob.glob(os.path.join(ROOT, "분석/지무비", "*", "gemini.json"))):
            doc = 정규화(json.load(open(path, encoding="utf-8")))
            json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            r = subprocess.run([sys.executable, 검사기, "--판독", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
            print((r.stdout or "").rstrip())
        return
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
