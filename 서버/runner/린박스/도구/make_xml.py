# -*- coding: utf-8 -*-
r"""FCP7 XML(xmeml) 을 **프리미어가 시퀀스로 풀도록** 쓴다.

두 번 실패했다. 원인은 둘 다 «있어야 할 게 없거나, 순서가 틀린» 것이었다.

 ① 첫 판 — `<project><children>` 감싸개가 없었다. 그러면 프리미어는 시퀀스를 프로젝트로
    읽지 않고 참조된 파일만 프로젝트 패널에 늘어놓는다.
 ② 둘째 판 — 감싸개는 넣었지만 **요소 순서**가 DTD 와 달랐다. xmeml 은 순서를 지켜야 하는
    포맷이라, `<timecode>` 를 `<media>` 뒤에 두거나 `<file>` 안에서 `<duration>` 을
    `<name>` 뒤에 두면 파서가 그 시퀀스를 통째로 버린다.

그래서 이 파일은 **순서를 상수로 박아** 쓴다. 아래 주석의 차례를 바꾸지 마라.

  sequence : uuid → name → duration → rate → timecode → in → out → media
  file     : duration → rate → name → pathurl → timecode → media
  clipitem : masterclipid → name → enabled → duration → rate → start → end
             → in → out → file → sourcetrack → compositemode
  track    : clipitem* → enabled → locked
"""
import os
import subprocess          # ★_크기() 가 ffprobe 를 부른다 (2026-08-26)
import urllib.parse
import uuid as _uuid

FPS = 30
BS = chr(92)


def url(p):
    return 'file://localhost/' + urllib.parse.quote(
        os.path.abspath(p).replace(BS, '/'), safe='/:')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


RATE = f'<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>'
TC = (f'<timecode>{RATE}<string>00:00:00:00</string><frame>0</frame>'
      f'<displayformat>NDF</displayformat></timecode>')

# ★합침(2026-09-03): 윈도우 판 set_fps — 소재 프레임률(23.976 등)에 맞춰 시퀀스 rate 를 다시 짠다. 부르지 않으면 예전과 같다.
def set_fps(fr):
    """소재 프레임률에 맞춰 시퀀스·파일 rate 를 다시 짠다 (2026-09-01).

    ★사장님 「싱크가 하나도 안 맞아 · 화면이 이상해」의 진짜 원인이 여기였다.
      원본이 23.976fps(24000/1001)인데 XML 을 30fps 로 박아 냈다. 그러면 프리미어가
      원본의 in/out 프레임을 30 으로 세어 **엉뚱한 초를 물어** 컷마다 점점 밀린다.
      render.py 는 이미 «소재에 맞춤»으로 냈기에 mp4 는 멀쩡했다 — prproj 만 어긋났다.

    fr 은 '24000/1001' 같은 문자열이나 실수. FCP7 XML 은 정수 timebase + ntsc 로 적는다:
      23.976 → timebase 24 · ntsc TRUE      29.97 → 30 · TRUE
      24 · 25 · 30 (정수) → 그대로 · ntsc FALSE
    """
    global FPS, RATE, TC
    if isinstance(fr, str) and '/' in fr:
        n, d = fr.split('/')
        val = float(n) / float(d)
    else:
        val = float(fr)
    tb = int(round(val))
    ntsc = 'TRUE' if abs(val - tb) > 0.001 else 'FALSE'
    FPS = val
    RATE = f'<rate><timebase>{tb}</timebase><ntsc>{ntsc}</ntsc></rate>'
    TC = (f'<timecode>{RATE}<string>00:00:00:00</string><frame>0</frame>'
          f'<displayformat>NDF</displayformat></timecode>')



_가진것_기억 = {}



def _크기(path, 기본=(1080, 1920)):
    """영상의 실제 가로x세로. 못 재면 기본값."""
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                            '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path],
                           capture_output=True, text=True).stdout.strip()
        # ★ffprobe 가 값을 두 줄로 내는 파일(타임코드 트랙)이 있다 — 첫 줄만 (2026-09-03 불륜 EP1: 파싱이 죽어
        #   기본값 1080x1920 이 박혔고, 프리미어가 그 선언 크기로 배율을 풀어 영상이 매트 안쪽에 작게 앉았다)
        w, h = (int(x) for x in r.split()[0].split(',')[:2])
        return (w, h) if w and h else 기본
    except Exception:
        return 기본


def _가진것(path):
    """그 파일에 영상·소리가 각각 들어 있는가 (ffprobe 로 한 번만 재고 기억한다)"""
    if path in _가진것_기억:
        return _가진것_기억[path]
    v = a = False
    try:
        import subprocess
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'stream=codec_type', '-of', 'csv=p=0', path],
                           capture_output=True, text=True)
        종류 = r.stdout.split()
        v = any('video' in x for x in 종류)
        a = any('audio' in x for x in 종류)
    except Exception:
        pass
    _가진것_기억[path] = (v, a)
    return v, a


