#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""도너/prproj_lib.py — prproj(gzip+XML 오브젝트 그래프) 다루는 최소 도구.
설계/참고_prproj구조.md 의 규칙만 구현한다. **서버/runner/조립_prproj.py 가 쓰는 라이브러리**(2026-08-17 계단 4).
도너/치환_*.py(보관용 체인)도 같은 것을 쓴다 — 한 벌만 둔다.

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
MAGIC = bytes([0x44, 0x33, 0x22, 0x11])   # 블롭 매직

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
        """여러 블록을 한 번에 제거 (블록 목록 재구성 — 대량 삭제용). 정수 문자열 = ObjectID, 그 외 = ObjectUID."""
        want = set(str(o) for o in oids)
        out, pos, n = [], 0, 0
        for m in BLOCK_RE.finditer(self.xml):
            if m.start() < pos:
                continue
            tag, kind, key = m.group(1), m.group(2), m.group(3)
            end = self.xml.index(f"\n\t</{tag}>", m.start()) + len(f"\n\t</{tag}>")
            if key in want:
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

def rewire(block: str, idmap: dict, uidmap: dict | None = None) -> str:
    """블록 안의 ObjectID / ObjectRef 를 idmap 대로, ObjectUID / ObjectURef 를 uidmap 대로 바꾼다
    (맵에 없는 참조는 그대로 = 공유 오브젝트)."""
    def sub_id(m):
        old = int(m.group(2)); return f'{m.group(1)}="{idmap.get(old, old)}"'
    block = re.sub(r'(ObjectID|ObjectRef)="(\d+)"', sub_id, block)
    if uidmap:
        block = re.sub(r'(ObjectUID|ObjectURef)="([^"]+)"', lambda m: f'{m.group(1)}="{uidmap.get(m.group(2), m.group(2))}"', block)
    return block

def collect_lineage(doc: "Doc", seeds, stop=()) -> tuple[set, set]:
    """seeds(ObjectID int 또는 UID str)에서 ObjectRef/ObjectURef 를 따라가며 닿는 블록 전부(ID 집합, UID 집합).
    stop 에 든 키는 따라가지 않는다(공유 오브젝트 — 예: 원본 mp4 미디어)."""
    ids, uids, todo = set(), set(), list(seeds)
    stop = set(str(x) for x in stop)
    while todo:
        k = todo.pop()
        ks = str(k)
        if ks in stop or ks in ids or ks in uids: continue
        try:
            b = doc.get(k) if ks.isdigit() else doc.get_uid(ks)
        except KeyError:
            continue
        (ids if ks.isdigit() else uids).add(ks)
        todo += re.findall(r'ObjectRef="(\d+)"', b) + re.findall(r'ObjectURef="([^"]+)"', b)
    return ids, uids

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

# ── Source Text 파라미터 찾기 — 이름은 프리미어 UI 언어로 번역돼 저장된다 ──────
#   한글 프리미어에서 도너를 다시 저장했더니 <Name>Source Text</Name> 가 전부
#   <Name>소스 텍스트</Name> 로 바뀌었다(2026-08-19 왕복 시험). 이름 하나만 보면 자막을 통째로 놓친다.
이름_동의어 = {                       # 표준(영문) 이름 → 실제로 나타날 수 있는 이름들
    "Source Text": ("Source Text", "소스 텍스트"),
    "Level": ("Level", "레벨"),
    "Mute": ("Mute", "음소거"),
}
소스텍스트_이름 = 이름_동의어["Source Text"]


def 이름인가(block: str, 표준: str) -> bool:
    """파라미터 블록이 그 이름인가 — UI 언어가 달라도 같은 것으로 본다"""
    return any(f"<Name>{n}</Name>" in block for n in 이름_동의어.get(표준, (표준,)))


def is_source_text(block: str) -> bool:
    return 이름인가(block, "Source Text")


SOURCE_TEXT_RE = "<Name>(?:" + "|".join(소스텍스트_이름) + ")</Name>"


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

