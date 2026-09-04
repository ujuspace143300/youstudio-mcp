/**
 * steps/린박스/srt.ts — 공식 SRT 를 **내용으로 고른다** (볼케이노 키트 도구/srt고르기.py 의 로직을 서버로 옮김 · 규격 §94 · 2026-09-04).
 *
 * 왜 서버가 고르나
 *   키트의 srt고르기.py 는 편 폴더 srt대사.txt(SRT 에서 베낀 대사)와 후보를 글자 그대로 대조한다.
 *   유스튜디오는 lb_transcript 시점에 그 파일이 없고 **전사 낱말(대사.json)** 만 있다. 그래서
 *   러너가 후보 SRT 를 통째로 올리고(srt후보읽기.py), 여기서 전사와 대조한다.
 *   경로로 짐작하지 않는다 — 옆 드라마·다른 회차를 물면 보고서가 그럴듯하게 거짓이 된다(약한영웅 6편이 포핸즈 SRT 와 대조됐다).
 *
 * 규칙 (srt고르기.py 그대로)
 *   · 밀기 = (전사 낱말 시각 − SRT 시각) 의 무리(1초 칸 최빈) 안 원래 값의 중앙값. 표 5개 미만이면 못 잰 것.
 *     ★밀기는 반드시 전사(클립 자체 소리)와 견준다 — SRT 에서 베낀 것과 견주면 언제나 0 이다(순환).
 *   · 글자는 SRT, 시각은 전사. 맞은 비율 < 최소비율(0.5) 이면 고르지 않는다. 1등이 2등의 1.5배 미만이면 고르지 않는다.
 *   · 못 고르면 **아무것도 적지 않는다** — 틀린 SRT 를 무는 것이 가장 나쁘다.
 *
 * 유스튜디오 쪽 차이(서버엔 srt대사.txt 가 없어서)
 *   · «맞음» 은 글자 그대로가 아니라 **글자 두 자 겹침(bigram) 담김 비율 ≥ 0.5** 로 센다 — 전사가 낱말을 흔히 틀리기 때문.
 *   · 구간 시각: SRT 는 방송본 시각, 전사는 절단본(0~span) 시각. 편 폴더 도구(SRT블록·대사빠짐검사)는 EPnn 폴더라
 *     구간시작을 0 으로 보므로, srt원본 의 밀기 = (전사 − SRT) 그대로 적으면 `SRT초 + 밀기` 가 곧 절단본 초가 된다.
 */

export type SrtLine = [number, number, string];
export interface SrtCandidate { path: string; lines: SrtLine[]; total?: number }
export interface AsrWord { s: number; e: number; t: string }
export interface SrtScore {
  path: string;
  /** 절단본 안(−1~span+1)에 드는 SRT 줄 수 */
  in_window: number;
  /** 그중 전사와 글자가 맞은 줄 수 */
  matched: number;
  ratio: number;
  /** 전사 − SRT (초). SRT초 + shift = 절단본 초. 못 재면 null */
  shift: number | null;
  /** 밀기를 잰 표 수 */
  samples: number;
}
export interface SrtPick { chosen: SrtScore | null; table: SrtScore[]; reason: string }

const strip = (s: string) => s.replace(/[^0-9A-Za-z가-힣]/g, "");
function bigrams(s: string): Set<string> {
  const out = new Set<string>();
  for (let i = 0; i + 1 < s.length; i++) out.add(s.slice(i, i + 2));
  return out;
}
function median(v: number[]): number {
  const a = [...v].sort((x, y) => x - y);
  const n = a.length;
  return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2;
}

/** 밀기재기 — SRT 줄 첫 두 토막 ↔ 전사 낱말을 앞 두 글자로 맞춰 (전사 − SRT) 의 무리 중앙값 */
export function measureShift(lines: SrtLine[], words: AsrWord[], startHint: number, span: number): { shift: number | null; samples: number } {
  if (!words.length) return { shift: null, samples: 0 };
  const diffs: number[] = [];
  for (const [s, , text] of lines) {
    const s2 = s - startHint;
    if (s2 < -120 || s2 > span + 120) continue;
    for (const tok of text.split(/\s+/).slice(0, 2)) {
      const k = strip(tok);
      if (k.length < 2) continue;
      for (const w of words) {
        if (strip(w.t).slice(0, 2) === k.slice(0, 2)) {
          const d = w.s - s2;
          if (d > -120 && d < 120) diffs.push(d);
        }
      }
    }
  }
  if (diffs.length < 5) return { shift: null, samples: diffs.length };
  const bins = new Map<number, number>();
  for (const d of diffs) bins.set(Math.round(d), (bins.get(Math.round(d)) ?? 0) + 1);
  let best = 0, bestN = -1;
  for (const [k, n] of bins) if (n > bestN) { best = k; bestN = n; }
  const near = diffs.filter((d) => Math.abs(d - best) <= 0.75);
  // 절단본 기준 밀기 = (전사 − (SRT − startHint)) − startHint ... 위 d 는 이미 s2 기준이므로 SRT초 + (d − startHint) = 절단본 초
  return { shift: Math.round((median(near) - startHint) * 100) / 100, samples: near.length };
}

