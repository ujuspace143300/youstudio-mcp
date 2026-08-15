/**
 * steps/subtitle.ts — 자막 타이밍 + 컷 타임라인. 명세: 설계/단계상세.md 「7. subtitle」 (결정 A~F, 2026-08-16)
 *
 * 두 번 부른다:
 *   ① payload.translations 가 없으면 → 타임라인을 짜고, 자막이 필요한 원어 대사 줄을 모아 need_input(번역) 으로 멈춘다.
 *      줄 수가 규격 「자막.대사_줄수_대화안_상한」을 넘으면 need_input 대신 jobs_kind:"judge"(EvoLink) 로 번역을 내보낸다.
 *   ② payload.translations 가 있으면 → 큐를 만들고 게이트(G-자막·G-죽은시간)를 재서 timeline.json + srt 3종을 write_files 로 쓴다.
 *
 * 타임라인 규칙(규격 「조립」): 화면 레인 = 구간 순서. 나레는 항상 그림 위.
 *   over → 시각몽타주는 균등, 대사 있는 역할은 발화 틈 · before/after → 인접 구간이 붙어 있고 대사 없으면 겹침, 아니면 원본 연장(덕킹) · bridge → 브리지 원본에서 컷 삽입(앵커 = 판정 장면)
 * 나레 큐는 voice 의 글자별 시각(chars_t)으로 자른다 — 없으면 글자 비례.
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import answer from "../../../스타일/영화롱폼/정답지.json";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";
import type { JudgeJob } from "../schema.js";

interface SubSpec { 나레_한줄_최대자수: number; 대사_한줄_최대자수: number; 큐_최소길이_s: number; 큐_최대길이_s: number; 대사큐_꼬리_s: number; 큐_사이_최소간격_s: number; 대사_줄수_대화안_상한: number; 대사_구두점: string; 번역_문체: string; 폰트: Record<string, unknown> }
interface AsmSpec { over_배치: Record<string, string>; before_after: Record<string, string>; 브리지_컷: { 사용: boolean; 패딩_s: number; 앵커: string }; 죽은시간_홀드_제외_역할: string[]; 덕킹_역할: string[]; 죽은시간_컷: { 사용: boolean; 임계_s: number; 앞_남김_s: number; 뒤_남김_s: number; 대상_역할: string[] } }
interface JudgeTextSpec { backend: string; 모델: string; 엔드포인트: string; 키_환경변수: string; 온도: number; thinkingBudget: number; maxOutputTokens: number; responseMimeType: string }
interface SubAnswer { "G-자막_한줄_최대자수": { 나레: number; 대사: number }; "G-자막_겹침_max": { value: number }; "G-죽은시간_max": { value: number }; 무자막_최장_s: { value: number }; 클립당_자막: { min: number; max: number } }
const SUB = (spec as unknown as { 자막: SubSpec })["자막"];
const ASM = (spec as unknown as { 조립: AsmSpec })["조립"];
const JT = (spec as unknown as { 판정: { 텍스트: JudgeTextSpec } })["판정"]["텍스트"];
const A = (answer as unknown as { 자막: SubAnswer })["자막"];

function join(root: string, ...parts: string[]): string { return [root.replace(/[\/]+$/, ""), ...parts].join("/"); }
const r3 = (x: number) => Math.round(x * 1000) / 1000;
const r2 = (x: number) => Math.round(x * 100) / 100;

// ── 입력 모양 ────────────────────────────────────────────────────────────
interface Segment { i: number; in: number; out: number; len_s: number; role: string; kind: string; src: string[]; why: string }
interface Bridge { start: number; end: number; len_s: number }
interface Selection { segments?: Segment[]; narration_bridges?: Bridge[] }
interface VBlock { n: number; pos: { kind: string; seg?: number; bridge?: number }; text: string; dur_s: number; wav: string; chars_t?: { c: string; s: number; e: number }[] | null }
interface Utt { start: number; end: number; text: string; i?: number }
interface Scene { start: number; end: number; what: string }

// ── 타임라인 요소 ────────────────────────────────────────────────────────
interface Pic { k: number; kind: "segment" | "extend" | "bridge"; role: string; src_in: number; src_out: number; t0: number; t1: number; audio: "keep" | "duck" | "hold"; seg?: number; bridge?: number; why?: string }
interface Nar { n: number; t0: number; t1: number; wav: string; text: string; anchor: string }
interface Cue { lane: "nar" | "dlg"; t0: number; t1: number; text: string; src?: string; ref?: string }

/** 나레 본문을 한 줄 상한 안의 큐 줄로 나눈다 — `..` 조각 우선, 넘치면 어절 단위 */
export function splitNarLines(text: string, maxLen: number): string[] {
  const pieces = text.split(/(?<=\.\.!?)\s*/).map((p) => p.trim()).filter(Boolean);
  const out: string[] = [];
  for (const p of pieces) {
    if (p.length <= maxLen) { out.push(p); continue; }
    let cur = "";
    for (const w of p.split(/\s+/)) {
      if (!cur) cur = w;
      else if ((cur + " " + w).length <= maxLen) cur += " " + w;
      else { out.push(cur); cur = w; }
    }
    if (cur) out.push(cur);
  }
  return out;
}