def _색읽기(b, st, 슬롯):
    """StyleTable 의 색 슬롯 → [R, G, B]. 색은 **작은 표 하나에 1바이트 3개**로 들어 있다."""
    p = _fpos(b, st, 슬롯)
    if p is None: return None
    t = p + _u32(b, p)
    if not (12 < t < len(b) - 2): return None
    vt = t - _i32(b, t)
    if not (12 <= vt < len(b) - 4): return None
    n = (_u16(b, vt) - 4) // 2
    out = []
    for i in range(min(n, 4)):
        r = _u16(b, vt + 4 + 2 * i)
        out.append(b[t + r] if r else 0)
    return out[:3] if len(out) >= 3 else None


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
            size = None; color = None; stroke = None; stf = _fpos(b, rt, 1)
            if stf is not None:
                st = stf + _u32(b, stf); szp = _fpos(b, st, 1)
                if szp is not None: size = struct.unpack_from("<f", b, szp)[0]
                color = _색읽기(b, st, 2)        # 채움색 — 2026-08-25 규명(진단일지 §26)
                stroke = _색읽기(b, st, 4)       # 테두리색(도너는 전부 검정)
            out["runs"].append({"text": text, "size": size, "color": color, "stroke": stroke})
    fp = _fpos(b, main, 1)
    if fp is not None:
        vec = fp + _u32(b, fp)
        for i in range(_u32(b, vec)):
            el = vec + 4 + 4 * i; out["fonts"].append(_rstr(b, el + _u32(b, el)))
    return out

# ── Source Text 블롭 쓰기 (tail relocation — 재조립 금지, 참고_prproj구조.md 4절) ──
def blob_set_texts(b64: str, texts: list[str]) -> tuple[str, str, dict]:
    """런 텍스트만 바꾼 새 블롭. 반환 (base64, BinaryHash, 재파싱 정보).
    규칙: 문자열은 **항상 버퍼 끝에 새로 붙이고**(4바이트 정렬) 그 런의 참조 오프셋 하나만 돌린다.
    옛 바이트는 죽은 채 남긴다(도너 문자열 슬롯 패딩이 공유 vtable 과 겹칠 수 있어 in-place 금지).
    서식(StyleTable)·폰트 벡터·레이어 테이블은 1바이트도 건드리지 않는다."""
    raw = bytearray(base64.b64decode(re.sub(r"\s+", "", b64)))
    b = bytes(raw)
    assert struct.unpack_from("<Q", b, 0)[0] == len(raw) - 12 and b[8:12] == MAGIC, "블롭 헤더/매직"
    root = 12 + _u32(b, 12); p = _fpos(b, root, 0); main = p + _u32(b, p)
    rp = _fpos(b, main, 0); assert rp is not None, "런 벡터 없음"
    vec = rp + _u32(b, rp); n = _u32(b, vec)
    assert len(texts) == n, f"런 수 {n} != 텍스트 {len(texts)}"
    tfs = []
    for i in range(n):
        el = vec + 4 + 4 * i; rt = el + _u32(b, el); tf = _fpos(b, rt, 0)
        assert tf is not None, f"런 {i} 텍스트 필드 없음"
        tfs.append(tf)
    for tf, text in zip(tfs, texts):
        data = text.encode("utf-8")
        while len(raw) % 4: raw.append(0)
        new_pos = len(raw)
        raw += struct.pack("<I", len(data)) + data + bytes([0])
        while len(raw) % 4: raw.append(0)
        struct.pack_into("<I", raw, tf, new_pos - tf)
    struct.pack_into("<Q", raw, 0, len(raw) - 12)
    out = base64.b64encode(bytes(raw)).decode("ascii")
    info = parse_blob(out)                       # 자가검증: 재파싱
    assert [r["text"] for r in info["runs"]] == texts, "재파싱 텍스트 불일치"
    return out, str(uuid.uuid4())[:28] + f"{len(raw) + 12:08x}", info

def blob_set_fonts(b64: str, font: str) -> tuple[str, str, dict]:
    """폰트 벡터의 모든 항목을 font 로 바꾼 새 블롭 — blob_set_texts 와 같은 tail relocation.
    (확정사실 §6 의 폰트 교체 기법. 문자열을 끝에 붙이고 uoffset 만 돌린다 — 서식은 안 건드린다.)
    2026-09-01 사장님 지시(페이퍼로지 전환)로 도입."""
    raw = bytearray(base64.b64decode(re.sub(r"\s+", "", b64)))
    b = bytes(raw)
    assert struct.unpack_from("<Q", b, 0)[0] == len(raw) - 12 and b[8:12] == MAGIC, "블롭 헤더/매직"
    root = 12 + _u32(b, 12); p = _fpos(b, root, 0); main = p + _u32(b, p)
    fp = _fpos(b, main, 1); assert fp is not None, "폰트 벡터 없음"
    vec = fp + _u32(b, fp); n = _u32(b, vec)
    els = [vec + 4 + 4 * i for i in range(n)]
    data = font.encode("utf-8")
    for el in els:
        while len(raw) % 4: raw.append(0)
        new_pos = len(raw)
        raw += struct.pack("<I", len(data)) + data + bytes([0])
        while len(raw) % 4: raw.append(0)
        struct.pack_into("<I", raw, el, new_pos - el)
    struct.pack_into("<Q", raw, 0, len(raw) - 12)
    out = base64.b64encode(bytes(raw)).decode("ascii")
    info = parse_blob(out)
    assert all(f == font for f in info["fonts"]), "재파싱 폰트 불일치"
    return out, str(uuid.uuid4())[:28] + f"{len(raw) + 12:08x}", info


