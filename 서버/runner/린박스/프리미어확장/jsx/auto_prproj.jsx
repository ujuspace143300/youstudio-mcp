/*  Volcano - queued FCP7 XML  ->  .prproj, no dialogs.  ASCII identifiers only.
 *
 *  2026-08-25 measured on Premiere 2026 (26.0.2):
 *    app.openDocument(<fcp7 xml>) does NOT work from the Home screen -
 *    it returns false, and on a second try it blocks the ExtendScript engine.
 *    What works: make a project first (app.newProject), then importFiles(xml).
 *
 *  2026-09-03 세 판 합침 (제안 20260903_린박스_auto_prproj_jsx_세_판이_갈라짐):
 *    바탕 = 설치본 08-31 (PAUSE 스위치·시퀀스0 재가져오기·MADE 후 닫기·남의 프로젝트면
 *    저장하고 진행·가져오기 미완이면 다음 판·ASCII 식별자)
 *    + 볼트 09-02 (mergeQueue 대기줄 합치기 · newProject 거부 시 껍데기 청소)
 */
(function () {
    // ★사용자 자리를 **박아 두지 마라** — 다른 컴퓨터에서 엉뚱한 곳을 짚는다 (2026-08-25).
    //   못 알아내면 아무것도 안 하고 나간다. 조용히 틀린 자리에 쓰는 것보다 낫다.
    var BS = String.fromCharCode(92);
    var HOME = '';
    try { HOME = String(Folder('~').fsName).split(BS).join('/'); } catch (e) {}
    if (!HOME) { try { HOME = String($.getenv('USERPROFILE')).split(BS).join('/'); } catch (e0) {} }
    if (!HOME) { return; }
    var LOG = File(HOME + '/.volcano/prproj_log.txt');
    var QUEUE = File(HOME + '/.volcano/prproj_queue.txt');

    function note(msg) {
        try {
            LOG.encoding = 'UTF-8';
            LOG.open('a');
            LOG.writeln('[' + new Date().toString() + '] ' + msg);
            LOG.close();
        } catch (e) {}
    }

    // ── 대기줄 읽기·합치기·다시 쓰기 ─────────────────────────────────────────
    //   ★2026-09-02 사장님 지시 — 회차 시작 때 읽은 줄(snapshot)로 일하고, 끝에 «남은 것»만
    //   덮어쓰면 그 사이(프리미어가 몇 분 일하는 동안) 다른 터미널이 보탠 줄이 **조용히** 사라졌다.
    //   그래서 다시 쓰기 직전에 파일을 한 번 더 읽어, snapshot 에 없던 새 줄은 살려 둔다.
    //   (ExtendScript 는 ES3 — Array.indexOf 가 없어 has() 로 돈다. 합치는 계산은 mergeQueue 에만
    //    두고 파일은 안 만진다 → node 로 시험한다: 키트/도구/대기줄합치기_시험.js)
    function trimS(s) { return String(s).replace(/^\s+|\s+$/g, ''); }
    function has(arr, s) {
        for (var h = 0; h < arr.length; h += 1) { if (arr[h] === s) { return true; } }
        return false;
    }
    function readQueue() {
        var arr = [];
        if (!QUEUE.exists) { return arr; }
        QUEUE.encoding = 'UTF-8';
        QUEUE.open('r');
        while (!QUEUE.eof) {
            var ln = trimS(QUEUE.readln());
            if (ln !== '') { arr.push(ln); }
        }
        QUEUE.close();
        return arr;
    }
    // keep: 이번 회차가 못 만들어 남기는 줄 · snapshot: 회차 시작 때 읽은 줄 · now: 지금 파일에 있는 줄
    // → keep 전부 + (now 중 snapshot 에 없던 새 줄). 중복은 하나로.
    function mergeQueue(keep, snapshot, now) {
        var out = [], m;
        for (m = 0; m < keep.length; m += 1) {
            var k = trimS(keep[m]);
            if (k !== '' && !has(out, k)) { out.push(k); }
        }
        for (m = 0; m < now.length; m += 1) {
            var n = trimS(now[m]);
            if (n !== '' && !has(snapshot, n) && !has(out, n)) { out.push(n); }
        }
        return out;
    }
    function rewriteQueue(keep, snapshot) {
        var now = [];
        try { now = readQueue(); } catch (eRR) { note('queue re-read failed: ' + eRR); }
        var out = mergeQueue(keep, snapshot, now);
        var fresh = out.length - keep.length;
        try {
            QUEUE.encoding = 'UTF-8';
            QUEUE.open('w');
            for (var w = 0; w < out.length; w += 1) { QUEUE.writeln(out[w]); }
            QUEUE.close();
        } catch (eWQ) { note('queue rewrite failed: ' + eWQ); }
        if (fresh > 0) { note('queue kept ' + fresh + ' line(s) added while working'); }
        return out.length;
    }

    // ★멈춤 스위치 (2026-08-26).
    //   사람이 프리미어에서 프로젝트를 여는 **도중**에 이 순환이 걸리면,
    //   아직 app.project.path 가 안 잡혀서 «열린 것이 없다» 고 보고 newProject 를
    //   해 버린다 — 사장님 눈에는 «파일을 여는데 자꾸 저절로 꺼진다» 로 보인다.
    //   ~/.volcano/멈춤.txt 가 있으면 아무것도 하지 않는다. 지우면 다시 돈다.
    try {
        if (File(HOME + '/.volcano/PAUSE.txt').exists) {
            // ★조용히 나가면 «어제부터 자동으로 안 뽑힌다» 가 된다 (2026-08-27).
            //   실제로 그랬다 — 18:03에 켜진 멈춤이 다음 날까지 남아 있었는데
            //   로그가 한 줄도 안 남아, 프리미어가 멎은 줄 알고 세 번을 껐다 켰다.
            //   15초마다 찍으면 시끄러우니 **한 판에 한 번만** 남긴다.
            if (!$.global.__volcano_pause_said) {
                $.global.__volcano_pause_said = true;
                try {
                    LOG.encoding = 'UTF-8'; LOG.open('a');
                    LOG.writeln('[' + new Date().toString()
                                + '] ※멈춤 스위치가 켜져 있다 (~/.volcano/PAUSE.txt) '
                                + '— 지워야 프로젝트를 만든다');
                    LOG.close();
                } catch (eL) {}
            }
            return;
        }
        $.global.__volcano_pause_said = false;
    } catch (eP) {}
    if ($.global.__volcano_busy) { return; }
    if (typeof app === 'undefined') { return; }
    if (!QUEUE.exists) { return; }
    $.global.__volcano_busy = true;

    var lines = [];
    try { lines = readQueue(); }
    catch (e2) { note('queue read failed: ' + e2); $.global.__volcano_busy = false; return; }
    if (!lines.length) { $.global.__volcano_busy = false; return; }   // 조용히 나간다
    note('pass start (' + lines.length + ' queued)');

    var open_path = '';
    try { open_path = String(app.project && app.project.path ? app.project.path : ''); } catch (e3) {}
    function samePath(a, b) {
        var BS2 = String.fromCharCode(92);
        return String(a).split(BS2).join('/').toLowerCase()
            === String(b).split(BS2).join('/').toLowerCase();
    }

    function openSequenceAndSave(out, left, xmlPath) {
        // ★가져오기만 하고 저장하면 시퀀스가 «안 열린 채» 저장된다.
        //   그러면 사장님이 프로젝트를 열었을 때 **타임라인이 비어 보인다.**
        //   (2026-08-25 사장님 지적: «미디어가 올라가있지 않아»)
        var n = 0;
        try { n = app.project.sequences.numSequences; } catch (eQ) {}
        note('sequences in project: ' + n);
        // ★시퀀스가 아직 0 이면 가져오기가 안 끝난 것이다 — 저장하면 «빈 껍데기» 가 된다.
        //   저장하지 말고 다음 판에 다시 본다 (2026-08-26).
        if (n === 0) {
            // ★열려 있는데 시퀀스가 0 이면 «빈 껍데기» 다 — 가져오기가 아예 안 됐다는 뜻이다.
            //   전에는 그냥 다음 판으로 미뤘는데, 아무도 가져오기를 안 하니 **영원히 맴돌았다**
            //   (2026-08-27 실측: 같은 줄이 열 번 넘게 찍혔다). 여기서 한 번 가져온다.
            note('no sequence yet — importing the xml into the open project');
            try {
                var okImp = app.project.importFiles([xmlPath], true,
                                                    app.project.rootItem, false);
                note('importFiles returned ' + okImp);
            } catch (eI) { note('importFiles threw: ' + eI); }
            var n2 = 0;
            try { n2 = app.project.sequences.numSequences; } catch (eQ2) {}
            note('sequences after import: ' + n2);
            if (n2 === 0) {
                left.push(xmlPath);
                return;
            }
            n = n2;
        }
        if (n > 0) {
            try {
                var sq = app.project.sequences[0];
                var okOpen = app.project.openSequence(sq.sequenceID);
                note('openSequence returned ' + okOpen + ' (' + sq.name + ')');
            } catch (eO) { note('openSequence threw: ' + eO); }
        }
        var v = 0, a = 0, k;
        try {
            var seq = app.project.activeSequence;
            if (seq) {
                for (k = 0; k < seq.videoTracks.numTracks; k += 1) { v += seq.videoTracks[k].clips.numItems; }
                for (k = 0; k < seq.audioTracks.numTracks; k += 1) { a += seq.audioTracks[k].clips.numItems; }
            }
        } catch (e6) {}
        // ★자막 SRT 도 프로젝트에 넣는다 (2026-08-25) — 알파 MOV 는 글자를 못 고치므로
        //   같은 시각·같은 문구의 SRT 를 곁들인다. 프리미어에서 캡션으로 글자를 고칠 수 있다.
        //   ※SRT 는 **하나씩** 가져와야 한다(여러 개를 한 번에 주면 안 먹는다 — 실측)
        try {
            var srtDir = Folder(out.replace(/[^\/]+$/, '') + '자막SRT');
            if (srtDir.exists) {
                var srts = srtDir.getFiles('*.srt');
                for (var q = 0; q < srts.length; q += 1) {
                    var kv1 = decodeURI(srts[q].name);
                    var okS = app.project.importFiles([srts[q].fsName], true,
                                                      app.project.rootItem, false);
                    note('SRT 가져오기 ' + kv1 + ' → ' + okS);
                    // ★캡션 트랙으로 **자동으로 얹는다** (2026-08-25)
                    //   app.project.activeSequence.createCaptionTrack(항목, 0)
                    //   for..in 으로는 안 보이는 네이티브 메서드라 «없다» 고 잘못 판정했었다.
                    //   (Cutback 확장이 쓰는 것과 같은 호출이다)
                    var kv2 = null;
                    try {
                        var rt = app.project.rootItem;
                        for (var w = rt.children.numItems - 1; w >= 0; w -= 1) {
                            var kv3 = rt.children[w];
                            var mp = '';
                            try { mp = String(kv3.getMediaPath()); } catch (eM) {}
                            if (mp && mp.toLowerCase() === srts[q].fsName.toLowerCase()) {
                                kv2 = kv3; break;
                            }
                        }
                    } catch (eF) { note('SRT 항목 찾기 오류: ' + eF); }
                    if (kv2) {
                        try {
                            var kv4 = app.project.activeSequence.createCaptionTrack(kv2, 0);
                            note('캡션 트랙 만들기 ' + kv1 + ' → ' + kv4);
                        } catch (eCT) { note('createCaptionTrack 오류: ' + eCT); }
                    } else {
                        note('SRT 항목을 프로젝트에서 못 찾았다: ' + kv1);
                    }
                }
                note('SRT ' + srts.length + '개를 넣고 캡션 트랙까지 만들었다');
            } else {
                note('자막SRT 폴더가 없다: ' + srtDir.fsName);
            }
        } catch (eSrt) { note('SRT 가져오기 오류: ' + eSrt); }

        // 캡션 트랙에 자동으로 올릴 수 있는지 재 본다 (되면 다음 편부터 자동)
        try {
            var sq2 = app.project.activeSequence;
            if (sq2) {
                var kv5 = [];
                for (var kk in sq2) { kv5.push(kk); }
                note('sequence keys: ' + kv5.join(','));
                note('captionTracks = ' + (sq2.captionTracks ?
                     sq2.captionTracks.numTracks : 'none'));
            }
        } catch (eC) { note('캡션 트랙 확인 오류: ' + eC); }

        try { app.project.save(); }
        catch (eS) { note('save failed: ' + eS); left.push(xmlPath); return; }
        note('MADE ' + out + '  (video clips ' + v + ', audio clips ' + a + ')');
        // ★만든 뒤 **바로 닫는다** (2026-08-31). 열린 채 두면 다음 편에서 모달·경합이 생겨
        //   확장이 멎었다(일괄 뽑기 중 7분 멈춤). 저장은 위에서 끝났으니 안 닫을 이유가 없다.
        try { app.project.closeDocument(0, 0); note('closed after MADE'); }
        catch (eCd) { note('closeDocument after MADE failed: ' + eCd); }
    }

    if (open_path !== '' && open_path.toLowerCase().indexOf('.prproj') > -1) {
        // 우리가 만들려던 그 프로젝트가 이미 열려 있으면 — 다시 만들지 말고 **시퀀스만 열어** 저장한다
        var kv6 = false;
        var kv7 = [];
        for (var q = 0; q < lines.length; q += 1) {
            var xp = lines[q].replace(/^\s+|\s+$/g, '');
            var op = xp.replace(/\.xml$/i, '.prproj');
            if (samePath(op, open_path) && File(op).exists) {
                note('that project is already open — opening its sequence and saving');
                openSequenceAndSave(op, kv7, xp);
                kv6 = true;
            } else { kv7.push(xp); }
        }
        if (kv6) {
            rewriteQueue(kv7, lines);
        } else {
            // ★열려 있는 프로젝트가 «우리 것이 아니면» 예전에는 그냥 나갔다 (2026-08-26).
            //   그러면 사람이 프리미어에서 손수 프로젝트를 닫아 줘야 큐가 돈다.
            //   app.newProject() 는 열린 프로젝트를 대신 닫고 새로 만든다 —
            //   잃을 것이 없도록 **먼저 저장해 두고** 그대로 밀고 나간다.
            note('a project is open (' + open_path + ') — saving it and carrying on');
            try { app.project.save(); note('saved the open project'); }
            catch (eSv) { note('save of open project failed: ' + eSv); }
        }
        if (kv6) {
            $.global.__volcano_busy = false;
            return;
        }
        lines = kv7;
        if (!lines.length) { $.global.__volcano_busy = false; return; }
    }

    var left = [];
    for (var i = 0; i < lines.length; i += 1) {
        var xmlPath = lines[i].replace(/^\s+|\s+$/g, '');
        var xml = File(xmlPath);
        if (!xml.exists) { note('missing xml: ' + xmlPath); continue; }
        var out = xmlPath.replace(/\.xml$/i, '.prproj');
        // ★«있다» 가 아니라 «쓸 만한가» 를 본다 — 빈 껍데기(5KB)를 «다 됐다» 로 읽으면
        //   그 편은 영영 안 만들어진다 (2026-08-26).
        if (File(out).exists && File(out).length > 20000) {
            note('already exists: ' + out); continue;
        }
        if (File(out).exists) {
            note('empty shell (' + File(out).length + ' bytes) — remaking: ' + out);
            try { File(out).remove(); } catch (eR) { note('could not remove shell: ' + eR); }
        }

        note('newProject: ' + out);
        var made = false;
        try { made = app.newProject(out); note('newProject returned ' + made); }
        catch (eN) { note('newProject threw: ' + eN); left.push(xmlPath); continue; }
        if (made === false) {
            note('newProject refused');
            // ★거부해도 **2KB 껍데기**를 남긴다 (2026-08-26, 볼트 09-02 판) — 치워야
            //   다음 판의 «있다» 판정이 안 속는다.
            try { if (File(out).exists) { File(out).remove(); note('stub cleaned'); } } catch (eC2) {}
            left.push(xmlPath); continue;
        }

        var before = 0, after = 0;
        try { before = app.project.rootItem.children.numItems; } catch (eA) {}
        note('importFiles: ' + xml.fsName);
        try {
            var ok = app.project.importFiles([xml.fsName], true, app.project.rootItem, false);
            note('importFiles returned ' + ok);
        } catch (eI) { note('importFiles threw: ' + eI); left.push(xmlPath); continue; }
        try { after = app.project.rootItem.children.numItems; } catch (eB) {}
        note('project items ' + before + ' -> ' + after);
        // ★importFiles 는 true 를 돌려주고도 **아직 안 끝나 있다** (2026-08-26).
        //   바로 세면 0개로 읽고 «빈 껍데기»(5KB .prproj) 를 저장해 버린다.
        //   ★★$.sleep 으로 기다리면 안 된다 — 엔진이 한 가닥이라 **기다리는 동안
        //   가져오기 자체가 멈춘다.** 프리미어가 통째로 얼어붙었다(2-3편에서 두 번).
        //   기다리지 말고 **엔진을 놓아주고 다음 판에 확인한다.**
        //   다음 판에는 이 프로젝트가 열려 있으므로 위쪽 «이미 열려 있다» 가지가 받는다.
        if (after <= before) {
            note('import still running — will check on the next pass');
            left.push(xmlPath);
            break;
        }

        openSequenceAndSave(out, left, xmlPath);

    }

    var leftNow = rewriteQueue(left, lines);
    $.global.__volcano_busy = false;
    note('pass finished, left ' + left.length + ' (queue now ' + leftNow + ')');
}());
