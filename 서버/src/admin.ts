/**
 * admin.ts — 사장님 관리 페이지(길 B · 설계 「사장님 관리 (b) 관리 웹페이지」 · 2026-09-04).
 *
 *   GET  /admin              관리 페이지(HTML · 인라인 JS). 페이지 자체엔 비밀이 없다 — 첫 진입에 관리자 토큰을 물어 sessionStorage 에 둔다.
 *   *    /admin/api/<명령>    대장(LICENSES KV) 조작 JSON. **관리자 전용 인증** — Authorization: Bearer <ADMIN_TOKEN>(wrangler secret).
 *                            지인 대장 토큰으로는 절대 안 열린다(대장 검사와 다른 경로 · 다른 비밀).
 *
 * 키 보호 규칙
 *   · 발급 토큰 값은 «발급» 응답에 한 번만 실린다. 목록·다른 응답·로그엔 안 실린다 — 줄은 id = sha256(토큰) 앞 16자로 가리킨다.
 *   · ADMIN_TOKEN 은 비교만 하고 어디에도 안 적는다. 비교는 길이+값 상수시간.
 *
 * 명령(대장.js 와 같은 뜻 · 워커 안에서 env.LICENSES 직접)
 *   GET  list                      목록 [{id, email, issued, expires, devices, maxDevices, blocked, presets}]
 *   POST issue   {email, days, maxDevices, presets[]}   → {token(1회), license}
 *   POST block | unblock | extend{days} | reset_devices | preset_add{preset} | preset_remove{preset} | revoke   — 전부 {id}
 */
import { DEVICE_CAP, newLicense, type License } from "./auth.js";
import { STYLES } from "./styles.js";

export interface AdminEnv {
  ADMIN_TOKEN?: string;
  LICENSES?: KVNamespace;
}

const PRESETS = Object.keys(STYLES);

function json(data: unknown, status = 200): Response {
  return Response.json(data, { status, headers: { "cache-control": "no-store" } });
}

