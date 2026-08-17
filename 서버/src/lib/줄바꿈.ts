/**
 * lib/줄바꿈.ts — 한국어 자막 줄 나누기: **검사기**(게이트 G-줄바꿈)와 **폴백 분할기**(A안 점수화).
 *
 * 규칙 원문은 `설계/한국어_줄바꿈규칙.md`. 이 파일은 그 규칙을 기계가 읽는 형태로만 옮긴다 —
 * 규칙을 바꿀 일이 생기면 문서를 먼저 고친다.
 *
 * 본선은 **집필자(script 단계)가 의미 단위로 나눈 `lines[]`** 다(B안). 여기 있는 분할기는
 * script 가 줄을 주지 않았거나 준 줄이 자수 상한을 넘을 때만 쓰는 **폴백**이다.
 *
 * 판정 한계(정직하게): 형태소 분석기가 없다. 확정으로 잡는 것은 ⓑ(조사·의존명사로 시작)·
 * ⓒ(짧은 조각)·ⓔ(어절 중간)뿐이고, ⓐ(명사구 절단)·ⓓ(수식어 분리)는 어절 모양으로 **의심**만 한다.
 */

/** 조사 — 앞말에 붙는 말(한글 맞춤법 제41항). 줄 첫머리에 오면 안 된다 */
const 조사 = ["은", "는", "이", "가", "을", "를", "에", "에서", "에게", "으로", "로", "와", "과", "도", "만", "까지",
  "부터", "처럼", "보다", "의", "라도", "조차", "마저", "이나", "나", "밖에", "대로", "께서", "한테", "라고", "이라고", "이란", "이라는", "든", "이든"];
/** 의존명사·위치명사 — 띄어 쓰지만(제42항) 앞말 없이는 뜻이 서지 않는다 */
const 의존명사 = ["것", "게", "거", "수", "줄", "바", "데", "뿐", "채", "척", "만큼", "따름", "터", "때", "안", "속", "앞",
  "뒤", "위", "아래", "옆", "사이", "동안", "중", "밖", "무렵", "까닭", "등", "편", "쪽", "님", "덕분", "탓", "대신", "번", "만"];
/** 관형사 — 뒤에 오는 말을 꾸민다. 이 뒤에서 끊으면 꾸밈 대상이 사라진다 */
const 관형사 = ["새", "그", "이", "저", "첫", "온", "전", "각", "여러", "모든", "어떤", "무슨", "웬", "딴", "별", "온갖",
  "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열", "몇", "수많은", "지난"];
/** 종결어미(지무비체 — 스타일/영화롱폼/나레이션.md 와 같은 목록) */
const 종결 = ["습니다", "니다", "죠", "요", "다", "까", "래", "군요", "네요", "거든요"];
/** 연결어미 — 절 경계 */
const 연결 = ["고", "지만", "는데", "은데", "어서", "아서", "니까", "면서", "며", "다가", "거나", "든지", "도록", "려고", "자", "면", "듯", "채로"];
/** 「~러」(목적) 는 앞 글자를 봐야 한다 — 「자랑하러」·「타러」는 어미, 「달러」는 명사 */
const 목적러 = /(하|으|이|아|어|가|오|타|보|놀|사|주)러$/;
/** 「것은→건」·「것을→걸」 처럼 줄어든 꼴 — 이것으로 끝나면 조사로 끝난 것과 같다 */
const 축약 = ["건", "걸", "게", "뭘", "널"];
/** 부사어·접속어 — 이 뒤도 괜찮은 자리 */
const 접속 = ["그렇게", "허나", "무려", "이제", "결국", "마침내", "한편", "이어서", "그리고", "게다가", "심지어", "다시", "곧"];

const 꼬리 = (w: string) => w.replace(/[.!?…]+$/g, "");
const 끝남 = (w: string, list: string[]) => { const c = 꼬리(w); return list.some((x) => c.length > x.length && c.endsWith(x)); };
const 한글로끝 = (w: string) => /[가-힣]$/.test(꼬리(w));

