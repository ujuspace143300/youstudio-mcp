/**
 * steps/린박스/check.ts — lb_check: 작업규칙 「완성 보고」 기계 항목을 한 번에 잰다 (정본 `신병4/완성검사.sh` 검사부). 두 번 부른다.
 *
 *   ① payload.check 없음 → jobs: 검사 한 벌(python -c JSON) + 글꼴폴백검사 + 마스터효과 --확인만 + 제목끝맞춤 --확인만 → measure
 *   ② payload.check 있음 → 판정표(통과/미통과) — 하나라도 미통과면 반려(«미완»). 통과면 next_step=lb_deliver 와 사람 확인 항목(9·10) 안내.
 *
 * 항목 (작업규칙 완성 보고 1~14 · 여기서 재는 것)
 *   1 _synccheck 3단계 — lb_render 가 이미 판정 · 2 길이 규격 — 경고만(사장님 확인 대기) · 3 매트(위 0~449 · 아래 1470~1919, 좌우 40px 띠로 잰다 — 로고·글자 피함)
 *   4 헤드라인 2줄·각 10자 · 5 효과자막 y 520~1140 · 6 글꼴 폴백 없음 · 7 1080×1920 · 8 captions_서버원본.ass 지문 = 서버가 만든 값(ass_fp)
 *   11 마스터 효과(prproj) · 12 클립 끝(prproj) · 13 대사빠짐검사(srt원본 있을 때) · 14 자막말머리맞춤 재기 — 9(마무리 프레임 인물)·10(소리 내어 읽기)은 사람 몫
 */
import { base, reject } from "../../response.js";
import type { StepHandler } from "../types.js";
import { CARRY_KEYS, RUNNER_DIR, join, readCarry, spec, str } from "./lib.js";

/** FNV-1a 64bit 지문 (BigInt) — 서버(lb_blocks C)와 러너(python) 가 같은 식으로 센다. 완성검사 8 «ass 가 서버 값과 같은가» */
export function fnv1a64(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let h = 0xcbf29ce484222325n;
  const P = 0x100000001b3n, M = 0xffffffffffffffffn;
  for (const b of bytes) { h ^= BigInt(b); h = (h * P) & M; }
  return h.toString(16).padStart(16, "0");
}
export const FNV_PY = "import sys;h=0xcbf29ce484222325\nfor b in open(sys.argv[1],'rb').read(): h=((h^b)*0x100000001b3)&0xffffffffffffffff\nprint('%016x'%h)";

const RC_WRAP = "import subprocess,sys;r=subprocess.run([sys.executable]+sys.argv[1:],capture_output=True,text=True,encoding='utf-8',errors='replace');print(r.stdout[-300:]);print('확인만 rc=%d'%r.returncode)";
const n1 = (s: string, re: RegExp): number | null => { const m = s.match(re); return m ? Number(m[1]) : null; };

const CHECK_PY = `import json,subprocess,re,sys,io
mp4,ass,fp_want=sys.argv[1],sys.argv[2],sys.argv[3]
out={}
r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-show_entries','format=duration','-of','json',mp4],capture_output=True,text=True)
j=json.loads(r.stdout or '{}');s=(j.get('streams') or [{}])[0];out['w']=s.get('width');out['h']=s.get('height');out['dur']=float(j.get('format',{}).get('duration',0) or 0)
r=subprocess.run(['ffmpeg','-hide_banner','-nostats','-i',mp4,'-af','ebur128=peak=true','-f','null','-'],capture_output=True,text=True)
m=re.search(r'I:\\s*(-?[\\d.]+) LUFS',r.stderr);out['lufs']=float(m.group(1)) if m else None
m=re.search(r'Peak:\\s*(-?[\\d.]+) dBFS',r.stderr);out['peak']=float(m.group(1)) if m else None
h=0xcbf29ce484222325
for b in open(ass.replace('captions_'+sys.argv[4]+'.ass','captions_서버원본.ass'),'rb').read(): h=((h^b)*0x100000001b3)&0xffffffffffffffff
out['fp']='%016x'%h;out['fp_want']=fp_want
try:
    import numpy as np
    from PIL import Image
    t=max(0.5,min(20.0,out['dur']-1.0))
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',mp4,'-frames:v','1','_검사20s.png'],check=True)
    im=np.array(Image.open('_검사20s.png').convert('L')).astype(int)
    band=lambda a:float(np.concatenate([a[:,0:40],a[:,-40:]],axis=1).mean())
    out['matte']={'top_side':band(im[0:450]),'bottom_side':band(im[1470:1920]),'top_all':float(im[0:450].mean()),'bottom_all':float(im[1470:1920].mean()),'mid':float(im[450:1470].mean()),'at':t}
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(max(0,out['dur']-1.0)),'-i',mp4,'-frames:v','1','_검사끝.png'],check=True);out['end_png']='_검사끝.png'
except Exception as e:
    out['matte']=None;out['matte_err']=str(e)
fx=[];hl=[];read=[]
for L in io.open(ass,encoding='utf-8'):
    if not L.startswith('Dialogue:'): continue
    p=L.split(',',9);st=p[3];txt=re.sub(r'\\{[^}]*\\}','',p[9]).strip()
    if st=='effect_float':
        m=re.search(r'\\\\pos\\(([\\d.]+),([\\d.]+)\\)',p[9]);mv=re.search(r'\\\\move\\(([\\d.]+),([\\d.]+),([\\d.]+),([\\d.]+)',p[9])
        ys=[int(float(m.group(2)))] if m else ([int(float(mv.group(2))),int(float(mv.group(4)))] if mv else [])
        fx.append({'y':ys,'t':txt})
    if st in ('headline_l1','headline_l2'): hl.append(txt)
    if st in ('band_narr','band_dlg','effect_float'): read.append(st[5:9] if st.startswith('band') else 'fx')
    if st in ('band_narr','band_dlg','effect_float'): read[-1]=read[-1]+' '+txt
out['fx']=fx;out['headline']=hl;out['read']=read
print(json.dumps(out,ensure_ascii=False))`;

