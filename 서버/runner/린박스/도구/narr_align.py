# -*- coding: utf-8 -*-
r"""나레이션 낱말 시각을 다시 잰다 → narr_words.json

왜 필요한가
  자막 카드를 언제 넘길지는 **TTS 가 실제로 그 낱말을 말한 시각**으로 정한다.
  서버는 글자수로 균등 분할해 주는데 그러면 카드가 0.2초씩 어긋난다.
  목소리를 바꾸면 낱말 시각이 전부 달라지므로 여기서 다시 잰다.

어떻게
  나레 13토막을 1초 무음으로 이어 붙여 **한 번만** ASR 에 보낸다
  (토막마다 부르면 최소 과금이 13번 붙는다). 받아 온 낱말을 offset 으로
  토막에 되돌려 나눈다.
"""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

GAP = 1.0                      # 토막 사이 무음 — 낱말이 넘어가 붙지 않게
SM = "https://asr.api.speechmatics.com/v2"


def env(k):
    for ln in io.open(os.path.expanduser(os.path.join('~', '.volcano', '.env')), encoding="utf-8"):
        ln = ln.strip()
        if ln.startswith(k + "="):
            return ln.split("=", 1)[1]
    raise KeyError(k)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())


def build(files, out):
    """토막 + 무음을 이어 붙이고 [(블록번호, 시작, 길이)] 를 돌려준다.

    ★토막을 먼저 48k 모노로 통일한다. 나레 wav 는 스테레오인데 무음을 모노로
      만들어 붙였더니 concat 이 깨져 길이가 31.9초 -> 25.4초로 줄고 낱말 시각이
      블록 사이로 밀렸다. concat demuxer 는 형식이 다르면 그냥 어긋난다.
    """
    tmp = "_narrmono"
    os.makedirs(tmp, exist_ok=True)
    sil = os.path.join(tmp, "_sil.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=48000:cl=mono", "-t", str(GAP),
                    "-c:a", "pcm_s16le", sil], check=True)
    spans, t = [], 0.0
    with io.open("_narrcat.txt", "w", encoding="utf-8") as f:
        for blk, p in files:
            q = os.path.join(tmp, os.path.basename(p))
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", p,
                            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", q], check=True)
            d = dur(q)
            f.write("file '%s'\n" % os.path.abspath(q).replace("\\", "/"))
            f.write("file '%s'\n" % os.path.abspath(sil).replace("\\", "/"))
            spans.append((blk, t, d))
            t += d + GAP
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", "_narrcat.txt", "-ar", "48000", "-ac", "1", out], check=True)
    got = dur(out)
    if abs(got - t) > 0.05:
        raise RuntimeError("이어붙인 길이가 안 맞는다: 계산 %.2f 실제 %.2f" % (t, got))
    return spans, t


def asr(path, key):
    cfg = json.dumps({"type": "transcription",
                      "transcription_config": {"language": "ko", "operating_point": "enhanced"}})
    body, bnd = [], "----volcano%d" % int(time.time())
    def part(name, filename, ctype, data):
        h = '--%s\r\nContent-Disposition: form-data; name="%s"' % (bnd, name)
        if filename:
            h += '; filename="%s"' % filename
        h += "\r\nContent-Type: %s\r\n\r\n" % ctype
        body.append(h.encode() + data + b"\r\n")
    part("config", None, "application/json", cfg.encode())
    part("data_file", os.path.basename(path), "audio/wav", open(path, "rb").read())
    body.append(("--%s--\r\n" % bnd).encode())
    req = urllib.request.Request(SM + "/jobs", data=b"".join(body),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "multipart/form-data; boundary=" + bnd})
    jid = json.load(urllib.request.urlopen(req, timeout=180))["id"]
    print("  ASR 작업 %s — 기다린다" % jid)
    for _ in range(120):
        time.sleep(5)
        r = urllib.request.Request(SM + "/jobs/" + jid,
                                   headers={"Authorization": "Bearer " + key})
        st = json.load(urllib.request.urlopen(r, timeout=60))["job"]["status"]
        if st == "done":
            break
        if st != "running":
            raise RuntimeError("ASR 상태 " + st)
    r = urllib.request.Request(SM + "/jobs/%s/transcript?format=json-v2" % jid,
                               headers={"Authorization": "Bearer " + key})
    return json.load(urllib.request.urlopen(r, timeout=120))


def main():
    files = []
    for p in sorted(os.listdir("blocks")):
        if p.startswith("n") and p.endswith(".wav") and p[1:-4].isdigit():
            files.append((int(p[1:-4]), os.path.join("blocks", p)))
    print("나레 토막 %d개" % len(files))

    spans, total = build(files, "narr_all.wav")
    print("이어붙인 길이 %.1f초" % total)

    # --reuse: 이미 받아 둔 ASR 결과를 다시 쓴다 (나눠 담는 규칙만 고칠 때 — 과금 없음)
    if "--reuse" in sys.argv and os.path.exists("narr_asr.json"):
        print("  ASR 결과를 다시 쓴다 (요청 안 보냄)")
        tr = json.load(io.open("narr_asr.json", encoding="utf-8"))
    else:
        tr = asr("narr_all.wav", env("SPEECHMATICS_API_KEY"))
        json.dump(tr, io.open("narr_asr.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    words = [(w["start_time"], w["end_time"], w["alternatives"][0]["content"])
             for w in tr["results"] if w.get("type") == "word"]
    print("낱말 %d개" % len(words))

    # 낱말을 **가장 가까운 토막**에 붙인다.
    #   구간에 딱 걸치는지로 나누면 각 토막의 첫 낱말이 앞 무음으로 조금 넘어가
    #   어느 쪽에도 안 들어가 사라진다. 낱말 한가운데를 기준으로 거리로 고른다.
    NW = {str(b): [] for b, _, _ in spans}
    for s, e, c in words:
        mid = (s + e) / 2.0
        blk = min(spans, key=lambda sp: max(sp[1] - mid, mid - (sp[1] + sp[2]), 0.0))
        off = blk[1]
        NW[str(blk[0])].append([round(s - off, 3), round(e - off, 3), c])
    json.dump(NW, io.open("narr_words.json", "w", encoding="utf-8"), ensure_ascii=False)

    for blk, off, d in spans:
        g = NW[str(blk)]
        print("  b%-3d %5.2f초  낱말 %d  %s" % (blk, d, len(g), " ".join(x[2] for x in g)))
    miss = [b for b, _, _ in spans if not NW[str(b)]]
    if miss:
        print("★낱말을 못 받은 블록:", miss)
    return 0


if __name__ == "__main__":
    sys.exit(main())
