#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_전사.py — 레퍼런스 영상의 말을 **단어 단위로** 전사한다 (분석 (a), 차원 D3·D7).

  왜: 나레:대사 턴 구조·문장 길이·어미 분포는 **말을 받아 적어야** 나온다. 우리 파이프라인이
      쓰는 것과 **같은 자**(Speechmatics batch v2, 단어 단위)로 재야 우리 결과와 비교가 된다.

  흐름: ffmpeg 로 오디오 추출(16kHz 모노 mp3, 규격 「전사.오디오추출」) → 배치 제출 → 폴링 → json-v2 저장 →
        단어 수·분당 단어·발화 시간·문장 길이 분포를 계산해 `<슬러그>.전사.json` 옆에 요약을 남긴다.

  비용: 오디오 길이에 비례한다. 편당 실측(오디오 분·처리 초·단어 수)을 기록해 10편 확장 전에 판단한다.
  키는 환경변수에서만 읽는다(서버 무보관).

사용:
  python 서버/runner/분석_전사.py --n 9              # 한 편
  python 서버/runner/분석_전사.py --n 9 --n 10 --n 6 # 여러 편
  python 서버/runner/분석_전사.py --전체 [--덮어쓰기]
"""
import argparse, json, os, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
목록_기본 = os.path.join(ROOT, "분석/지무비/목록.json")
원본_기본 = "C:/Users/user/Desktop/youstudio_work/분석/지무비/원본"
작업_기본 = "C:/Users/user/Desktop/youstudio_work/분석/지무비/전사"
UA = "youstudio-mcp/0.8 (analysis runner)"
SM = "https://asr.api.speechmatics.com/v2/jobs"


def 키(env):
    v = os.environ.get(env)
    if v: return v.strip()
    r = subprocess.run(["powershell", "-NoProfile", "-Command", f"[Environment]::GetEnvironmentVariable('{env}','User')"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def 오디오추출(video, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out) and os.path.getsize(out) > 0: return os.path.getsize(out)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-map", "0:a:0", "-vn",
                    "-ar", "16000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "48k", out], capture_output=True)
    return os.path.getsize(out) if os.path.exists(out) else 0


def 제출(mp3, 키값, 언어="ko"):
    """multipart/form-data 를 손으로 만든다(표준 라이브러리만 쓴다)"""
    경계 = "----youstudio" + str(int(time.time() * 1000))
    config = json.dumps({"type": "transcription", "transcription_config": {"language": 언어, "operating_point": "enhanced"}})
    앞 = (f"--{경계}\r\nContent-Disposition: form-data; name=\"config\"\r\n\r\n{config}\r\n"
          f"--{경계}\r\nContent-Disposition: form-data; name=\"data_file\"; filename=\"{os.path.basename(mp3)}\"\r\n"
          f"Content-Type: audio/mpeg\r\n\r\n").encode("utf-8")
    뒤 = f"\r\n--{경계}--\r\n".encode("utf-8")
    body = 앞 + open(mp3, "rb").read() + 뒤
    req = urllib.request.Request(SM, data=body, method="POST",
                                 headers={"content-type": f"multipart/form-data; boundary={경계}",
                                          "user-agent": UA, "authorization": f"Bearer {키값}"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode("utf-8"))["id"]


def 받기(url, 키값):
    req = urllib.request.Request(url, headers={"user-agent": UA, "authorization": f"Bearer {키값}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def 분포(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs: return None
    q = lambda p: round(xs[min(len(xs) - 1, max(0, int(round((len(xs) - 1) * p))))], 2)
    return {"n": len(xs), "min": xs[0], "p25": q(0.25), "중앙": q(0.5), "p75": q(0.75), "max": xs[-1],
            "평균": round(sum(xs) / len(xs), 2)}


def 요약(tr, 오디오_s):
    res = tr.get("results") or []
    단어 = [{"w": (r.get("alternatives") or [{}])[0].get("content", ""), "s": r.get("start_time"), "e": r.get("end_time")}
           for r in res if (r.get("type") or "word") == "word" and isinstance(r.get("start_time"), (int, float))]
    말 = sum((w["e"] or w["s"]) - w["s"] for w in 단어)
    # 문장 = 마침표·물음표·느낌표로 끊는다(json-v2 는 punctuation 을 따로 준다)
    문장, cur = [], []
    for r in res:
        t = (r.get("alternatives") or [{}])[0].get("content", "")
        if (r.get("type") or "word") == "word": cur.append(t)
        elif t in (".", "?", "!") and cur: 문장.append(" ".join(cur)); cur = []
    if cur: 문장.append(" ".join(cur))
    자수 = [len(s.replace(" ", "")) for s in 문장]
    간격 = [round(단어[i + 1]["s"] - (단어[i]["e"] or 단어[i]["s"]), 3) for i in range(len(단어) - 1)]
    return {"오디오_s": round(오디오_s, 1), "단어_수": len(단어), "분당_단어": round(len(단어) / (오디오_s / 60), 1) if 오디오_s else None,
            "말한_시간_s": round(말, 1), "말한_비율": round(말 / 오디오_s, 3) if 오디오_s else None,
            "문장_수": len(문장), "문장_자수_분포": 분포(자수), "단어_사이_간격_분포_s": 분포(간격),
            "긴_쉼_1s이상": sum(1 for g in 간격 if g >= 1.0), "첫_문장": 문장[0] if 문장 else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, action="append")
    ap.add_argument("--전체", action="store_true")
    ap.add_argument("--덮어쓰기", action="store_true")
    ap.add_argument("--목록", default=목록_기본)
    ap.add_argument("--원본", default=원본_기본)
    ap.add_argument("--작업", default=작업_기본)
    ap.add_argument("--언어", default="ko")
    ap.add_argument("--poll_s", type=float, default=15.0)
    a = ap.parse_args()
    if not a.전체 and not a.n: ap.error("--n <번호> 또는 --전체")
    키값 = 키("SPEECHMATICS_API_KEY")
    if not 키값: raise SystemExit("SPEECHMATICS_API_KEY 없음")
    목록 = json.load(open(a.목록, encoding="utf-8"))["표본"]
    대상 = [x for x in 목록 if x.get("파일") and (a.전체 or x["n"] in (a.n or []))]
    기록 = []
    for row in 대상:
        n = row["n"]
        mp3 = os.path.join(a.작업, f"{n:02d}.mp3")
        out = os.path.join(a.작업, f"{n:02d}.전사.json")
        if os.path.exists(out) and not a.덮어쓰기:
            print(f"· {n:02d} 이미 있음 — 건너뜀"); continue
        video = os.path.join(a.원본, row["파일"])
        크기 = 오디오추출(video, mp3)
        오디오_s = row.get("길이_s") or 0
        print(f"→ {n:02d} {row.get('제목')} · 오디오 {round(크기/1048576,1)}MB · {round(오디오_s/60,1)}분 제출", flush=True)
        t0 = time.time()
        try:
            jid = 제출(mp3, 키값, a.언어)
        except urllib.error.HTTPError as e:
            print(f"  ✗ 제출 실패 {e.code} {e.read()[:200]}"); 기록.append({"n": n, "상태": f"제출 실패 {e.code}"}); continue
        상태 = ""
        while time.time() - t0 < 3600:
            time.sleep(a.poll_s)
            try:
                st = 받기(f"{SM}/{jid}", 키값)
            except Exception as e:
                print(f"  ! 상태 조회 실패 {e} — 계속"); continue
            상태 = (st.get("job") or {}).get("status") or st.get("status")
            if 상태 in ("done", "rejected", "expired"): break
        if 상태 != "done":
            print(f"  ✗ {상태}"); 기록.append({"n": n, "상태": 상태 or "시간초과"}); continue
        tr = 받기(f"{SM}/{jid}/transcript?format=json-v2", 키값)
        걸린 = round(time.time() - t0, 1)
        json.dump(tr, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        요 = 요약(tr, 오디오_s)
        요.update({"n": n, "제목": row.get("제목"), "job_id": jid, "걸린_s": 걸린, "오디오_MB": round(크기 / 1048576, 2)})
        json.dump(요, open(os.path.join(a.작업, f"{n:02d}.요약.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f'  ✓ 단어 {요["단어_수"]} · 분당 {요["분당_단어"]} · 말한 비율 {요["말한_비율"]} · 문장 {요["문장_수"]}(자수 중앙 {(요["문장_자수_분포"] or {}).get("중앙")}) · {걸린}s')
        기록.append({"n": n, "상태": "통과", **요})
    if 기록:
        p = os.path.join(ROOT, "분석/지무비/_전사기록.json")
        옛 = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
        json.dump(옛 + 기록, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        분 = sum((x.get("오디오_s") or 0) for x in 기록) / 60
        print(f'\n합계 {len(기록)}편 · 통과 {sum(1 for x in 기록 if x["상태"] == "통과")} · 오디오 {round(분,1)}분 · 처리 {round(sum(x.get("걸린_s") or 0 for x in 기록),1)}s')


if __name__ == "__main__":
    main()