class Files:
    """같은 파일은 한 번만 펼쳐 쓰고 그다음부터 id 로만 가리킨다."""

    def __init__(self):
        self.seen = {}

    def tag(self, path, dur_f, kind):
        if path in self.seen:
            return f'<file id="{self.seen[path]}"/>'
        self.seen[path] = f'file-{len(self.seen) + 1}'
        # ★파일이 실제로 무엇을 담고 있는지 **재서** 적는다 (2026-08-25).
        #   전에는 «처음 부른 쪽» 기준으로 적었다. 그래서 같은 원본을 V1(영상)과
        #   A1(소리)이 함께 물리면 `<file>` 에 영상만 적혀, 프리미어가 소리를 못 찾고
        #   가져오기에서 **매달렸다.** 한 파일에 영상·소리가 다 있으면 둘 다 적는다.
        영상, 소리 = _가진것(path)
        if kind == 'v':
            영상 = True
        else:
            소리 = True
        # ★크기도 **재서** 적는다 (2026-08-26). 전에는 파일이 무엇이든 1080x1920 을
        #   박아 썼다. 1920x960 원본이나 1080x1020 재프레이밍본을 물리면 프리미어가
        #   «시퀀스와 같은 크기» 로 알고 앉혀 **화면이 작게** 들어간다. 사장님 지적.
        _w, _h = _크기(path)
        media = '<media>'
        if 영상:
            media += ('<video><samplecharacteristics>'
                      f'{RATE}<width>{_w}</width><height>{_h}</height>'
                      '<anamorphic>FALSE</anamorphic>'
                      '<pixelaspectratio>square</pixelaspectratio>'
                      '<fielddominance>none</fielddominance>'
                      '</samplecharacteristics></video>')
        if 소리:
            media += ('<audio><samplecharacteristics><depth>16</depth>'
                      '<samplerate>48000</samplerate></samplecharacteristics>'
                      '<channelcount>2</channelcount></audio>')
        media += '</media>'
        # 순서: duration → rate → name → pathurl → timecode → media
        return (f'<file id="{self.seen[path]}">'
                f'<duration>{dur_f}</duration>{RATE}'
                f'<name>{esc(os.path.basename(path))}</name>'
                f'<pathurl>{url(path)}</pathurl>{TC}{media}</file>')


def clip(cid, mcid, name, start, dur, path, kind, files, srcin=0,
         srcout=None, extra=''):
    """★srcout·extra 는 «원본을 타임코드로 물리는» 판을 위해 붙였다 (2026-08-25).

    srcout 를 주면 원본에서 쓰는 길이가 화면 길이와 달라진다 = **배속**이다.
    extra 에는 `<filter>` 를 넘긴다 — 서버가 컷마다 넣은 확대를 프리미어 «크기» 로 옮긴다.
    """
    # 순서: masterclipid → name → enabled → duration → rate → start → end
    #       → in → out → file → sourcetrack → compositemode
    s = (f'<clipitem id="{cid}">'
         f'<masterclipid>{mcid}</masterclipid>'
         f'<name>{esc(name)}</name>'
         f'<enabled>TRUE</enabled>'
         f'<duration>{dur}</duration>{RATE}'
         f'<start>{start}</start><end>{start + dur}</end>'
         f'<in>{srcin}</in><out>{srcin + dur if srcout is None else srcout}</out>'
         f'{files.tag(path, dur, kind)}')
    if kind == 'a':
        s += ('<sourcetrack><mediatype>audio</mediatype>'
              '<trackindex>1</trackindex></sourcetrack>')
    else:
        s += '<compositemode>normal</compositemode>'
    return s + extra + '</clipitem>'


def scale_filter(pct):
    """FCP7 XML 의 기본 모션(scale) — 프리미어가 클립의 «크기» 로 읽는다.

    서버는 컷마다 crop 으로 확대해 굽는다(1.00~1.45배). 원본을 그대로 물리면 그 확대가
    사라져 완성본보다 헐렁해 보인다. 그래서 같은 배율을 **크기 파라미터**로 옮겨 준다 —
    이러면 화면은 완성본과 같으면서, 사장님이 프리미어에서 배율을 손으로 바꿀 수 있다.
    """
    if abs(pct - 100.0) < 0.5:
        return ''
    return ('<filter><effect><name>Basic Motion</name><effectid>basic</effectid>'
            '<effectcategory>motion</effectcategory><effecttype>motion</effecttype>'
            '<mediatype>video</mediatype>'
            '<parameter authoringApp="PremierePro"><parameterid>scale</parameterid>'
            '<name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax>'
            f'<value>{pct:.2f}</value></parameter>'
            '</effect></filter>')


