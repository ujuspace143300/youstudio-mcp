#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도너/prproj_lib.py — prproj(gzip+XML 오브젝트 그래프) 다루는 최소 도구.
설계/참고_prproj구조.md 의 규칙만 구현한다. 계단 3 실험용 — 통과하면 서버(export)로 옮긴다.

- load/save: gzip ↔ XML 문자열 (레벨 9, mtime 0)
- Doc: 루트 블록(\t<Tag ObjectID|ObjectUID="…"> … \t</Tag>) 단위로 get/replace/remove/append
- 틱: TPS 254016000000, 23.976 프레임 틱 10594584000, 프레임 스냅 = round(초×24000/1001)×프레임틱
- verify: 검증 규칙 7개 (ID 유일·댕글링 0·트랙 수·겹침 0·경로 실존·블롭 재파싱·gzip 왕복)
"""
from __future__ import annotations
import gzip, re, os, uuid, struct, base64, hashlib, json

TPS = 254016000000
FRAME_TICKS = 10594584000          # 23.976
SEQ_AUDIO_RATE = 5292000            # 48k
GRAPHIC_IN = 914457600000000        # 3600s

def frame_ticks(sec: float) -> int:
    return round(sec * 24000 / 1001) * FRAME_TICKS

def load(path: str) -> str:
    raw = open(path, "rb").read()
    assert raw[:2] == b"\x1f\x8b", "gzip 아님"
    return gzip.decompress(raw).decode("utf-8")

def save(path: str, xml: str) -> None:
    open(path, "wb").write(gzip.compress(xml.encode("utf-8"), 9, mtime=0))

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\r", "&#13;")

BLOCK_RE = re.compile(r'^\t<(\w+) (ObjectID|ObjectUID)="([^"]+)"[^>]*>', re.M)

class Doc:
    """루트 오브젝트 블록 저장소. xml 문자열을 그대로 들고 블록 단위로 편집한다."""
    def __init__(self, xml: str):
        self.xml = xml
    def _find(self, attr: str, key: str):
        m = re.search(rf'^\t<(\w+) [^>]*{attr}="{re.escape(str(key))}"', self.xml, re.M)
        if not m:
            raise KeyError(f"{attr}={key}")
        tag = m.group(1)
        end = self.xml.index(f"\n\t</{tag}>", m.start()) + len(f"\n\t</{tag}>")
        return m.start(), end, tag
    def get(self, oid) -> str:
        s, e, _ = self._find("ObjectID", oid); return self.xml[s:e]
    def get_uid(self, uid) -> str:
        s, e, _ = self._find("ObjectUID", uid); return self.xml[s:e]
    def replace(self, oid, text: str):
        s, e, _ = self._find("ObjectID", oid); self.xml = self.xml[:s] + text + self.xml[e:]
    def replace_uid(self, uid, text: str):
        s, e, _ = self._find("ObjectUID", uid); self.xml = self.xml[:s] + text + self.xml[e:]
    def remove_many(self, oids) -> int:
        """여러 ObjectID 블록을 한 번에 제거 (블록 목록 재구성 — 대량 삭제용)."""
        want = set(str(o) for o in oids)
        out, pos, n = [], 0, 0
        for m in BLOCK_RE.finditer(self.xml):
            if m.start() < pos:
                continue
            tag, kind, key = m.group(1), m.group(2), m.group(3)
            end = self.xml.index(f"\n\t</{tag}>", m.start()) + len(f"\n\t</{tag}>")
            if kind == "ObjectID" and key in want:
                out.append(self.xml[pos:m.start()])
                pos = end + 1 if self.xml[end:end + 1] == "\n" else end
                n += 1
        out.append(self.xml[pos:])
        self.xml = "".join(out)
        return n
    def append(self, blocks) -> None:
        anchor = self.xml.rindex("</PremiereData>")
        self.xml = self.xml[:anchor] + "".join(b.strip("\n") + "\n" for b in blocks) + self.xml[anchor:]
    def max_id(self) -> int:
        return max(int(m) for m in re.findall(r'^\t<\w+ ObjectID="(\d+)"', self.xml, re.M))

def child(block: str, tag: str):
    m = re.search(rf"<{re.escape(tag)}>([^<]*)</{re.escape(tag)}>", block)
    return m.group(1) if m else None

def set_child(block: str, tag: str, value: str) -> str:
    pat = re.compile(rf"(<{re.escape(tag)}>)[^<]*(</{re.escape(tag)}>)")
    assert pat.search(block), f"<{tag}> 없음"
    return pat.sub(lambda m: m.group(1) + value + m.group(2), block, count=1)

def rewire(block: str, idmap: dict) -> str:
    """블록 안의 ObjectID / ObjectRef 를 idmap 대로 바꾼다 (idmap 에 없는 참조는 그대로 = 공유 오브젝트)."""
    def sub_id(m):
        old = int(m.group(2)); return f'{m.group(1)}="{idmap.get(old, old)}"'
    return re.sub(r'(ObjectID|ObjectRef)="(\d+)"', sub_id, block)

def track_set_items(doc: Doc, track_uid: str, refs, transitions=None) -> None:
    blk = doc.get_uid(track_uid)
    def section(blk, name, refs):
        inner = "".join(f'\n\t\t\t\t\t<TrackItem Index="{i}" ObjectRef="{r}"/>' for i, r in enumerate(refs))
        m = re.search(rf'<{name} Version="3">(.*?)</{name}>', blk, re.S)
        assert m, name
        body = m.group(1)
        new_body = re.sub(r'<TrackItems Version="1">.*?</TrackItems>',
                          f'<TrackItems Version="1">{inner}\n\t\t\t\t</TrackItems>', body, count=1, flags=re.S)
        assert new_body != body or not refs or inner in body, name
        return blk[:m.start(1)] + new_body + blk[m.end(1):]
    blk = section(blk, "ClipItems", refs)
    if transitions is not None:
        blk = section(blk, "TransitionItems", transitions)
    doc.replace_uid(track_uid, blk)

def track_items(doc: Doc, track_uid: str):
    blk = doc.get_uid(track_uid)
    m = re.search(r'<ClipItems Version="3">(.*?)</ClipItems>', blk, re.S)
    clips = [int(x) for x in re.findall(r'<TrackItem Index="\d+" ObjectRef="(\d+)"/>', m.group(1))]
    m2 = re.search(r'<TransitionItems Version="3">(.*?)</TransitionItems>', blk, re.S)
    trans = [int(x) for x in re.findall(r'<TrackItem Index="\d+" ObjectRef="(\d+)"/>', m2.group(1))] if m2 else []
    return clips, trans

# ── Source Text 블롭 (읽기 전용 파서 — 검증용) ─────────────────────────────
def _u32(b, o): return struct.unpack_from("<I", b, o)[0]
def _i32(b, o): return struct.unpack_from("<i", b, o)[0]
def _u16(b, o): return struct.unpack_from("<H", b, o)[0]
def _fpos(b, t, i):
    vt = t - _i32(b, t); n = (_u16(b, vt) - 4) // 2
    if i >= n: return None
    r = _u16(b, vt + 4 + 2 * i); return t + r if r else None
def _rstr(b, p):
    n = _u32(b, p); return b[p + 4:p + 4 + n].decode("utf-8")

def parse_blob(b64: str) -> dict:
    raw = base64.b64decode(b64); b = raw
    assert struct.unpack_from("<Q", b, 0)[0] == len(raw) - 12, "헤더 길이 불일치"
    assert b[8:12] == b"\x44\x33\x22\x11", "매직 불일치"
    root = 12 + _u32(b, 12); p = _fpos(b, root, 0); main = p + _u32(b, p)
    out = {"runs": [], "fonts": [], "len": len(raw)}
    rp = _fpos(b, main, 0)
    if rp is not None:
        vec = rp + _u32(b, rp)
        for i in range(_u32(b, vec)):
            el = vec + 4 + 4 * i; rt = el + _u32(b, el); tf = _fpos(b, rt, 0)
            text = _rstr(b, tf + _u32(b, tf)) if tf else ""
            size = None; stf = _fpos(b, rt, 1)
            if stf is not None:
                st = stf + _u32(b, stf); szp = _fpos(b, st, 1)
                if szp is not None: size = struct.unpack_from("<f", b, szp)[0]
            out["runs"].append({"text": text, "size": size})
    fp = _fpos(b, main, 1)
    if fp is not None:
        vec = fp + _u32(b, fp)
        for i in range(_u32(b, vec)):
            el = vec + 4 + 4 * i; out["fonts"].append(_rstr(b, el + _u32(b, el)))
    return out

# ── 검증 규칙 7개 ────────────────────────────────────────────────────────────
def verify(path: str, expect_tracks: dict | None = None) -> dict:
    """expect_tracks: {"V1": (track_uid, n), ...}. 반환 {'pass': bool, 'checks': [...]}"""
    xml = load(path)
    checks = []
    def ok(name, cond, detail=""):
        checks.append({"check": name, "pass": bool(cond), "detail": detail})
    # 1 ID 유일 · 댕글링 0
    root_ids = re.findall(r'^\t<\w+ ObjectID="(\d+)"', xml, re.M)
    uids = re.findall(r'^\t<\w+ ObjectUID="([^"]+)"', xml, re.M)
    ok("루트 ObjectID 유일", len(root_ids) == len(set(root_ids)), f"{len(root_ids)}개")
    ok("ObjectUID 유일", len(uids) == len(set(uids)), f"{len(uids)}개")
    idset = set(re.findall(r'ObjectID="(\d+)"', xml)); uidset = set(re.findall(r'ObjectUID="([^"]+)"', xml))
    dang = sorted(set(re.findall(r'ObjectRef="(\d+)"', xml)) - idset, key=int)
    dangu = sorted(set(re.findall(r'ObjectURef="([^"]+)"', xml)) - uidset)
    ok("댕글링 ObjectRef 0", not dang, f"{dang[:10]}")
    ok("댕글링 ObjectURef 0", not dangu, f"{dangu[:5]}")
    # 2·3 트랙 수 · 겹침
    doc = Doc(xml)
    if expect_tracks:
        for label, (uid, n) in expect_tracks.items():
            clips, trans = track_items(doc, uid)
            ok(f"트랙 {label} 클립 수 = {n}", len(clips) == n, f"실제 {len(clips)} (전환 {len(trans)})")
            spans = []
            for c in clips:
                b = doc.get(c); m = re.search(r"<TrackItem Version=\"4\">(.*?)</TrackItem>", b, re.S)
                st = int(child(m.group(1), "Start") or 0); en = int(child(m.group(1), "End") or 0)
                spans.append((st, en))
            spans.sort()
            overl = [(a, b) for a, b in zip(spans, spans[1:]) if b[0] < a[1]]
            bad = [s for s in spans if s[1] <= s[0]]
            ok(f"트랙 {label} 겹침 0 · 길이 > 0", not overl and not bad, f"겹침 {len(overl)} 비정상 {len(bad)}")
    # 4 경로 실존
    paths = set(re.findall(r"<(?:FilePath|ActualMediaFilePath)>([^<]+)<", xml))
    missing = [p for p in paths if re.match(r"^[A-Za-z]:\\", p) and not os.path.exists(p)]
    ok("미디어 경로 실존", not missing, f"경로 {len([p for p in paths if re.match(r'^[A-Za-z]:', p)])}개 · 없음 {missing[:3]}")
    # 5 블롭 재파싱
    blobs = re.findall(r'<Name>Source Text</Name>.*?<StartKeyframeValue Encoding="base64" BinaryHash="([^"]+)">([^<]+)</StartKeyframeValue>', xml, re.S)
    nbad = 0; nhash = 0
    for h, b64 in blobs:
        try:
            info = parse_blob(re.sub(r"\s+", "", b64))
            if int(h[-8:], 16) != info["len"] + 12: nhash += 1
        except Exception:
            nbad += 1
    ok("Source Text 블롭 재파싱", nbad == 0 and nhash == 0, f"{len(blobs)}개 · 파싱 실패 {nbad} · BinaryHash 길이 불일치 {nhash}")
    # 6 gzip 왕복
    again = gzip.decompress(gzip.compress(xml.encode("utf-8"), 9, mtime=0)).decode("utf-8")
    ok("gzip 왕복 동일", again == xml, hashlib.md5(xml.encode("utf-8")).hexdigest()[:12])
    return {"pass": all(c["pass"] for c in checks), "checks": checks}