/** 큐 줄들의 시각 — chars_t 가 있으면 글자 위치로 실측, 없으면 글자 비례 */
function narCueTimes(text: string, lines: string[], dur: number, charsT: VBlock["chars_t"]): [number, number][] {
  const times: [number, number][] = [];
  // 글자별 시각이 본문 길이의 80% 미만이면 어긋난 것 — 글자 비례로 대신한다
  if (charsT && charsT.length >= Math.floor(text.length * 0.8)) {
    // 본문 글자열과 chars_t 를 앞에서부터 대응 (공백 포함 그대로 온다)
    let pos = 0;
    const flat = text;
    for (const ln of lines) {
      const idx = flat.indexOf(ln, pos);
      const a = idx >= 0 ? idx : pos, b = a + ln.length;
      const seg = charsT.slice(Math.min(a, charsT.length - 1), Math.min(b, charsT.length));
      const s = seg.length ? seg[0].s : (times.at(-1)?.[1] ?? 0);
      const e = seg.length ? seg[seg.length - 1].e : s;
      times.push([r3(s), r3(Math.max(e, s + 0.01))]);
      pos = b;
    }
    // 마지막 큐 끝은 실측 총길이까지
    if (times.length) times[times.length - 1][1] = r3(Math.max(times[times.length - 1][1], dur));
    return times;
  }
  const total = lines.reduce((a, l) => a + l.length, 0) || 1;
  let t = 0;
  for (const ln of lines) { const d = dur * (ln.length / total); times.push([r3(t), r3(t + d)]); t += d; }
  return times;
}