export const lbCheck: StepHandler = {
  name: "lb_check",
  run({ preset, payload }) {
    const carry = readCarry(payload);
    const source = payload.source as { path?: string; title?: string } | undefined;
    if (!carry || !source?.path) {
      return reject("lb_check", preset, "payload 에 carry 값(source·workdir·ep·start_s·end_s)이 없다", "lb_render 응답의 carry 값을 payload 에 그대로 실어 lb_check 를 다시 부르라.");
    }
    const repo = str(payload, "repo");
    if (!repo) return reject("lb_check", preset, "payload.repo 가 없다", "carry 의 repo 를 실어 다시 부르라.");
    const title = str(payload, "title") || (typeof source.title === "string" && source.title.trim()) || "린박스";
    const final = str(payload, "final") || join(carry.ep_dir, `${title}_${carry.ep}_숏폼.mp4`);
    const prproj = str(payload, "prproj") || join(carry.ep_dir, `${title}_${carry.ep}.prproj`);
    const ass = str(payload, "ass") || join(carry.ep_dir, `captions_${title}.ass`);
    const assFp = str(payload, "ass_fp");
    const tool = (name: string) => join(repo, RUNNER_DIR, "도구", name);
    const common = {
      source, workdir: carry.workdir, ep: carry.ep, ep_dir: carry.ep_dir, start_s: carry.start_s, end_s: carry.end_s,
      repo, probe_summary: payload.probe_summary, 편정보: payload.편정보, authored: payload.authored, srt_pick: payload.srt_pick ?? null, title, ass, ass_logo: payload.ass_logo ?? null, ass_fp: assFp || null,
      xml: payload.xml ?? null, master: payload.master ?? source.path, prproj, final,
    };
    const carryKeys = [...CARRY_KEYS, "repo", "probe_summary", "편정보", "authored", "srt_pick", "title", "ass", "ass_logo", "ass_fp", "xml", "master", "prproj", "final"];
    const L = (k: string) => String(payload[k] ?? "");

    // ── ② 판정표 ────────────────────────────────────────────────────────
    if (payload.check !== undefined) {
      const c = (typeof payload.check === "object" && payload.check !== null ? payload.check : {}) as Record<string, unknown>;
      const rows: { no: number; item: string; ok: boolean | null; got: string }[] = [];
      const target = (spec as unknown as { edit?: { target_sec?: [number, number] } }).edit?.target_sec ?? [40, 60];
      const dur = typeof c.dur === "number" ? c.dur : null;
      rows.push({ no: 1, item: "_synccheck 3단계", ok: true, got: "lb_render 에서 「싱크 검사 통과」" });
      rows.push({ no: 2, item: `길이 규격 ${target[0]}~${target[1]}초(경고만 · 사장님 확인 대기)`, ok: dur === null ? null : (dur >= target[0] && dur <= target[1]) || null, got: `${dur ?? "?"}초` });
      const matte = c.matte as { top_side?: number; bottom_side?: number; mid?: number; at?: number } | null | undefined;
      rows.push({ no: 3, item: "상단 매트(0~449)·하단 매트(1470~1919) — 좌우 40px 띠 평균 < 40", ok: matte ? (matte.top_side ?? 999) < 40 && (matte.bottom_side ?? 999) < 40 : false, got: matte ? `위 ${matte.top_side?.toFixed(1)} · 아래 ${matte.bottom_side?.toFixed(1)} · 창 ${matte.mid?.toFixed(1)} (${matte.at}초 프레임)` : `프레임을 못 뽑았다 ${String(c.matte_err ?? "")}` });
      const hl = Array.isArray(c.headline) ? (c.headline as unknown[]).map(String) : [];
      const hlOk = hl.length === 2 && hl.every((x) => x.length <= 10 && !/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u.test(x));
      rows.push({ no: 4, item: "헤드라인 2줄 · 각 10자 · 이모지 없음", ok: hlOk, got: hl.join(" / ") || "없음" });
      const fx = Array.isArray(c.fx) ? (c.fx as { y?: number[]; t?: string }[]) : [];
      const fxBad = fx.filter((f) => !(f.y ?? []).every((y) => y >= 520 && y <= 1140));
      rows.push({ no: 5, item: "효과자막 y 520~1140", ok: fxBad.length === 0, got: fxBad.length ? fxBad.map((f) => `${f.t} y${(f.y ?? []).join("→")}`).join(" · ") : `${fx.length}장 전부 안전대` });
      const font = L("font_log");
      const fb = n1(font, /폴백으로 그려지는 글꼴 (\d+)개/);
      rows.push({ no: 6, item: "글꼴 폴백 없음", ok: fb === null ? /✔ 제 글꼴/.test(font) && !/★폴백이다/.test(font) : fb === 0, got: fb === null ? (font.split("\n").filter((l) => /★|✔/.test(l)).slice(0, 4).map((l) => l.trim()).join(" | ") || "로그 없음") : `폴백 ${fb}개` });
      rows.push({ no: 7, item: "1080×1920", ok: c.w === 1080 && c.h === 1920, got: `${c.w}×${c.h}` });
      const fp = String(c.fp ?? ""), want = assFp || String(c.fp_want ?? "");
      rows.push({ no: 8, item: "captions_서버원본.ass 지문 = 서버 값", ok: want ? fp === want : null, got: want ? `${fp.slice(0, 8)} vs ${want.slice(0, 8)}` : "서버 지문(ass_fp) 없음 — 옛 편이면 건너뜀" });
      rows.push({ no: 11, item: "마스터 트랙 멀티밴드 «브로드캐스트» + 선택적 제한 −3dB", ok: n1(L("master_check_log"), /확인만 rc=(\d+)/) === 0, got: `확인만 rc=${n1(L("master_check_log"), /확인만 rc=(\d+)/) ?? "?"}` });
      rows.push({ no: 12, item: "제목·자막·소리 클립이 영상 끝을 안 넘는다", ok: n1(L("end_check_log"), /확인만 rc=(\d+)/) === 0, got: L("end_check_log").split("\n").find((l) => /영상 끝/.test(l))?.trim() ?? `rc=${n1(L("end_check_log"), /확인만 rc=(\d+)/) ?? "?"}` });
      const miss = L("missing_log");
      rows.push({ no: 13, item: "SRT 정답 — 대사빠짐검사 0(srt원본 있을 때)", ok: !/✗|막힘 \d+건/.test(miss), got: /건너뛴다/.test(miss) ? "srt원본 없음 — 건너뜀(경고)" : (/어긋난 자리 없음/.test(miss) ? "어긋난 자리 없음" : miss.split("\n").filter((l) => l.includes("✗")).slice(0, 3).map((l) => l.trim()).join(" | ")) });
      const head = L("head_log");
      rows.push({ no: 14, item: "자막이 말보다 먼저 안 뜬다(자막말머리맞춤 재기)", ok: !/✗/.test(head), got: /어긋난 카드 없음/.test(head) ? "어긋난 카드 없음" : head.split("\n").filter((l) => l.includes("✗")).slice(0, 3).map((l) => l.trim()).join(" | ") || "로그 없음" });
      const lufs = typeof c.lufs === "number" ? c.lufs : null, peak = typeof c.peak === "number" ? c.peak : null;
      const peakMax = (spec as unknown as { audio?: { final_peak_db_max?: number } }).audio?.final_peak_db_max ?? -3.0;
      rows.push({ no: 15, item: `완성본 소리 — 피크 ≤ ${peakMax} dB(완료표시 관문) · I 참고`, ok: peak === null ? null : peak <= peakMax + 0.05, got: `I ${lufs ?? "?"} LUFS · Peak ${peak ?? "?"} dBFS` });
      const fails = rows.filter((r) => r.ok === false);
      const table = rows.map((r) => `${r.ok === false ? "✗" : r.ok === null ? "△" : "✓"} ${r.no}. ${r.item} — ${r.got}`);
      if (fails.length) {
        return reject("lb_check", preset, `완성 검사 미통과 ${fails.length}건 — «미완»`, table.join(" ‖ ") + " ‖ 미통과 항목을 고친 뒤 그 단계(lb_subs·lb_prproj·lb_render)부터 다시 태우고 lb_check 를 다시 부르라.");
      }
      const human = ["9. 마무리 블록 배경에 인물이 있는가 — 편 폴더 _검사끝.png 를 눈으로", "10. 전체 자막을 소리 내어 읽어 오타 확인 — 아래 낭독 전문", "2. 길이가 채널 규격 안인가 — 사장님 확인(신병4 실측이 규격 밖이라 기계로 «미완» 판정 안 함)"];
      return base("lb_check", preset, {
        status: "execute",
        next_step: "lb_deliver",
        message: `완성 검사 기계 항목 전부 통과(${rows.filter((r) => r.ok === true).length}/${rows.length} · △ ${rows.filter((r) => r.ok === null).length} 은 사람 확인). 사람 확인 3개를 본 뒤 lb_deliver 로 — 그 전엔 «완성» 이라 하지 않는다.`,
        instructions: [...table, ...human.map((h) => "사람 확인 " + h), "낭독 전문: " + (Array.isArray(c.read) ? (c.read as string[]).join(" / ") : "").slice(0, 3000), "① 사람 확인이 끝나면 carry 를 그대로 실어 lb_deliver 를 부른다(payload.human_ok: true)."],
        then_call_with: ["step: 'lb_deliver'", "payload: { …carry, human_ok: true }"],
        jobs_kind: null, jobs: [], measure: [],
        metrics: { passed: rows.filter((r) => r.ok === true).length, pending: rows.filter((r) => r.ok === null).length, final_s: dur, lufs, peak },
        carry: carryKeys,
        ...common,
        check_table: table,
      });
    }

    // ── ① 검사 지시 ─────────────────────────────────────────────────────
    const fonts = join(carry.ep_dir, "fonts");
    return base("lb_check", preset, {
      status: "execute",
      next_step: "lb_check",
      message: `완성 검사 기계 항목을 잰다(작업규칙 「완성 보고」 · 완성검사.sh 검사부) — ${final} · ${prproj}. 로그를 실어 다시 부르라.`,
      instructions: [
        `① jobs 는 편 폴더 ${carry.ep_dir} 를 cwd 로. check 가 해상도·길이·ebur128·매트 프레임(_검사20s.png)·마무리 프레임(_검사끝.png)·효과자막 y·헤드라인·낭독 전문·captions_서버원본.ass 지문을 JSON 하나로 낸다.`,
        "② 글꼴폴백검사(완성검사 6) · 마스터효과심기 --확인만(11) · 제목끝맞춤 --확인만(12) · 대사빠짐검사(13) · 자막말머리맞춤 재기(14) 는 rc·로그로.",
        "③ measure 대로 payload.check(JSON)·font_log·master_check_log·end_check_log·missing_log·head_log 를 실어 lb_check 를 **다시** 부른다 — 서버가 표로 판정한다.",
      ],
      then_call_with: ["step: 'lb_check'", "payload: { …carry, check: <JSON>, font_log, master_check_log, end_check_log, missing_log, head_log }"],
      jobs_kind: "argv",
      jobs_cwd: carry.ep_dir,
      jobs: [
        { name: "check", argv: ["python", "-c", CHECK_PY, final, ass, assFp || "", title], out: join(carry.ep_dir, "_check.json"), note: "완성검사 2·3·4·5·7·8·15 + 9(마무리 프레임)·10(낭독 전문) 재료 → JSON." },
        { name: "font", argv: ["python", tool("글꼴폴백검사.py"), ass, fonts], optional: true, note: "완성검사 6 — libass 잉크 대조로 폴백 글꼴을 찾는다. 「★ 폴백으로 그려지는 글꼴 N개」 면 rc 1." },
        { name: "master_check", argv: ["python", "-c", RC_WRAP, tool("마스터효과심기.py"), prproj, "--확인만"], optional: true, note: "완성검사 11." },
        { name: "end_check", argv: ["python", "-c", RC_WRAP, tool("제목끝맞춤.py"), prproj, "--확인만"], optional: true, note: "완성검사 12." },
        { name: "dlg_missing", argv: ["python", tool("대사빠짐검사.py")], optional: true, note: "완성검사 13(§94) — srt원본 없으면 건너뜀." },
        { name: "head_check", argv: ["python", tool("자막말머리맞춤.py")], optional: true, note: "완성검사 14(§93) — 재기만 · ✗ 면 rc 1." },
      ],
      measure: [
        { as: "check", from: "job:check", unit: "json_stdout" }, { as: "font_log", from: "job:font", unit: "stdout" }, { as: "master_check_log", from: "job:master_check", unit: "stdout" },
        { as: "end_check_log", from: "job:end_check", unit: "stdout" }, { as: "missing_log", from: "job:dlg_missing", unit: "stdout" }, { as: "head_log", from: "job:head_check", unit: "stdout" },
      ],
      metrics: { final, prproj, ass_fp: assFp || null },
      carry: carryKeys,
      ...common,
    });
  },
};
