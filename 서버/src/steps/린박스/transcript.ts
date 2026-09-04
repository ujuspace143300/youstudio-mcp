/**
 * steps/린박스/transcript.ts — lb_transcript: 전사(★Speechmatics 유료) + 화자표. 두 번 부른다.
 *
 * 볼케이노 키트 대응: 전사.py(세 벌 듣고 대조 → 대사.json·대사표.txt·seg_asr.json) · 화자표.py(누가 말했는가 — 얼굴 오려 보여 줌).
 *   ① payload.대사 가 없으면 → 먼저 lb_cut 결과를 검사하고(절단본 길이·start_time §78·장면컷 표), ★유료 승인을 묻는 지시를 낸다.
 *      do[] 로 낱말사전(사전.json)을 쓰고, jobs 로 전사.py·화자표.py 를 편 폴더에서 돌린 뒤 대사.json 을 payload.대사 로 재 온다.
 *      키는 러너가 본인 자리(~/.volcano/keys/speechmatics · 환경변수)에서 읽는다 — 서버는 키를 보관하지 않는다.
 *   ② payload.대사 가 있으면 → 검사(낱말 0 이면 반려) · metrics(낱말·말 길이·셋 다 일치 비율·화자 수)
 *      ②a srt_candidates 가 없으면 → jobs 로 드라마 폴더의 SRT 후보를 전부 읽어 온다(srt후보읽기.py) → 다시 자기 자신
 *      ②b srt_candidates 가 있으면 → 서버가 **내용으로** 고른다(srt.ts pickSrt · 규격 §94 「글자는 SRT, 시각은 전사」).
 *         골랐으면 do 로 편 폴더 `srt원본`(경로·밀기)을 쓰고 jobs 로 SRT블록.py(srt대사.txt · _대본초안_D블록.txt) → next_step=lb_plan.
 *         못 골랐으면 **아무것도 안 적고**(틀린 SRT 를 무는 것이 가장 나쁘다) 경고와 함께 lb_plan 으로. payload.skip_srt=true 면 ②a·②b 를 건너뛴다.
 * 요금: Speechmatics 배치 — 구간 길이 × 3벌(원음·말소리·잡음제거). 지인 본인 키·본인 계정(설계 7절).
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, r3, readCarry, str } from "./lib.js";
import { pickSrt, type SrtCandidate } from "./srt.js";

interface Word { s: number; e: number; t: string; c?: number; spk?: string; votes?: number; sure?: boolean }

/** 장면컷.py 표준출력의 「찾은 장면전환 N개」 */
export function parseSceneCount(log: unknown): number | null {
  if (typeof log !== "string") return null;
  const m = log.match(/찾은 장면전환\s+(\d+)개/);
  return m ? Number(m[1]) : null;
}