/** 이 어절이 조사·의존명사로 시작하는가 — 붙은 조사까지 감싸 본다 (ⓑ) */
export function 앞말에기댐(word: string): string | null {
  const c = 꼬리(word);
  if (!c) return null;
  for (const j of [...조사].sort((a, b) => b.length - a.length)) if (c === j) return `조사 「${j}」 단독`;
  const jos = [...조사].sort((a, b) => b.length - a.length).map((j) => j.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  for (const b of [...의존명사].sort((a, b) => b.length - a.length)) {
    if (c === b || new RegExp(`^${b}(${jos})$`).test(c)) return `의존·위치명사 「${b}」(으)로 시작`;
  }
  return null;
}

/** 조사·어미 없이 끝난 어절 = 명사구가 아직 안 끝났을 가능성 (ⓐ 의심) */
export function 맨명사끝(word: string): boolean {
  if (!한글로끝(word)) return false;
  if (축약.includes(꼬리(word))) return false;
  if (목적러.test(꼬리(word))) return false;
  return !(끝남(word, 종결) || 끝남(word, 연결) || 끝남(word, 조사));
}

/** 관형사·관형격 「의」로 끝났는가 (ⓓ) */
export function 꾸미다끝(word: string): boolean {
  const c = 꼬리(word);
  return 관형사.includes(c) || (c.length > 1 && c.endsWith("의"));
}

export interface 줄바꿈위반 { 패턴: "ⓐ" | "ⓑ" | "ⓒ" | "ⓓ" | "ⓔ"; 앞줄: string | null; 줄: string; 이유: string; ref?: string; t0?: number }

/**
 * 줄 목록을 검사한다. `lines` 는 **한 블록(한 문장)** 이 쪼개진 줄들 — 인접 쌍을 본다.
 * 확정(ⓑⓒⓔ)과 의심(ⓐⓓ)을 함께 돌려주고, 부르는 쪽이 hard/soft 로 가른다.
 */
export function 줄검사(lines: string[], opts: { 조각_최소자수?: number; ref?: string; t0s?: number[] } = {}): 줄바꿈위반[] {
  const 최소 = opts.조각_최소자수 ?? 4;         // 3자 이하 = 조각 (규격 「자막.줄_조각_최소자수」)
  const out: 줄바꿈위반[] = [];
  const 어절 = (s: string) => s.trim().split(/\s+/).filter(Boolean);
  lines.forEach((ln, i) => {
    const 앞 = i > 0 ? lines[i - 1] : null;
    const t0 = opts.t0s?.[i];
    const add = (패턴: 줄바꿈위반["패턴"], 이유: string) => out.push({ 패턴, 앞줄: 앞, 줄: ln, 이유, ref: opts.ref, t0 });
    const 알맹이 = ln.replace(/[.!?…\s]/g, "");
    if (lines.length > 1 && 알맹이.length > 0 && 알맹이.length < 최소) add("ⓒ", `조각 ${알맹이.length}자 (최소 ${최소}자)`);
    const ws = 어절(ln);
    if (i > 0 && ws.length) {
      const r = 앞말에기댐(ws[0]);
      if (r) add("ⓑ", r);
      const pws = 어절(앞 ?? "");
      const p = pws[pws.length - 1] ?? "";
      if (꾸미다끝(p)) add("ⓓ", `꾸미는 말 「${꼬리(p)}」 뒤에서 끊김 → 꾸밈 대상이 다음 줄로`);
      // 앞 줄이 `..` 로 끝나면 **저자가 찍은 쉼 자리**다 — 그 자리의 적합성은 대본 규칙(나레이션.md 「끊는 자리는 셋뿐」)이 본다.
      //   여기서 또 세면 같은 것을 두 번 세는 셈이라 ⓐ 의심에서 뺀다.
      else if (맨명사끝(p) && !/\.\.!?$/.test(앞?.trim() ?? "")) add("ⓐ", `조사·어미 없는 「${꼬리(p)}」 뒤에서 끊김 → 다음 줄 「${ws[0]}」`);
    }
    if (/[가-힣]-$/.test(ln.trim())) add("ⓔ", "어절 중간에서 끊김");
  });
  return out;
}

export const 확정패턴 = ["ⓑ", "ⓒ", "ⓔ"] as const;
export const 의심패턴 = ["ⓐ", "ⓓ"] as const;
export const 확정 = (v: 줄바꿈위반[]) => v.filter((x) => (확정패턴 as readonly string[]).includes(x.패턴));
export const 의심 = (v: 줄바꿈위반[]) => v.filter((x) => (의심패턴 as readonly string[]).includes(x.패턴));

/** 분할점 벌점 — 낮을수록 좋은 자리 (설계/한국어_줄바꿈규칙.md §2 우선순위) */
function 벌점(words: string[], i: number, 조각_최소자수: number): number {
  const 앞 = words[i], 뒤 = words[i + 1] ?? "";
  let p: number;
  if (끝남(앞, 종결) || /\.\.!?$/.test(앞)) p = 0;              // 1순위 문장 종결 · `..` 조각 경계
  else if (끝남(앞, 연결) || 목적러.test(꼬리(앞))) p = 2;         // 3순위 절 경계
  else if (접속.includes(꼬리(앞))) p = 3;                        // 4순위 부사어·접속어
  else if (끝남(앞, 조사) && !꼬리(앞).endsWith("의")) p = 4;     // 5순위 체언+조사 (관형격 「의」 제외)
  else p = 12;                                                    // 6순위 그 외 어절 경계
  if (앞말에기댐(뒤)) p += 40;                                    // ⓑ 확정 위반
  if (꾸미다끝(앞)) p += 40;                                      // ⓓ 확정에 가까운 위반(관형사·「의」)
  else if (맨명사끝(앞)) p += 18;                                 // ⓐ 의심
  const 뒷조각 = 뒤.replace(/[.!?…]/g, "");
  if (뒷조각.length > 0 && 뒷조각.length < 조각_최소자수 && i + 2 >= words.length) p += 15;   // ⓒ 마지막 줄이 조각
  return p;
}

/**
 * 한 줄을 **어쩔 수 없이 한 번 더 쪼개야 할 때**(발성 덩어리 경계) 쓸 자리를 고른다.
 * `근처` 글자 위치 주변 `창` 안의 어절 경계 중 벌점이 가장 낮은 곳을 돌려주고,
 * **쓸 만한 자리가 없으면 null** — 그때는 쪼개지 말고 한 덩어리에 통째로 앉힌다.
 */
export function 좋은자리(txt: string, 근처: number, 창 = 6, 조각_최소자수 = 4): number | null {
  const 공백: number[] = [];
  for (let i = 0; i < txt.length; i++) if (txt[i] === " ") 공백.push(i);
  if (!공백.length) return null;
  let best: { i: number; p: number } | null = null;
  for (const i of 공백) {
    if (Math.abs(i - 근처) > 창) continue;
    const 앞 = txt.slice(0, i).trim(), 뒤 = txt.slice(i + 1).trim();
    if (!앞 || !뒤) continue;
    const 앞알맹이 = 앞.replace(/[.!?…\s]/g, ""), 뒤알맹이 = 뒤.replace(/[.!?…\s]/g, "");
    if (앞알맹이.length < 조각_최소자수 || 뒤알맹이.length < 조각_최소자수) continue;   // ⓒ
    const 뒤첫 = 뒤.split(/\s+/)[0], 앞끝 = 앞.split(/\s+/).slice(-1)[0];
    if (앞말에기댐(뒤첫)) continue;                                                     // ⓑ 확정 위반은 후보에서 제외
    if (꾸미다끝(앞끝) || 맨명사끝(앞끝)) continue;      // ⓓ·ⓐ 의심 자리는 아예 쓰지 않는다
    let p = Math.abs(i - 근처);                          // 원래 자리에서 멀어지는 값
    if (끝남(앞끝, 종결) || /\.\.!?$/.test(앞끝)) p -= 8;
    else if (끝남(앞끝, 연결) || 목적러.test(꼬리(앞끝))) p -= 5;
    else if (끝남(앞끝, 조사) && !꼬리(앞끝).endsWith("의")) p -= 3;
    if (!best || p < best.p) best = { i, p };
  }
  // 깨끗한 자리가 하나도 없으면 **쪼개지 않는다** — 규칙을 어기며 쪼개는 것보다 한 덩어리에 통째로 두는 게 낫다
  return best ? best.i : null;
}

/**
 * 폴백 분할 — 어절 경계 중 **벌점 합이 가장 낮은** 조합을 고른다(줄 하나가 상한을 넘지 않게).
 * 그리디로 앞 줄을 꽉 채우던 옛 방식과 달리, 좋은 자리를 위해 앞 줄을 짧게 남길 수 있다.
 */
export function 규칙분할(text: string, maxLen: number, 조각_최소자수 = 4): string[] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  if (text.trim().length <= maxLen) return [text.trim()];
  const n = words.length;
  const len: number[][] = Array.from({ length: n }, () => new Array(n).fill(0));
  for (let a = 0; a < n; a++) { let s = 0; for (let b = a; b < n; b++) { s += words[b].length + (b > a ? 1 : 0); len[a][b] = s; } }
  const INF = 1e9;
  const best = new Array(n + 1).fill(INF), from = new Array(n + 1).fill(-1);
  best[0] = 0;
  for (let a = 0; a < n; a++) {
    if (best[a] === INF) continue;
    for (let b = a; b < n; b++) {
      if (len[a][b] > maxLen) break;                       // 이 줄이 상한을 넘으면 더 못 붙인다
      const 줄끝 = b === n - 1;
      const 조각 = words.slice(a, b + 1).join(" ").replace(/[.!?…]/g, "");
      let c = 3;                                           // 줄 하나 늘어나는 값 — 쓸데없이 잘게 쪼개지 않게
      if (조각.length < 조각_최소자수 && !(a === 0 && 줄끝)) c += 15;      // ⓒ 조각 금지
      if (!줄끝) c += 벌점(words, b, 조각_최소자수);
      if (best[a] + c < best[b + 1]) { best[b + 1] = best[a] + c; from[b + 1] = a; }
    }
  }
  if (best[n] >= INF) {                                    // 한 어절이 상한보다 길다 — 어절은 쪼개지 않는다(ⓔ)
    const out: string[] = []; let cur = "";
    for (const w of words) { if (!cur) cur = w; else if ((cur + " " + w).length <= maxLen) cur += " " + w; else { out.push(cur); cur = w; } }
    if (cur) out.push(cur);
    return out;
  }
  const cuts: number[] = []; let k = n;
  while (k > 0) { cuts.push(k); k = from[k]; }
  cuts.push(0); cuts.reverse();
  const out: string[] = [];
  for (let i = 0; i + 1 < cuts.length; i++) out.push(words.slice(cuts[i], cuts[i + 1]).join(" "));
  return out;
}
