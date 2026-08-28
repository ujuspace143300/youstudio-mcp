# 화면에 얹을 **댓글만** 다시 고른다. 요금이 나가지 않는다 — yt-dlp 만 쓴다.
#
# ★이 채널은 댓글이 생명이다. 자막처럼 계속 갈아 끼워야 읽는 재미가 산다 —
#   댓글이 두어 개뿐이면 build 가 편 전체에 균등 배치하므로 하나가 30초 넘게 떠 있고,
#   그러면 읽을 게 없어 지루해진다.
#
# 규격을 고쳤거나 원본 댓글을 더 받고 싶을 때 이것만 돌린다. 대본·구간은 건드리지 않는다.
#
#   python -m s2pipe.comments projects/<편>.json
#   python -m s2pipe.comments projects/<편>.json --refetch   # 원본 댓글을 다시 받는다
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from .cfg import CFG  # 작업 폴더의 생성 config (--config 또는 S2_CONFIG)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from .plan import pick_comments                          # noqa: E402


def refetch(vid, work, url):
    """원본 댓글을 다시 받는다. ★yt-dlp 는 info.json 이 있으면 건너뛰므로 지우고 받는다."""
    info = os.path.join(work, f"{vid}.info.json")
    if os.path.exists(info):
        os.remove(info)
    r = subprocess.run(["yt-dlp", "--encoding", "utf-8", "--skip-download",
                        "--write-comments", "--extractor-args",
                        "youtube:comment_sort=top;max_comments=120,120,0,0",
                        "-o", os.path.join(work, "%(id)s.%(ext)s"), url],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not os.path.exists(info):
        why = [ln for ln in (r.stderr or "").splitlines() if "ERROR" in ln]
        print("  댓글을 다시 받지 못했다" + (f" — {why[-1].strip()}" if why else ""))
    return info


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("python -m s2pipe.comments <프로젝트.json> [--refetch]")
        return 1
    pj = args[0] if os.path.isabs(args[0]) else os.path.join(HERE, args[0])
    proj = json.load(open(pj, encoding="utf-8"))
    vid = proj["source"]["id"]
    work = os.path.join(HERE, CFG["paths"]["work"])
    info = os.path.join(work, f"{vid}.info.json")

    if "--refetch" in sys.argv or not os.path.exists(info):
        print("원본 댓글을 받는 중…", flush=True)
        info = refetch(vid, work, proj["source"]["url"])

    got = len((json.load(open(info, encoding="utf-8")).get("comments") or [])) \
        if os.path.exists(info) else 0
    dur = proj.get("_est_sec") or sum(s["t1"] - s["t0"]
                                      for s in proj["segments"] if s.get("keep", True))
    old = len(proj.get("comments", []))
    # ★계획 때 모델이 고른 순서가 있으면 그대로 따른다(그 편에 어울리는 것들이다)
    proj["comments"] = pick_comments(info, dur, proj.get("comment_picks"))
    json.dump(proj, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    cm = CFG["layout"]["comment"]
    n = len(proj["comments"])
    print(f"원본 댓글 {got}개 → 화면에 쓸 것 {old} → {n}개"
          f"  ({dur/max(n,1):.1f}초에 하나 · 목표 {cm.get('sec_each', 6.0)}초)")
    for c in proj["comments"][:6]:
        print(f"  {c['likes']:>6} {c['text']}")
    if n > 6:
        print(f"  … 그 밖 {n - 6}개")
    if n < dur / cm.get("sec_each", 6.0) * 0.7:
        print("  ★목표보다 적다 — 원본에 쓸 만한 댓글이 모자란다(--refetch 로 더 받아 본다)")
    print(f"\n저장: {pj}\n★대본이 바뀌었으니 다시 검사해야 제작할 수 있다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