export const subtitle: StepHandler = {
  name: "subtitle",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; title?: string; lang?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number } | undefined;
    const selection = payload.selection as Selection | undefined;
    const voice = payload.voice as { blocks?: VBlock[] } | undefined;
    const utts = (payload.transcript_utterances as Utt[] | undefined) ?? [];
    const visual = (payload.visual ?? {}) as { silent?: { scenes?: Scene[] }[] };
    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !selection?.segments || !voice?.blocks || utts.length === 0) {
      return reject(
        "subtitle", preset,
        "payload 에 carry 값(source·workdir·probe_summary) 또는 selection / voice / transcript_utterances 가 없다",
        "voice 응답의 carry 값과 함께 payload.selection(clips/selection.json 내용) · payload.voice(voice/voice.json 내용) · payload.transcript_utterances(transcript.json 의 utterances 배열) · payload.visual(clips/visual.json 내용)을 실어 subtitle 를 다시 부르라.",
      );
    }
    const segs = [...selection.segments].sort((a, b) => a.in - b.in);
    const bridges = selection.narration_bridges ?? [];
    const vblocks = voice.blocks;
    const subDir = join(workdir, "subtitle");
    const scenes: Scene[] = (visual.silent ?? []).flatMap((st) => st.scenes ?? []);
    const PAD = ASM.브리지_컷.패딩_s;
    const holdRoles = new Set(ASM.죽은시간_홀드_제외_역할);
    const dialogueRoles = new Set(["원본대사", "나레이션덮기"]);
    const warnings: string[] = [];

    // ── 타임라인 조립 ──────────────────────────────────────────────────
    const pics: Pic[] = [];
    const nars: Nar[] = [];
    let t = 0, k = 0;
    const byPos = (kind: string, ref: number) => vblocks.filter((b) => b.pos.kind === kind && (kind === "bridge" ? b.pos.bridge === ref : b.pos.seg === ref));
    const uttsIn = (a: number, b: number) => utts.filter((u) => u.start < b && u.end > a);
    /** 구간 s 안에서 나레 블록들을 배치 — 시각몽타주 균등 / 대사 역할은 발화 틈 */
    const placeOver = (s: Segment, pic: Pic, blocks: VBlock[]) => {
      if (blocks.length === 0) return;
      const anchorTag = `over seg#${s.i}`;
      if (!dialogueRoles.has(s.role)) {
        const sum = blocks.reduce((a, b) => a + b.dur_s, 0);
        const gap = Math.max(0, (pic.t1 - pic.t0 - sum) / (blocks.length + 1));
        let cur = pic.t0 + gap;
        for (const b of blocks) { nars.push({ n: b.n, t0: r3(cur), t1: r3(cur + b.dur_s), wav: b.wav, text: b.text, anchor: `${anchorTag} 균등` }); cur += b.dur_s + gap; }
        return;
      }
      // 발화 틈: [구간 시작~첫 발화], 발화 사이, [마지막 발화~구간 끝]
      const us = uttsIn(s.in, s.out).map((u) => [Math.max(u.start, s.in), Math.min(u.end, s.out)] as [number, number]).sort((a, b) => a[0] - b[0]);
      const gaps: [number, number][] = [];
      let cur = s.in;
      for (const [a, b] of us) { if (a - cur > 0.05) gaps.push([cur, a]); cur = Math.max(cur, b); }
      if (s.out - cur > 0.05) gaps.push([cur, s.out]);
      // 이야기 순서대로 채운다 — 앞에서부터 남는 자리가 있는 틈에 놓고(한 틈에 여러 블록 가능), 없으면 가장 큰 틈에 겹쳐 놓는다(덕킹)
      const room = gaps.map(([a, b]) => ({ a, b, cur: a }));
      const GAPPAD = SUB.큐_사이_최소간격_s;
      let lastEnd = s.in;
      for (const b of blocks) {
        let g = room.find((r) => r.cur >= lastEnd - 1e-6 && r.b - r.cur >= b.dur_s + GAPPAD);
        if (!g) g = room.find((r) => r.b - r.cur >= b.dur_s + GAPPAD);
        let start: number;
        if (g) { start = g.cur + GAPPAD / 2; g.cur = start + b.dur_s + GAPPAD / 2; }
        else {
          const big = [...room].sort((x, y) => (y.b - y.a) - (x.b - x.a))[0];
          start = Math.max(big ? big.a : s.in, lastEnd);
          warnings.push(`블록 ${b.n} (${r2(b.dur_s)}s)이 구간 ${s.i} 의 남은 틈보다 길다 — 대사 위에 겹친다(덕킹).`);
          if (big) big.cur = Math.max(big.cur, start + b.dur_s);
        }
        lastEnd = start + b.dur_s;
        const t0 = pic.t0 + (start - s.in);
        nars.push({ n: b.n, t0: r3(t0), t1: r3(t0 + b.dur_s), wav: b.wav, text: b.text, anchor: `${anchorTag} 틈 ${g ? `${r2(g.a)}~${r2(g.b)}` : "(겹침)"}` });
      }
    };
    for (let idx = 0; idx < segs.length; idx++) {
      const s = segs[idx];
      const prev = segs[idx - 1], next = segs[idx + 1];
      // 이 구간 앞에 놓이는 브리지 (prev.out ≤ bridge.start < s.in)
      for (let bi = 0; bi < bridges.length; bi++) {
        const br = bridges[bi];
        if (!(br.start >= (prev?.out ?? -1) - 0.2 && br.end <= s.in + 0.2)) continue;
        const bbl = byPos("bridge", bi);
        if (!bbl.length || !ASM.브리지_컷.사용) continue;
        let lastEnd = br.start;
        for (const b of bbl) {
          const sc = scenes.find((x) => x.start >= lastEnd - 0.01 && x.start < br.end - 1);
          let a = sc ? sc.start : lastEnd;
          let len = b.dur_s + PAD * 2;
          if (a + len > br.end) a = Math.max(br.start, br.end - len);
          if (a < lastEnd) a = lastEnd; // 앞 컷과 겹치지 않게
          const o = Math.min(br.end, a + len);
          if (o - a < b.dur_s) warnings.push(`브리지 ${bi} 컷이 나레 ${b.n}(${r2(b.dur_s)}s)보다 짧다 (${r2(o - a)}s) — 브리지 구간이 좁다.`);
          pics.push({ k: k++, kind: "bridge", role: "브리지", src_in: r3(a), src_out: r3(o), t0: r3(t), t1: r3(t + (o - a)), audio: "duck", bridge: bi, why: sc ? `앵커 장면 ${sc.start}s "${sc.what.slice(0, 30)}"` : "브리지 시작" });
          nars.push({ n: b.n, t0: r3(t + PAD), t1: r3(t + PAD + b.dur_s), wav: b.wav, text: b.text, anchor: `bridge#${bi} 컷` });
          t += o - a; lastEnd = o;
        }
      }
      // before 블록
      const before = byPos("before", s.i);
      const prevContiguousSilent = prev && Math.abs(prev.out - s.in) < 0.2 && !dialogueRoles.has(prev.role);
      for (const b of before) {
        if (prevContiguousSilent) {
          const prevPic = pics.filter((p) => p.kind === "segment" && p.seg === prev!.i).at(-1)!;
          const t0 = Math.max(prevPic.t0, prevPic.t1 - b.dur_s);
          nars.push({ n: b.n, t0: r3(t0), t1: r3(t0 + b.dur_s), wav: b.wav, text: b.text, anchor: `before seg#${s.i} → 앞 구간 ${prev!.i} 꼬리 겹침` });
        } else {
          const a = Math.max(0, s.in - b.dur_s);
          pics.push({ k: k++, kind: "extend", role: "연장", src_in: r3(a), src_out: r3(s.in), t0: r3(t), t1: r3(t + (s.in - a)), audio: "duck", seg: s.i, why: `before 나레 ${b.n} 자리 — 원본 앞으로 연장` });
          nars.push({ n: b.n, t0: r3(t), t1: r3(t + b.dur_s), wav: b.wav, text: b.text, anchor: `before seg#${s.i} 연장` });
          t += s.in - a;
        }
      }
      // 구간 본체
      const pic: Pic = { k: k++, kind: "segment", role: s.role, src_in: s.in, src_out: s.out, t0: r3(t), t1: r3(t + (s.out - s.in)), audio: dialogueRoles.has(s.role) ? "keep" : "hold", seg: s.i };
      pics.push(pic);
      t += s.out - s.in;
      placeOver(s, pic, byPos("over", s.i));
      // after 블록
      const after = byPos("after", s.i);
      const nextContiguousSilent = next && Math.abs(next.in - s.out) < 0.2 && !dialogueRoles.has(next.role);
      for (const b of after) {
        if (nextContiguousSilent) {
          // 다음 구간 머리에 겹친다 — 다음 구간 pic 은 아직 없으니 예약: t 기준으로 배치 (다음 pic 은 t 에서 시작한다)
          nars.push({ n: b.n, t0: r3(t), t1: r3(t + b.dur_s), wav: b.wav, text: b.text, anchor: `after seg#${s.i} → 다음 구간 ${next!.i} 머리 겹침` });
        } else {
          const o = Math.min(ps.duration_s, s.out + b.dur_s);
          pics.push({ k: k++, kind: "extend", role: "연장", src_in: r3(s.out), src_out: r3(o), t0: r3(t), t1: r3(t + (o - s.out)), audio: "duck", seg: s.i, why: `after 나레 ${b.n} 자리 — 원본 뒤로 연장` });
          nars.push({ n: b.n, t0: r3(t), t1: r3(t + b.dur_s), wav: b.wav, text: b.text, anchor: `after seg#${s.i} 연장` });
          t += o - s.out;
        }
      }
    }
    // ── 죽은 시간 컷 (규격 조립.죽은시간_컷): 대사 역할 구간 안에서 대사도 나레도 없는 임계 이상 구간을 잘라 당겨 붙인다 ──
    let trimmedS = 0, trimCuts = 0;
    if (ASM.죽은시간_컷?.사용) {
      const TC = ASM.죽은시간_컷;
      const target = new Set(TC.대상_역할);
      const newPics: Pic[] = [];
      let shift = 0; // 지금까지 잘라낸 누적 초 (뒤 요소를 앞으로 당긴다)
      const shiftedNars = new Map<number, number>(); // nar n → 당길 초
      for (const p of pics) {
        const p0 = p.t0, p1 = p.t1;
        if (p.kind !== "segment" || !target.has(p.role)) { newPics.push({ ...p, t0: r3(p.t0 - shift), t1: r3(p.t1 - shift) }); for (const n of nars) if (n.t0 >= p0 && n.t0 < p1) shiftedNars.set(n.n, shift); continue; }
        // 이 구간의 소리 구간(타임라인 시각): 대사 + 이 구간 위 나레
        const sound: [number, number][] = [
          ...uttsIn(p.src_in, p.src_out).map((u) => [p.t0 + (Math.max(u.start, p.src_in) - p.src_in), p.t0 + (Math.min(u.end, p.src_out) - p.src_in)] as [number, number]),
          ...nars.filter((n) => n.t1 > p0 && n.t0 < p1).map((n) => [Math.max(n.t0, p0), Math.min(n.t1, p1)] as [number, number]),
        ].sort((a, b) => a[0] - b[0]);
        // 잘라낼 무음 구간 (안쪽만 — 구간 머리·꼬리는 그대로)
        const cuts: [number, number][] = [];
        let cur = -1;
        for (const [a, b] of sound) { if (cur >= 0 && a - cur >= TC.임계_s) cuts.push([cur + TC.뒤_남김_s, a - TC.앞_남김_s]); cur = Math.max(cur, b); }
        if (cuts.length === 0) { newPics.push({ ...p, t0: r3(p.t0 - shift), t1: r3(p.t1 - shift) }); for (const n of nars) if (n.t0 >= p0 && n.t0 < p1) shiftedNars.set(n.n, shift); continue; }
        // 구간을 조각으로 나눈다
        let segStart = p0, localShift = shift;
        for (const [ca, cb] of cuts) {
          if (ca <= segStart) continue;
          newPics.push({ ...p, k: -1, src_in: r3(p.src_in + (segStart - p0)), src_out: r3(p.src_in + (ca - p0)), t0: r3(segStart - localShift), t1: r3(ca - localShift), why: `${p.why ?? ""} 무음 ${r2(cb - ca)}s 컷`.trim() });
          for (const n of nars) if (n.t0 >= segStart && n.t0 < ca) shiftedNars.set(n.n, localShift);
          localShift += cb - ca; trimmedS += cb - ca; trimCuts++;
          segStart = cb;
        }
        newPics.push({ ...p, k: -1, src_in: r3(p.src_in + (segStart - p0)), src_out: p.src_out, t0: r3(segStart - localShift), t1: r3(p1 - localShift) });
        for (const n of nars) if (n.t0 >= segStart && n.t0 < p1) shiftedNars.set(n.n, localShift);
        shift = localShift;
      }
      newPics.forEach((p, i) => { p.k = i; });
      pics.length = 0; pics.push(...newPics);
      for (const n of nars) { const sh = shiftedNars.get(n.n) ?? shift; n.t0 = r3(n.t0 - sh); n.t1 = r3(n.t1 - sh); }
      t -= shift;
      trimmedS = r3(trimmedS);
    }
    const totalT = r3(t);
    nars.sort((a, b) => a.t0 - b.t0);
    // 나레끼리 겹침 해소: 뒤 것을 밀어낸다 (앞뒤 겹침이 생기는 자리는 대개 겹침 규칙의 꼬리/머리)
    for (let i = 1; i < nars.length; i++) {
      const gapMin = SUB.큐_사이_최소간격_s;
      if (nars[i].t0 < nars[i - 1].t1 + gapMin) { const shift = nars[i - 1].t1 + gapMin - nars[i].t0; nars[i].t0 = r3(nars[i].t0 + shift); nars[i].t1 = r3(nars[i].t1 + shift); warnings.push(`나레 ${nars[i].n} 을 ${r2(shift)}s 뒤로 밀었다 (앞 나레 ${nars[i - 1].n} 과 겹침).`); }
    }

    // ── 대사 줄 (자막 대상 = 대사 역할 구간 안 발화) ──────────────────────
    const dlgLines: { id: string; seg: number; t0: number; t1: number; src_start: number; src_end: number; en: string }[] = [];
    // 발화가 두 구간에 걸치면 더 많이 겹치는 구간에만 둔다 (같은 줄이 두 번 뜨지 않게)
    const dlgPics = pics.filter((p) => p.kind === "segment" && dialogueRoles.has(p.role));
    const bestPic = new Map<Utt, Pic>();
    for (const u of utts) { let best: Pic | null = null, bo = 0; for (const p of dlgPics) { const o = Math.min(u.end, p.src_out) - Math.max(u.start, p.src_in); if (o > bo) { bo = o; best = p; } } if (best && bo >= 0.15) bestPic.set(u, best); }
    for (const p of dlgPics) {
      for (const u of uttsIn(p.src_in, p.src_out)) {
        if (bestPic.get(u) !== p) continue;
        const a = Math.max(u.start, p.src_in), b = Math.min(u.end, p.src_out);
        if (b - a < 0.15) continue;
        dlgLines.push({ id: `d${String(dlgLines.length + 1).padStart(3, "0")}`, seg: p.seg!, t0: r3(p.t0 + (a - p.src_in)), t1: r3(p.t0 + (b - p.src_in)), src_start: u.start, src_end: u.end, en: u.text });
      }
    }

    // ── ① need_input / judge ─────────────────────────────────────────────
    if (payload.translations === undefined) {
      const timelinePreview = { total_s: totalT, cuts: pics.length, narrations: nars.length, dialogue_lines: dlgLines.length };
      const styleGuide = [
        `대사 자막 번역 — ${SUB.번역_문체}`,
        `한 줄 ${SUB.대사_한줄_최대자수}자 이내(공백 포함). 넘으면 두 큐로 나누지 말고 줄여 써라 — 자막은 읽는 시간이 정해져 있다.`,
        `구두점: ${SUB.대사_구두점}.`,
        "화자 표시·괄호 설명을 넣지 않는다. 원문이 잘린 문장(ASR)이면 잘린 그대로 짧게 옮긴다. 욕설은 수위 그대로(순화하지 않는다).",
        "출력: [{id, ko}] — id 는 material.dialogue_lines 의 id 그대로, 빠짐없이.",
      ];
      if (dlgLines.length <= SUB.대사_줄수_대화안_상한) {
        return base("subtitle", preset, {
          status: "need_input",
          next_step: "subtitle",
          message: `대사 번역 차례 — ${dlgLines.length}줄(상한 ${SUB.대사_줄수_대화안_상한} 이하라 대화 안에서). 타임라인은 짜였다: 총 ${totalT}s · 컷 ${pics.length} · 나레 ${nars.length}. payload.translations = [{id, ko}] 로 subtitle 을 다시 부르라.`,
          need_input: { keys: ["translations"], why: "짧고 문체 통제가 필요한 번역은 대화 안에서 (단계와게이트.md 「판정을 어디서 하는가」). 줄 수가 상한을 넘으면 judge 로 나간다." },
          instructions: [
            "① style_guide 대로 material.dialogue_lines 의 en 을 한국어로 옮긴다 (지무비 구어체).",
            "② payload.translations = [{id, ko}, …] 를 carry 값과 함께 실어 subtitle 을 다시 부른다. 서버가 한 줄 자수·구두점을 검사한다.",
          ],
          then_call_with: ["step: 'subtitle'", "payload: { …carry, selection, voice, transcript_utterances, visual, translations: [{id, ko}] }"],
          jobs_kind: null, jobs: [], measure: [],
          carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path", "selection", "voice", "transcript_utterances", "visual"],
          source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: payload.voice_path,
          selection, voice, transcript_utterances: utts, visual,
          style_guide: styleGuide,
          material: { title: source.title ?? null, lang: source.lang ?? null, dialogue_lines: dlgLines.map((d) => ({ id: d.id, seg: d.seg, t: `${d.src_start}→${d.src_end}`, en: d.en })), timeline_preview: timelinePreview },
        });
      }
      // judge 경로 (줄 수 초과)
      const url = JT.엔드포인트.replace("{model}", JT.모델);
      const prompt = [
        `너는 한국 영화 리캡 채널의 대사 자막 번역가다. 아래 영어 대사 ${dlgLines.length}줄을 한국어로 옮겨라.`,
        ...styleGuide,
        "## 출력 — JSON 객체 하나만",
        '{"translations":[{"id":"d001","ko":"…"}]}',
        "## 대사",
        ...dlgLines.map((d) => `${d.id}\t${d.en}`),
      ].join("\n");
      const job: JudgeJob = {
        name: "translate_dialogue", provider: JT.backend as "evolink" | "google", model: JT.모델,
        request: { method: "POST", url, headers: { "Content-Type": "application/json" }, body: { contents: [{ role: "user", parts: [{ text: prompt }] }], generationConfig: { temperature: JT.온도, thinkingConfig: { thinkingBudget: JT.thinkingBudget }, maxOutputTokens: JT.maxOutputTokens, responseMimeType: JT.responseMimeType, responseSchema: { type: "OBJECT", properties: { translations: { type: "ARRAY", items: { type: "OBJECT", properties: { id: { type: "STRING" }, ko: { type: "STRING" } }, required: ["id", "ko"] } } }, required: ["translations"] } } } },
        inputs: [], auth: { env: JT.키_환경변수, header: `Authorization: Bearer <${JT.키_환경변수} 값>`, note: "서버는 키를 보관하지 않는다." },
        out: join(subDir, "translate_raw.json"), note: `대사 ${dlgLines.length}줄 번역 (상한 ${SUB.대사_줄수_대화안_상한} 초과라 judge)`,
      };
      return base("subtitle", preset, {
        status: "execute", next_step: "subtitle",
        message: `대사 ${dlgLines.length}줄 — 상한 ${SUB.대사_줄수_대화안_상한} 초과라 judge(${JT.backend})로 번역한다. 결과를 payload.translations 에 실어 subtitle 을 다시 부르라.`,
        instructions: ["① jobs 의 judge 를 그대로 보낸다 (키는 auth 대로 환경변수에서).", "② measure 대로 응답 JSON 의 translations 배열을 payload.translations 에 넣고 carry 값과 함께 다시 부른다."],
        then_call_with: ["step: 'subtitle'", "payload: { …carry, translations: <응답.translations> }"],
        jobs_kind: "judge", jobs: [job], measure: [{ as: "translations_raw", from: "job:translate_dialogue", unit: "gemini_json_text" }],
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path", "selection", "voice", "transcript_utterances", "visual"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: payload.voice_path,
        selection, voice, transcript_utterances: utts, visual,
      });
    }

    // ── ② 큐 · 게이트 · 산출물 ────────────────────────────────────────────
    let tr = payload.translations as unknown;
    if (tr && typeof tr === "object" && !Array.isArray(tr) && Array.isArray((tr as { translations?: unknown }).translations)) tr = (tr as { translations: unknown }).translations;
    if (!Array.isArray(tr)) return reject("subtitle", preset, "payload.translations 가 배열이 아니다", "[{id, ko}] 배열을 실어 다시 부르라.");
    const trMap = new Map<string, string>((tr as { id: string; ko: string }[]).map((x) => [x.id, String(x.ko ?? "").trim()]));
    const hard: string[] = [];
    const missing = dlgLines.filter((d) => !trMap.get(d.id));
    if (missing.length) hard.push(`번역 누락 ${missing.length}줄: ${missing.slice(0, 8).map((d) => d.id).join(", ")}${missing.length > 8 ? " …" : ""}`);
    const cues: Cue[] = [];
    // 대사 큐
    for (const d of dlgLines) {
      const ko = trMap.get(d.id) ?? "";
      if (!ko) continue;
      if (ko.length > A["G-자막_한줄_최대자수"].대사) hard.push(`${d.id}: 대사 ${ko.length}자 > ${A["G-자막_한줄_최대자수"].대사}자 — 「${ko}」 (원문: ${d.en})`);
      if (/[.,，]/.test(ko)) hard.push(`${d.id}: 대사 자막에 마침표·쉼표 금지 — 「${ko}」`);
      const t1 = Math.min(Math.max(d.t1, d.t0 + SUB.큐_최소길이_s), d.t0 + SUB.큐_최대길이_s); // 늘어난 발화는 큐 상한으로 자른다
      cues.push({ lane: "dlg", t0: d.t0, t1: r3(t1), text: ko, src: d.en, ref: d.id });
    }
    // 나레 큐
    const vmap = new Map(vblocks.map((b) => [b.n, b]));
    for (const n of nars) {
      const b = vmap.get(n.n)!;
      const lines = splitNarLines(b.text, A["G-자막_한줄_최대자수"].나레);
      const times = narCueTimes(b.text, lines, b.dur_s, b.chars_t ?? null);
      lines.forEach((ln, i) => {
        if (ln.length > A["G-자막_한줄_최대자수"].나레) hard.push(`나레 ${n.n}: 줄 ${ln.length}자 > ${A["G-자막_한줄_최대자수"].나레}자 — 「${ln}」`);
        const [a, e] = times[i];
        cues.push({ lane: "nar", t0: r3(n.t0 + a), t1: r3(n.t0 + Math.max(e, a + SUB.큐_최소길이_s)), text: ln, ref: `n${n.n}` });
      });
    }
    // 대사 큐 꼬리 — 발화 뒤 규격만큼 남긴다 (다음 대사 큐 직전·큐 최대길이 안에서)
    {
      const D = cues.filter((c) => c.lane === "dlg").sort((a, b) => a.t0 - b.t0);
      for (let i = 0; i < D.length; i++) {
        const nextT0 = D[i + 1]?.t0 ?? Infinity;
        const extended = Math.min(D[i].t1 + SUB.대사큐_꼬리_s, nextT0 - SUB.큐_사이_최소간격_s, D[i].t0 + SUB.큐_최대길이_s);
        D[i].t1 = r3(Math.max(D[i].t1, extended)); // 늘리기만 한다 (줄이지 않는다)
      }
    }
    cues.sort((x, y) => x.t0 - y.t0);
    // 같은 레인 겹침 → 뒤 큐 앞당김 불가하니 앞 큐 끝을 자른다 (자막은 다음 큐가 뜨면 사라진다)
    let overlapsFixed = 0;
    for (const lane of ["nar", "dlg"] as const) {
      const L = cues.filter((c) => c.lane === lane);
      for (let i = 1; i < L.length; i++) if (L[i].t0 < L[i - 1].t1) {
      // 앞 큐 끝을 자르고, 그래도 겹치면(앞 큐가 너무 짧아짐) 뒤 큐 시작을 민다
      L[i - 1].t1 = r3(Math.max(L[i - 1].t0 + 0.3, L[i].t0 - SUB.큐_사이_최소간격_s));
      if (L[i].t0 < L[i - 1].t1) { L[i].t0 = r3(L[i - 1].t1 + SUB.큐_사이_최소간격_s); L[i].t1 = r3(Math.max(L[i].t1, L[i].t0 + 0.3)); }
      overlapsFixed++;
    }
    }
    let overlapsLeft = 0;
    for (const lane of ["nar", "dlg"] as const) { const L = cues.filter((c) => c.lane === lane); for (let i = 1; i < L.length; i++) if (L[i].t0 < L[i - 1].t1) overlapsLeft++; }
    if (overlapsLeft > (A["G-자막_겹침_max"].value ?? 0)) hard.push(`같은 레인 자막 겹침 ${overlapsLeft}건 (허용 ${A["G-자막_겹침_max"].value})`);

    // ── 죽은 시간 (홀드 제외) ─────────────────────────────────────────────
    const holdIntervals = pics.filter((p) => holdRoles.has(p.role)).map((p) => [p.t0, p.t1] as [number, number]);
    const holdS = r3(holdIntervals.reduce((a, [x, y]) => a + (y - x), 0));
    // 축 = 자막 큐(나레·대사)가 있는 시간 (가족 G14 와 같은 축 — 정답지 대본.G-죽은시간_max.적용)
    const sound: [number, number][] = cues.map((c) => [c.t0, c.t1] as [number, number]).sort((a, b) => a[0] - b[0]);
    const union: [number, number][] = [];
    for (const [a, b] of sound) { const last = union[union.length - 1]; if (last && a <= last[1]) last[1] = Math.max(last[1], b); else union.push([a, b]); }
    const inHold = (x: number, y: number) => holdIntervals.reduce((acc, [h0, h1]) => acc + Math.max(0, Math.min(y, h1) - Math.max(x, h0)), 0);
    const coveredNonHold = r3(union.reduce((a, [x, y]) => a + (y - x) - inHold(x, y), 0));
    const denom = r3(totalT - holdS);
    const deadS = r3(Math.max(0, denom - coveredNonHold));
    const deadRatio = denom > 0 ? r3(deadS / denom) : 0;
    // 죽은 구간 상위 (홀드 밖)
    const deadSpans: { t0: number; t1: number; len: number }[] = [];
    { let cur = 0; const pts = [...union, [totalT, totalT] as [number, number]]; for (const [a, b] of pts) { if (a - cur > 0.5) { const seg = [cur, a] as [number, number]; const h = inHold(seg[0], seg[1]); if (seg[1] - seg[0] - h > 0.5) deadSpans.push({ t0: r3(seg[0]), t1: r3(seg[1]), len: r3(seg[1] - seg[0] - h) }); } cur = Math.max(cur, b); } }
    deadSpans.sort((x, y) => y.len - x.len);
    // 무자막 최장 · 클립당 자막
    let maxNoSub = 0; { let cur = 0; const cs = [...cues].sort((a, b) => a.t0 - b.t0); for (const c of cs) { maxNoSub = Math.max(maxNoSub, c.t0 - cur); cur = Math.max(cur, c.t1); } maxNoSub = r3(Math.max(maxNoSub, totalT - cur)); }
    const cuesPerClip = r3(cues.length / pics.length);
    const maxLineNar = Math.max(0, ...cues.filter((c) => c.lane === "nar").map((c) => c.text.length));
    const maxLineDlg = Math.max(0, ...cues.filter((c) => c.lane === "dlg").map((c) => c.text.length));

    const gates: { id: string; pass: boolean; hard: boolean; detail: string; fix?: string }[] = [];
    gates.push({ id: "G-자막(한 줄 자수)", pass: !hard.some((h) => /자 > /.test(h)), hard: true, detail: `나레 최대 ${maxLineNar}/${A["G-자막_한줄_최대자수"].나레} · 대사 최대 ${maxLineDlg}/${A["G-자막_한줄_최대자수"].대사}`, fix: "초과 큐 목록을 보고 각각 축약(대사) 또는 분할(나레 — splitNarLines 가 어절로 나누므로 한 어절이 상한을 넘는 경우만 본문을 고친다)" });
    gates.push({ id: "G-자막(같은 레인 겹침)", pass: overlapsLeft <= (A["G-자막_겹침_max"].value ?? 0), hard: true, detail: `겹침 ${overlapsLeft} (앞 큐 끝을 잘라 ${overlapsFixed}건 해소)` });
    const deadPass = deadRatio <= (A["G-죽은시간_max"].value ?? 0.1);
    gates.push({ id: "G-죽은시간(홀드 제외)", pass: deadPass, hard: true, detail: `죽은 ${deadS}s / (총 ${totalT}s − 홀드 ${holdS}s = ${denom}s) = ${deadRatio} (≤${A["G-죽은시간_max"].value}). 죽은 구간 상위: ${deadSpans.slice(0, 5).map((d) => `${d.t0}~${d.t1}(${d.len}s)`).join(", ")}`, fix: deadPass ? undefined : `죽은 구간 상위 ${Math.min(5, deadSpans.length)}개 위치를 보고 script 로 돌아가 그 자리에 원인·의미 나레를 쓰거나(나레이션.md 2절), 그 구간을 자르거나 당겨 붙여라(규격 조립). 대사 역할인데 대사가 없는 자리면 select 의 역할을 시각몽타주(홀드)로 바꾼다.` });
    const soft: string[] = [...warnings];
    if (maxNoSub > A.무자막_최장_s.value) soft.push(`[soft] 무자막 최장 ${maxNoSub}s > ${A.무자막_최장_s.value}s (G64)`);
    if (cuesPerClip < A.클립당_자막.min || cuesPerClip > A.클립당_자막.max) soft.push(`[soft] 클립당 자막 ${cuesPerClip} (대역 ${A.클립당_자막.min}~${A.클립당_자막.max}, G12)`);
    // 나레-대사 겹침(다른 레인, 덕킹) 정보
    let narOverDlg = 0; for (const n of nars) for (const d of dlgLines) narOverDlg += Math.max(0, Math.min(n.t1, d.t1) - Math.max(n.t0, d.t0));
    narOverDlg = r3(narOverDlg);

    const metrics = { total_s: totalT, cuts: pics.length, narrations: nars.length, cue_count: cues.length, cues_nar: cues.filter((c) => c.lane === "nar").length, cues_dlg: cues.filter((c) => c.lane === "dlg").length, cues_per_min: r3(cues.length / (totalT / 60)), max_line_chars: { nar: maxLineNar, dlg: maxLineDlg }, overlaps: overlapsLeft, dead_ratio: deadRatio, dead_s: deadS, hold_s: holdS, max_no_sub_s: maxNoSub, cues_per_clip: cuesPerClip, nar_over_dialogue_s: narOverDlg, added_time_s: r3(totalT - segs.reduce((a, s) => a + (s.out - s.in), 0)), trimmed_silence_s: trimmedS, trim_cuts: trimCuts, source_ratio: r3(totalT / ps.duration_s) };
    // 죽은 구간 → 어느 컷(원본 시각)인지 대응 + 역할별 합계 (수리 지침에 위치를 준다)
    const picAt = (x: number) => pics.find((p) => x >= p.t0 - 1e-6 && x < p.t1 + 1e-6);
    const deadDiag = deadSpans.slice(0, 12).map((d) => { const p = picAt(d.t0); return { ...d, picture: p ? { k: p.k, kind: p.kind, role: p.role, seg: p.seg ?? null, src: `${r2(p.src_in + (d.t0 - p.t0))}~${r2(Math.min(p.src_out, p.src_in + (d.t1 - p.t0)))}` } : null }; });
    const deadByRole: Record<string, number> = {};
    for (const p of pics) { if (holdRoles.has(p.role)) continue; let covered = 0; for (const [a, b] of union) covered += Math.max(0, Math.min(b, p.t1) - Math.max(a, p.t0)); const dead = (p.t1 - p.t0) - covered; deadByRole[p.role] = r3((deadByRole[p.role] ?? 0) + Math.max(0, dead)); }
    if (hard.length || gates.some((g) => g.hard && !g.pass)) {
      const fails = gates.filter((g) => g.hard && !g.pass);
      return {
        ...reject(
          "subtitle", preset,
          `자막 검사 불통 — ${[...hard.slice(0, 6), ...fails.map((g) => `${g.id}: ${g.detail}`)].join(" / ")}${hard.length > 6 ? ` / … (+${hard.length - 6})` : ""}`,
          [...fails.map((g) => g.fix ?? ""), hard.length ? "위 줄을 고쳐 payload.translations 를 다시 실어 부르라." : ""].filter(Boolean).join(" "),
        ),
        diagnostics: { dead_spans_top: deadDiag, dead_by_role: deadByRole, metrics },
      };
    }

    // ── 산출물 ────────────────────────────────────────────────────────
    const fmt = (x: number) => { const ms = Math.round(x * 1000); const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), s = Math.floor((ms % 60000) / 1000), mm = ms % 1000; return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(mm).padStart(3, "0")}`; };
    const srt = (list: Cue[], prefixDlg: boolean) => list.map((c, i) => `${i + 1}\n${fmt(c.t0)} --> ${fmt(c.t1)}\n${prefixDlg && c.lane === "dlg" ? "– " : ""}${c.text}\n`).join("\n") + "\n";
    const timelineDoc = {
      source: source.path, title: source.title ?? null, duration_s: ps.duration_s, total_s: totalT,
      rules: { over: ASM.over_배치, before_after: ASM.before_after, bridge: ASM.브리지_컷, hold_roles: ASM.죽은시간_홀드_제외_역할, duck_roles: ASM.덕킹_역할 },
      fonts: SUB.폰트,
      metrics, gates, warnings: soft,
      picture: pics, narration: nars,
      dialogue: dlgLines.map((d) => ({ ...d, ko: trMap.get(d.id) ?? "" })),
      cues,
      dead_spans_top: deadSpans.slice(0, 10),
    };
    return base("subtitle", preset, {
      status: "execute",
      next_step: "export",
      message: `자막·타임라인 통과: 총 ${totalT}s(원본의 ${metrics.source_ratio}) · 컷 ${pics.length} · 큐 ${cues.length}(나레 ${metrics.cues_nar}·대사 ${metrics.cues_dlg}) · 죽은 시간 ${deadRatio}(홀드 ${holdS}s 제외). write_files 를 쓰고 export 로 넘어가라.`,
      instructions: [
        `① write_files 4개를 그대로 쓴다 — ${join(subDir, "timeline.json")} · subtitle.srt(합본, 대사 줄 접두 "– ") · subtitle_nar.srt · subtitle_dlg.srt.`,
        "② metrics 와 gates 를 사람에게 보여준다. 죽은 구간 상위·나레-대사 겹침 초도.",
        "③ carry 의 값을 payload 에 그대로 실어 next_step 을 부른다. export 는 아직 스텁이다.",
      ],
      then_call_with: ["step: 'export'", "payload: { workdir, source, probe_summary, transcript_path, brief_path, selection_path, script_path, voice_path, timeline_path }"],
      jobs_kind: null, jobs: [], measure: [],
      write_files: [
        { path: join(subDir, "timeline.json"), content: timelineDoc, note: "컷 타임라인 + 나레 배치 + 큐. export 의 입력" },
        { path: join(subDir, "subtitle.srt"), content: srt(cues, true), note: "합본 (대사 줄 접두 – )" },
        { path: join(subDir, "subtitle_nar.srt"), content: srt(cues.filter((c) => c.lane === "nar"), false), note: "나레 자막만" },
        { path: join(subDir, "subtitle_dlg.srt"), content: srt(cues.filter((c) => c.lane === "dlg"), false), note: "대사 자막만" },
      ],
      metrics, gates,
      carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path", "timeline_path"],
      source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: payload.voice_path, timeline_path: join(subDir, "timeline.json"),
      ...(soft.length ? { warnings: soft } : {}),
    });
  },
};
