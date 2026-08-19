#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_강조판독.py — 영상 **구간별**로 자막 강조를 판독한다 (D6 표본 고르게 만들기).

  왜: 1차 판독(유튜브 URL)은 영상 앞 2~22% 만 보고 답했다. 그래서 강조 구성비가 **도입부에 치우쳐** 있고,
      밀도는 아예 못 쟀다(프롬프트가 「최소 8개」를 요구해 10편 전부 8개였다).

  이번엔 다르게: **길이가 정해진 클립**(기본 90초)을 잘라 올리고, 개수를 지정하지 않고
      「이 조각에 있는 강조를 **빠짐없이**」 찾게 한다 → **분당 강조 건수(밀도)** 가 나온다.

  구간: 중간(영상 50% 지점) · 끝(마지막 90초). 앞부분은 기존 1차 판독을 쓴다.
  키는 환경변수에서만 읽는다(서버 무보관).

사용:
  python 서버/runner/분석_강조판독.py --n 9 --구간 중간
  python 서버/runner/분석_강조판독.py --전체 [--초 90] [--덮어쓰기]
"""
import argparse, base64, json, os, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
목록_기본 = os.path.join(ROOT, "분석/지무비/목록.json")
원본_기본 = "C:/Users/user/Desktop/youstudio_work/분석/지무비/원본"
임시 = "C:/Users/user/Desktop/youstudio_work/분석/_강조클립"
UA = "youstudio-mcp/0.8 (analysis runner)"

프롬프트 = """이 영상 조각은 한국어 리캡 영상의 일부다. **자막 강조**만 판독해라.

여기서 「강조」란 **한 자막 줄 안에서 일부 글자만** 색·크기·폰트가 다른 것을 말한다.

## 지켜야 할 것
- 답은 JSON 하나만. 코드블록으로 감싸고 그 밖에는 아무 말도 쓰지 않는다.
- **이 조각에 나오는 강조를 빠짐없이 적는다.** 개수를 맞추려고 없는 것을 만들지 마라. 하나도 없으면 빈 배열로 둔다.
- 시각은 **이 조각 안에서의 초**(0부터 시작). 확실하지 않으면 그 항목의 "확신"을 "낮음"으로.
- 강조가 아닌 것(전체가 같은 색인 자막, 화면 속 원본 자막, 로고·헤더)은 넣지 않는다.

## 각 강조마다 적을 것
시각 · 그 자막 줄 전체 · 강조된 단어 · 강조 색(HEX 근사) · 크기 배수(보통 글자 대비) · 폰트가 다른가 ·
왜 그 단어를 강조했다고 보는가 · 의미 유형 [숫자, 고유명사, 감정어, 반전어, 의성어, 행위어, 기타]