export const lbTranscript: StepHandler = {
  name: "lb_transcript",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_transcript", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_cut 응답의 carry 값을 payload 에 그대로 실어 lb_transcript 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) {
      return reject("lb_transcript", preset, "payload.repo(저장소 루트 절대경로)가 없다", "youstudio-mcp 저장소 루트의 절대경로를 payload.repo 에 실어 다시 부르라.");
    }
    const spanS = r3(carry.end_s - carry.start_s);
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const cut = join(carry.ep_dir, "구간.mp4");
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary,
    };

    // ── ② 결과 검사 ──────────────────────────────────────────────────────
    if (payload.대사 !== undefined) {
      const d = payload.대사 as { words?: Word[] } | undefined;
      const words = Array.isArray(d?.words) ? d!.words!.filter((w) => w && typeof w.s === "number" && typeof w.e === "number" && typeof w.t === "string") : [];
      if (!words.length) {
        return reject("lb_transcript", preset, "hard_fail: 대사.json 에 낱말이 하나도 없다", "구간에 말이 없거나 전사가 실패한 것이다. 편 폴더의 대사표.txt 와 전사 로그(transcript_log)를 보라 — 키(SPEECHMATICS_API_KEY / ~/.volcano/keys/speechmatics)가 없으면 전사.py 가 첫 줄에서 죽는다. 말이 정말 없으면 구간을 바꿔 start 부터 다시.");
      }
      const speechS = r3(words.reduce((a, w) => a + Math.max(0, w.e - w.s), 0));
      const sure = words.filter((w) => w.sure === true).length;
      const speakers = new Set(words.map((w) => w.spk ?? "?")).size;
      const sureRatio = Math.round((sure / words.length) * 100);
      const warnings: string[] = [];
      if (sureRatio < 50) warnings.push(`셋 다 일치한 낱말이 ${sureRatio}% 뿐이다 — 음악·효과음이 세거나 낱말사전(이름)이 비었을 수 있다. 대사표.txt 의 ★ 를 귀로 확인하고, 이름은 사전.json 에 넣어 다시 전사하는 쪽이 낫다.`);
      if (speakers <= 1) warnings.push("화자가 한 뭉치로 묶였다(실측 11편 중 4편) — 화자표.py 가 낸 _화자줄.jpg 로 줄마다 이름을 적어라(화자줄.json).");
      const asr = words.map((w) => ({ s: w.s, e: w.e, t: w.t }));
      const dramaDir = source.path.replace(/[\\/][^\\/]*$/, "");
      // ②a — SRT 후보 훑기 (드라마 폴더 아래 *.srt 전부 · 우리 납품 SRT 가 있는 작업/·완성/ 은 건너뛴다)
      if (payload.srt_candidates === undefined && payload.skip_srt !== true) {
        if (!repo) return reject("lb_transcript", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
        return base("lb_transcript", preset, {
          status: "execute",
          next_step: "lb_transcript",
          message: `전사 확인: 낱말 ${words.length}개 · 말 ${speechS}초(구간 ${spanS}초) · 셋 다 일치 ${sureRatio}% · 화자 뭉치 ${speakers}. 이제 드라마 폴더 ${dramaDir} 아래의 공식 SRT 후보를 전부 읽어 오라 — 서버가 전사와 내용을 대조해 고른다(규격 §94 · 경로로 짐작하지 않는다).`,
          instructions: [
            "① 전사(ASR)는 반드시 틀린다 — 자막 글자는 공식 SRT 가 정답, 시각은 전사가 정답이다(§94). 그래서 SRT 를 **내용으로** 고른다.",
            `② jobs 의 srt_scan 이 ${dramaDir} 아래 *.srt 를 전부 읽어 JSON 으로 낸다(작업/·완성/ 은 건너뜀). SRT 가 한 파일도 없으면 빈 배열이다 — 그래도 실어 보내라(서버가 «없음» 으로 판정하고 전사 글자로 간다).`,
            "③ measure 대로 payload.srt_candidates 에 그 JSON 을 실어 lb_transcript 를 **다시** 부른다. SRT 를 쓰지 않을 편이면 srt_candidates 대신 skip_srt: true.",
          ],
          then_call_with: ["step: 'lb_transcript'", "payload: { …carry, 대사, srt_candidates: <srt_scan JSON> }"],
          jobs_kind: "argv",
          jobs_cwd: carry.ep_dir,
          jobs: [{ name: "srt_scan", argv: ["python", tool("srt후보읽기.py"), dramaDir], out: join(carry.ep_dir, "_srt_candidates.json"), note: "드라마 폴더 아래 *.srt 전부 → [{path, lines:[[s,e,글]]}] JSON. 서버(pickSrt)가 전사 낱말과 대조해 고른다." }],
          measure: [{ as: "srt_candidates", from: "job:srt_scan", unit: "json_stdout" }],
          metrics: { words: words.length, speech_s: speechS, span_s: spanS, sure_ratio_pct: sureRatio, speakers, scene_count: payload.scene_count ?? null },
          carry: [...CARRY_KEYS, "repo", "probe_summary", "scene_count", "대사"],
          ...common,
          scene_count: payload.scene_count ?? null,
          대사: payload.대사,
          ...(warnings.length ? { warnings } : {}),
        });
      }
      // ②b — 고르기 → srt원본 못박기 · SRT블록(srt대사.txt · D 블록 초안)
      let srtPick: Record<string, unknown> | null = null;
      const srtDo: { name: string; argv: string[]; out?: string; note?: string }[] = [];
      const srtJobs: { name: string; argv: string[]; optional?: boolean; out?: string; note?: string }[] = [];
      const srtMeasure: { as: string; from: string; unit: "stdout" }[] = [];
      if (payload.skip_srt !== true) {
        const cands = (Array.isArray(payload.srt_candidates) ? payload.srt_candidates : []) as SrtCandidate[];
        const valid = cands.filter((c) => c && typeof c.path === "string" && Array.isArray(c.lines));
        const forced = str(payload, "srt_path");
        const pool = forced ? valid.filter((c) => c.path === forced) : valid;
        const pick = pickSrt(pool, asr, carry.start_s, spanS);
        if (forced && !pool.length) warnings.push(`payload.srt_path 「${forced}」 가 후보 목록에 없다 — 드라마 폴더 아래에 두고 다시 훑어라.`);
        if (pick.chosen) {
          const c = pick.chosen;
          srtPick = { path: c.path, shift: c.shift, matched: c.matched, in_window: c.in_window, ratio: c.ratio, samples: c.samples };
          srtDo.push({
            name: "write_srt_pin",
            argv: ["python", "-c", "import io,sys;io.open('srt원본','w',encoding='utf-8').write(sys.argv[1]);print(io.open('srt원본',encoding='utf-8').read().split(chr(10))[0])", `${c.path}\n밀기=${c.shift}\n맞음=${c.matched}/${c.in_window} · 유스튜디오 내용대조(전사 표 ${c.samples})\n`],
            out: join(carry.ep_dir, "_srt_pin_log.txt"),
            note: "편 폴더 srt원본(경로 · 밀기= · 맞음=) — 키트 srt고르기.py 가 내던 꼴. 밀기는 «SRT초 + 밀기 = 절단본 초»(EPnn 폴더는 구간시작 0).",
          });
          srtJobs.push(
            { name: "srt_blocks", argv: ["python", tool("SRT블록.py"), "--구간시작", "0", "--구간끝", String(spanS)], optional: true, note: "srt원본 → srt대사.txt(SRT 글자 · 절단본 시각) + _대본초안_D블록.txt(author BLOCKS 에 붙일 D 블록 초안). 사람은 빼기만(§94)." },
            { name: "read_draft", argv: ["python", "-c", "import io,os;print(io.open('_대본초안_D블록.txt',encoding='utf-8').read() if os.path.exists('_대본초안_D블록.txt') else '')"], optional: true, note: "초안을 measure 로 실어 lb_script need_input 에 보여 준다." },
          );
          srtMeasure.push({ as: "srt_draft", from: "job:read_draft", unit: "stdout" });
        } else {
          warnings.push(`공식 SRT 를 못박지 않았다 — ${pick.reason} 전사 글자로 간다(완성검사 13 은 srt원본 이 없으면 건너뛴다). 후보: ${pick.table.slice(0, 3).map((x) => `${x.path.split("/").pop()} ${x.matched}/${x.in_window}${x.shift === null ? "(밀기 못 잼)" : ""}`).join(" · ") || "없음"}`);
        }
      }
      return base("lb_transcript", preset, {
        status: "execute",
        next_step: "lb_plan",
        message: `전사 확인: 낱말 ${words.length}개 · 말 ${speechS}초(구간 ${spanS}초) · 셋 다 일치 ${sureRatio}% · 화자 뭉치 ${speakers}${srtPick ? ` · 공식 SRT 「${String(srtPick.path).split("/").pop()}」 못박음(밀기 ${srtPick.shift}초 · 맞음 ${srtPick.matched}/${srtPick.in_window})` : " · 공식 SRT 없음"}. 사람이 화자.json/화자줄.json 에 이름을 적은 뒤 lb_plan 으로.`,
        instructions: [
          "① 편 폴더의 _화자.jpg / _화자줄.jpg 를 보고 화자.json(뭉치별) 또는 화자줄.json(줄별)에 사람 이름을 적는다 — 규격.md §33 «누가 말했는가를 대본보다 먼저». 사람을 가리키는 말은 프레임을 보고 쓴다(§71).",
          "② 대사표.txt 의 ★ 낱말은 귀로 확인한다 — ★ 가 없어도 사투리·구어는 틀릴 수 있다. 자막 글자는 공식 SRT 가 정답(§94) — 못박혔으면 편 폴더 srt대사.txt·_대본초안_D블록.txt 를 쓴다.",
          "③ carry 의 값(… 대사·scene_count·srt_pick)과 measure 의 srt_draft 를 payload 에 그대로 실어 lb_plan 을 부른다 — lb_plan 이 쓸거리(≥ 규격 edit.min_usable_speech_sec)·대사 밀도를 재고 하단(로고/문구)을 묻는다.",
        ],
        then_call_with: ["step: 'lb_plan'", "payload: { source, workdir, ep, ep_dir, start_s, end_s, repo, probe_summary, scene_count, 대사, srt_pick, srt_draft }"],
        ...(srtJobs.length ? { jobs_kind: "argv" as const, jobs_cwd: carry.ep_dir, do: srtDo, jobs: srtJobs, measure: srtMeasure } : { jobs_kind: null, jobs: [], measure: [] }),
        metrics: { words: words.length, speech_s: speechS, span_s: spanS, sure_ratio_pct: sureRatio, speakers, scene_count: payload.scene_count ?? null, srt_pinned: !!srtPick },
        carry: [...CARRY_KEYS, "repo", "probe_summary", "scene_count", "대사", "srt_pick"],
        ...common,
        scene_count: payload.scene_count ?? null,
        대사: payload.대사,
        srt_pick: srtPick,
        ...(warnings.length ? { warnings } : {}),
      });
    }

    // ── ① lb_cut 결과 검사 + 유료 지시 ─────────────────────────────────────
    const cp = payload.cut_probe as { streams?: { codec_type?: string; start_time?: string; duration?: string }[]; format?: { duration?: string; start_time?: string } } | undefined;
    if (!cp || !cp.format) {
      return reject("lb_transcript", preset, "payload.cut_probe(절단본 ffprobe JSON)가 없다", "lb_cut 이 지시한 cut_probe 를 실행해 그 JSON 을 payload.cut_probe 에, 장면컷.py 표준출력을 payload.scene_cuts_log 에 실어 lb_transcript 를 다시 부르라.");
    }
    const cutDur = Number(cp.format.duration ?? NaN);
    if (!Number.isFinite(cutDur) || Math.abs(cutDur - spanS) > 0.5) {
      return reject("lb_transcript", preset, `절단본 길이 ${Number.isFinite(cutDur) ? r3(cutDur) : "?"}초가 요청 구간 ${spanS}초와 0.5초 넘게 다르다`, "구간.mp4 가 덜 구워졌거나 옛 파일이다. 편 폴더의 구간.mp4·구간_원본.mp4 를 지우고 lb_cut 을 다시 부르라.");
    }
    const v = cp.streams?.find((s) => s.codec_type === "video");
    const st = Number(v?.start_time ?? cp.format.start_time ?? 0) || 0;
    const sceneCount = parseSceneCount(payload.scene_cuts_log);
    const warnings: string[] = [];
    if (st > 0.1) warnings.push(`절단본 start_time 이 ${r3(st)}초다 — 옛 scene_cuts.txt 가 있었다면 그만큼 어긋난다(§78). 이번에 장면컷.py 가 새로 쟀으니 그 표만 쓴다.`);
    if (sceneCount === null) warnings.push("scene_cuts_log 에서 「찾은 장면전환 N개」를 못 읽었다 — 장면컷.py 가 돌았는지(numpy·pillow·av/cv2 설치) 확인하라. 컷 표 없이는 lb_blocks 가 컷을 촬영본 안에 못 앉힌다.");
    else if (sceneCount === 0) warnings.push("장면전환 0개 — 롱테이크일 수 있다(4편 76초 무전환 실측). 의심되면 프레임을 뽑아 확인.");

    const dict = Array.isArray(payload.dictionary) ? (payload.dictionary as unknown[]).filter((x) => typeof x === "object" && x !== null && typeof (x as { content?: unknown }).content === "string") : [];
    const doJobs = dict.length
      ? [{
          name: "write_dict",
          argv: ["python", "-c", "import json,sys;json.dump(json.loads(sys.argv[1]),open('사전.json','w',encoding='utf-8'),ensure_ascii=False,indent=1);print('사전.json',len(json.loads(sys.argv[1])))", JSON.stringify(dict)],
          out: join(carry.ep_dir, "_dict_log.txt"),
          note: "낱말사전(이름·고유명사 sounds_like) → 편 폴더 사전.json. 전사.py 가 additional_vocab 으로 보낸다(없으면 「고니」를 「보니」로 듣는다).",
        }]
      : [];

    return base("lb_transcript", preset, {
      status: "execute",
      next_step: "lb_transcript",
      message: `★유료 단계 — Speechmatics 전사 요금이 나간다: 구간 ${spanS}초 × 3벌(원음·말소리·잡음제거) = 약 ${r3((spanS * 3) / 60)}분 분량. 실행 전에 사장님(또는 본인)에게 비용을 보고하고 승인받은 뒤 jobs 를 돌리라.`,
      instructions: [
        `① ★유료 API 단계다 — 실행 전에 예상 분량(구간 ${spanS}초 × 3벌 ≈ ${r3((spanS * 3) / 60)}분, Speechmatics 배치 과금 · 본인 키 ~/.volcano/keys/speechmatics 또는 SPEECHMATICS_API_KEY)을 보고하고 승인받는다. 승인 전에는 돌리지 않는다.`,
        `② jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로 순서대로 실행한다 (jobs_cwd). do 의 write_dict 가 먼저 사전.json 을 쓴다(payload.dictionary 를 줬을 때만). 이름·고유명사가 있으면 dictionary: [{content, sounds_like[]}] 로 실어 오는 쪽이 낫다 — 지금 없으면 전사.py 가 경고만 하고 사전 없이 간다.`,
        "③ 전사.py 는 세 벌을 동시에 보내 대조한다(셋 다 같게 들린 낱말만 sure). 끝나면 대사.json·대사표.txt·seg_asr.json 이 편 폴더에 생긴다. 화자표.py 는 얼굴을 오려 _화자.jpg·_화자줄.jpg 와 화자.json 틀을 낸다(optional — yunet 이 없으면 화면 전체를 보여 준다).",
        "④ measure 대로 payload.대사(대사.json 전체)·payload.transcript_log(전사.py 표준출력)·payload.scene_count 를 실어 lb_transcript 를 **다시** 부른다 — 서버가 검사한다.",
      ],
      then_call_with: ["step: 'lb_transcript'", "payload: { source, workdir, ep, ep_dir, start_s, end_s, repo, probe_summary, scene_count, 대사: <대사.json>, transcript_log: <stdout> }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      ...(doJobs.length ? { do: doJobs } : {}),
      jobs: [
        {
          name: "transcribe",
          argv: ["python", tool("전사.py"), cut],
          out: join(carry.ep_dir, "_transcript_log.txt"),
          note: "★유료 — Speechmatics 배치 3건(ko · enhanced · 화자 분리 · additional_vocab=사전). 키는 러너가 본인 자리에서 읽는다. 표준출력 첫 줄에 「■ 화자 N명 · 낱말 N개 · 셋 다 일치 N개」.",
        },
        {
          name: "speakers",
          argv: ["python", tool("화자표.py"), cut],
          optional: true,
          note: "대사.json 의 화자 뭉치마다 얼굴을 오려 _화자.jpg·_화자줄.jpg 로 보여 준다. 판정은 안 한다 — 이름은 사람이 화자.json/화자줄.json 에 적는다(§33).",
        },
        {
          name: "read_words",
          argv: ["python", "-c", "import io;print(io.open('대사.json',encoding='utf-8').read())"],
          note: "대사.json 을 표준출력으로 — measure 가 payload.대사 로 싣는다.",
        },
      ],
      measure: [
        { as: "대사", from: "job:read_words", unit: "json_stdout" },
        { as: "transcript_log", from: "job:transcribe", unit: "stdout" },
      ],
      metrics: { cut_duration_s: r3(cutDur), cut_start_time_s: r3(st), scene_count: sceneCount, asr_minutes_est: r3((spanS * 3) / 60) },
      carry: [...CARRY_KEYS, "repo", "probe_summary", "scene_count"],
      ...common,
      scene_count: sceneCount,
      ...(warnings.length ? { warnings } : {}),
    });
  },
};
