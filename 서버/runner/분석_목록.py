#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""서버/runner/분석_목록.py — 분석 표본 폴더를 훑어 `목록.json` 을 만든다 (분석 단계 준비).

  `분석/지무비/링크.json` 의 표본 순서(01~10)와 `원본/` 폴더의 실제 파일을 **파일명 앞 번호**로 짝지어,
  ffprobe 실측(길이·해상도·fps·오디오·크기)을 붙인다. 없는 편은 `상태: "없음"` 으로 남겨 무엇이 빠졌는지 보인다.

  영상 파일은 저장소 밖에 둔다 — 저장소에는 이 스크립트가 만든 **목록.json 과 계측 결과만** 들어간다.

사용: python 서버/runner/분석_목록.py [--원본 <폴더>] [--링크 <링크.json>] [--out <목록.json>]
"""
import argparse, json, os, re, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
기본_원본 = "C:/Users/user/Desktop/youstudio_work/분석/지무비/원본"

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    return {"길이_s": round(float(d.get("format", {}).get("duration", 0)), 3),
            "해상도": [v.get("width"), v.get("height")],
            "fps": round(float(num) / float(den or 1), 3) if float(den or 1) else None,
            "비디오코덱": v.get("codec_name"), "오디오코덱": a.get("codec_name"),
            "오디오_샘플레이트": a.get("sample_rate"), "오디오_채널": a.get("channels"),
            "크기_MB": round(os.path.getsize(path) / 1048576, 1)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--원본", default=기본_원본)
    ap.add_argument("--링크", default=os.path.join(ROOT, "분석/지무비/링크.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "분석/지무비/목록.json"))
    a = ap.parse_args()
    링크 = json.load(open(a.링크, encoding="utf-8"))
    파일들 = []
    if os.path.isdir(a.원본):
        파일들 = [f for f in sorted(os.listdir(a.원본)) if os.path.splitext(f)[1].lower() in (".mp4", ".mkv", ".webm", ".mov")]
    def 찾기(n):
        for f in 파일들:
            m = re.match(r"^\D*(\d{1,2})", f)
            if m and int(m.group(1)) == n: return f
        return None

    표본, 있음 = [], 0
    for row in 링크["표본"]:
        f = row.get("파일") or 찾기(row["n"])
        item = {"n": row["n"], "url": row["url"], "파일": f, "제목": row.get("제목")}
        if f and os.path.exists(os.path.join(a.원본, f)):
            item.update(probe(os.path.join(a.원본, f)))
            item["상태"] = "있음"; 있음 += 1
        else:
            item["상태"] = "없음"
        표본.append(item)

    있는것 = [x for x in 표본 if x["상태"] == "있음"]
    doc = {"_안내": "분석 표본 목록 — 영상 파일은 저장소 밖(원본 폴더). 이 파일에는 실측 메타만 둔다.",
           "_용도": 링크.get("_용도"), "원본_폴더": a.원본,
           "요약": {"표본": len(표본), "있음": 있음, "없음": len(표본) - 있음,
                   "총_길이_s": round(sum(x.get("길이_s", 0) for x in 있는것), 1),
                   "총_길이_분": round(sum(x.get("길이_s", 0) for x in 있는것) / 60, 1),
                   "총_용량_MB": round(sum(x.get("크기_MB", 0) for x in 있는것), 1)},
           "표본": 표본}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"저장": a.out, **doc["요약"]}, ensure_ascii=False))
    for x in 표본:
        mark = "○" if x["상태"] == "있음" else "×"
        print(f'  {mark} {x["n"]:02d} {x.get("파일") or "(없음)"} {x.get("길이_s", "")} {x.get("해상도", "")}')

if __name__ == "__main__":
    main()