## 출력 스키마
{
  "조각_길이_s": <숫자>,
  "자막_줄_수": <이 조각에 나온 자막 줄의 대략 개수>,
  "강조": [
    {"시각_s": <숫자>, "자막_전문": "<그 줄 전체>", "강조_단어": ["<단어>"],
     "강조_방식": {"색_HEX": "#RRGGBB", "크기_배수": <숫자>, "폰트_다름": <true|false>},
     "왜_강조라고_보나": "<한 줄>", "의미_유형": "숫자|고유명사|감정어|반전어|의성어|행위어|기타",
     "확신": "높음|보통|낮음"}
  ],
  "판독_불가": ["<한 줄>"]
}"""


def 키(env):
    v = os.environ.get(env)
    if v: return v.strip()
    r = subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetEnvironmentVariable('{env}','User')"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def 클립(video, 구간, 초, 길이_s, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    argv = ["ffmpeg", "-y", "-v", "error"]
    if 구간 == "끝":
        argv += ["-sseof", f"-{초}", "-i", video]
    else:
        argv += ["-ss", str(round(max(0, 길이_s * 0.5), 2)), "-i", video, "-t", str(초)]
    argv += ["-vf", "scale=640:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
             "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", out]
    subprocess.run(argv, capture_output=True)
    return os.path.getsize(out) if os.path.exists(out) else 0


def 느슨한파싱(text):
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


def 호출(clip, model, 최대토큰=16384):
    b64 = base64.b64encode(open(clip, "rb").read()).decode("ascii")
    body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "video/mp4", "data": b64}}, {"text": 프롬프트}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 최대토큰, "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    req = urllib.request.Request(f"https://api.evolink.ai/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"content-type": "application/json", "user-agent": UA,
                                          "authorization": f"Bearer {키('EVOLINK_API_KEY')}"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:
        raw, status = json.dumps({"error": {"message": str(e)}}), 0
    초 = round(time.time() - t0, 1)
    답, usage = "", None
    try:
        j = json.loads(raw)
        답 = "".join(p.get("text", "") for p in (j.get("candidates") or [{}])[0].get("content", {}).get("parts", []))
        usage = j.get("usageMetadata")
    except Exception:
        pass
    return status, 답.strip(), usage, raw, 초


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, action="append")
    ap.add_argument("--전체", action="store_true")
    ap.add_argument("--구간", default="둘다", choices=["중간", "끝", "둘다"])
    ap.add_argument("--초", type=int, default=90)
    ap.add_argument("--덮어쓰기", action="store_true")
    ap.add_argument("--모델", default="gemini-3.5-flash")
    ap.add_argument("--목록", default=목록_기본)
    ap.add_argument("--원본", default=원본_기본)
    a = ap.parse_args()
    if not a.전체 and not a.n: ap.error("--n <번호> 또는 --전체")
    목록 = json.load(open(a.목록, encoding="utf-8"))["표본"]
    대상 = [x for x in 목록 if x.get("파일") and (a.전체 or x["n"] in (a.n or []))]
    구간들 = ["중간", "끝"] if a.구간 == "둘다" else [a.구간]
    기록 = []
    for row in 대상:
        n = row["n"]
        for 구 in 구간들:
            폴더 = os.path.join(ROOT, "분석/지무비", f"{n:02d}")
            out = os.path.join(폴더, f"gemini_강조_{구}.json")
            if os.path.exists(out) and not a.덮어쓰기:
                print(f"· {n:02d} {구} 이미 있음 — 건너뜀"); continue
            os.makedirs(폴더, exist_ok=True)
            c = os.path.join(임시, f"{n:02d}_{구}{a.초}s.mp4")
            mb = round(클립(os.path.join(a.원본, row["파일"]), 구, a.초, row.get("길이_s") or 0, c) / 1048576, 2)
            if not mb:
                print(f"✗ {n:02d} {구} 클립 실패"); continue
            print(f"→ {n:02d} {구} 클립 {mb}MB 업로드", flush=True)
            status, 답, usage, raw, 초 = 호출(c, a.모델)
            if status != 200 or not 답:
                print(f"  ✗ HTTP {status} · {초}s — {raw[:150]}"); 기록.append({"n": n, "구간": 구, "상태": f"실패 {status}"}); continue
            try:
                doc = 느슨한파싱(답)
            except Exception as e:
                open(os.path.join(폴더, f"_강조_{구}_원응답.json"), "w", encoding="utf-8").write(raw[:100000])
                print(f"  ✗ 파싱 실패 {e}"); 기록.append({"n": n, "구간": 구, "상태": "파싱 실패"}); continue
            강조 = doc.get("강조") or []
            doc["_클립"] = {"구간": 구, "초": a.초, "MB": mb, "걸린_s": 초, "토큰": (usage or {}).get("totalTokenCount")}
            json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            분당 = round(len(강조) / (a.초 / 60), 2)
            print(f'  ✓ 강조 {len(강조)}건 · 분당 {분당} · 자막 줄 {doc.get("자막_줄_수")} · {초}s · 토큰 {(usage or {}).get("토큰") or (usage or {}).get("totalTokenCount")}')
            기록.append({"n": n, "구간": 구, "상태": "통과", "강조": len(강조), "분당_강조": 분당,
                        "자막_줄_수": doc.get("자막_줄_수"), "토큰": (usage or {}).get("totalTokenCount"), "초": 초})
    if 기록:
        p = os.path.join(ROOT, "분석/지무비/_강조판독기록.json")
        옛 = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
        json.dump(옛 + 기록, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f'\n합계 {len(기록)}건 · 통과 {sum(1 for x in 기록 if x["상태"] == "통과")} · 토큰 {sum(x.get("토큰") or 0 for x in 기록)}')


if __name__ == "__main__":
    main()
