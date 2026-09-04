/**
 * steps/린박스/ass.ts — 볼케이노 서버가 내던 것을 그대로 만드는 순수 함수 셋 (설계 5.6.1 · 신병4 EP19 실물로 규칙 확정 2026-09-04).
 *
 *   planBlocks(authored, wav_secs)          → 블록 계획 [{index, kind, ss, frames, seconds}]   (= _block_jobs.json 의 뼈대)
 *   blockArgv(plan, epDir, fpsFraction)     → 블록 하나의 ffmpeg argv (볼케이노 stitch_blocks argv, 맥 사슬 훅이 고친 뒤 꼴)
 *   buildServerAss(입력)                     → captions_서버원본.ass 전문
 *
 * 되짚은 규칙 (EP19 35블록 전수 · EP10~20 교차):
 *   · D 블록: -ss = ceil(s×30)/30 · frames = round((e−s)×30)  ★Python round(은행가) 와 부동소수 그대로 — 31/31 일치
 *   · N 블록: -ss = ceil(화면초×30)/30 · frames = round(샘플수/1600)+2 (= wav×30, 샘플 격자) · seconds = frames/30(소수 4자리) · -t = (frames+8)/30 · apad whole_len = round(seconds×48000)
 *   · 자막 시각은 계획값이 아니라 **구운 뒤 실측 길이(clip_secs, 29.97fps)** 누적. D 카드 = [누적 시작, 누적 끝] 을 1/100초로 반올림
 *     (실물은 31개 중 5개의 끝이 0.01 짧다 — 서버 내부 반올림, 미확인). N 카드 = 낱말 시각. 헤드라인·크레딧 끝 = 총 실측.
 *   · 효과자막: 시작 = 블록 시작 + 늦출초, 끝 = min(시작+길이, 블록 끝 − 0.05) · pos 소수 2자리
 *   · N 카드 나누기: 어절 단위로 붙여 12자(띄어쓰기 포함) 이내 — EP19 N 4블록 전부 재현
 *   · 페이드: 첫 카드만 fad(133,33), 나머지 fad(0,33) ★실물은 종류 전환 50곳 중 30곳에 133 — 촬영본·틈과 무관해 서버 내부 판단으로 봄(미재현)
 *   · 헤드라인 Fontsize 는 서버가 잉크 폭으로 맞춘 값(EP19 114/115) — 서식.py 가 채널 서식으로 덮으므로 기본 114/115 로 둔다
 */

export type NBlock = ["N", string, [number, number][]];
export type DSeg = [number, number, string, string, string];
export type DBlock = ["D", DSeg[]];
export type Block = NBlock | DBlock;
export type Effect = [number, number, number, string, string, number, number];
export interface Authored { HEADLINE: string[]; CREDIT: string[]; BLOCKS: Block[]; EFFECTS_BY_BLOCK?: Effect[] }

/** Python round() — 정확히 .5 면 짝수로 (은행가). 부동소수 곱은 JS 도 같은 double 이라 값이 같다 */
export function pyRound(x: number): number {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}
const r4 = (x: number) => Math.round(x * 10000) / 10000;
const r6 = (x: number) => Number(x.toFixed(6));

export interface BlockPlan {
  index: number;
  kind: "N" | "D";
  /** 소재(구간_인물.mp4) 초 — ceil(s×30)/30 */
  ss: number;
  frames: number;
  /** frames/30 (4자리) — _block_jobs.json 의 seconds */
  seconds: number;
}

export function planBlocks(a: Authored, wavSecs: Record<string, number>): BlockPlan[] {
  return a.BLOCKS.map((b, index) => {
    if (b[0] === "N") {
      const at = b[2][0][0];
      const w = wavSecs[String(index)];
      if (typeof w !== "number") throw new Error(`나레 블록 ${index} 의 wav 길이(wav_secs)가 없다`);
      // wav 길이는 샘플 격자(48kHz)로 되돌린 뒤 프레임을 센다 — 실물 n34 = 116000샘플(2.41666…) → 72.5 → 72+2 = 74.
      // 6자리로 반올림된 2.416667×30 = 72.50001 로 세면 75 가 되어 1프레임 어긋난다 (2026-09-04 EP19 대조에서 잡음)
      const samples = Math.round(w * 48000);
      const frames = pyRound(samples / 1600) + 2;
      return { index, kind: "N" as const, ss: Math.ceil(at * 30) / 30, frames, seconds: r4(frames / 30) };
    }
    const segs = b[1];
    const s = segs[0][0], e = segs[segs.length - 1][1];
    const frames = pyRound((e - s) * 30);
    return { index, kind: "D" as const, ss: Math.ceil(s * 30) / 30, frames, seconds: r4(frames / 30) };
  });
}

