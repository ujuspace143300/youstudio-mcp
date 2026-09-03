# Speechmatics 로 대사와 **정확한 타임스탬프**를 받는다.
#
#   python -m s2pipe.asr projects/<slug>.json
#
# 왜 Gemini 만 쓰지 않는가:
#   - Gemini 는 화면을 보고 시각을 **추정**한다. ASR 은 음성 신호에서 **직접** 잰다
#   - Gemini 무료 티어는 모델당 하루 20요청이다. 전사를 ASR 로 넘기면 그만큼 아낀다
#   반대로 ASR 이 못 하는 것:
#   - 대사가 없는 구간의 상황 자막 — 화면을 못 본다. 그건 Gemini 몫이다
import json, os, subprocess, sys, time, urllib.request, urllib.error, uuid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)
KEY = open(os.path.expanduser("~/.volcano/keys/speechmatics"), encoding="utf-8").read().strip()
API = "https://asr.api.speechmatics.com/v2/jobs"


def multipart(fields, files):
    """urllib 으로 multipart 를 직접 만든다(requests 의존을 안 만든다)."""
    b = "----sketch" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (name, data, ctype) in files.items():
        out.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                   f"filename=\"{name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
        out.append(data)
        out.append(b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={b}"


def req(url, data=None, ctype=None, method=None):
    h = {"Authorization": f"Bearer {KEY}"}
    if ctype:
        h["Content-Type"] = ctype
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=300) as res:
        return json.loads(res.read().decode())


def submit(audio_path, lang="ko"):
    cfg = {"type": "transcription",
           "transcription_config": {"language": lang,
                                    "operating_point": "enhanced",
                                    "enable_entities": False}}
    data, ctype = multipart({"config": json.dumps(cfg)},
                            {"data_file": (os.path.basename(audio_path),
                                           open(audio_path, "rb").read(), "audio/wav")})
    return req(API, data, ctype)["id"]


def wait(job_id, every=6, limit=900):
    t0 = time.time()
    while time.time() - t0 < limit:
        s = req(f"{API}/{job_id}")["job"]["status"]
        if s == "done":
            return True
        if s in ("rejected", "expired"):
            print(f"  작업 실패: {s}")
            return False
        print(f"  {s}… {int(time.time()-t0)}초", flush=True)
        time.sleep(every)
    return False


def words_of(job_id):
    tr = req(f"{API}/{job_id}/transcript?format=json-v2")
    out = []
    for r in tr.get("results", []):
        alts = r.get("alternatives") or []
        if not alts:
            continue
        out.append({"t": r["start_time"], "e": r["end_time"],
                    "w": alts[0]["content"], "type": r.get("type", "word")})
    return out


def to_lines(words, max_chars, gap=0.55):
    """단어를 자막 줄로 묶는다 — 말 쉼(gap)이 1순위. 글자수에 걸리면 문장 한중간을
    싹둑 자르지 않고 ★뭉치 안에서 가장 크게 쉰 자리로 되끊는다(2026-09-03,
    «…다음 / 주까지야» «잠 / 오는 사람» 실측 후 개정)."""
    lines, cur = [], []                       # cur: [{"w","t","e"}...]

    def emit(part):
        if part:
            lines.append({"t": round(part[0]["t"], 2), "text": " ".join(x["w"] for x in part)})

    for i, w in enumerate(words):
        if w["type"] == "punctuation":
            if cur:
                cur[-1]["w"] += w["w"]
            continue
        cur.append({"w": w["w"], "t": w["t"], "e": w["e"]})
        nxt = next((x for x in words[i + 1:] if x["type"] != "punctuation"), None)
        if nxt is None or (nxt["t"] - w["e"]) >= gap:
            emit(cur)
            cur = []
        elif len(" ".join(x["w"] for x in cur)) >= max_chars:
            if len(cur) > 1:
                gaps = [cur[k + 1]["t"] - cur[k]["e"] for k in range(len(cur) - 1)]
                k = max(range(len(gaps)), key=lambda j: gaps[j])
                emit(cur[:k + 1])
                cur = cur[k + 1:]
            else:
                emit(cur)
                cur = []
    emit(cur)
    return lines


def main():
    if len(sys.argv) < 2:
        print("python -m s2pipe.asr projects/<slug>.json")
        return 1
    pj = sys.argv[1]
    proj = json.load(open(pj, encoding="utf-8"))
    cut = os.path.join(HERE, CFG["paths"]["work"], proj["slug"], "cut.mp4")
    if not os.path.exists(cut):
        print(f"잘라 붙인 영상이 없다: {cut}")
        return 1

    # ★길이 정합 게이트(2026-09-03 Deep04: keep=False 조각이 구워져 3.7초 어긋남) —
    #   유료 전사에 돈을 태우기 전에, 완성본 길이 = 계획(keep 합)인지 먼저 확인한다.
    kept = sum(x["t1"] - x["t0"] for x in proj.get("segments", []) if x.get("keep", True))
    cd = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", cut], capture_output=True, text=True)
    try:
        cdur = float(cd.stdout.strip())
    except ValueError:
        cdur = 0.0
    if kept and abs(cdur - kept) > 0.8:
        print(f"★완성본 {cdur:.1f}s ≠ 계획 {kept:.1f}s — 굽기가 낡았거나 조각이 어긋났다."
              f"\n  make 굽기를 다시 돌려라. (유료 전사 전에 멈춤)")
        return 1

    wav = os.path.join(os.path.dirname(cut), "cut.wav")
    # ★완성본이 새로 구워졌으면 옛 wav 를 버린다(2026-09-03 — 낡은 소리를 전사한 실측)
    if os.path.exists(wav) and os.path.getmtime(wav) < os.path.getmtime(cut):
        os.remove(wav)
    if not os.path.exists(wav):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", cut,
                        "-vn", "-ac", "1", "-ar", "16000", "-y", wav], check=True)
    mb = os.path.getsize(wav) / 1024 / 1024
    print(f"오디오 {mb:.1f}MB — Speechmatics 로 보낸다", flush=True)

    job = submit(wav)
    print(f"  job {job}", flush=True)
    if not wait(job):
        return 1
    words = words_of(job)
    lines = to_lines(words, CFG["layout"]["subtitle"]["max_chars"])

    # ★단어도 남긴다. 줄로 뭉쳐 두면 **단어 단위 정렬**을 못 한다 — `s2pipe.sync` 가
    #   모델 자막의 시각을 여기에 맞춘다.
    proj["asr_words"] = words
    proj["subs_asr"] = lines
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    gaps = [(lines[i-1]["t"], lines[i]["t"]) for i in range(1, len(lines))
            if lines[i]["t"] - lines[i-1]["t"] >= 3.0]
    print(f"\n단어 {len(words)}개 → 자막 {len(lines)}줄")
    print(f"3초 이상 비는 곳 {len(gaps)}군데" + (f" (예: {gaps[0][0]:.0f}~{gaps[0][1]:.0f}초)" if gaps else ""))
    print("\n앞 12줄:")
    for l in lines[:12]:
        print(f"  {l['t']:6.1f}  {l['text']}")
    print(f"\n저장: {pj}  (`subs_asr` 필드 — 기존 `subs` 는 그대로 뒀다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
