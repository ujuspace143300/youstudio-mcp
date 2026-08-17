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

interface SubSpec { 나레_한줄_최대자수: number; 대사_한줄_최대자수: number; 큐_최소길이_s: number; 잘린_대사큐_최소길이_s?: number; 큐_무음노출_상한_s?: number; 큐_최대길이_s: number; 대사큐_꼬리_s: number; 큐_사이_최소간격_s: number; 대사_줄수_대화안_상한: number; 대사_구두점: string; 번역_문체: string; 폰트: Record<string, unknown> }
interface AsmSpec { over_배치: Record<string, string>; before_after: Record<string, string>; 브리지_컷: { 사용: boolean; 패딩_s: number; 앵커: string }; 죽은시간_홀드_제외_역할: string[]; 덕킹_역할: string[]; 죽은시간_컷: { 사용: boolean; 임계_s: number; 앞_남김_s: number; 뒤_남김_s: number; 대상_역할: string[]; 보호_소리_최소_s?: number } }
interface JudgeTextSpec { backend: string; 모델: string; 엔드포인트: string; 키_환경변수: string; 온도: number; thinkingBudget: number; maxOutputTokens: number; responseMimeType: string }
interface SubAnswer { "G-자막_한줄_최대자수": { 나레: number; 대사: number }; "G-자막_겹침_max": { value: number }; "G-교차겹침_max"?: { value: number }; "G-죽은시간_max": { value: number }; 무자막_최장_s: { value: number }; 클립당_자막: { min: number; max: number } }
const SUB = (spec as unknown as { 자막: SubSpec })["자막"];
const TRIG = (spec as unknown as { 전사: { 늘어난발화_규칙: { 트리거_단어당_s: number; 트리거_여유_s: number } } })["전사"]["늘어난발화_규칙"];
/** 전사 발화가 '수상하게 긴가' (끝이 늘어난 whisper 세그먼트) — 이런 발화는 시각을 믿지 않고 실측 소리를 쓴다 */
const suspiciousUtt = (u: { start: number; end: number; text: string }) => (u.end - u.start) > u.text.trim().split(/\s+/).filter(Boolean).length * TRIG.트리거_단어당_s + TRIG.트리거_여유_s;
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
interface VBlock { n: number; pos: { kind: string; seg?: number; bridge?: number }; text: string; dur_s: number; wav: string; chars_t?: { c: string; s: number; e: number }[] | null; speech?: [number, number][] | null; _prefer?: "head" | "tail" }
interface Utt { start: number; end: number; text: string; i?: number }
interface Scene { start: number; end: number; what: string }

// ── 타임라인 요소 ────────────────────────────────────────────────────────
interface Pic { k: number; kind: "segment" | "extend" | "bridge"; role: string; src_in: number; src_out: number; t0: number; t1: number; audio: "keep" | "duck" | "hold"; seg?: number; bridge?: number; why?: string }
interface Nar { n: number; t0: number; t1: number; wav: string; text: string; anchor: string }
interface Cue { lane: "nar" | "dlg"; t0: number; t1: number; text: string; src?: string; ref?: string }