const nn = (i: number) => `b${String(i).padStart(2, "0")}`;
const nw = (i: number) => `n${String(i).padStart(2, "0")}`;

/** 볼케이노 stitch_blocks argv 를 맥 사슬 훅(배율상한 1.00 → crop 없음 · 화질 → unsharp 없음 · 프레임률 → 소재값)이 고친 뒤 꼴로 */
export function blockArgv(p: BlockPlan, epDir: string, fpsFraction: string): string[] {
  const j = (...x: string[]) => [epDir.replace(/[\/]+$/, ""), ...x].join("/");
  const src = j("구간_인물.mp4");
  const out = j("blocks", `${nn(p.index)}.mp4`);
  const sec = p.frames / 30;
  const sec4 = p.seconds;
  const whole = Math.round(sec4 * 48000); // 실물: 2.0333→97598 · 2.3667→113602 (반올림)
  const t = (p.frames + 8) / 30;
  const v = `[0:v]scale=1080:1020:flags=lanczos,setsar=1,fps=${fpsFraction},tpad=stop_mode=clone:stop_duration=2,trim=end_frame=${p.frames},setpts=PTS-STARTPTS[v0];`;
  const a0 = `[0:a]asetpts=PTS-STARTPTS,aresample=48000:async=1,apad,atrim=0:${sec},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.001,afade=t=out:st=${sec - 0.001}:d=0.001[a0];`;
  const cc = `[v0][a0]concat=n=1:v=1:a=1[cv][ca];`;
  const tail = p.kind === "D"
    ? `[ca]loudnorm=I=-23.0:TP=-3:LRA=11,apad=whole_len=${whole},atrim=0:${sec4},afade=t=in:st=0:d=0.002:curve=qsin,afade=t=out:st=${r4(sec4 - 0.002)}:d=0.002:curve=qsin[a]`
    : `[ca]loudnorm=I=-23.0:TP=-3:LRA=11,volume=0.1778,afade=t=in:st=0:d=0.002:curve=qsin[m0];[1:a]afade=t=in:st=0:d=0.008,apad[m1];[m0][m1]amix=inputs=2:duration=first:normalize=0,apad=whole_len=${whole},atrim=0:${sec4},afade=t=out:st=${r4(sec4 - 0.002)}:d=0.002:curve=qsin[a]`;
  const inputs = p.kind === "D" ? ["-i", src] : ["-i", src, "-i", j("blocks", `${nw(p.index)}.wav`)];
  return [
    "ffmpeg", "-y", "-ss", String(r6(p.ss)), "-t", String(t), ...inputs,
    "-filter_complex", v + a0 + cc + tail,
    "-map", "[cv]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
    "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
    "-r", fpsFraction, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-video_track_timescale", "30000",
    out, "-loglevel", "error",
  ];
}

// ── 자막 ass ────────────────────────────────────────────────────────────

/** 나레 문장을 어절 단위로 붙여 한 카드 12자(띄어쓰기 포함) 이내 — EP19 실물 4블록 재현 */
export function splitNarr(text: string, max = 12): string[] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const cards: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (cur && next.length > max) { cards.push(cur); cur = w; } else cur = next;
  }
  if (cur) cards.push(cur);
  return cards;
}

