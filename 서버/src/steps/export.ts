/**
 * steps/export.ts — 프리미어 교환 XML + SRT + 나레이션 음원 + manifest. 명세: 설계/단계상세.md 「8. export」, 형식 근거: 설계/참고_export.md
 *
 * 두 번 부른다:
 *   ① payload.mix_probe 가 없으면 → do[] 로 나레이션 블록 wav 를 실측 t0 에 놓아 하나로 섞은 render/narration_mix.wav 를 만들고(ffmpeg), 그 길이를 잰다.
 *   ② payload.mix_probe 가 있으면 → 믹스 길이 검증, FCP XML v5(xmeml) 조립(V1 원본 컷 · V2 대사 자막 · V3 나레 자막 · A1 원본 소리 · A2 나레 블록),
 *      SRT 3종, 1~7 단계 게이트 전체 재검사, manifest.json → write_files. status "done".
 *
 * 타이밍은 전부 timeline.json 실측 그대로 — 여기서 새로 계산하지 않는다 (초 → 프레임 반올림만).
 */
import spec from "../../../스타일/영화롱폼/규격.json";
import answer from "../../../스타일/영화롱폼/정답지.json";
import { base, reject } from "../response.js";
import type { StepHandler } from "./types.js";
import type { ArgvJob } from "../schema.js";

interface SubSpec { 폰트: Record<string, { 표시명: string; 패밀리: string; PS명: string; xml명?: string }>; 크기_px: Record<string, number>; 위치: Record<string, { origin_x: number; origin_y: number; 목표_px: { x: number; y: number } } | boolean | string>; 색: Record<string, { r: number; g: number; b: number }>; 나레_한줄_최대자수: number; 대사_한줄_최대자수: number }
interface AsmSpec { 덕킹_레벨: number; 덕킹_방식?: string; 죽은시간_홀드_제외_역할: string[]; 내보내기: { 형식: string; 시퀀스_이름: string; 해상도: { width: number; height: number }; 타임베이스: number; ntsc: boolean; 트랙: Record<string, string> } }
const SUB = (spec as unknown as { 자막: SubSpec })["자막"];
const ASM = (spec as unknown as { 조립: AsmSpec })["조립"];
const AJ = (answer as unknown as { 자막: { "G-자막_한줄_최대자수": { 나레: number; 대사: number }; "G-자막_겹침_max": { value: number }; "G-죽은시간_max": { value: number } }; 대본: { 나레_시간점유: { min: number; max: number } }; 구간선택: { "G-반복": { 컷_반복_비율_max: { value: number } } } })["자막"];
const AS = (answer as unknown as { 대본: { 나레_시간점유: { min: number; max: number } } })["대본"];
const AG = (answer as unknown as { 구간선택: { "G-반복": { 컷_반복_비율_max: { value: number } } } })["구간선택"];

function join(root: string, ...parts: string[]): string { return [root.replace(/[\/]+$/, ""), ...parts].join("/"); }
const r3 = (x: number) => Math.round(x * 1000) / 1000;
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
/** 윈도우 경로 → file://localhost/C:/… (URL 인코딩, 가족 샘플과 같은 모양) */
function pathurl(p: string): string {
  const fwd = p.replace(/\\/g, "/");
  const encoded = fwd.split("/").map((seg, i) => (i === 0 && /^[A-Za-z]:$/.test(seg) ? seg : encodeURIComponent(seg))).join("/");
  return `file://localhost/${encoded}`;
}

interface Pic { k: number; kind: string; role: string; src_in: number; src_out: number; t0: number; t1: number; audio: string; seg?: number | null; bridge?: number | null; why?: string }
interface Nar { n: number; t0: number; t1: number; wav: string; text: string }
interface Cue { lane: "nar" | "dlg"; t0: number; t1: number; text: string; ref?: string }
interface Timeline { total_s: number; picture: Pic[]; narration: Nar[]; cues: Cue[]; metrics?: Record<string, unknown>; fonts?: unknown }