BLOB_RE = re.compile(r'(<StartKeyframeValue Encoding="base64" BinaryHash=")([^"]+)(">)([^<]+)(</StartKeyframeValue>)', re.S)

# 빈 블롭 — 프리미어는 **같은 내용의 블롭을 두 번 쓰지 않는다**. 둘째부터는 본문 없이
# BinaryHash 만 남기고 먼저 나온 같은 해시의 본문을 가리킨다(2026-08-19 왕복 시험에서 확인:
# 똑같은 대사 자막 「고맙네」 두 개 중 하나가 <StartKeyframeValue .../> 로 비어 있었다).
빈블롭_RE = re.compile(r'<StartKeyframeValue Encoding="base64" BinaryHash="([^"]+)"\s*/>')


def param_blob(block: str, xml: str = None) -> str:
    """블록의 Source Text 블롭(base64). 비어 있으면 xml 안에서 같은 BinaryHash 의 본문을 찾아 온다."""
    m = BLOB_RE.search(block)
    if m:
        return re.sub(r"\s+", "", m.group(4))
    e = 빈블롭_RE.search(block)
    assert e, "Source Text 블롭 없음"
    assert xml, f"빈 블롭(해시 참조) — 본문을 찾으려면 xml 이 필요하다: {e.group(1)}"
    참 = re.search(r'<StartKeyframeValue Encoding="base64" BinaryHash="' + re.escape(e.group(1)) + r'">([^<]+)<', xml)
    assert 참, f"빈 블롭이 가리키는 본문을 못 찾았다: {e.group(1)}"
    return re.sub(r"\s+", "", 참.group(1))

def param_set_blob(block: str, b64: str, binhash: str) -> str:
    return BLOB_RE.sub(lambda m: m.group(1) + binhash + m.group(3) + b64 + m.group(5), block, count=1)

def blob_set_colors(b64: str, colors: list) -> tuple[str, str, dict]:
    """런 채움색만 바꾼 새 블롭. colors[i] = [R,G,B] 또는 None(그대로).

    규칙은 텍스트 치환과 같다 — **색 표를 버퍼 끝에 새로 만들고**(원본 표를 복사해 3바이트만 고친다)
    그 런의 참조 오프셋 하나만 돌린다. 원본 표는 다른 런·다른 큐가 함께 쓸 수 있으므로 **제자리 수정 금지**.
    반환 (base64, BinaryHash, 재파싱 정보)."""
    raw = bytearray(base64.b64decode(re.sub(r"\s+", "", b64)))
    b = bytes(raw)
    assert struct.unpack_from("<Q", b, 0)[0] == len(raw) - 12 and b[8:12] == MAGIC, "블롭 헤더/매직"
    root = 12 + _u32(b, 12); p = _fpos(b, root, 0); main = p + _u32(b, p)
    rp = _fpos(b, main, 0); assert rp is not None, "런 벡터 없음"
    vec = rp + _u32(b, rp); n = _u32(b, vec)
    assert len(colors) == n, f"런 수 {n} != 색 {len(colors)}"
    for i, rgb in enumerate(colors):
        if rgb is None: continue
        b = bytes(raw)
        el = vec + 4 + 4 * i; rt = el + _u32(b, el)
        stf = _fpos(b, rt, 1); assert stf is not None, f"런 {i} StyleTable 없음"
        st = stf + _u32(b, stf)
        cp = _fpos(b, st, 2); assert cp is not None, f"런 {i} 색 슬롯(f2) 없음"
        t = cp + _u32(b, cp); vt = t - _i32(b, t)
        vs = _u16(b, vt); ts = _u16(b, vt + 2)
        while len(raw) % 4: raw.append(0)
        new_vt = len(raw); raw += bytes(b[vt:vt + vs])          # vtable 복사
        while len(raw) % 4: raw.append(0)
        new_t = len(raw); raw += bytes(b[t:t + max(ts, 4)])      # 표 본체 복사
        struct.pack_into("<i", raw, new_t, new_t - new_vt)       # 새 vtable 을 가리키게
        for k in range(3):                                       # R·G·B 세 바이트
            r = _u16(bytes(raw), new_vt + 4 + 2 * k)
            if r: raw[new_t + r] = int(rgb[k]) & 0xFF
        struct.pack_into("<I", raw, cp, new_t - cp)              # 런 → 새 색 표
    struct.pack_into("<Q", raw, 0, len(raw) - 12)
    out = base64.b64encode(bytes(raw)).decode("ascii")
    info = parse_blob(out)
    for i, rgb in enumerate(colors):
        if rgb is not None:
            assert info["runs"][i]["color"] == list(rgb), f"재파싱 색 불일치 런 {i}: {info['runs'][i]['color']} != {rgb}"
    return out, str(uuid.uuid4())[:28] + f"{len(raw) + 12:08x}", info