def 모션(pct=100.0, 밀기x=0.0, 밀기y=0.0):
    """기본 모션 — 크기와 **자리**를 함께 낸다 (2026-08-26).

    ★사장님: «원본 파일은 왜 잘려있는거야? 원본 그대로 들어가야 인물 상세 조정이 가능해»
      전에는 이미 인물을 가운데로 **잘라 구운** `구간_인물.mp4`(1080x1020)를 물렸다.
      화면은 완성본과 같지만 **좌우가 잘려 나가서 다시 잡을 수가 없다.**
      이제 **원본(1920x1080)** 을 물리고, 재프레이밍을 «크기 + 자리» 로 옮긴다 —
      화면은 같고, 사장님이 클립을 골라 자리를 끌면 인물을 다시 잡을 수 있다.

    자리는 FCP7 의 `center` — **화면 전체를 1.0 으로 세는 값**이다.
      가로 : 밀기x px  →  밀기x / 1080
      세로 : 밀기y px  →  밀기y / 1920

    ★2026-08-26 윈도우에서 실측으로 바로잡았다 (합침 2026-09-03). «절반이 1.0» 인 줄 알고 540 으로 나눴더니
      **두 배로 밀려** 소재가 화면 밖으로 나가고 **검정이 드러났다.**
      만든 프로젝트에서 되읽은 「위치」가 0.982 · -0.178 로, 소재가 덮을 수 있는
      한계(0.161~0.839)를 훌쩍 넘었다. 프리미어는 위치.x = 0.5 + horiz 로 받는다.
    """
    칸 = []
    if abs(pct - 100.0) >= 0.01:
        칸.append('<parameter authoringApp="PremierePro"><parameterid>scale</parameterid>'
                  '<name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax>'
                  f'<value>{pct:.3f}</value></parameter>')
    if abs(밀기x) >= 0.5 or abs(밀기y) >= 0.5:
        칸.append('<parameter authoringApp="PremierePro"><parameterid>center</parameterid>'
                  '<name>Center</name>'
                  f'<value><horiz>{밀기x / 1080.0:.6f}</horiz>'
                  f'<vert>{밀기y / 1920.0:.6f}</vert></value></parameter>')
    if not 칸:
        return ''
    return ('<filter><effect><name>Basic Motion</name><effectid>basic</effectid>'
            '<effectcategory>motion</effectcategory><effecttype>motion</effecttype>'
            '<mediatype>video</mediatype>' + ''.join(칸) + '</effect></filter>')


def 글자클립(cid, name, start, dur, 글, 글꼴='GangwonEduAllBold', 크기=60,
             색='#FFFFFF', 세로가운데=None, 프레임높이=1920, 외곽=0.0):
    """자막 한 장을 **프리미어 native 텍스트 그래픽**으로 만든다 (2026-08-25).

    ★이 길을 찾기까지 세 번 헛돌았다. 기록해 둔다:
      ① 알파 MOV 로 구워 얹기 → 사장님: «자막이 이미지야? 텍스트가 수정이 안됨»
      ② prproj 에 그래픽을 밖에서 심기 → «프로젝트 파일 손상되었다고 꺼졌어»
      ③ MOGRT 얹고 API 로 글자 넣기 → 서식을 못 입힌다(날것 UTF-16 만 들어간다).
         게다가 20장째 저장에서 **프리미어가 죽는다.**
      ④ 캡션→그래픽 올리기 → qe.executeConsoleCommand 가 전부 false, 캡션을 고를 API 도 없다.

    ⑤ **FCP7 XML 의 `<generatoritem>` 텍스트 제너레이터** — 프리미어가 이걸 가져오면
       «소스 텍스트»(44332211 플랫버퍼) + «변형»(위치·비율·회전)을 갖춘 **진짜 텍스트
       그래픽**을 만들어 준다. 손도 안 들고, 안 죽고, 본떠서만들기.py 가 그대로 먹는다.
    """
    def 칸(pid, 이름, 값, mn=None, mx=None):
        한계 = f'<valuemin>{mn}</valuemin><valuemax>{mx}</valuemax>' if mn is not None else ''
        return (f'<parameter><parameterid>{pid}</parameterid>'
                f'<name>{esc(이름)}</name>{한계}<value>{esc(str(값))}</value></parameter>')
    return (f'<generatoritem id="{cid}">'
            f'<name>{esc(글)}</name>'
            f'<enabled>TRUE</enabled>'
            f'<duration>{dur}</duration>{RATE}'
            f'<start>{start}</start><end>{start + dur}</end>'
            f'<in>0</in><out>{dur}</out>'
            f'<effect><name>Text</name><effectid>Text</effectid>'
            f'<effectcategory>Text</effectcategory>'
            f'<effecttype>generator</effecttype><mediatype>video</mediatype>'
            + 칸('str', 'Text', 글)
            + 칸('fontsize', 'Size', 크기, 0, 1000)
            + 칸('font', 'Font', 글꼴)
            + _색칸('fontcolor', 'Font Color', 색)
            + _자리칸(세로가운데, 프레임높이)
            + 칸('fontstyle', 'Style', 1, 1, 4)
            + 칸('fontalign', 'Alignment', 2, 1, 3)
            + (칸('linewidth', 'Outline', 외곽, 0, 100) if 외곽 else '')
            + '</effect></generatoritem>')