/** 나레 본문을 한 줄 상한 안의 큐 줄로 나눈다 — `..` 조각 우선, 넘치면 어절 단위 */
export function splitNarLines(text: string, maxLen: number): string[] {
  // R2(2026-08-17): `..` 뒤에서 자르되 `..!` 는 통째로 — 구두점만 남는 조각("!"·"..")을 만들지 않는다.
  //   전에는 「…끝났습니다..!」가 「…끝났습니다..」 + 「!」로 갈려 한 글자짜리 큐가 음성 밖에 놓였다.
  const pieces = text.split(/(?<=\.\.!)\s*|(?<=\.\.(?!!))\s*/).map((p) => p.trim()).filter(Boolean)
    .reduce<string[]>((acc, p) => { if (/^[.!?\u2026\s]+$/.test(p) && acc.length) { acc[acc.length - 1] += p; } else { acc.push(p); } return acc; }, []);
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

/** 큐 줄들의 시각 + 본문 글자 인덱스 범위 — chars_t 가 있으면 글자 위치로 실측, 없으면 글자 비례 */
function narCueTimes(text: string, lines: string[], dur: number, charsT: VBlock["chars_t"]): { t0: number; t1: number; ci0: number; ci1: number }[] {
  const times: { t0: number; t1: number; ci0: number; ci1: number }[] = [];
  // 글자별 시각이 본문 길이의 80% 미만이면 어긋난 것 — 글자 비례로 대신한다
  if (charsT && charsT.length >= Math.floor(text.length * 0.8)) {
    // 본문 글자열과 chars_t 를 앞에서부터 대응 (공백 포함 그대로 온다)
    let pos = 0;
    const flat = text;
    for (const ln of lines) {
      const idx = flat.indexOf(ln, pos);
      const a = idx >= 0 ? idx : pos, b = a + ln.length;
      const seg = charsT.slice(Math.min(a, charsT.length - 1), Math.min(b, charsT.length));
      const s = seg.length ? seg[0].s : (times.at(-1)?.t1 ?? 0);
      const e = seg.length ? seg[seg.length - 1].e : s;
      times.push({ t0: r3(s), t1: r3(Math.max(e, s + 0.01)), ci0: a, ci1: b });
      pos = b;
    }
    // 마지막 큐 끝은 실측 총길이까지
    if (times.length) times[times.length - 1].t1 = r3(Math.max(times[times.length - 1].t1, dur));
    return times;
  }
  const total = lines.reduce((a, l) => a + l.length, 0) || 1;
  let t = 0, ci = 0;
  for (const ln of lines) { const d = dur * (ln.length / total); const idx = text.indexOf(ln, ci); const a2 = idx >= 0 ? idx : ci; times.push({ t0: r3(t), t1: r3(t + d), ci0: a2, ci1: a2 + ln.length }); t += d; ci = a2 + ln.length; }
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
    const silences = ((payload.transcript_silences as [number, number][] | undefined) ?? []).filter((x) => Array.isArray(x) && x.length === 2);
    /** 원본 [a,b] 안에서 '소리가 있는' 구간 = 무음 실측의 여집합. 실측이 없으면 발화만 믿는다 */
    const soundIn = (a: number, b: number): [number, number][] => {
      if (!silences.length) return [];
      const out: [number, number][] = []; let cur = a;
      for (const [sa, sb] of silences) { if (sb <= a || sa >= b) continue; if (sa > cur) out.push([cur, Math.min(sa, b)]); cur = Math.max(cur, sb); }
      if (cur < b) out.push([cur, b]);
      return out;
    };
    const visual = (payload.visual ?? {}) as { silent?: { scenes?: Scene[] }[] };
    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !selection?.segments || !voice?.blocks || utts.length === 0) {
      return reject(
        "subtitle", preset,
        "payload 에 carry 값(source·workdir·probe_summary) 또는 selection / voice / transcript_utterances 가 없다",
        "voice 응답의 carry 값과 함께 payload.selection(clips/selection.json 내용) · payload.voice(voice/voice.json 내용) · payload.transcript_utterances(transcript.json 의 utterances 배열) · payload.transcript_silences(transcript.json 의 silences — 무음 실측) · payload.visual(clips/visual.json 내용)을 실어 subtitle 를 다시 부르라.",
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
    // 전처리 — before/after 블록이 가리키는 구간의 이웃이 원본에서 붙어 있으면(≤0.2s) 그 이웃 구간의 over 로 돌린다:
    //   화면을 늘려 같은 장면을 두 번 쓰지 않고, 이웃 구간의 대사 틈에 놓는다. (before → 앞 구간의 마지막 틈, after → 뒤 구간의 첫 틈)
    const segIdx = new Map(segs.map((x, i) => [x.i, i]));
    const rerouted: string[] = [];
    const eff: VBlock[] = vblocks.map((b) => {
      if ((b.pos.kind === "before" || b.pos.kind === "after") && typeof b.pos.seg === "number") {
        const i = segIdx.get(b.pos.seg); if (i === undefined) return b;
        const nb = b.pos.kind === "before" ? segs[i - 1] : segs[i + 1];
        const me = segs[i];
        if (nb && Math.abs(b.pos.kind === "before" ? nb.out - me.in : nb.in - me.out) < 0.2) { rerouted.push(`나레 ${b.n}: ${b.pos.kind} seg#${me.i} → 붙어 있는 구간 ${nb.i} 의 틈으로`); return { ...b, pos: { kind: "over", seg: nb.i }, _prefer: b.pos.kind === "before" ? "tail" : "head" } as VBlock; }
      }
      return b;
    });
    const byPos = (kind: string, ref: number) => eff.filter((b) => b.pos.kind === kind && (kind === "bridge" ? b.pos.bridge === ref : b.pos.seg === ref));
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
      // 틈 = 소리가 없는 자리. 무음 실측이 있으면 **실측 소리**만 믿는다(전사 세그먼트는 끝이 늘어나 있을 수 있다 — 'Hey!' 21s).
      //   실측이 없으면 발화 시각으로 대신한다.
      // 점유 = 정상 길이 발화(전사 시각 신뢰) ∪ 실측 소리(전사에 안 잡힌 외침·수상하게 긴 발화의 실제 소리)
      const occupied = [
        ...uttsIn(s.in, s.out).filter((u) => !silences.length || !suspiciousUtt(u)).map((u) => [Math.max(u.start, s.in), Math.min(u.end, s.out)] as [number, number]),
        ...soundIn(s.in, s.out),
      ].sort((a, b) => a[0] - b[0]);
      const gaps: [number, number][] = [];
      let cur = s.in;
      for (const [a, b] of occupied) { if (a - cur > 0.05) gaps.push([cur, a]); cur = Math.max(cur, b); }
      if (s.out - cur > 0.05) gaps.push([cur, s.out]);
      // 이야기 순서대로 채운다 — 앞에서부터 남는 자리가 있는 틈에 놓고(한 틈에 여러 블록 가능), 없으면 가장 큰 틈에 겹쳐 놓는다(덕킹)
      const room = gaps.map(([a, b]) => ({ a, b, cur: a }));
      const GAPPAD = SUB.큐_사이_최소간격_s;
      let lastEnd = s.in;
      // 순서: 앞 구간에서 넘어온(before) 블록은 이 구간의 **마지막** 틈, 나머지는 이야기 순서대로 앞에서부터
      const ordered = [...blocks.filter((b) => b._prefer !== "tail"), ...blocks.filter((b) => b._prefer === "tail")];
      for (const b of ordered) {
        let g: { a: number; b: number; cur: number } | undefined;
        if (b._prefer === "tail") {
          const cands = room.filter((r) => r.b - r.cur >= b.dur_s + GAPPAD); g = cands[cands.length - 1];
          if (g) { const start = g.b - GAPPAD / 2 - b.dur_s; g.b = start - GAPPAD / 2; const t0 = pic.t0 + (start - s.in); nars.push({ n: b.n, t0: r3(t0), t1: r3(t0 + b.dur_s), wav: b.wav, text: b.text, anchor: `${anchorTag} 마지막 틈(before 에서 이동)` }); continue; }
        }
        if (!g) g = room.find((r) => r.cur >= lastEnd - 1e-6 && r.b - r.cur >= b.dur_s + GAPPAD);
        if (!g) g = room.find((r) => r.b - r.cur >= b.dur_s + GAPPAD);
        let start: number;
        if (g) { start = g.cur + GAPPAD / 2; g.cur = start + b.dur_s + GAPPAD / 2; }
        else {
          // 자리가 없다 — 소리와 가장 덜 겹치는 위치를 0.25s 격자로 찾는다 (실측 우선)
          let best = Math.max(s.in, lastEnd), bestOv = Infinity;
          for (let x = Math.max(s.in, lastEnd); x + b.dur_s <= s.out + 1e-6; x += 0.25) {
            const ov = occupied.reduce((acc, [a, e]) => acc + Math.max(0, Math.min(e, x + b.dur_s) - Math.max(a, x)), 0);
            if (ov < bestOv - 1e-6) { bestOv = ov; best = x; }
          }
          start = best;
          warnings.push(`블록 ${b.n} (${r2(b.dur_s)}s)이 구간 ${s.i} 의 남은 틈보다 길다 — 소리와 ${r2(bestOv)}s 겹치는 자리에 놓았다(덕킹).`);
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
      // 연장 창 고르기 — 인접 30s 안(선택 구간과 겹치지 않는 원본)에서 실측 소리가 가장 적은 창. 같으면 구간에 가까운 쪽
      const soundLen = (a: number, b: number) => soundIn(a, b).reduce((acc, [x, y]) => acc + (y - x), 0);
      const pickWindow = (dur: number, dir: "before" | "after", edge: number): number => {
        const lo = dir === "before" ? Math.max(prev ? prev.out : 0, edge - 30) : edge;
        const hi = dir === "before" ? edge : Math.min(next ? next.in : ps.duration_s!, edge + 30);
        let best = dir === "before" ? Math.max(lo, edge - dur) : edge, bestS = Infinity;
        if (dir === "before") { for (let x = edge - dur; x >= lo; x -= 0.5) { const sl = silences.length ? soundLen(x, x + dur) : 0; if (sl < bestS - 1e-6) { bestS = sl; best = x; } if (bestS === 0) break; } }
        else { for (let x = edge; x + dur <= hi; x += 0.5) { const sl = silences.length ? soundLen(x, x + dur) : 0; if (sl < bestS - 1e-6) { bestS = sl; best = x; } if (bestS === 0) break; } }
        return best;
      };
      // before 블록 (붙어 있는 이웃이 있으면 전처리에서 이미 over 로 돌렸다 → 여기 남은 것은 연장)
      const before = byPos("before", s.i);
      for (const b of before) {
        const a = pickWindow(b.dur_s, "before", s.in);
        pics.push({ k: k++, kind: "extend", role: "연장", src_in: r3(a), src_out: r3(a + b.dur_s), t0: r3(t), t1: r3(t + b.dur_s), audio: "duck", seg: s.i, why: `before 나레 ${b.n} 자리 — 원본 앞 30s 안 소리 가장 적은 창` });
        nars.push({ n: b.n, t0: r3(t), t1: r3(t + b.dur_s), wav: b.wav, text: b.text, anchor: `before seg#${s.i} 연장` });
        t += b.dur_s;
      }
      // 구간 본체
      const pic: Pic = { k: k++, kind: "segment", role: s.role, src_in: s.in, src_out: s.out, t0: r3(t), t1: r3(t + (s.out - s.in)), audio: dialogueRoles.has(s.role) ? "keep" : "hold", seg: s.i };
      pics.push(pic);
      t += s.out - s.in;
      placeOver(s, pic, byPos("over", s.i));
      // after 블록 (붙어 있는 이웃은 전처리에서 over 로 돌렸다 → 여기 남은 것은 연장)
      const after = byPos("after", s.i);
      for (const b of after) {
        const a = pickWindow(b.dur_s, "after", s.out);
        pics.push({ k: k++, kind: "extend", role: "연장", src_in: r3(a), src_out: r3(a + b.dur_s), t0: r3(t), t1: r3(t + b.dur_s), audio: "duck", seg: s.i, why: `after 나레 ${b.n} 자리 — 원본 뒤 30s 안 소리 가장 적은 창` });
        nars.push({ n: b.n, t0: r3(t), t1: r3(t + b.dur_s), wav: b.wav, text: b.text, anchor: `after seg#${s.i} 연장` });
        t += b.dur_s;
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
        // 이 구간의 소리 구간(타임라인 시각): 실측 소리(있으면 그것만 — 늘어난 전사 끝을 믿지 않는다) 또는 발화 + 이 구간 위 나레
        const sound: [number, number][] = [
          ...uttsIn(p.src_in, p.src_out).filter((u) => !silences.length || !suspiciousUtt(u)).map((u) => [p.t0 + (Math.max(u.start, p.src_in) - p.src_in), p.t0 + (Math.min(u.end, p.src_out) - p.src_in)] as [number, number]),
          // 실측 소리는 지속 길이가 규격 보호_소리_최소_s 이상인 것만 컷을 막는다 (짧은 현장음 스웰은 잘라도 된다)
          ...soundIn(p.src_in, p.src_out).filter(([a, b]) => b - a >= (TC.보호_소리_최소_s ?? 0)).map(([a, b]) => [p.t0 + (a - p.src_in), p.t0 + (b - p.src_in)] as [number, number]),
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
    for (const r of rerouted) warnings.push(r);
    const totalT = r3(t);
    nars.sort((a, b) => a.t0 - b.t0);
    // 나레끼리 겹침 해소: 뒤 것을 밀어낸다 (앞뒤 겹침이 생기는 자리는 대개 겹침 규칙의 꼬리/머리)
    for (let i = 1; i < nars.length; i++) {
      const gapMin = SUB.큐_사이_최소간격_s;
      if (nars[i].t0 < nars[i - 1].t1 + gapMin) { const shift = nars[i - 1].t1 + gapMin - nars[i].t0; nars[i].t0 = r3(nars[i].t0 + shift); nars[i].t1 = r3(nars[i].t1 + shift); warnings.push(`나레 ${nars[i].n} 을 ${r2(shift)}s 뒤로 밀었다 (앞 나레 ${nars[i - 1].n} 과 겹침).`); }
    }

    // ── 대사 줄 (자막 대상 = 대사 역할 구간 안 발화) ──────────────────────
    // 단어 단위 실측(Speechmatics). 있으면 대사 큐의 시작·끝을 **그 말의 첫/마지막 단어**에 맞춘다(G-대사선행).
    const words = (Array.isArray(payload.transcript_words) ? payload.transcript_words : []) as { w: string; s: number; e: number }[];
    const wordSpan = (a: number, b: number): [number, number] | null => {
      const inside = words.filter((w) => w.e > a - 0.02 && w.s < b + 0.02);
      return inside.length ? [inside[0].s, inside[inside.length - 1].e] : null;
    };
    const dlgLines: { id: string; seg: number; t0: number; t1: number; src_start: number; src_end: number; en: string; word_t0?: number }[] = [];
    // 발화가 두 구간에 걸치면 더 많이 겹치는 구간에만 둔다 (같은 줄이 두 번 뜨지 않게)
    const dlgPics = pics.filter((p) => p.kind === "segment" && dialogueRoles.has(p.role));
    const bestPic = new Map<Utt, Pic>();
    for (const u of utts) { let best: Pic | null = null, bo = 0; for (const p of dlgPics) { const o = Math.min(u.end, p.src_out) - Math.max(u.start, p.src_in); if (o > bo) { bo = o; best = p; } } if (best && bo >= 0.15) bestPic.set(u, best); }
    for (const p of dlgPics) {
      for (const u of uttsIn(p.src_in, p.src_out)) {
        if (bestPic.get(u) !== p) continue;
        const a = Math.max(u.start, p.src_in), b = Math.min(u.end, p.src_out);
        if (b - a < 0.15) continue;
        const ws = wordSpan(a, b);                                   // 실측 단어 구간(원본 시각)
        const a2 = ws ? Math.max(a, ws[0]) : a, b2 = ws ? Math.min(b, Math.max(ws[1], ws[0] + 0.2)) : b;
        dlgLines.push({ id: `d${String(dlgLines.length + 1).padStart(3, "0")}`, seg: p.seg!, t0: r3(p.t0 + (a2 - p.src_in)), t1: r3(p.t0 + (b2 - p.src_in)), src_start: r3(a2), src_end: r3(b2), en: u.text, word_t0: ws ? r3(p.t0 + (ws[0] - p.src_in)) : undefined });
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
          carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path", "selection", "voice", "transcript_utterances", "transcript_silences", "visual"],
          source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: payload.voice_path,
          selection, voice, transcript_utterances: utts, transcript_silences: silences, visual,
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
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path", "selection", "voice", "transcript_utterances", "transcript_silences", "visual"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: payload.voice_path,
        selection, voice, transcript_utterances: utts, transcript_silences: silences, visual,
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
      // R1(2026-08-17): 나레 큐는 **음성 밖으로 나가지 않는다**. 최소 길이는 뒤로 밀지 말고 **앞으로 당겨** 채우고,
      //   그래도 모자라면 앞 큐와 합친다(짧아도 소리 있는 동안만). 근거: 8:59~9:07 사례 — 최소 길이를 뒤로 밀어
      //   자막만 남고 소리가 없었다(n16·n18·n22·n23·n27 5건). 규격 「자막.나레_큐_음성_안」
      const voiceEnd = b.dur_s;                       // 블록 안 음성 끝(초) = wav 실측 = voice.json
      // 실측 발성 구간(voice ② 의 silencedetect). 문자 정렬은 문장 사이 쉼을 글자에 붙여 늘리므로 큐를 이 구간으로 클램프한다
      const SP: [number, number][] = (b.speech && b.speech.length ? b.speech : [[0, voiceEnd]]) as [number, number][];
      const spIn = (x: number, y: number) => SP.filter(([u, v]) => Math.min(y, v) - Math.max(x, u) > 0.001).map(([u, v]) => [Math.max(x, u), Math.min(y, v)] as [number, number]);
      const clamp = (x: number, y: number): [number, number] | null => { const seg = spIn(x, y); return seg.length ? [seg[0][0], seg[seg.length - 1][1]] : null; };
      const mine: Cue[] = [];
      const quietMax0 = SUB.큐_무음노출_상한_s ?? 0.25;
      // 실측 발성 덩어리(쉼 상한보다 긴 무음으로만 나눈다)
      const RUNS: [number, number][] = [];
      for (const [u, v] of SP) { const last = RUNS[RUNS.length - 1]; if (last && u - last[1] <= quietMax0 + 1e-6) last[1] = v; else RUNS.push([u, v]); }
      // 덩어리가 둘 이상이면 문자 정렬(chars_t)을 믿지 않는다 — 정렬은 쉼을 무시해 앞으로 밀린다(2026-08-17 실측).
      //   대신 **발성 시간을 글자 수 비례로** 줄에 나눠 주고, 덩어리 경계에서 줄을 쪼갠다.
      type Piece = { text: string; a: number; e: number };
      const planned: Piece[][] | null = (() => {
        if (RUNS.length <= 1) return null;
        const spTotal = RUNS.reduce((acc, [u, v]) => acc + (v - u), 0);
        const w = lines.map((l) => Math.max(1, l.replace(/\s/g, "").length));
        const wTot = w.reduce((x, y) => x + y, 0);
        const toWall = (sp: number) => {           // 발성 누적시간 → 실제 시각
          let acc = 0;
          for (const [u, v] of RUNS) { const len = v - u; if (sp <= acc + len + 1e-9) return u + (sp - acc); acc += len; }
          return RUNS[RUNS.length - 1][1];
        };
        const out: Piece[][] = []; let cum = 0;
        for (let li = 0; li < lines.length; li++) {
          const spA = cum, spB = cum + spTotal * (w[li] / wTot); cum = spB;
          // 이 줄의 발성 구간을 덩어리 경계에서 쪼갠다
          const segs: [number, number][] = [];
          let accA = 0;
          for (const [u, v] of RUNS) {
            const len = v - u, rA = accA, rB = accA + len; accA = rB;
            const x = Math.max(spA, rA), y = Math.min(spB, rB);
            if (y - x > 0.05) segs.push([u + (x - rA), u + (y - rA)]);
          }
          if (!segs.length) { segs.push([toWall(spA), Math.max(toWall(spB), toWall(spA) + 0.05)]); }
          // 글자도 같은 비율로 나눈다 (어절 경계로 반올림)
          const txt = lines[li]; const pieces: Piece[] = [];
          const spLen = spB - spA || 1; let ci = 0;
          segs.forEach(([x, y], k) => {
            const share = segs.length === 1 ? 1 : ((y - x) / segs.reduce((acc2, [p, q]) => acc2 + (q - p), 0));
            let cut = k === segs.length - 1 ? txt.length : Math.min(txt.length, ci + Math.max(1, Math.round(txt.length * share)));
            if (k < segs.length - 1) {
              const sp2 = txt.lastIndexOf(" ", cut);                      // 어절 경계로만 자른다
              cut = sp2 > ci ? sp2 : txt.length;                          // 경계가 없으면 이 조각이 줄 전체를 가진다
            }
            const t2 = txt.slice(ci, cut).trim(); ci = cut;
            if (!t2) return;
            const prevP = pieces[pieces.length - 1];
            if (/^[.!?…]+$/.test(t2) && prevP) { prevP.text += t2; prevP.e = y; return; }   // 구두점만 남은 조각은 앞에 붙인다(R2)
            pieces.push({ text: t2, a: x, e: y });
          });
          // 너무 짧은 조각(2자 이하)은 옆 조각에 붙인다 — 「불」 같은 한 글자 자막을 만들지 않는다
          for (let k = pieces.length - 1; k >= 0 && pieces.length > 1; k--) {
            if (pieces[k].text.replace(/\s/g, "").length > 2 && pieces[k].e - pieces[k].a >= (SUB.큐_최소길이_s ?? 0.8) / 2) continue;
            const prevP = pieces[k - 1], nextP = pieces[k + 1];
            const target = !prevP ? nextP : !nextP ? prevP : (prevP.e - prevP.a >= nextP.e - nextP.a ? prevP : nextP);
            if (!target) break;
            if (target === prevP) target.text = `${target.text} ${pieces[k].text}`.trim();
            else target.text = `${pieces[k].text} ${target.text}`.trim();
            pieces.splice(k, 1);
          }
          out.push(pieces.length ? pieces : [{ text: txt, a: segs[0][0], e: segs[segs.length - 1][1] }]);
          void spLen;
        }
        warnings.push(`나레 ${n.n}: 문장 사이 쉼 ${RUNS.length - 1}곳이 실측돼 자막 시각을 문자 정렬 대신 **발성 실측**에 맞췄다.`);
        return out;
      })();
      lines.forEach((ln, i) => {
        if (ln.length > A["G-자막_한줄_최대자수"].나레) hard.push(`나레 ${n.n}: 줄 ${ln.length}자 > ${A["G-자막_한줄_최대자수"].나레}자 — 「${ln}」`);
        const T0 = times[i];
        let a0 = T0.t0, e0 = Math.min(T0.t1, voiceEnd);
        const c0 = clamp(a0, e0);                                                   // ⓪ 실측 발성으로 클램프(앞뒤 쉼 제거)
        if (c0) { a0 = c0[0]; e0 = c0[1]; }
        // ⓪-2 줄 **안쪽**에 상한을 넘는 쉼이 있으면 그 자리에서 큐를 쪼갠다 (글자별 시각으로 문구도 나눈다)
        const runs = spIn(a0, e0);
        const merged: [number, number][] = [];
        for (const rr of runs) {
          const last = merged[merged.length - 1];
          if (last && rr[0] - last[1] <= quietMax0 + 1e-6) last[1] = rr[1]; else merged.push([rr[0], rr[1]]);
        }
        let pieces: Piece[] = [{ text: ln, a: a0, e: e0 }];
        if (planned) { pieces = planned[i]; }
        else if (merged.length > 1) {
          const ct = b.chars_t ?? null;
          if (ct && T0.ci1 <= ct.length) {
            const out: Piece[] = [];
            for (const [ra, re] of merged) {
              let lo = -1, hi = -1;
              for (let ci = T0.ci0; ci < T0.ci1; ci++) {
                const mid = (ct[ci].s + ct[ci].e) / 2;
                if (mid >= ra - 1e-6 && mid <= re + 1e-6) { if (lo < 0) lo = ci; hi = ci; }
              }
              if (lo < 0) continue;
              const txt = b.text.slice(lo, hi + 1).trim();
              if (txt) out.push({ text: txt, a: ra, e: re });
            }
            if (out.length && out.reduce((acc, p2) => acc + p2.text.length, 0) >= ln.replace(/\s/g, "").length * 0.5) {
              pieces = out;
              warnings.push(`나레 ${n.n}: 줄 「${ln}」 안에 ${r2(merged[1][0] - merged[0][1])}s 쉼이 있어 큐를 ${out.length}개로 쪼갰다(실측).`);
            } else { pieces = [{ text: ln, a: merged[0][0], e: merged[merged.length - 1][1] }]; }
          } else {
            pieces = [{ text: ln, a: merged[0][0], e: merged[0][1] }];   // 글자 시각이 없으면 첫 발성 덩어리만
          }
        }
        for (const pc of pieces) {
          let a = pc.a, e = pc.e;
          const prev = mine.length ? mine[mine.length - 1] : null;
          const gapS = SUB.큐_사이_최소간격_s, minS = SUB.큐_최소길이_s;
          if (e - a < minS) {
            const seg = SP.find(([u, v]) => a >= u - 0.001 && a <= v + 0.001) ?? SP[0];
            a = Math.max(seg[0], Math.min(a, e - minS));                             // ① 발성 안에서 앞으로 당긴다
            if (prev) {
              const prevT0 = prev.t0 - n.t0, prevT1 = prev.t1 - n.t0;
              if (a < prevT1 + gapS) {
                const borrowed = a - gapS;                                           // ② 앞 큐에서 시간을 빌린다
                const prevFloor = Math.max(0.4, minS / 2);                         // 앞 큐는 0.4s 까지 양보할 수 있다
                if (borrowed - prevT0 >= prevFloor) prev.t1 = r3(n.t0 + borrowed);
                else a = prevT1 + gapS;
              }
            }
          }
          if (e - a < minS && prev && `${prev.text} ${pc.text}`.trim().length <= A["G-자막_한줄_최대자수"].나레
              && (pc.a - (prev.t1 - n.t0)) <= quietMax0 + 1e-6) {                    // ③ 앞 큐와 병합(자수·쉼 안에서만)
            prev.text = `${prev.text} ${pc.text}`.trim(); prev.t1 = r3(n.t0 + e);
            warnings.push(`나레 ${n.n}: 끝줄 「${pc.text}」을 앞 큐와 합쳤다 — 음성이 ${r2(voiceEnd)}s 에서 끝나 최소 길이를 뒤로 밀 수 없다.`);
            continue;
          }
          if (e - a < 0.12) {                                                       // ④ 뒤집혔거나 너무 짧다
            const canMerge = prev && `${prev.text} ${pc.text}`.trim().length <= A["G-자막_한줄_최대자수"].나레;
            if (canMerge) { prev!.text = `${prev!.text} ${pc.text}`.trim(); prev!.t1 = r3(Math.max(prev!.t1, n.t0 + e)); continue; }
            if (prev) {                                                              // 자수가 넘치면 앞 큐를 조금 더 줄여 제 자리를 만든다
              const room = r3(n.t0 + e - 0.3) - gapS;
              if (room - prev.t0 >= 0.3) { prev.t1 = r3(room); a = e - 0.3; }
            }
            if (e - a < 0.12) { warnings.push(`나레 ${n.n}: 큐 「${pc.text}」을 놓을 자리가 없어 버렸다(발성 ${r2(Math.max(0, e - a))}s).`); continue; }
          }
          if (e - a < minS) warnings.push(`나레 ${n.n}: 큐 「${pc.text}」이 ${r2(e - a)}s 로 최소 길이 ${minS}s 미만이다 — 발성 구간을 넘지 않는 것을 우선했다.`);
          mine.push({ lane: "nar", t0: r3(n.t0 + Math.max(0, a)), t1: r3(n.t0 + e), text: pc.text, ref: `n${n.n}` });
        }
      });
      cues.push(...mine);
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
    // ── R3(2026-08-17): 나레 자막과 대사 자막은 **동시에 뜨지 않는다** (사용자 결정 — 같이 뜨면 집중이 안 된다).
    //   나레 음성이 나오는 동안은 나레 우선 → 겹치는 **대사 큐를 자르고**, 남은 길이가 큐_최소길이 미만이면 버린다.
    //   원본 소리는 A3 로 덕킹돼 있어 자막이 빠져도 흐름이 끊기지 않는다. 볼케이노 완성본도 교차 겹침 0(벤치마크 실측).
    const dlgDropped: string[] = [], dlgTrimmed: string[] = [];
    {
      const N = cues.filter((c) => c.lane === "nar").sort((x, y) => x.t0 - y.t0);
      const gapS = SUB.큐_사이_최소간격_s, minS = SUB.큐_최소길이_s;
      const minCut = SUB.잘린_대사큐_최소길이_s ?? minS;   // 나레를 피해 잘리거나 미뤄진 큐는 이만큼까지 허용(규격 「자막.잘린_대사큐_최소길이_s」)
      const drop = new Set<string>();
      const D = cues.filter((c) => c.lane === "dlg").sort((x, y) => x.t0 - y.t0);
      for (const d of D) {
        const utt = dlgLines.find((x) => x.id === d.ref);
        // 이 대사 큐가 쓸 수 있는 시간 = [발화 시작, 발화 끝 + 꼬리] 에서 **나레 큐와 다른 대사 큐**를 뺀 것
        const hi = Math.min(utt ? Math.max(utt.t1, utt.t0 + minS) + SUB.대사큐_꼬리_s : d.t1, d.t0 + SUB.큐_최대길이_s);
        const busy = N.map((c) => [c.t0, c.t1] as [number, number]);   // 나레 큐만 피한다 (대사끼리는 아래 정리 단계에서)
        const free: [number, number][] = [];
        let cur = d.t0;
        for (const n of busy) {
          if (n[1] <= cur + 1e-6 || n[0] >= hi - 1e-6) continue;
          if (n[0] - gapS > cur) free.push([cur, n[0] - gapS]);
          cur = Math.max(cur, n[1] + gapS);
        }
        if (hi > cur) free.push([cur, hi]);
        const best = free.filter(([x, y]) => y - x >= minCut).sort((p, q) => (q[1] - q[0]) - (p[1] - p[0]))[0];
        if (!best) { drop.add(String(d.ref)); dlgDropped.push(`${d.ref} ${d.t0}~${d.t1} 「${d.text}」 (나레 자막을 피할 ${minCut}s 자리가 없다)`); continue; }
        const t0 = r3(best[0]), t1 = r3(Math.min(best[1], Math.max(best[0] + minS, Math.min(d.t1, best[1]))));
        if (Math.abs(t0 - d.t0) > 1e-6 || Math.abs(t1 - d.t1) > 1e-6) dlgTrimmed.push(`${d.ref} ${d.t0}~${d.t1} → ${t0}~${t1} 「${d.text}」`);
        d.t0 = t0; d.t1 = t1;
      }
      // 대사끼리 겹치면 **앞 큐 끝만 자른다**(뒤 큐 시작을 밀면 나레와 다시 겹칠 수 있다). 잘라서 최소 길이 미만이면 앞 큐를 버린다.
      {
        const L = D.filter((x) => !drop.has(String(x.ref))).sort((x, y) => x.t0 - y.t0);
        for (let i = 1; i < L.length; i++) {
          if (L[i].t0 < L[i - 1].t1 - 1e-6) {
            const end = r3(L[i].t0 - gapS);
            if (end - L[i - 1].t0 >= minCut) { dlgTrimmed.push(`${L[i - 1].ref} 끝 ${L[i - 1].t1} → ${end} (뒤 대사 큐와 겹침)`); L[i - 1].t1 = end; }
            else { drop.add(String(L[i - 1].ref)); dlgDropped.push(`${L[i - 1].ref} ${L[i - 1].t0}~${L[i - 1].t1} 「${L[i - 1].text}」 (앞뒤 큐 사이에 ${minCut}s 자리가 없다)`); }
          }
        }
      }
      for (let i = cues.length - 1; i >= 0; i--) if (cues[i].lane === "dlg" && drop.has(String(cues[i].ref))) cues.splice(i, 1);
      cues.sort((x, y) => x.t0 - y.t0);
      if (dlgTrimmed.length) warnings.push(`교차 겹침(나레 우선): 대사 큐 ${dlgTrimmed.length}개를 나레 자막 밖으로 자르거나 미뤘다.`);
      if (dlgDropped.length) warnings.push(`교차 겹침(나레 우선): 대사 큐 ${dlgDropped.length}개를 버렸다 — ${dlgDropped.slice(0, 4).join(" · ")}${dlgDropped.length > 4 ? " …" : ""}`);
    }
    let overlapsLeft = 0;
    for (const lane of ["nar", "dlg"] as const) { const L = cues.filter((c) => c.lane === lane); for (let i = 1; i < L.length; i++) if (L[i].t0 < L[i - 1].t1) overlapsLeft++; }
    // 교차 겹침 실측 (G-교차겹침)
    let crossS = 0, crossN = 0;
    for (const n of cues.filter((c) => c.lane === "nar")) for (const d of cues.filter((c) => c.lane === "dlg")) {
      const ov = Math.min(n.t1, d.t1) - Math.max(n.t0, d.t0);
      if (ov > 0.001) { crossN++; crossS += ov; }
    }
    crossS = r3(crossS);
    // 자막↔음성 일치 실측 (G-자막음성일치)
    const epsF = 1 / 24;
    const narOut: string[] = [], dlgOut: string[] = [];
    const quietMax = SUB.큐_무음노출_상한_s ?? 0.25;
    let quietTotal = 0, quietWorst = 0, speechMeasured = 0;
    for (const n of nars) {
      const nb = vmap.get(n.n); if (!nb) continue;
      const vEnd = n.t0 + nb.dur_s;
      const sp = (nb.speech && nb.speech.length ? nb.speech : null);
      if (sp) speechMeasured++;
      for (const c of cues) {
        if (c.lane !== "nar" || c.ref !== `n${n.n}`) continue;
        if (c.t0 < n.t0 - epsF || c.t1 > vEnd + epsF) narOut.push(`n${n.n} 큐 ${c.t0}~${c.t1} ⊄ 음성 ${r3(n.t0)}~${r3(vEnd)} 「${c.text}」`);
        if (!sp) continue;
        const a = c.t0 - n.t0, b2 = c.t1 - n.t0;
        const spk = sp.reduce((acc, [u, v]) => acc + Math.max(0, Math.min(b2, v) - Math.max(a, u)), 0);
        const quiet = r3(Math.max(0, (b2 - a) - spk));
        quietTotal += quiet; quietWorst = Math.max(quietWorst, quiet);
        if (quiet > quietMax + 1e-6) narOut.push(`n${n.n} 큐 ${c.t0}~${c.t1} 안에 무음 ${quiet}s > ${quietMax}s 「${c.text}」`);
      }
    }
    quietTotal = r3(quietTotal); quietWorst = r3(quietWorst);
    if (speechMeasured === 0) warnings.push("나레 발성 구간 실측(voice.json blocks[].speech)이 없다 — 자막 큐를 문자 정렬만으로 잘랐다. 쉼 위에 자막이 뜰 수 있다(voice ② 를 다시 돌려 speech 를 채운다).");
    for (const c of cues) {
      if (c.lane !== "dlg") continue;
      const d = dlgLines.find((x) => x.id === c.ref);
      if (!d) { dlgOut.push(`${c.ref}: 대응 발화 없음`); continue; }
      const maxEnd = Math.max(d.t1, d.t0 + SUB.큐_최소길이_s) + SUB.대사큐_꼬리_s;
      if (c.t0 < d.t0 - 0.05 || c.t1 > maxEnd + epsF) dlgOut.push(`${c.ref} 큐 ${c.t0}~${c.t1} ⊄ 발화 ${d.t0}~${d.t1}(+꼬리 ${SUB.대사큐_꼬리_s}) 「${c.text}」`);
    }
    if (overlapsLeft > (A["G-자막_겹침_max"].value ?? 0)) hard.push(`같은 레인 자막 겹침 ${overlapsLeft}건 (허용 ${A["G-자막_겹침_max"].value})`);

    // ── 죽은 시간 (홀드 제외) ─────────────────────────────────────────────
    const holdIntervals = pics.filter((p) => holdRoles.has(p.role)).map((p) => [p.t0, p.t1] as [number, number]);
    const holdS = r3(holdIntervals.reduce((a, [x, y]) => a + (y - x), 0));
    // 축 = 자막 큐(나레·대사)가 있는 시간 (가족 G14 와 같은 축 — 정답지 대본.G-죽은시간_max.적용)
    // 축 = 자막 큐 ∪ **나레 음성 구간**. 나레 큐를 실측 발성으로 바짝 자른 뒤(2026-08-17)부터
    //   블록 안 쉼(숨·문장 사이)이 "죽은 시간"으로 잡혔다 — 그 시간에도 나레는 들리고 있으므로 죽은 시간이 아니다.
    const sound: [number, number][] = [...cues.map((c) => [c.t0, c.t1] as [number, number]), ...nars.map((n) => [n.t0, n.t1] as [number, number])].sort((a, b) => a[0] - b[0]);
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
    gates.push({ id: "G-교차겹침(나레×대사 자막)", pass: crossS <= (A["G-교차겹침_max"]?.value ?? 0), hard: true, detail: `겹침 ${crossN}건 · ${crossS}s (허용 ${A["G-교차겹침_max"]?.value ?? 0}s) · 대사 큐 잘림 ${dlgTrimmed.length} · 버림 ${dlgDropped.length}`, fix: "나레 음성이 나오는 동안은 나레 자막 우선 — 겹치는 대사 큐의 시작/끝을 나레 큐 밖으로 밀고(큐_사이_최소간격), 통째로 덮이거나 남은 길이가 큐_최소길이 미만이면 그 대사 큐를 버린다. 버린 대사가 전체 대사 큐의 5%를 넘으면 나레 배치(placeOver)를 대사 틈 쪽으로 다시 잡는다." });
    const leadMax = (SUB as unknown as { 대사선행_상한_s?: number }).대사선행_상한_s ?? 0.1;
    const leads = cues.filter((c) => c.lane === "dlg").map((c) => {
      const d = dlgLines.find((x) => x.id === c.ref);
      const w0 = d?.word_t0;
      return { ref: c.ref, lead: w0 === undefined ? null : r3(w0 - c.t0), text: c.text };
    });
    const leadVals = leads.filter((l) => l.lead !== null).map((l) => l.lead as number);
    const leadBad = leads.filter((l) => (l.lead ?? 0) > leadMax + 1e-6);
    const leadAvg = leadVals.length ? r3(leadVals.reduce((a, b) => a + b, 0) / leadVals.length) : 0;
    const leadWorst = leadVals.length ? r3(Math.max(...leadVals)) : 0;
    gates.push({ id: "G-대사선행", pass: leadBad.length === 0, hard: true,
      detail: `대사 큐가 첫 단어보다 먼저 뜬 정도 — 평균 ${leadAvg}s · 최대 ${leadWorst}s (상한 ${leadMax}s) · 초과 ${leadBad.length}건 · 단어 실측 ${leadVals.length}/${leads.length}${leadBad.length ? " — " + leadBad.slice(0, 3).map((l) => `${l.ref} ${l.lead}s 「${l.text}」`).join(" · ") : ""}`,
      fix: "대사 큐 시작을 그 말의 **첫 단어 시작**(transcript.json words)으로 맞춘다. 단어 실측이 0이면 전사를 Speechmatics(규격 전사.제공자)로 다시 돌린다 — Groq 폴백은 세그먼트 단위라 자막이 말보다 앞선다." });
    gates.push({ id: "G-자막음성일치", pass: narOut.length === 0 && dlgOut.length === 0, hard: true, detail: `나레 큐 음성 밖/무음초과 ${narOut.length} · 대사 큐 발화 밖 ${dlgOut.length} · 무음 노출 총 ${quietTotal}s(최대 ${quietWorst}s ≤ ${quietMax}s, 실측 블록 ${speechMeasured}/${nars.length})${narOut.length || dlgOut.length ? " — " + [...narOut, ...dlgOut].slice(0, 4).join(" · ") : ""}`, fix: "나레: 큐를 **실측 발성 구간**(voice.json blocks[].speech)으로 클램프하고 최소 길이도 발성 안에서만 채운다. 실측이 없으면 voice ② 를 다시 돌린다. 큐 끝은 음성 끝(t0+wav)을 넘지 않는다. 최소 길이는 앞으로 당겨 채운다(모자라면 앞 큐와 병합) — 뒤로 미루지 않는다. 대사: 큐 시작 = 발화 시작, 끝 ≤ max(발화 끝, 시작+큐_최소길이)+대사큐_꼬리 안에 들어오는지 규격 값을 확인한다." });
    const deadPass = deadRatio <= (A["G-죽은시간_max"].value ?? 0.1);
    gates.push({ id: "G-죽은시간(홀드 제외)", pass: deadPass, hard: true, detail: `죽은 ${deadS}s / (총 ${totalT}s − 홀드 ${holdS}s = ${denom}s) = ${deadRatio} (≤${A["G-죽은시간_max"].value}). 죽은 구간 상위: ${deadSpans.slice(0, 5).map((d) => `${d.t0}~${d.t1}(${d.len}s)`).join(", ")}`, fix: deadPass ? undefined : `죽은 구간 상위 ${Math.min(5, deadSpans.length)}개 위치를 보고 script 로 돌아가 그 자리에 원인·의미 나레를 쓰거나(나레이션.md 2절), 그 구간을 자르거나 당겨 붙여라(규격 조립). 대사 역할인데 대사가 없는 자리면 select 의 역할을 시각몽타주(홀드)로 바꾼다.` });
    const soft: string[] = [...warnings];
    if (dlgDropped.length) soft.push(`[교차겹침] 버린 대사 큐 ${dlgDropped.length}: ${dlgDropped.join(" · ")}`);
    if (!silences.length) soft.push("무음 실측(transcript_silences)이 없어 틈·컷을 발화 시각만으로 계산했다 — 전사에 안 잡힌 소리 위에 나레가 얹힐 수 있다.");
    if (maxNoSub > A.무자막_최장_s.value) soft.push(`[soft] 무자막 최장 ${maxNoSub}s > ${A.무자막_최장_s.value}s (G64)`);
    if (cuesPerClip < A.클립당_자막.min || cuesPerClip > A.클립당_자막.max) soft.push(`[soft] 클립당 자막 ${cuesPerClip} (대역 ${A.클립당_자막.min}~${A.클립당_자막.max}, G12)`);
    // 나레-대사 겹침(다른 레인, 덕킹) 정보
    let narOverDlg = 0; for (const n of nars) for (const d of dlgLines) narOverDlg += Math.max(0, Math.min(n.t1, d.t1) - Math.max(n.t0, d.t0));
    narOverDlg = r3(narOverDlg);

    const metrics = { dlg_lead_avg_s: leadAvg, dlg_lead_max_s: leadWorst, dlg_lead_over: leadBad.length, words_measured: words.length, nar_cue_quiet_s: quietTotal, nar_cue_quiet_max_s: quietWorst, nar_speech_measured_blocks: speechMeasured, cross_overlap_s: crossS, cross_overlap_n: crossN, dlg_cues_trimmed: dlgTrimmed.length, dlg_cues_dropped: dlgDropped.length, total_s: totalT, cuts: pics.length, narrations: nars.length, cue_count: cues.length, cues_nar: cues.filter((c) => c.lane === "nar").length, cues_dlg: cues.filter((c) => c.lane === "dlg").length, cues_per_min: r3(cues.length / (totalT / 60)), max_line_chars: { nar: maxLineNar, dlg: maxLineDlg }, overlaps: overlapsLeft, dead_ratio: deadRatio, dead_s: deadS, hold_s: holdS, max_no_sub_s: maxNoSub, cues_per_clip: cuesPerClip, nar_over_dialogue_s: narOverDlg, added_time_s: r3(totalT - segs.reduce((a, s) => a + (s.out - s.in), 0)), trimmed_silence_s: trimmedS, trim_cuts: trimCuts, silence_measured: silences.length > 0, source_ratio: r3(totalT / ps.duration_s) };
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
        diagnostics: { dead_spans_top: deadDiag, dead_by_role: deadByRole, metrics, dlg_dropped: dlgDropped, dlg_trimmed: dlgTrimmed },
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
        "③ carry 의 값을 payload 에 그대로 실어 next_step 을 부른다. export 는 payload.timeline(방금 쓴 timeline.json 내용) · voice(voice.json) · script(script.json) · brief(brief.json) · transcript_metrics(transcript.json 의 metrics 요약: utterance_count) 를 더 받는다 — 최종 재검사에 쓴다.",
      ],
      then_call_with: ["step: 'export'", "payload: { …carry, timeline: <timeline.json>, voice: <voice.json>, script: <script.json>, brief: <brief.json>, transcript_metrics: { utterance_count } }"],
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
