/**
 * lib/단어정렬.ts — 자막 줄 ↔ **실측 단어**를 순서대로 맞춘다.
 *
 * 왜: 나레 자막 타이밍을 글자 수 비례 추정에서 **단어 단위 실측**으로 올렸다(HARNESS 강제 규칙,
 * 설계/진단일지.md 22절). 우리는 정답 텍스트와 그 순서를 알고 있으므로, 전사된 단어를 줄에
 * **단조(monotonic)** 로 나눠 주면 된다 — 어느 줄이 어느 단어에서 시작·끝나는지가 곧 큐 시각이다.
 *
 * ASR 이 우리 TTS 를 조금 다르게 적어도(「정규직이」→「정규직에」) 글자 유사도로 흡수한다.
 * 유사도가 낮으면 부르는 쪽이 폴백(chars_t)으로 내려간다.
 */

/** 숫자를 한글 수사로 — ASR 은 「삼십 퍼센트」를 「30%」, 「이천 달러」를 「2000달러」로 적는다(실측) */
const 자 = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"];
const 단 = ["", "십", "백", "천"];
function 네자리(n: number): string {
  let out = "";
  for (let i = 3; i >= 0; i--) {
    const d = Math.floor(n / Math.pow(10, i)) % 10;
    if (!d) continue;
    out += (d === 1 && i > 0 ? "" : 자[d]) + 단[i];
  }
  return out;
}
export function 한글수(n: number): string {
  if (!Number.isFinite(n) || n < 0) return String(n);
  if (n === 0) return "영";
  const 큰 = ["", "만", "억", "조"];
  let out = "", g = 0, m = Math.floor(n);
  while (m > 0 && g < 4) { const q = m % 10000; if (q) out = 네자리(q) + 큰[g] + out; m = Math.floor(m / 10000); g++; }
  return out;
}

/** 공백·문장부호를 지우고 숫자·기호를 한글로 옮긴 알맹이 — 비교는 이 형태로만 한다 */
export const 정규화 = (s: string) =>
  s.replace(/(\d+)\s*%/g, (_m, d) => `${한글수(Number(d))}퍼센트`)
    .replace(/\$\s*(\d+)/g, (_m, d) => `${한글수(Number(d))}달러`)
    .replace(/\d+/g, (m) => 한글수(Number(m)))
    .replace(/[\s.,!?…·「」'"\-~%$]/g, "");

/** 두 문자열의 최장 공통 부분수열 비율 (0~1) */
export function 유사도(a: string, b: string): number {
  const x = 정규화(a), y = 정규화(b);
  if (!x || !y) return 0;
  const dp = new Array(y.length + 1).fill(0);
  for (let i = 1; i <= x.length; i++) {
    let prev = 0;
    for (let j = 1; j <= y.length; j++) {
      const tmp = dp[j];
      dp[j] = x[i - 1] === y[j - 1] ? prev + 1 : Math.max(dp[j], dp[j - 1]);
      prev = tmp;
    }
  }
  return Math.round((2 * dp[y.length] / (x.length + y.length)) * 1000) / 1000;
}

export interface 실측단어 { w: string; s: number; e: number }
export interface 정렬결과 { ranges: ([number, number] | null)[]; sim: number; 줄유사도: number[] }

/**
 * 줄들에 단어를 순서대로 나눠 준다. 돌려주는 `ranges[i]` = 그 줄이 차지하는 단어 구간 `[처음, 끝]`(포함),
 * 단어를 못 받은 줄은 `null`. `sim` = 줄별 유사도의 (글자 수) 가중 평균.
 *
 * 방법: 줄 경계를 어디에 둘지 DP 로 고른다 — 각 줄의 「받은 단어들을 이어 붙인 것」과
 * 「그 줄 본문」의 글자 유사도 합이 가장 큰 조합. 줄 수·단어 수가 작아(≤6·≤40) 그대로 계산한다.
 */
export function 줄에단어배정(lines: string[], words: 실측단어[]): 정렬결과 {
  const L = lines.length, W = words.length;
  if (!L) return { ranges: [], sim: 0, 줄유사도: [] };
  if (!W) return { ranges: lines.map(() => null), sim: 0, 줄유사도: lines.map(() => 0) };
  const norm = lines.map(정규화);
  const joined: string[][] = [];                        // joined[a][b] = 단어 a..b 를 이어 붙인 것
  for (let a = 0; a < W; a++) {
    joined[a] = [];
    let acc = "";
    for (let b = a; b < W; b++) { acc += 정규화(words[b].w); joined[a][b] = acc; }
  }
  const score = (i: number, a: number, b: number) => 유사도(norm[i], joined[a][b]) * Math.max(1, norm[i].length);
  // dp[i][j] = 줄 i 까지 채우고 단어 j 개를 썼을 때의 최고 점수
  const NEG = -1e9;
  const dp: number[][] = Array.from({ length: L + 1 }, () => new Array(W + 1).fill(NEG));
  const back: number[][] = Array.from({ length: L + 1 }, () => new Array(W + 1).fill(-1));
  dp[0][0] = 0;
  for (let i = 0; i < L; i++) {
    for (let j = 0; j <= W; j++) {
      if (dp[i][j] === NEG) continue;
      const 남은줄 = L - i - 1;
      for (let k = j + 1; k <= W - 남은줄; k++) {        // 줄 i 가 단어 j..k-1 을 가진다 (최소 1개)
        const v = dp[i][j] + score(i, j, k - 1);
        if (v > dp[i + 1][k]) { dp[i + 1][k] = v; back[i + 1][k] = j; }
      }
    }
  }
  if (dp[L][W] === NEG) return { ranges: lines.map(() => null), sim: 0, 줄유사도: lines.map(() => 0) };
  const ranges: ([number, number] | null)[] = new Array(L).fill(null);
  let j = W;
  for (let i = L; i > 0; i--) { const pj = back[i][j]; ranges[i - 1] = [pj, j - 1]; j = pj; }
  const 줄유사도 = ranges.map((r, i) => (r ? 유사도(lines[i], joined[r[0]][r[1]]) : 0));
  const 무게 = norm.map((x) => Math.max(1, x.length));
  const sim = Math.round((줄유사도.reduce((acc, v, i) => acc + v * 무게[i], 0) / 무게.reduce((a, b) => a + b, 0)) * 1000) / 1000;
  return { ranges, sim, 줄유사도 };
}

/** 큐 창 안에서 실제로 발음된 단어들 (중심이 창 안에 든 것) */
export function 창안의단어(words: 실측단어[], t0: number, t1: number): 실측단어[] {
  return words.filter((w) => { const mid = (w.s + w.e) / 2; return mid >= t0 - 0.001 && mid <= t1 + 0.001; });
}