export function scoreCandidate(c: SrtCandidate, words: AsrWord[], startHint: number, span: number): SrtScore {
  const { shift, samples } = measureShift(c.lines, words, startHint, span);
  if (shift === null) return { path: c.path, in_window: 0, matched: 0, ratio: 0, shift: null, samples };
  let inWindow = 0, matched = 0;
  for (const [s, e, text] of c.lines) {
    const a = s + shift, b = e + shift;
    if (a < -1 || a > span + 1) continue;
    inWindow++;
    const need = strip(text);
    if (need.length < 2) continue;
    const win = words.filter((w) => w.e >= a - 2 && w.s <= b + 2).map((w) => strip(w.t)).join("");
    const bg = bigrams(need);
    let hit = 0;
    const have = bigrams(win);
    for (const g of bg) if (have.has(g)) hit++;
    if (hit / bg.size >= 0.5) matched++;
  }
  return { path: c.path, in_window: inWindow, matched, ratio: inWindow ? Math.round((matched / inWindow) * 1000) / 1000 : 0, shift, samples };
}

/**
 * 후보 중 하나를 고른다. startHint = 구간 시작(소재 초 · SRT 시각과 비슷한 자리를 찾는 힌트일 뿐, 밀기는 전사로 잰다).
 * 못 고르면 chosen=null 과 이유 — 그때는 srt원본 을 쓰지 않는다.
 */
export function pickSrt(candidates: SrtCandidate[], words: AsrWord[], startHint: number, span: number, opts: { minRatio?: number; lead?: number } = {}): SrtPick {
  const minRatio = opts.minRatio ?? 0.5;
  const lead = opts.lead ?? 1.5;
  if (!candidates.length) return { chosen: null, table: [], reason: "후보 SRT 가 하나도 없다 — 드라마 폴더에 공식 SRT 를 두면 lb_transcript 가 내용으로 고른다. 없으면 전사 글자로 간다(완성검사 13 은 건너뜀)." };
  if (!words.length) return { chosen: null, table: [], reason: "전사 낱말이 없어 밀기를 못 잰다 — 못박지 않는다." };
  const table = candidates.map((c) => scoreCandidate(c, words, startHint, span)).sort((x, y) => y.matched - x.matched || y.ratio - x.ratio);
  const top = table[0];
  const second = table[1]?.matched ?? 0;
  if (top.shift === null) return { chosen: null, table, reason: `밀기를 못 쟀다(전사 표 ${top.samples}개 < 5) — 전사가 너무 짧거나 이 드라마 SRT 가 아니다. 못박지 않는다.` };
  if (top.in_window < 3) return { chosen: null, table, reason: `절단본 안에 드는 SRT 줄이 ${top.in_window}개뿐이다 — 회차가 다르거나 밀기가 틀렸다. 못박지 않는다.` };
  if (top.ratio < minRatio) return { chosen: null, table, reason: `가장 많이 맞은 것도 ${Math.round(top.ratio * 100)}% 뿐이다(${top.matched}/${top.in_window}) — 고르지 않는다(사람이 payload.srt_path 로 준다).` };
  if (second && top.matched < second * lead) return { chosen: null, table, reason: `1등(${top.matched})과 2등(${second})이 비슷하다 — 고르지 않는다(사람이 payload.srt_path 로 정한다).` };
  return { chosen: top, table, reason: `맞음 ${top.matched}/${top.in_window}(${Math.round(top.ratio * 100)}%) · 밀기 ${top.shift >= 0 ? "+" : ""}${top.shift}초(전사 표 ${top.samples}개)` };
}