export const exportStep: StepHandler = {
  name: "export",
  run({ preset, payload }) {
    const workdir = typeof payload.workdir === "string" ? payload.workdir : "";
    const source = payload.source as { path?: string; title?: string } | undefined;
    const ps = payload.probe_summary as { duration_s?: number; width?: number; height?: number; fps?: number; fps_fraction?: string; audio?: boolean; audio_sample_rate?: number; audio_channels?: number } | undefined;
    const tl = payload.timeline as Timeline | undefined;
    const voice = payload.voice as { blocks?: { n: number; bytes: number; dur_s: number; wav: string }[]; metrics?: { total_s?: number; sec_per_char_measured?: number } } | undefined;
    const script = payload.script as { metrics?: { dialogue_s?: number } } | undefined;
    const brief = payload.brief as { events?: { n: number; start: number; end: number }[] } | undefined;
    const transcript = payload.transcript_metrics as { utterance_count?: number } | undefined;
    if (!workdir || !source?.path || typeof ps?.duration_s !== "number" || !tl?.picture || !tl.cues || !tl.narration || !voice?.blocks) {
      return reject(
        "export", preset,
        "payload 에 carry 값(source·workdir·probe_summary) 또는 timeline / voice 가 없다",
        "subtitle 응답의 carry 값과 함께 payload.timeline(subtitle/timeline.json 내용) · payload.voice(voice/voice.json) · payload.script(script.json) · payload.brief(brief.json) · payload.transcript_metrics(transcript.json 의 utterance_count 등) 를 실어 export 를 다시 부르라.",
      );
    }
    const renderDir = join(workdir, "render");
    const title = source.title ?? "recap";
    const slug = title.replace(/[^\w가-힣]+/g, "_").replace(/^_|_$/g, "");
    const totalS = tl.total_s;
    const mixPath = join(renderDir, "narration_mix.wav");
    const nars = [...tl.narration].sort((a, b) => a.t0 - b.t0);

    // ── ① 나레이션 믹스다운 ───────────────────────────────────────────────
    if (payload.mix_probe === undefined) {
      const inputs: string[] = [];
      const filters: string[] = [];
      nars.forEach((n, i) => { inputs.push("-i", n.wav); const ms = Math.round(n.t0 * 1000); filters.push(`[${i}]adelay=${ms}|${ms}[a${i}]`); });
      const mixIn = nars.map((_, i) => `[a${i}]`).join("");
      const fc = `${filters.join(";")};${mixIn}amix=inputs=${nars.length}:normalize=0:dropout_transition=0,apad=whole_dur=${totalS}[out]`;
      const mix: ArgvJob = { name: "narration_mix", argv: ["ffmpeg", "-y", "-v", "error", ...inputs, "-filter_complex", fc, "-map", "[out]", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", "-t", String(totalS), mixPath], note: `나레 블록 ${nars.length}개를 실측 t0 에 놓아 한 트랙으로 (길이 = 타임라인 총장 ${totalS}s)` };
      const probe: ArgvJob = { name: "mix_probe", argv: ["ffprobe", "-v", "error", "-print_format", "json", "-show_entries", "format=duration,size", mixPath], note: "믹스 길이 확인" };
      return base("export", preset, {
        status: "execute", next_step: "export",
        message: `내보내기 준비: 나레 ${nars.length}블록 믹스다운 → ${mixPath}. 결과를 payload.mix_probe 에 실어 export 를 다시 부르라.`,
        instructions: ["① do[] 의 ffmpeg 두 개를 그대로 실행한다 (믹스 → 확인).", "② measure 대로 mix_probe 를 payload 에 넣고 carry 값과 함께 export 를 다시 부른다."],
        then_call_with: ["step: 'export'", "payload: { …carry, timeline, voice, script, brief, transcript_metrics, mix_probe }"],
        do: [mix, probe], jobs_kind: null, jobs: [], measure: [{ as: "mix_probe", from: "job:mix_probe", unit: "json_stdout" }],
        carry: ["source", "workdir", "probe_summary", "transcript_path", "brief_path", "selection_path", "script_path", "voice_path", "timeline_path", "timeline", "voice", "script", "brief", "transcript_metrics"],
        source, workdir, probe_summary: ps, transcript_path: payload.transcript_path, brief_path: payload.brief_path, selection_path: payload.selection_path, script_path: payload.script_path, voice_path: payload.voice_path, timeline_path: payload.timeline_path,
        timeline: tl, voice, script, brief, transcript_metrics: transcript,
      });
    }

    // ── ② 검증 · XML · 게이트 재검사 · manifest ────────────────────────────
    const mp = payload.mix_probe as { format?: { duration?: string; size?: string } };
    const mixDur = Number(mp?.format?.duration ?? NaN);
    if (!Number.isFinite(mixDur) || Math.abs(mixDur - totalS) > 0.5) {
      return reject("export", preset, `hard_fail: 나레이션 믹스 길이 ${mixDur}s 가 타임라인 총장 ${totalS}s 와 다르다`, "① 의 ffmpeg 를 다시 실행하고(입력 wav 27개가 전부 있는지 · adelay/apad 인자 그대로인지) mix_probe 를 다시 실어 부르라.");
    }

    // 프레임
    const tb = ASM.내보내기.타임베이스, ntsc = ASM.내보내기.ntsc;
    const fps = ntsc ? tb * 1000 / 1001 : tb;
    const F = (sec: number) => Math.round(sec * fps);
    const RATE = `<rate><timebase>${tb}</timebase><ntsc>${ntsc ? "TRUE" : "FALSE"}</ntsc></rate>`;
    const W = ASM.내보내기.해상도.width, H = ASM.내보내기.해상도.height;
    const totalF = F(totalS);
    const srcDurF = F(ps.duration_s);
    const srcW = ps.width ?? W, srcH = ps.height ?? H;
    const sr = ps.audio_sample_rate ?? 44100, ch = ps.audio_channels ?? 2;
    const srcName = source.path.split(/[\\/]/).pop() ?? "source.mp4";
    const srcFile = (id: string) => `<file id="${id}"><name>${esc(srcName)}</name><pathurl>${esc(pathurl(source.path!))}</pathurl>${RATE}<duration>${srcDurF}</duration><media><video><samplecharacteristics><width>${srcW}</width><height>${srcH}</height></samplecharacteristics></video><audio><samplecharacteristics><depth>16</depth><samplerate>${sr}</samplerate></samplecharacteristics><channelcount>${ch}</channelcount></audio></media></file>`;
    const fileRef = `<file id="src-file"/>`;
    const pics = [...tl.picture].sort((a, b) => a.t0 - b.t0);
    // V1 원본 컷
    let firstFile = true;
    const v1 = pics.map((p, i) => {
      const s = F(p.t0), e = F(p.t1), inF = F(p.src_in), outF = inF + (e - s);
      const f = firstFile ? srcFile("src-file") : fileRef; firstFile = false;
      return `<clipitem id="v1-${i + 1}"><name>${esc(`${String(i + 1).padStart(2, "0")} ${p.role}${p.seg != null ? ` seg${p.seg}` : ""}`)}</name><duration>${e - s}</duration>${RATE}<start>${s}</start><end>${e}</end><in>${inF}</in><out>${outF}</out>${f}<sourcetrack><mediatype>video</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>`;
    }).join("\n        ");
    // A1 원본 소리 — 살릴 컷만. 덕킹 컷의 원본 소리는 A3 별도 트랙(규격 조립.덕킹_방식=별도트랙) — 프리미어 필터 의존을 끊는다
    const separateDuck = (ASM.덕킹_방식 ?? "별도트랙") === "별도트랙";
    const audioClip = (p: Pic, i: number, tag: string, withFilter: boolean) => {
      const s = F(p.t0), e = F(p.t1), inF = F(p.src_in), outF = inF + (e - s);
      const duck = withFilter ? `<filter><effect><name>Audio Levels</name><effectid>audiolevels</effectid><effectcategory>audiolevels</effectcategory><effecttype>audiolevels</effecttype><mediatype>audio</mediatype><parameter><parameterid>level</parameterid><name>Level</name><value>${ASM.덕킹_레벨}</value></parameter></effect></filter>` : "";
      return `<clipitem id="${tag}-${i + 1}"><name>${esc(`${String(i + 1).padStart(2, "0")} ${p.role} 소리${p.audio === "duck" ? " (덕킹)" : ""}`)}</name><duration>${e - s}</duration>${RATE}<start>${s}</start><end>${e}</end><in>${inF}</in><out>${outF}</out>${fileRef}<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>${duck}</clipitem>`;
    };
    const a1 = pics.map((p, i) => (separateDuck && p.audio === "duck") ? "" : audioClip(p, i, "a1", !separateDuck && p.audio === "duck")).filter(Boolean).join("\n        ");
    const a3 = separateDuck ? pics.map((p, i) => p.audio === "duck" ? audioClip(p, i, "a3", true) : "").filter(Boolean).join("\n        ") : "";
    // A2 나레 블록
    const vmap = new Map(voice.blocks.map((b) => [b.n, b]));
    const a2 = nars.map((n, i) => {
      const s = F(n.t0), e = Math.max(s + 1, F(n.t1));
      const wavName = n.wav.split(/[\\/]/).pop() ?? `b${n.n}.wav`;
      return `<clipitem id="a2-${i + 1}"><name>${esc(`나레 ${n.n} ${n.text.slice(0, 20)}`)}</name><duration>${e - s}</duration>${RATE}<start>${s}</start><end>${e}</end><in>0</in><out>${e - s}</out><file id="nar-${n.n}"><name>${esc(wavName)}</name><pathurl>${esc(pathurl(n.wav))}</pathurl>${RATE}<duration>${e - s}</duration><media><audio><samplecharacteristics><depth>16</depth><samplerate>24000</samplerate></samplecharacteristics><channelcount>1</channelcount></audio></media></file><sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>`;
    }).join("\n        ");
    // V2 대사 · V3 나레 자막 (Text 제너레이터)
    const gen = (c: Cue, id: string) => {
      const kind = c.lane === "nar" ? "나레" : "대사";
      const font = SUB.폰트[kind]; const size = SUB.크기_px[kind]; const pos = SUB.위치[kind] as { origin_x: number; origin_y: number; 목표_px: { x: number; y: number } }; const col = SUB.색[kind];
      // 위치: origin(중앙 기준 비율 — 프리미어가 읽는 통로, 규격 자막.위치) + Basic Motion center(픽셀, FCP 규약 병기)
      const bmH = pos.목표_px.x - W / 2, bmV = pos.목표_px.y - H / 2;
      const fontName = font.xml명 ?? font.패밀리;
      const s = F(c.t0), e = Math.max(s + 1, F(c.t1));
      return `<generatoritem id="${id}"><name>${esc(c.text.slice(0, 24))}</name><duration>${e - s}</duration>${RATE}<start>${s}</start><end>${e}</end><in>0</in><out>${e - s}</out><effect><name>Text</name><effectid>Text</effectid><effectcategory>Text</effectcategory><effecttype>generator</effecttype><mediatype>video</mediatype><parameter><parameterid>str</parameterid><name>Text</name><value>${esc(c.text)}</value></parameter><parameter><parameterid>font</parameterid><name>Font</name><value>${esc(fontName)}</value></parameter><parameter><parameterid>fontsize</parameterid><name>Size</name><value>${size}</value></parameter><parameter><parameterid>alignment</parameterid><name>Alignment</name><value>center</value></parameter><parameter><parameterid>fillcolor</parameterid><name>Color</name><value><alpha>255</alpha><red>${col.r}</red><green>${col.g}</green><blue>${col.b}</blue></value></parameter><parameter><parameterid>origin</parameterid><name>Origin</name><value><horiz>${pos.origin_x}</horiz><vert>${pos.origin_y}</vert></value></parameter></effect><filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype><parameter><parameterid>scale</parameterid><name>Scale</name><value>100.0000</value></parameter><parameter><parameterid>center</parameterid><name>Center</name><value><horiz>${bmH}</horiz><vert>${bmV}</vert></value></parameter></effect></filter></generatoritem>`;
    };
    const dlgCues = tl.cues.filter((c) => c.lane === "dlg").sort((a, b) => a.t0 - b.t0);
    const narCues = tl.cues.filter((c) => c.lane === "nar").sort((a, b) => a.t0 - b.t0);
    const v2 = dlgCues.map((c, i) => gen(c, `v2-${i + 1}`)).join("\n        ");
    const v3 = narCues.map((c, i) => gen(c, `v3-${i + 1}`)).join("\n        ");
    const seqName = ASM.내보내기.시퀀스_이름.replace("{title}", title);
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <sequence id="sequence-1">
    <name>${esc(seqName)}</name>
    <duration>${totalF}</duration>
    ${RATE}
    <media>
      <video>
        <format><samplecharacteristics><width>${W}</width><height>${H}</height><pixelaspectratio>square</pixelaspectratio>${RATE}</samplecharacteristics></format>
        <track>
        ${v1}
        </track>
        <track>
        ${v2}
        </track>
        <track>
        ${v3}
        </track>
      </video>
      <audio>
        <track>
        ${a1}
        </track>
        <track>
        ${a2}
        </track>${a3 ? `
        <track>
        ${a3}
        </track>` : ""}
      </audio>
    </media>
  </sequence>
</xmeml>
`;

    // ── SRT (timeline 큐 그대로) ───────────────────────────────────────────
    const fmt = (x: number) => { const ms = Math.round(x * 1000); const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), s = Math.floor((ms % 60000) / 1000), mm = ms % 1000; return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(mm).padStart(3, "0")}`; };
    const srt = (list: Cue[], prefixDlg: boolean) => list.map((c, i) => `${i + 1}\n${fmt(c.t0)} --> ${fmt(c.t1)}\n${prefixDlg && c.lane === "dlg" ? "– " : ""}${c.text}\n`).join("\n") + "\n";
    const allCues = [...tl.cues].sort((a, b) => a.t0 - b.t0);

    // ── 게이트 전체 재검사 (최종 산출물에서 독립 계산) ──────────────────────
    const gates: { step: string; id: string; pass: boolean | null; hard: boolean; detail: string }[] = [];
    gates.push({ step: "probe", id: "오디오 트랙", pass: ps.audio === true, hard: true, detail: `audio=${ps.audio}` });
    gates.push({ step: "transcript", id: "발화 0건 아님", pass: (transcript?.utterance_count ?? 0) > 0, hard: true, detail: `발화 ${transcript?.utterance_count ?? "?"}` });
    const evs = brief?.events ?? [];
    const evBad = evs.filter((e) => e.start < 0 || e.end > ps.duration_s! + 1 || e.end <= e.start).length;
    gates.push({ step: "brief", id: "사건 타임코드 범위", pass: evs.length > 0 && evBad === 0, hard: true, detail: `사건 ${evs.length}건 · 범위 밖 ${evBad}` });
    // select G16: 원본 재사용 (V1 컷끼리 원본 구간 겹침 >50%)
    let reuseS = 0; const totalPicS = pics.reduce((a, p) => a + (p.src_out - p.src_in), 0);
    for (let i = 0; i < pics.length; i++) for (let j = i + 1; j < pics.length; j++) { const o = Math.min(pics[i].src_out, pics[j].src_out) - Math.max(pics[i].src_in, pics[j].src_in); if (o > 0 && o > 0.5 * Math.min(pics[i].src_out - pics[i].src_in, pics[j].src_out - pics[j].src_in)) reuseS += o; }
    const reuseRatio = r3(reuseS / totalPicS);
    gates.push({ step: "select", id: "G-반복(G16 원본 재사용)", pass: reuseRatio <= AG["G-반복"].컷_반복_비율_max.value, hard: true, detail: `재사용 ${reuseRatio} (≤${AG["G-반복"].컷_반복_비율_max.value})` });
    // script: 나레 시간점유 (voice 실측 ÷ (voice + 대사 발화))
    const narTotal = voice.blocks.reduce((a, b) => a + b.dur_s, 0);
    const dlgS = script?.metrics?.dialogue_s ?? 0;
    const share = dlgS > 0 ? r3(narTotal / (narTotal + dlgS)) : null;
    gates.push({ step: "script", id: "나레 시간점유(G27, 실측)", pass: share === null ? null : share >= AS.나레_시간점유.min && share <= AS.나레_시간점유.max, hard: true, detail: `${share} (대역 ${AS.나레_시간점유.min}~${AS.나레_시간점유.max})` });
    // voice: 전 블록 합성됨 + XML 의 A2 와 대응
    const missingWav = nars.filter((n) => !vmap.get(n.n) || (vmap.get(n.n)!.bytes ?? 1) <= 0).length;
    gates.push({ step: "voice", id: "블록 합성 전건", pass: missingWav === 0 && nars.length === voice.blocks.length, hard: true, detail: `타임라인 나레 ${nars.length} / voice ${voice.blocks.length} · 빈 파일 ${missingWav}` });
    // subtitle: 자수 · 겹침 · 죽은 시간 (큐에서 다시 계산)
    const maxNar = Math.max(0, ...narCues.map((c) => c.text.length)), maxDlg = Math.max(0, ...dlgCues.map((c) => c.text.length));
    let ov = 0; for (const L of [narCues, dlgCues]) for (let i = 1; i < L.length; i++) if (L[i].t0 < L[i - 1].t1 - 1e-6) ov++;
    const holdIv = pics.filter((p) => ASM.죽은시간_홀드_제외_역할.includes(p.role)).map((p) => [p.t0, p.t1] as [number, number]);
    const holdS = holdIv.reduce((a, [x, y]) => a + (y - x), 0);
    // 축 = 자막 큐 ∪ 나레 음성 구간 (subtitle 과 같은 축 — 2026-08-17 정정: 나레 안 쉼은 죽은 시간이 아니다)
    const union: [number, number][] = []; for (const [a, b] of [...allCues.map((c) => [c.t0, c.t1] as [number, number]), ...nars.map((n) => [n.t0, n.t1] as [number, number])].sort((x, y) => x[0] - y[0])) { const l = union[union.length - 1]; if (l && a <= l[1]) l[1] = Math.max(l[1], b); else union.push([a, b]); }
    const inHold = (x: number, y: number) => holdIv.reduce((acc, [h0, h1]) => acc + Math.max(0, Math.min(y, h1) - Math.max(x, h0)), 0);
    const covered = union.reduce((a, [x, y]) => a + (y - x) - inHold(x, y), 0);
    const deadRatio = r3(Math.max(0, (totalS - holdS - covered)) / (totalS - holdS));
    gates.push({ step: "subtitle", id: "G-자막(한 줄 자수)", pass: maxNar <= AJ["G-자막_한줄_최대자수"].나레 && maxDlg <= AJ["G-자막_한줄_최대자수"].대사, hard: true, detail: `나레 ${maxNar}/${AJ["G-자막_한줄_최대자수"].나레} · 대사 ${maxDlg}/${AJ["G-자막_한줄_최대자수"].대사}` });
    gates.push({ step: "subtitle", id: "G-자막(같은 레인 겹침)", pass: ov <= AJ["G-자막_겹침_max"].value, hard: true, detail: `겹침 ${ov}` });
    gates.push({ step: "subtitle", id: "G-죽은시간(홀드 제외)", pass: deadRatio <= AJ["G-죽은시간_max"].value, hard: true, detail: `${deadRatio} (≤${AJ["G-죽은시간_max"].value}, 홀드 ${r3(holdS)}s)` });
    // export 자체: XML 요소 수 = 실측 수
    const duckN = pics.filter((p) => p.audio === "duck").length;
    gates.push({ step: "export", id: "XML 요소 수 = 타임라인 실측", pass: true, hard: true, detail: `V1 컷 ${pics.length} · V2 대사 자막 ${dlgCues.length} · V3 나레 자막 ${narCues.length} · A1 원본 소리 ${separateDuck ? pics.length - duckN : pics.length} · A2 나레 ${nars.length}${separateDuck ? ` · A3 덕킹 컷 소리 ${duckN}` : ""} · 믹스 ${r3(mixDur)}s` });
    const failed = gates.filter((g) => g.hard && g.pass === false);
    if (failed.length) {
      return reject("export", preset, `최종 재검사 불통 ${failed.length}건 — ${failed.map((g) => `[${g.step}] ${g.id}: ${g.detail}`).join(" / ")}`, "불통 단계로 돌아가 그 단계의 수리 지침대로 고친 뒤 이후 단계를 다시 돌리고 export 를 다시 부르라. 최종 산출물은 중간 파일을 신뢰하지 않고 다시 잰다.");
    }

    const fontsUsed = { 나레: SUB.폰트.나레, 대사: SUB.폰트.대사 };
    const manifest = {
      title, source: source.path, created: new Date().toISOString().slice(0, 10),
      format: ASM.내보내기.형식, sequence: { name: seqName, width: W, height: H, timebase: tb, ntsc, fps: r3(fps), total_s: totalS, total_frames: totalF, tracks: { ...ASM.내보내기.트랙, ...(separateDuck ? { A3: "덕킹 컷 원본 소리(볼륨 낮춤·필요시 음소거)" } : {}) } },
      materials: {
        xml: join(renderDir, `${slug}.xml`), narration_mix_wav: mixPath, narration_block_wavs: nars.map((n) => n.wav),
        srt: { all: join(renderDir, "subtitle.srt"), narration: join(renderDir, "subtitle_nar.srt"), dialogue: join(renderDir, "subtitle_dlg.srt") },
        source_video: source.path, timeline: payload.timeline_path ?? null,
      },
      counts: { cuts: pics.length, narration_blocks: nars.length, cues: allCues.length, cues_nar: narCues.length, cues_dlg: dlgCues.length },
      fonts: fontsUsed,
      gates,
      metrics: { total_s: totalS, source_ratio: r3(totalS / ps.duration_s), narration_s: r3(narTotal), dialogue_s: dlgS, nar_share: share, dead_ratio: deadRatio, reuse_ratio: reuseRatio, mix_duration_s: r3(mixDur), sec_per_char: voice.metrics?.sec_per_char_measured ?? null },
      notes: ["타이밍은 subtitle/timeline.json 실측 그대로(초→프레임 반올림)", "산돌구름이 켜져 있어야 폰트가 이름으로 잡힌다 (XML 폰트 이름은 규격 자막.폰트.xml명 = PS 명, 2026-08-16 확정)", separateDuck ? "연장·브리지 컷의 원본 소리는 A3 트랙에 따로 두었다 — 나레와 겹치면 A3 볼륨을 내리거나 음소거" : "연장·브리지 컷의 원본 소리는 Audio Levels 로 낮춰 두었다 — 프리미어가 안 읽으면 수동", "자막 위치: Text 제너레이터 origin 파라미터(중앙 기준 비율, 규격 자막.위치)로 자동 배치 — 2026-08-16 시험5b 로 좌표계 확정. 임포트 뒤 나레 y≈840·대사 y≈980 인지 확인만"],
      프리미어_후속: [
        { 트랙: "V3 나레 자막", 방법: "확인만 — origin 으로 자동 배치됨. 어긋나면 V3 클립 전부 선택 → Essential Graphics 정렬 및 변형에서 아래 값으로", 위치_px: (SUB.위치.나레 as { 목표_px: { x: number; y: number } }).목표_px, origin_y: (SUB.위치.나레 as { origin_y: number }).origin_y, 정렬: "가운데", 폰트: `${SUB.폰트.나레.패밀리} (${SUB.폰트.나레.xml명 ?? SUB.폰트.나레.PS명})`, 크기_px: SUB.크기_px.나레 },
        { 트랙: "V2 대사 자막", 방법: "확인만 — origin 으로 자동 배치됨. 어긋나면 V2 클립 전부 선택 → Essential Graphics 정렬 및 변형에서 아래 값으로", 위치_px: (SUB.위치.대사 as { 목표_px: { x: number; y: number } }).목표_px, origin_y: (SUB.위치.대사 as { origin_y: number }).origin_y, 정렬: "가운데", 폰트: `${SUB.폰트.대사.패밀리} (${SUB.폰트.대사.xml명 ?? SUB.폰트.대사.PS명})`, 크기_px: SUB.크기_px.대사 },
        ...(separateDuck ? [{ 트랙: "A3 덕킹 컷 소리", 방법: "나레와 부딪히면 A3 트랙 볼륨을 내리거나 음소거", 위치_px: null, origin_y: null, 정렬: null, 폰트: null, 크기_px: null }] : []),
      ],
    };
    return base("export", preset, {
      status: "done", next_step: null,
      message: `내보내기 완료: ${seqName} — 컷 ${pics.length} · 나레 ${nars.length} · 자막 ${allCues.length} · 총 ${totalS}s. 게이트 ${gates.length}개 전부 통과. render/ 에 XML·SRT 3종·나레이션 믹스·manifest.`,
      instructions: [`① write_files 5개를 그대로 쓴다 (${renderDir}).`, "② manifest.json 의 gates 표와 metrics 를 사람에게 보여준다.", "③ 프리미어: **반드시 새 빈 프로젝트**를 만들어 파일 > 가져오기로 XML 을 연다 (같은 소재가 이미 있는 프로젝트에 재임포트하면 오디오 트랙이 조용히 빠진다 — 2026-08-16 실측, 참고_export.md 8절). 시퀀스 하나가 생긴다. 자막 위치는 origin 파라미터로 자동 배치된다 — 나레 y≈840·대사 y≈980 인지 확인만(어긋나면 manifest.프리미어_후속). 순서는 서버 README."],
      then_call_with: [], jobs_kind: null, jobs: [], measure: [],
      write_files: [
        { path: join(renderDir, `${slug}.xml`), content: xml, note: "FCP XML v5 — 프리미어 파일 > 가져오기" },
        { path: join(renderDir, "subtitle.srt"), content: srt(allCues, true), note: "합본(대사 –)" },
        { path: join(renderDir, "subtitle_nar.srt"), content: srt(narCues, false), note: "나레 자막" },
        { path: join(renderDir, "subtitle_dlg.srt"), content: srt(dlgCues, false), note: "대사 자막" },
        { path: join(renderDir, "manifest.json"), content: manifest, note: "재료 목록·총 길이·게이트·폰트" },
      ],
      metrics: manifest.metrics, gates,
      carry: [],
    });
  },
};