/** 상수시간 비교 — 길이가 다르면 바로 false 지만 값 비교는 끝까지 돈다 */
export function tokenEq(a: string, b: string): boolean {
  if (a.length !== b.length || !a.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

async function sha16(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

interface Row { id: string; email: string; issued: string; expires: string; devices: number; maxDevices: number; blocked: boolean; presets: string[] }

async function allRows(kv: KVNamespace): Promise<{ key: string; lic: License; id: string }[]> {
  const out: { key: string; lic: License; id: string }[] = [];
  let cursor: string | undefined;
  do {
    const page = await kv.list({ cursor, limit: 1000 });
    for (const k of page.keys) {
      const lic = await kv.get<License>(k.name, "json");
      if (lic && typeof lic.email === "string") out.push({ key: k.name, lic, id: await sha16(k.name) });
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  out.sort((a, b) => a.lic.email.localeCompare(b.lic.email) || a.lic.expires.localeCompare(b.lic.expires));
  return out;
}

const row = (r: { id: string; lic: License }): Row => ({
  id: r.id, email: r.lic.email, issued: r.lic.issued, expires: r.lic.expires,
  devices: r.lic.devices.length, maxDevices: r.lic.maxDevices, blocked: r.lic.blocked, presets: Array.isArray(r.lic.presets) ? r.lic.presets : [],
});

const ymd = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export async function handleAdmin(request: Request, env: AdminEnv, url: URL): Promise<Response> {
  if (url.pathname === "/admin" || url.pathname === "/admin/") {
    if (request.method !== "GET") return json({ error: "GET 만" }, 405);
    return new Response(ADMIN_HTML, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "x-frame-options": "DENY", "referrer-policy": "no-referrer" } });
  }
  if (!url.pathname.startsWith("/admin/api/")) return json({ error: "없는 경로" }, 404);
  // ── 관리자 인증 — 대장 토큰과 무관한 별도 비밀 ──
  const want = (env.ADMIN_TOKEN ?? "").trim();
  if (!want) return json({ error: "관리자 토큰이 설정돼 있지 않다 — wrangler secret put ADMIN_TOKEN (설계 「사장님 관리」)" }, 503);
  const got = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "").trim();
  if (!tokenEq(got, want)) return json({ error: "관리자 인증 실패" }, 401);
  const kv = env.LICENSES;
  if (!kv) return json({ error: "발급 대장(LICENSES KV)이 이 서버에 없다 — 로컬 dev 는 KV 없이 뜬다" }, 503);
  const cmd = url.pathname.slice("/admin/api/".length);

  if (cmd === "list") {
    if (request.method !== "GET") return json({ error: "GET 만" }, 405);
    const rows = (await allRows(kv)).map(row);
    return json({ rows, presets: PRESETS, today: ymd(Date.now()) });
  }
  if (request.method !== "POST") return json({ error: "POST 만" }, 405);
  let body: Record<string, unknown> = {};
  try { body = (await request.json()) as Record<string, unknown>; } catch { body = {}; }

  if (cmd === "issue") {
    const email = String(body.email ?? "").trim();
    const days = Math.max(1, Math.min(3650, Number(body.days ?? 90) || 90));
    const maxDevices = Math.max(1, Math.min(DEVICE_CAP, Number(body.maxDevices ?? 2) || 2));
    const presets = (Array.isArray(body.presets) ? body.presets : []).map((p) => String(p).trim()).filter((p) => PRESETS.includes(p));
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: "이메일이 비었거나 꼴이 아니다" }, 400);
    if (!presets.length) return json({ error: `허용프리셋을 하나 이상 골라라(${PRESETS.join("·")}) — 기본이 전부 거부라 없으면 setup 부터 막힌다` }, 400);
    const token = b64url(crypto.getRandomValues(new Uint8Array(32)));
    const lic = newLicense(email, days, maxDevices, Date.now(), presets);
    await kv.put(token, JSON.stringify(lic));
    // ★토큰 값은 여기서 한 번만 나간다. 로그·목록엔 안 싣는다.
    return json({ token, license: { ...row({ id: await sha16(token), lic }) } });
  }

  const id = String(body.id ?? "").trim();
  if (!/^[0-9a-f]{16}$/.test(id)) return json({ error: "id(대장 줄 식별자 16자)가 없다" }, 400);
  const hit = (await allRows(kv)).find((r) => r.id === id);
  if (!hit) return json({ error: "그 id 의 대장 줄이 없다 — 목록을 다시 받아라" }, 404);
  const lic = { ...hit.lic, presets: Array.isArray(hit.lic.presets) ? [...hit.lic.presets] : [] };
  let note = "";
  switch (cmd) {
    case "block": lic.blocked = true; note = "차단"; break;
    case "unblock": lic.blocked = false; note = "차단 해제"; break;
    case "extend": {
      const days = Math.max(1, Math.min(3650, Number(body.days ?? 0) || 0));
      if (!days) return json({ error: "연장 일수(days)가 없다" }, 400);
      lic.expires = ymd(Date.now() + days * 86400000); note = `만료 ${lic.expires}`; break;
    }
    case "reset_devices": lic.devices = []; note = "기기 초기화(0대)"; break;
    case "max_devices": {
      const n = Math.max(1, Math.min(DEVICE_CAP, Number(body.maxDevices ?? 0) || 0));
      if (!n) return json({ error: "대수(maxDevices)가 없다" }, 400);
      lic.maxDevices = n; note = `허용 ${n}대`; break;
    }
    case "preset_add": case "preset_remove": {
      const p = String(body.preset ?? "").trim();
      if (!PRESETS.includes(p)) return json({ error: `프리셋 이름이 아니다(${PRESETS.join("·")})` }, 400);
      const set = new Set(lic.presets);
      if (cmd === "preset_add") set.add(p); else set.delete(p);
      lic.presets = [...set]; note = `허용프리셋 ${lic.presets.join("·") || "없음(전부 거부)"}`; break;
    }
    case "revoke":
      await kv.delete(hit.key);
      return json({ ok: true, note: `${hit.lic.email} 폐기` });
    default:
      return json({ error: `모르는 명령: ${cmd}` }, 404);
  }
  await kv.put(hit.key, JSON.stringify(lic));
  return json({ ok: true, note: `${lic.email} → ${note}`, row: row({ id, lic }) });
}