def _색칸(pid, 이름, 색):
    """#RRGGBB 를 FCP7 색 칸으로. 프리미어가 «칠» 로 읽는다."""
    h = 색.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (f'<parameter><parameterid>{pid}</parameterid><name>{esc(이름)}</name>'
            f'<value><alpha>255</alpha><red>{r}</red><green>{g}</green>'
            f'<blue>{b}</blue></value></parameter>')


def _자리칸(세로가운데, 프레임높이):
    """자막이 화면 어디에 앉는가 — FCP7 origin (가운데가 0, 아래가 +).

    ★2026-08-26 · 사장님 지적 «자막 위치랑 크기가 이상해».
      전에는 자리를 **아예 안 넘겼다.** 그래서 프리미어가 전부 화면 한가운데에
      기본 크기로 앉혔다. ass 의 윗선을 화면 비율로 바꿔 실어 보낸다.
    """
    if 세로가운데 is None:
        return ''
    v = (세로가운데 - 프레임높이 / 2) / (프레임높이 / 2)
    return ('<parameter><parameterid>origin</parameterid><name>Origin</name>'
            f'<value><horiz>0</horiz><vert>{v:.4f}</vert></value></parameter>')


def vtrack(items):
    # 순서: clipitem* → enabled → locked
    return (f'<track>{"".join(items)}'
            f'<enabled>TRUE</enabled><locked>FALSE</locked></track>')


def atrack(items):
    return (f'<track>{"".join(items)}'
            f'<enabled>TRUE</enabled><locked>FALSE</locked>'
            f'<outputchannelindex>1</outputchannelindex></track>')


def _아래트랙들(a1, a2):
    """a1 이 트랙 목록이면 그대로 쌓는다 (A1 원음 · A2 나레 · A3 효과음)"""
    if a1 and isinstance(a1[0], (list, tuple)):
        return ''.join(atrack(t) for t in a1 if t)
    return atrack(a1) + (atrack(a2) if a2 else '')


def _윗트랙들(v2):
    """v2 가 트랙 하나면 그대로, 트랙 목록이면 아래에서 위로 쌓는다"""
    if v2 and isinstance(v2[0], (list, tuple)):
        return ''.join(vtrack(t) for t in v2)
    return vtrack(v2)


def build(name, total_f, v1, v2, a1, a2):
    """★v2 자리에는 **여러 트랙**을 줄 수 있다 (2026-08-25).

    자막을 한 장에 구워 얹으면 프리미어에서 **갈라낼 수가 없다.**
    사장님 지시 — «자막이랑 템플릿은 모두 분리, 나레이션 자막과 대사 자막도 구분».
    그래서 V2 위로 트랙을 여러 개 쌓는다: 템플릿 · 나레자막 · 대사자막 · 모션자막.
    v2 에 «클립 목록의 목록» 을 주면 그만큼 트랙이 생긴다. 하나만 주면 예전과 같다.
    """

    vfmt = ('<format><samplecharacteristics>'
            f'{RATE}<width>1080</width><height>1920</height>'
            '<anamorphic>FALSE</anamorphic>'
            '<pixelaspectratio>square</pixelaspectratio>'
            '<fielddominance>none</fielddominance>'
            '<colordepth>24</colordepth>'
            '</samplecharacteristics></format>')
    afmt = ('<format><samplecharacteristics><depth>16</depth>'
            '<samplerate>48000</samplerate></samplecharacteristics></format>')
    # 순서: uuid → name → duration → rate → timecode → in → out → media
    seq = (f'<sequence id="sequence-1">'
           f'<uuid>{_uuid.uuid4()}</uuid>'
           f'<name>{esc(name)}</name>'
           f'<duration>{total_f}</duration>{RATE}{TC}'
           f'<in>-1</in><out>-1</out>'
           f'<media>'
           f'<video>{vfmt}{vtrack(v1)}{_윗트랙들(v2)}</video>'
           f'<audio><numOutputChannels>2</numOutputChannels>{afmt}'
           f'{_아래트랙들(a1, a2)}</audio>'
           f'</media></sequence>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE xmeml>\n'
            '<xmeml version="5">\n'
            f'<project><name>{esc(name)}</name><children>{seq}</children></project>\n'
            '</xmeml>\n')