/** h:mm:ss.cc (1/100초 반올림) */
export function assTime(t: number): string {
  const cs = Math.round(t * 100 + 1e-9);
  const h = Math.floor(cs / 360000), m = Math.floor((cs % 360000) / 6000), s = Math.floor((cs % 6000) / 100), c = cs % 100;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(c).padStart(2, "0")}`;
}

export type WordT = [number, number, string]; // 시작·끝(초)·글
export interface DlgWord { s: number; e: number; t: string }

/** 카드 글자(공백 제외)를 낱말에 차례로 대응시켜 카드마다 [첫 낱말 시작, 마지막 낱말 끝] — 못 맞추면 null */
export function alignCards(cards: string[], words: WordT[]): ([number, number] | null)[] {
  const out: ([number, number] | null)[] = [];
  let wi = 0;
  const strip = (s: string) => s.replace(/\s/g, "");
  for (const c of cards) {
    const need = strip(c).length;
    if (!need) { out.push(null); continue; }
    let got = 0; const first = wi;
    while (wi < words.length && got < need) { got += strip(words[wi][2]).length; wi++; }
    if (got === 0) { out.push(null); continue; }
    out.push([words[first][0], words[wi - 1][1]]);
  }
  return out;
}

export interface AssInput {
  authored: Authored;
  /** 블록마다 구운 뒤 실측 길이(초) — 볼케이노 clip_secs */
  clipSecs: Record<string, number>;
  /** N 블록 나레 wav 길이(초) — 마지막 카드 끝 */
  wavSecs: Record<string, number>;
  /** N 블록마다 낱말 시각(블록 안 상대초) — narr_words.json */
  narrWords?: Record<string, WordT[]>;
  /** 원음 낱말(구간 기준 초) — 대사.json words. D 블록에 «|» 카드가 있을 때 카드 경계에 쓴다 */
  dlgWords?: DlgWord[];
  headlineFontsize?: [number, number];
  /** 블록 계획(소재 -ss·계획 초) — D 카드 경계를 소재 시각에서 타임라인으로 옮길 때 */
  plan?: BlockPlan[];
}

const STYLE_HEAD = `[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
`;

export function buildServerAss(inp: AssInput): string {
  const a = inp.authored;
  const [h1, h2] = inp.headlineFontsize ?? [114, 115];
  const styles = [
    `Style: headline_l1,Gmarket Sans Bold,${h1},&H0000FDF7,&H0000FDF7,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1`,
    `Style: headline_l2,Gmarket Sans Bold,${h2},&H000000FD,&H000000FD,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1`,
    "Style: band_narr,GmarketSansMedium,82,&H00268CFD,&H00268CFD,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3.5,0,8,40,40,20,1",
    "Style: band_dlg,GmarketSansMedium,85,&H00F7F7F7,&H00F7F7F7,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3.5,0,8,40,40,20,1",
    "Style: band_emph,GmarketSansMedium,83,&H0000FEFA,&H0000FEFA,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3.5,0,8,40,40,20,1",
    "Style: effect_float,GmarketSansMedium,70,&H0002FEF6,&H0002FEF6,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3.5,0,5,40,40,20,1",
    "Style: credit_cta_l1,Gmarket Sans Bold,75,&H00818281,&H00818281,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1",
    "Style: credit_cta_l2,Gmarket Sans Bold,75,&H00818281,&H00818281,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,40,40,20,1",
  ];
  // 타임라인 — 실측 누적
  const n = a.BLOCKS.length;
  const cum: number[] = [];
  let t = 0;
  for (let i = 0; i < n; i++) {
    cum.push(t);
    const c = inp.clipSecs[String(i)];
    if (typeof c !== "number") throw new Error(`블록 ${i} 의 실측 길이(clip_secs)가 없다`);
    t += c;
  }
  const total = t;
  const END = assTime(total);
  const blkEnd = (i: number) => cum[i] + inp.clipSecs[String(i)];

  const lines: string[] = [];
  lines.push(`Dialogue: 3,0:00:00.00,${END},headline_l1,,0,0,0,,{\\an8\\pos(540,214)\\fax-0.1799}${a.HEADLINE[0] ?? ""}`);
  lines.push(`Dialogue: 3,0:00:00.00,${END},headline_l2,,0,0,0,,{\\an8\\pos(540,335)\\fax-0.177}${a.HEADLINE[1] ?? ""}`);

  // 카드 — 블록 순서대로
  type Card = { st: number; en: number; style: "band_narr" | "band_dlg"; text: string };
  const cards: Card[] = [];
  a.BLOCKS.forEach((b, i) => {
    const bs = cum[i], be = blkEnd(i);
    if (b[0] === "N") {
      const parts = splitNarr(b[1]);
      const words = inp.narrWords?.[String(i)] ?? [];
      const wav = inp.wavSecs[String(i)] ?? (be - bs);
      let bounds = alignCards(parts, words);
      if (!words.length || bounds.some((x) => x === null)) {
        // 낱말 시각이 없으면 글자 수 비례 — 0.06초에서 wav 끝까지
        const chars = parts.map((p) => p.replace(/\s/g, "").length);
        const sum = chars.reduce((x, y) => x + y, 0) || 1;
        let acc = 0.06;
        bounds = chars.map((c) => { const st = acc; acc += (wav - 0.06) * (c / sum); return [st, acc] as [number, number]; });
      }
      // 마지막 카드 끝 = max(마지막 낱말 끝, wav 길이) — 실물 4블록에서 wav±0.02 · 낱말 끝과 일치
      const lastEnd = Math.max(wav, (bounds[bounds.length - 1] as [number, number])[1] ?? 0);
      parts.forEach((text, k) => {
        const st = bs + (bounds[k] as [number, number])[0];
        const en = k + 1 < parts.length ? bs + (bounds[k + 1] as [number, number])[0] : Math.min(be, bs + lastEnd);
        cards.push({ st, en, style: "band_narr", text });
      });
    } else {
      const segs = b[1];
      const s0 = segs[0][0], e1 = segs[segs.length - 1][1];
      const scale = (be - bs) / Math.max(1e-6, e1 - s0);
      const toTL = (src: number) => bs + (src - s0) * scale;
      segs.forEach((sg, k) => {
        const parts = sg[2].split("|").map((x) => x.trim()).filter(Boolean);
        const segSt = k === 0 ? bs : toTL(sg[0]);
        const segEn = k === segs.length - 1 ? be : toTL(sg[1]);
        if (parts.length <= 1) { cards.push({ st: segSt, en: segEn, style: "band_dlg", text: parts[0] ?? sg[2] }); return; }
        const words: WordT[] = (inp.dlgWords ?? []).filter((w) => w.s >= sg[0] - 0.05 && w.e <= sg[1] + 0.05).map((w) => [w.s, w.e, w.t]);
        let bounds = alignCards(parts, words);
        if (!words.length || bounds.some((x) => x === null)) {
          const chars = parts.map((p) => p.replace(/\s/g, "").length);
          const sum = chars.reduce((x, y) => x + y, 0) || 1;
          let acc = sg[0];
          bounds = chars.map((c) => { const st = acc; acc += (sg[1] - sg[0]) * (c / sum); return [st, acc] as [number, number]; });
        }
        parts.forEach((text, q) => {
          const st = q === 0 ? segSt : toTL((bounds[q] as [number, number])[0]);
          const en = q + 1 < parts.length ? toTL((bounds[q + 1] as [number, number])[0]) : segEn;
          cards.push({ st, en, style: "band_dlg", text });
        });
      });
    }
  });
  cards.forEach((c, k) => {
    const fad = k === 0 ? "\\fad(133,33)" : "\\fad(0,33)";
    const pos = c.style === "band_narr" ? "\\pos(540,1209.99)" : "\\pos(540,1208.69)";
    lines.push(`Dialogue: 2,${assTime(c.st)},${assTime(c.en)},${c.style},,0,0,0,,{\\an8${pos}${fad}\\fax-0.177}${c.text}`);
  });
  lines.push(`Dialogue: 3,0:00:00.00,${END},credit_cta_l1,,0,0,0,,{\\an8\\pos(540,1512)\\fax-0.1799}${a.CREDIT[0] ?? ""}`);
  lines.push(`Dialogue: 3,0:00:00.00,${END},credit_cta_l2,,0,0,0,,{\\an8\\pos(540,1592)\\fax-0.1799}${a.CREDIT[1] ?? ""}`);
  for (const f of a.EFFECTS_BY_BLOCK ?? []) {
    const [blk, delay, len, , text, x, y] = f;
    if (blk < 0 || blk >= n) continue;
    const st = cum[blk] + delay;
    const en = Math.min(st + len, blkEnd(blk) - 0.05);
    lines.push(`Dialogue: 4,${assTime(st)},${assTime(en)},effect_float,,0,0,0,,{\\an5\\pos(${x.toFixed(2)},${y.toFixed(2)})\\fax-0.1726}${text}`);
  }
  return STYLE_HEAD + styles.join("\n") + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + lines.join("\n") + "\n";
}