/** 관리 페이지 — 표·버튼 위주. 토큰은 sessionStorage(탭 닫으면 사라짐). */
const ADMIN_HTML = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>유스튜디오 발급 대장</title>
<style>
  :root{color-scheme:light}body{margin:0;background:#f6f6f4;color:#222;font:14px/1.5 -apple-system,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
  main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:18px;margin:0 0 4px}.sub{color:#666;margin:0 0 20px}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #ddd}th,td{padding:8px 10px;border-bottom:1px solid #eee;text-align:left;vertical-align:top;font-size:13px}th{background:#fafaf8;font-weight:600}
  tr.blocked td{color:#999}tr.expired td.exp{color:#b00;font-weight:600}
  button{font:inherit;font-size:12px;padding:4px 9px;border:1px solid #bbb;border-radius:6px;background:#fff;cursor:pointer;margin:2px 2px 2px 0}button:hover{background:#f0f0ee}button.danger{border-color:#d33;color:#b00}button.primary{background:#222;color:#fff;border-color:#222}
  form.issue{background:#fff;border:1px solid #ddd;padding:14px;margin:20px 0;display:flex;flex-wrap:wrap;gap:10px;align-items:end}form.issue label{display:flex;flex-direction:column;font-size:12px;color:#555}form.issue input[type=text],form.issue input[type=number]{font:inherit;padding:6px 8px;border:1px solid #bbb;border-radius:6px;min-width:200px}
  .chips label{display:inline-flex;align-items:center;gap:4px;margin-right:10px;font-size:13px;color:#222}
  #token{display:none;background:#fff8e1;border:2px solid #e0a800;padding:14px;margin:16px 0;word-break:break-all}#token code{font-size:15px;display:block;margin:8px 0}
  #msg{min-height:20px;color:#444;margin:8px 0}#msg.err{color:#b00}
  .id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#888}
  #login{background:#fff;border:1px solid #ddd;padding:16px;max-width:520px}#login input{font:inherit;padding:6px 8px;border:1px solid #bbb;border-radius:6px;width:100%;box-sizing:border-box}
</style></head><body><main>
<h1>유스튜디오 발급 대장</h1><p class="sub">이메일 허가제 — 발급·차단·연장·기기·프리셋·폐기. 관리자만. 토큰 값은 발급 때 한 번만 보인다.</p>
<div id="login"><label>관리자 토큰 (ADMIN_TOKEN)<br><input id="tok" type="password" autocomplete="off" placeholder="wrangler secret put ADMIN_TOKEN 으로 넣은 값"></label><div style="margin-top:8px"><button class="primary" id="enter">들어가기</button> <span style="color:#777;font-size:12px">이 탭에만 저장(sessionStorage) · 탭 닫으면 사라짐</span></div></div>
<div id="app" hidden>
<form class="issue" id="issue">
  <label>이메일<input type="text" name="email" required placeholder="friend@example.com"></label>
  <label>기간(일)<input type="number" name="days" value="90" min="1" max="3650"></label>
  <label>기기 대수<input type="number" name="maxDevices" value="2" min="1" max="50"></label>
  <div class="chips" id="chips"></div>
  <button class="primary" type="submit">발급</button>
</form>
<div id="token"><b>발급됐다 — 이 토큰은 지금 한 번만 보인다. 지인에게 전달하고 창을 닫아라.</b><code id="tokval"></code><button id="copy">복사</button> <span id="tokwho"></span></div>
<div id="msg"></div>
<table><thead><tr><th>이메일</th><th>발급</th><th>만료</th><th>기기</th><th>대수</th><th>차단</th><th>허용프리셋</th><th>id</th><th>조작</th></tr></thead><tbody id="rows"></tbody></table>
<p style="color:#777;font-size:12px;margin-top:12px">지인 설치: <code>bash 설치/한방설치.sh &lt;토큰&gt;</code> (맥) · <code>powershell -ExecutionPolicy Bypass -File 설치\\한방설치.ps1 &lt;토큰&gt;</code> (윈도우)</p>
</div>
<script>
(function(){
  var KEY='youstudio_admin';var tok=sessionStorage.getItem(KEY)||'';var presets=[];
  var $=function(s){return document.querySelector(s)};
  function msg(t,err){var m=$('#msg');m.textContent=t||'';m.className=err?'err':''}
  function api(cmd,body,method){return fetch('/admin/api/'+cmd,{method:method||(body?'POST':'GET'),headers:{'authorization':'Bearer '+tok,'content-type':'application/json'},body:body?JSON.stringify(body):undefined}).then(function(r){return r.json().then(function(j){if(!r.ok){throw new Error(j.error||('HTTP '+r.status))}return j})})}
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function render(d){presets=d.presets;$('#chips').innerHTML=presets.map(function(p){return '<label><input type="checkbox" name="presets" value="'+esc(p)+'"'+(p==='린박스'?' checked':'')+'>'+esc(p)+'</label>'}).join('');
    var tb=$('#rows');tb.innerHTML='';d.rows.forEach(function(r){var tr=document.createElement('tr');tr.className=(r.blocked?'blocked ':'')+(r.expires<d.today?'expired':'');
      var ps=presets.map(function(p){var has=r.presets.indexOf(p)!==-1;return '<button data-cmd="'+(has?'preset_remove':'preset_add')+'" data-preset="'+esc(p)+'" title="'+(has?'빼기':'넣기')+'">'+(has?'✔ ':'＋ ')+esc(p)+'</button>'}).join('');
      tr.innerHTML='<td>'+esc(r.email)+'</td><td>'+esc(r.issued)+'</td><td class="exp">'+esc(r.expires)+'</td><td>'+r.devices+'</td><td>'+r.maxDevices+'</td><td>'+(r.blocked?'★차단':'-')+'</td><td>'+ps+'</td><td class="id">'+esc(r.id)+'</td>'+
        '<td><button data-cmd="'+(r.blocked?'unblock':'block')+'"'+(r.blocked?'':' class="danger"')+'>'+(r.blocked?'풀기':'막기')+'</button><button data-cmd="extend">연장 90일</button><button data-cmd="reset_devices">기기 초기화</button><button data-cmd="max_devices">대수…</button><button data-cmd="revoke" class="danger">폐기</button></td>';
      tr.querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){act(r,b.dataset.cmd,b.dataset.preset)})});tb.appendChild(tr)});
    if(!d.rows.length){tb.innerHTML='<tr><td colspan="9" style="color:#777">대장이 비어 있다 — 위에서 발급한다</td></tr>'}}
  function load(){return api('list').then(function(d){$('#login').hidden=true;$('#app').hidden=false;render(d);msg('')}).catch(function(e){sessionStorage.removeItem(KEY);tok='';$('#login').hidden=false;$('#app').hidden=true;msg(e.message,true)})}
  function act(r,cmd,preset){var body={id:r.id};
    if(cmd==='extend'){body.days=90}
    if(cmd==='max_devices'){var n=prompt('허용 기기 대수(1~50)',r.maxDevices);if(!n)return;body.maxDevices=Number(n)}
    if(cmd==='preset_add'||cmd==='preset_remove'){body.preset=preset}
    if(cmd==='revoke'&&!confirm(r.email+' 대장 줄을 폐기한다 — 그 토큰은 바로 못 쓰게 된다. 계속?'))return;
    if(cmd==='block'&&!confirm(r.email+' 을 차단한다. 계속?'))return;
    api(cmd,body).then(function(j){msg(j.note||'됐다');return load()}).catch(function(e){msg(e.message,true)})}
  $('#enter').addEventListener('click',function(){tok=$('#tok').value.trim();if(!tok)return;sessionStorage.setItem(KEY,tok);$('#tok').value='';load()});
  $('#tok').addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();$('#enter').click()}});
  $('#issue').addEventListener('submit',function(e){e.preventDefault();var f=e.target;var ps=[].slice.call(f.querySelectorAll('input[name=presets]:checked')).map(function(x){return x.value});
    api('issue',{email:f.email.value.trim(),days:Number(f.days.value),maxDevices:Number(f.maxDevices.value),presets:ps}).then(function(j){$('#tokval').textContent=j.token;$('#tokwho').textContent=j.license.email+' · 만료 '+j.license.expires+' · '+j.license.presets.join('·');$('#token').style.display='block';f.email.value='';load()}).catch(function(e){msg(e.message,true)})});
  $('#copy').addEventListener('click',function(){navigator.clipboard.writeText($('#tokval').textContent).then(function(){msg('토큰을 복사했다')})});
  if(tok)load();
})();
</script></main></body></html>`;
