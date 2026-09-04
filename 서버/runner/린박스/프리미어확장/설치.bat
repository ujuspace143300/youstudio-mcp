@echo off
REM ─────────────────────────────────────────────────────────────
REM  볼케이노 프리미어 확장 설치 — 다른 컴퓨터에서 한 번만 (관리자로 실행)
REM  오른쪽 클릭 → 관리자 권한으로 실행
REM ─────────────────────────────────────────────────────────────
setlocal
echo.
echo [1/3] 확장 복사...
set "SRC=%~dp0com.volcano.prproj"
set "DST=%APPDATA%\Adobe\CEP\extensions\com.volcano.prproj"
if exist "%DST%" rmdir /S /Q "%DST%"
xcopy /E /I /Y /Q "%SRC%" "%DST%" >nul
echo     %DST%

echo [2/3] 서명 우회 켜기 (CSXS 11~14)...
for %%v in (11 12 13 14) do (
  reg add "HKCU\Software\Adobe\CSXS.%%v" /v PlayerDebugMode /t REG_SZ /d 1 /f >nul 2>&1
)
echo     PlayerDebugMode = 1

echo [3/3] 확인...
if exist "%DST%\jsx\auto_prproj.jsx" (echo     확장 OK) else (echo     [실패] 확장 파일이 없다)

echo.
echo  끝. 프리미어를 켜 두면 프로젝트가 자동으로 나온다.
echo  ★프리미어 2026(26.0.2)은 확장의 한글 변수명을 못 읽는 버그가 있으나
echo    이 배포본의 auto_prproj.jsx 는 이미 영문으로 되어 있다. 건드리지 말 것.
echo.
pause