def split_runs_words(text: str, n: int) -> list[str]:
    """[B안] 텍스트를 런 n개로 나누되 **단어 경계에서만** 자른다(중간 끊김 방지).
    단어 수가 런 수보다 적으면 첫 런에 전부 넣고 나머지는 빈 런(맛보기에서 빈 런 정상 확인).
    런은 같은 폰트·크기라 이어 보인다.
    ※ 조립기는 2026-08-26부터 이 함수를 쓰지 않는다 — 런은 **강조 구간**으로 나눈다
      (조립_prproj.런배분 · 규격 「자막.강조」). 이 함수는 계단 3 치환 체인이 쓴다."""
    if n <= 1:
        return [text]
    parts = re.split(r"(\s+)", text)
    toks, i = [], 0
    while i < len(parts):
        w = parts[i]; sp = parts[i + 1] if i + 1 < len(parts) else ""
        if w: toks.append(w + sp)
        elif sp and toks: toks[-1] += sp
        i += 2
    if len(toks) < n:
        return [text] + [""] * (n - 1)
    out, target = [], len(text) / n
    for r in range(n):
        left = n - r - 1
        cur = ""
        while toks and (len(cur) < target or len(toks) <= left) and not (len(toks) <= left and cur):
            if len(toks) <= left and cur: break
            cur += toks.pop(0)
            if len(cur) >= target and len(toks) > left: break
        out.append(cur)
    if toks: out[-1] += "".join(toks)
    return out

def split_runs(text: str, n: int) -> list[str]:
    """텍스트를 런 n개로 나눈다(같은 폰트·크기라 이어 보인다). n=1 이면 그대로."""
    if n <= 1: return [text]
    cut = max(1, round(len(text) / n))
    parts = [text[:cut]] + [""] * (n - 1)
    rest = text[cut:]
    step = max(1, round(len(rest) / (n - 1))) if n > 2 else len(rest)
    for i in range(1, n):
        parts[i] = rest[:step] if i < n - 1 else rest
        rest = rest[step:]
    return parts

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
    blobs = re.findall(SOURCE_TEXT_RE + r'.*?<StartKeyframeValue Encoding="base64" BinaryHash="([^"]+)">([^<]+)</StartKeyframeValue>', xml, re.S)
    빈참조 = len(빈블롭_RE.findall(xml))       # 해시로 앞의 본문을 가리키는 블롭(프리미어가 만든 중복 제거)
    nbad = 0; nhash = 0
    for h, b64 in blobs:
        try:
            info = parse_blob(re.sub(r"\s+", "", b64))
            if int(h[-8:], 16) != info["len"] + 12: nhash += 1
        except Exception:
            nbad += 1
    ok("Source Text 블롭 재파싱", nbad == 0 and nhash == 0, f"{len(blobs)}개 · 파싱 실패 {nbad} · BinaryHash 길이 불일치 {nhash}" + (f" · 해시 참조 {빈참조}" if 빈참조 else ""))
    # 6 gzip 왕복
    again = gzip.decompress(gzip.compress(xml.encode("utf-8"), 9, mtime=0)).decode("utf-8")
    ok("gzip 왕복 동일", again == xml, hashlib.md5(xml.encode("utf-8")).hexdigest()[:12])
    return {"pass": all(c["pass"] for c in checks), "checks": checks}
