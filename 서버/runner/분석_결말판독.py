#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_결말판독.py — 각 편의 **마지막 60~90초만** 잘라 제미나이에 다시 판독시킨다 (D11 수리).

  왜: 유튜브 URL 로 넣은 1차 판독은 **영상 앞 2~22% 만 보고** 답했다(총장_대조.json).
      그래서 「결말 공개 여부·마무리 방식·CTA」는 근거가 없다. 이제 원본 파일이 있으므로
      **끝부분 클립을 인라인(base64)으로 올려** 그 구간만 정확히 보게 한다.

  방법: ffmpeg `-sseof` 로 끝에서 N초를 잘라 640x360·저비트레이트 mp4 로 만든다(인라인 상한 20MB, 규격 「판정.영상.인라인_상한_mb」).
        EvoLink generateContent 의 inline_data 로 보내고, 답은 `분석/지무비/NN/gemini_결말.json` 에 저장한다.

  키는 환경변수에서만 읽는다(서버 무보관).

사용:
  python 서버/runner/분석_결말판독.py --n 9            # 한 편
  python 서버/runner/분석_결말판독.py --전체 [--초 90] [--덮어쓰기]
"""
import argparse, base64, json, os, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
목록_기본 = os.path.join(ROOT, "분석/지무비/목록.json")
원본_기본 = "C:/Users/user/Desktop/youstudio_work/분석/지무비/원본"
임시 = "C:/Users/user/Desktop/youstudio_work/분석/_결말클립"
UA = "youstudio-mcp/0.8 (analysis runner)"

프롬프트 = """이 영상 조각은 한국어 리캡 영상의 **마지막 부분**이다. 이 조각만 보고 아래를 판독해라.

## 지켜야 할 것
- 답은 JSON 하나만. 코드블록으로 감싸고 그 밖에는 아무 말도 쓰지 않는다.
- 시각은 **이 조각 안에서의 초**(0부터). 확실하지 않으면 그 항목의 "확신"을 "낮음"으로.
- 본 것만 적는다. 안 보이면 값은 null 로 두고 "판독_불가"에 이유를 적는다.

## 판독할 것
1. 이야기의 **결말을 공개**하는가, 아니면 결정적인 대목에서 끊고 넘기는가.
2. 마지막 나레이션 문장을 **그대로**.
3. 마무리 방식 — [여운, 교훈, 반전 재확인, 다음 영상 유도, 원작 보기 유도, 기타] 중 하나.
4. 구독·좋아요·댓글·다음 영상 등 **시청자 행동 유도(CTA)** 가 말이나 화면으로 나오는가. 나온다면 무엇을 어떻게.
5. 채널 고정 요소(로고·엔드카드·다음 영상 썸네일)가 나오는가.
6. 마지막 10초에 화면과 소리가 어떻게 끝나는가(암전·정지화면·음악 페이드 등).

## 출력 스키마
{
  "결말_공개": true 또는 false,
  "끊은_지점": "<공개하지 않았다면 어디서 끊는지 한 줄, 아니면 null>",
  "마지막_나레": "<그대로>",
  "마무리_유형": "여운|교훈|반전 재확인|다음 영상 유도|원작 보기 유도|기타",
  "CTA": {"있음": true 또는 false, "무엇": "<한 줄>", "방식": "말|화면|둘 다|없음"},
  "채널_고정요소": ["<한 줄>"],
  "마지막_10초": "<한 줄>",
  "확신": "높음|보통|낮음",
  "판독_불가": ["<한 줄>"]
}"""


def 키(env):
    v = os.environ.get(env)
    if v: return v.strip()
    r = subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetEnvironmentVariable('{env}','User')"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def 클립만들기(video, 초, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    argv = ["ffmpeg", "-y", "-v", "error", "-sseof", f"-{초}", "-i", video,
            "-vf", "scale=640:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", out]
    subprocess.run(argv, capture_output=True)
    return os.path.getsize(out) if os.path.exists(out) else 0


def 호출(clip, model, 최대토큰=8192):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int)
    ap.add_argument("--전체", action="store_true")
    ap.add_argument("--초", type=int, default=90)
    ap.add_argument("--덮어쓰기", action="store_true")
    ap.add_argument("--모델", default="gemini-3.5-flash")
    ap.add_argument("--목록", default=목록_기본)
    ap.add_argument("--원본", default=원본_기본)
    a = ap.parse_args()
    if not a.전체 and a.n is None: ap.error("--n <번호> 또는 --전체")
    목록 = json.load(open(a.목록, encoding="utf-8"))["표본"]
    대상 = [x for x in 목록 if x.get("파일") and (a.n is None or x["n"] == a.n)]
    기록 = []
    for row in 대상:
        n = row["n"]
        폴더 = os.path.join(ROOT, "분석/지무비", f"{n:02d}")
        out = os.path.join(폴더, "gemini_결말.json")
        if os.path.exists(out) and not a.덮어쓰기:
            print(f"· {n:02d} 이미 있음 — 건너뜀"); continue
        os.makedirs(폴더, exist_ok=True)
        clip = os.path.join(임시, f"{n:02d}_끝{a.초}s.mp4")
        mb = round(클립만들기(os.path.join(a.원본, row["파일"]), a.초, clip) / 1048576, 2)
        if not mb:
            print(f"✗ {n:02d} 클립 실패"); continue
        print(f"→ {n:02d} 끝 {a.초}s 클립 {mb}MB 업로드", flush=True)
        status, 답, usage, raw, 초 = 호출(clip, a.모델)
        if status != 200 or not 답:
            print(f"  ✗ HTTP {status} · {초}s — {raw[:160]}")
            기록.append({"n": n, "상태": f"실패 {status}"}); continue
        try:
            doc = 느슨한파싱(답)
        except Exception as e:
            open(os.path.join(폴더, "_결말_원응답.json"), "w", encoding="utf-8").write(raw[:100000])
            print(f"  ✗ 파싱 실패 {e}"); 기록.append({"n": n, "상태": "파싱 실패"}); continue
        doc["_클립"] = {"끝에서_초": a.초, "MB": mb, "모델": a.모델, "걸린_s": 초,
                      "토큰": (usage or {}).get("totalTokenCount")}
        json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f'  ✓ 결말공개 {doc.get("결말_공개")} · 마무리 {doc.get("마무리_유형")} · CTA {(doc.get("CTA") or {}).get("있음")} · {초}s · 토큰 {(usage or {}).get("totalTokenCount")}')
        기록.append({"n": n, "상태": "통과", "초": 초, "토큰": (usage or {}).get("totalTokenCount"), "MB": mb})
    if 기록:
        json.dump(기록, open(os.path.join(ROOT, "분석/지무비/_결말판독기록.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        tok = sum(x.get("토큰") or 0 for x in 기록)
        print(f'\n합계 {len(기록)}편 · 통과 {sum(1 for x in 기록 if x["상태"] == "통과")} · 토큰 {tok}')


if __name__ == "__main__":
    main()
