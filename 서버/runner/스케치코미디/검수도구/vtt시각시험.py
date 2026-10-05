# 원본 전사 vtt 뒤집힌 시각 시험 (2026-10-05 루키치8 «00:00:00.000 --> -1:59:59.850»)
#
#   사건: 자막띠시각.맞춤() 이 예상 시작이 0 앞인 줄의 시작만 0 으로 자르고 끝은 자르기 전 시작으로 재
#         끝이 음수(−0.15초)가 됐다. 읽는 쪽 정규식은 그 줄을 말없이 버렸다(work 8편).
#   시험: work 의 «맞춤 전» 원문(.ko.vtt.맞춤전)을 scratch 로 옮겨 고친 맞춤을 다시 돌린다(카드는 원본 옆 캐시만 —
#         캐시 열쇠가 안 맞는 편은 건너뜀, 다시 재지 않는다).
#     ① 사건 8편 — 뒤집힌 줄 0
#     ② 사건 8편·정상 편 — 뒤집혔던 줄 말고는 지금 work 의 vtt 와 줄마다 같다(회귀 없음)
#     ③ 쓰기() 관문 — 뒤집힌 줄을 주면 멈춘다
#   쓰는 법: python 검수도구/vtt시각시험.py [작업폴더=~/Desktop/스케치코미디/work]
import glob, json, os, re, shutil, sys, tempfile

여기 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(여기))
from s2pipe import 자막띠시각 as Z

work = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/Desktop/스케치코미디/work")
사건 = ["루키치1", "루키치8", "루키치28", "루키치248", "싱글146", "싱글164", "싱글239", "싱글273"]
정상 = ["루키치2", "루키치3", "루키치5", "루키치9", "루키치20", "루키치30", "루키치100", "루키치200", "싱글50", "싱글150"]

PAT = re.compile(r"(-?\d+):(\d+):([\d.]+) --> (-?\d+):(\d+):([\d.]+)\n(.+)")


def 줄들(txt):
    out = []
    for m in PAT.finditer(txt):
        a = (-1 if m[1].startswith("-") else 1, abs(int(m[1])) * 3600 + int(m[2]) * 60 + float(m[3]))
        b = (-1 if m[4].startswith("-") else 1, abs(int(m[4])) * 3600 + int(m[5]) * 60 + float(m[6]))
        out.append((m[1].startswith("-") or m[4].startswith("-"), a[1], b[1], m[7]))
    return out


def 캐시맞음(src):
    try:
        c = json.load(open(Z.캐시경로(src), encoding="utf-8"))
        st = os.stat(src)
        return c.get("key") == f"{Z.판}:{st.st_size}:{int(st.st_mtime)}:{Z.FPS}:{Z.W}x{Z.H}"
    except (OSError, ValueError):
        return False


틀림 = 0
잰편 = 0
잰사건 = 0
tmp = tempfile.mkdtemp(prefix="vtt시각시험_")
for slug in 사건 + 정상:
    src = os.path.join(work, slug + ".mp4")
    전 = os.path.join(work, slug + ".ko.vtt.맞춤전")
    지금 = os.path.join(work, slug + ".ko.vtt")
    if not (os.path.exists(src) and os.path.exists(전) and os.path.exists(지금)):
        print(f"  {slug}: 자료 없음 — 건너뜀")
        continue
    if not 캐시맞음(src):
        print(f"  {slug}: 카드 캐시 열쇠 안 맞음 — 건너뜀(다시 재지 않는다)")
        continue
    v = os.path.join(tmp, slug + ".ko.vtt")
    shutil.copy(전, v)
    결과 = Z.실행(src, v, 반영=True, log=lambda *_: None)
    잰편 += 1
    잰사건 += slug in 사건
    새 = 줄들(open(v, encoding="utf-8").read())
    옛 = 줄들(open(지금, encoding="utf-8").read())
    뒤집 = [x for x in 새 if x[0] or x[2] <= x[1]]
    옛뒤집 = [i for i, x in enumerate(옛) if x[0] or x[2] <= x[1]]
    다름 = 0
    if len(새) != len(옛):
        다름 = abs(len(새) - len(옛))
    else:
        for i, (a, b) in enumerate(zip(새, 옛)):
            if i in 옛뒤집:
                continue
            if abs(a[1] - b[1]) > 0.005 or abs(a[2] - b[2]) > 0.005 or a[3] != b[3]:
                다름 += 1
    판 = "통과" if not 뒤집 and not 다름 else "틀림"
    if 판 == "틀림":
        틀림 += 1
    고친 = [(round(새[i][1], 2), round(새[i][2], 2)) for i in 옛뒤집 if i < len(새)]
    print(f"  {slug}: {'사건' if slug in 사건 else '정상'} · 채택 {결과 and 결과.get('채택')} · 뒤집힌 줄 {len(뒤집)} "
          f"(옛 vtt {len(옛뒤집)} → 고친 시각 {고친}) · 그 밖에 바뀐 줄 {다름} · {판}")
    if slug in 사건 and not 옛뒤집:
        print(f"    ★{slug}: 사건 편인데 옛 vtt 에 뒤집힌 줄이 없다 — 표본 확인")
        틀림 += 1

# ③ 쓰기 관문
try:
    Z.쓰기(os.path.join(tmp, "관문.vtt"), "WEBVTT\n\nNOTE x\n\n", [(0.0, -0.15, "흐헤헤")])
    print("  쓰기 관문: 뒤집힌 줄을 썼다 — 틀림")
    틀림 += 1
except ValueError as e:
    print(f"  쓰기 관문: 멈춤 ✓ ({e})")
shutil.rmtree(tmp, ignore_errors=True)
print(f"잰 편 {잰편}(사건 {잰사건}) · 틀림 {틀림}")
sys.exit(0 if 틀림 == 0 and 잰사건 >= 3 else 1)   # 원본 mp4 가 지워진 사건 편은 못 잰다(2026-10-05 남은 것 3편)
