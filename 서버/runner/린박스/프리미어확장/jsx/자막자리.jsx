/*  자막·제목을 «자막자리표» 대로 제자리에 앉힌다. (2026-08-26)
 *
 *  왜 있나 — 프리미어는 FCP7 XML 로 받은 텍스트의 **자리를 버린다.** 그래서 전부
 *  화면 한가운데로 몰린다. 밖에서 prproj 를 고치는 길은 파일을 깨뜨린다(여러 번 겪음).
 *  프리미어 자신에게 시키면 안 깨진다.
 *
 *  ★클립을 **이름(=자막 글자)** 으로 짝짓는다. 길이나 트랙으로 어림하면 어긋난다 —
 *    «30초 넘으면 제목» 이라는 어림 때문에 방영정보가 제목 자리로 올라가
 *    제목이 두 개로 겹쳐 보였다.
 *
 *  ★2026-08-26 부터 **여러 편을 한 줄에 세운다.** 한 편씩 열어 손보고 저장하려면
 *    사람이 여덟 번 프리미어를 켜야 했다. 대기줄 한 줄이 «prproj<탭>자리표» 다.
 *      ~/.volcano/자리대기줄.txt
 *    다 된 줄은 지우므로, 도중에 멈춰도 남은 것만 이어서 한다.
 */
(function () {
    var BS = String.fromCharCode(92);
    var HOME = String(Folder('~').fsName).split(BS).join('/');
    var LOG = File(HOME + '/.volcano/자막자리.log');
    var 줄파일 = File(HOME + '/.volcano/자리대기줄.txt');
    function note(m){try{LOG.encoding='UTF-8';LOG.open('a');LOG.writeln(m);LOG.close();}catch(e){}}
    function 읽기(f){try{f.encoding='UTF-8';f.open('r');var s=f.read();f.close();return s;}catch(e){return '';}}
    function 쓰기(f,s){try{f.encoding='UTF-8';f.open('w');f.write(s);f.close();}catch(e){}}

    if ($.global.__자리바쁨) { return; }
    if (typeof app === 'undefined') { return; }
    if (!줄파일.exists) { return; }
    var 줄 = 읽기(줄파일).split(/[\r\n]+/);
    var 남 = [];
    for (var q = 0; q < 줄.length; q++) { if (줄[q].replace(/^\s+|\s+$/g,'') !== '') { 남.push(줄[q]); } }
    if (!남.length) { return; }
    $.global.__자리바쁨 = true;

    // ★한 번에 **한 편만** 한다 (2026-08-26).
    //   `openDocument` 는 바로 갈아 끼워지지 않는다. 여섯 편을 한 번에 돌렸더니
    //   앞 편이 열린 채로 뒤 편의 자리표를 대어 «못 찾음» 만 40줄 나왔다.
    //   열렸는지 **확인**하고, 안 열렸으면 줄을 그대로 두고 다음 차례에 다시 온다.
    {
        var 한줄 = 남[0];
        var 칸 = 한줄.split(String.fromCharCode(9));
        var pr = 칸[0], 표길 = 칸[1];
        try {
            var 표파일 = File(표길);
            if (!표파일.exists) {
                note('자리표가 없다: ' + 표길);
                남.shift(); 쓰기(줄파일, 남.join(String.fromCharCode(10)));
                $.global.__자리바쁨 = false; return;
            }
            var 표 = eval('(' + 읽기(표파일) + ')');
            // ★경로 글자를 곧이곧대로 견주면 안 된다 (2026-08-26).
            //   맥은 한글 이름을 NFD 로 적고 프리미어는 NFC 로 돌려주기도 한다.
            //   그러면 «열었는데도 안 열렸다» 며 **끝없이 맴돈다.** 그래서
            //   한 번 열라고 시킨 것은 다음 차례에 그대로 믿고 손을 댄다.
            // ★한글은 빼고 **ASCII 만 남겨** 견준다 (2026-08-26).
            //   맥은 이름을 NFD 로, 프리미어는 NFC 로 돌려주기도 해서 곧이곧대로
            //   견주면 «열었는데 안 열렸다» 며 끝없이 맴돈다. 편 폴더 이름
            //   (ep_0350-0435) 은 ASCII 라 이것만으로도 편이 갈린다.
            function 견줌(x) { return String(x).replace(/[^\x20-\x7E]/g, ''); }
            var 열림 = app.project && 견줌(app.project.path) === 견줌(pr);
            if (!열림) {
                note('연다: ' + pr);
                app.openDocument(pr);
                $.global.__자리바쁨 = false;
                return;                      // ★이번엔 열기만. 다음 차례에 손본다.
            }
            // ★`activeSequence` 를 그냥 믿으면 안 된다 (2026-08-26).
            //   프로젝트를 갈아 끼워도 **앞 편의 시퀀스가 활성인 채로 남는다.**
            //   그래서 «열었다» 면서 앞 편의 클립 40장을 뒤 편 자리표로 뒤졌고
            //   «표에 없던 것 40장» 이 나왔다. **이 프로젝트의 시퀀스를 직접 연다.**
            var seq = null;
            try {
                // `app.project.sequences` 가 **이 프로젝트의** 시퀀스 목록이다.
                //   (rootItem 의 projectItem 에는 getSequenceID 가 없다)
                var 목 = app.project.sequences;
                if (목 && 목.numSequences > 0) {
                    app.project.openSequence(목[0].sequenceID);
                }
            } catch (e2) { note('  시퀀스 열기 탈: ' + e2); }
            seq = app.project.activeSequence;
            if (!seq) { note('시퀀스를 못 열었다: ' + pr); $.global.__자리바쁨 = false; return; }
            var 맞춘 = 0, 못찾은 = 0;
            for (var i = 0; i < seq.videoTracks.numTracks; i++) {
                var t = seq.videoTracks[i];
                for (var j = 0; j < t.clips.numItems; j++) {
                    var c = t.clips[j];
                    for (var k = 0; k < c.components.numItems; k++) {
                        var cm = c.components[k];
                        if (String(cm.matchName) !== 'AE.ADBE Text') { continue; }
                        var 자리 = 표[String(c.name)];
                        if (!자리) { 못찾은 += 1; note('  못 찾음: ' + c.name); continue; }
                        try { cm.properties[2].setValue([자리[0], 자리[1]], true); 맞춘 += 1; }
                        catch (e1) { note('  탈 ' + c.name + ': ' + e1); }
                    }
                }
            }
            app.project.save();
            note('[' + pr + '] 시퀀스 «' + seq.name + '» · 자리 맞춘 것 ' + 맞춘
                 + '장 · 표에 없던 것 ' + 못찾은 + '장 · 저장 완료');
            남.shift(); 쓰기(줄파일, 남.join(String.fromCharCode(10)));
        } catch (e) {
            note('탈 ' + pr + ': ' + e);
            남.shift(); 쓰기(줄파일, 남.join(String.fromCharCode(10)));
        }
    }
    $.global.__자리바쁨 = false;
}());
