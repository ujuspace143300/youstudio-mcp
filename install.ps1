# ============================================================
#  유스튜디오 한방 설치 (윈도우) — 지인용. PowerShell 에서:
#
#    powershell -ExecutionPolicy Bypass -File install.ps1 <관리자에게-받은-토큰> [-저장소 <git URL>] [-서버 <URL>] [-자리 <폴더>]
#    한 줄 설치(PowerShell):  irm https://raw.githubusercontent.com/ujuspace143300/youstudio-mcp/main/install.ps1 -OutFile install.ps1; powershell -ExecutionPolicy Bypass -File .\install.ps1 <토큰>
#    (파일 이름·위치가 ASCII 인 이유: raw URL 에 한글이 들어가면 환경마다 %인코딩이 갈려 404 가 난다 · 2026-09-07)
#
#  하는 일 (여러 번 실행해도 안전 — 있는 것은 건너뛴다)
#    1 winget 으로 node · ffmpeg · python · git      2 Claude Code
#    3 코드(러너) 받기 — 공개 GitHub 에서 clone / 이미 있으면 pull
#    4 설치 id(~/.youstudio/device) + 서버 자산 받기(글꼴 등 · 토큰 있는 사람만 · sha256 확인)
#    5 러너 파이썬 venv(~/.youstudio/venv · pillow numpy opencv)   6 API 키(본인 발급 · ~/.volcano/keys)
#    7 Claude Code 에 유스튜디오 붙이기(claude mcp add · 두 헤더)  8 프리미어 + CEP 확장(레지스트리 PlayerDebugMode)
#  ★이 파일은 UTF-8 BOM 으로 저장돼야 한글이 안 깨진다.
# ============================================================
param(
  [Parameter(Position = 0)][string]$토큰 = "",
  [string]$저장소 = "https://github.com/ujuspace143300/youstudio-mcp.git",
  [string]$서버 = "https://youstudio-mcp.youstudio.workers.dev",
  [string]$자리 = "$HOME\Desktop\youstudio-mcp",
  [string]$프리셋 = "린박스"
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"
function Say($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "   ✔ $m" -ForegroundColor Green }
function Warn($m) { Write-Host "   ⚠ $m" -ForegroundColor Yellow }
function Stop-Here($m) { Write-Host "   ★ $m" -ForegroundColor Red; exit 1 }
if (-not $토큰) { Stop-Here "토큰이 필요하다:  powershell -ExecutionPolicy Bypass -File install.ps1 <토큰>" }

# ── 도구 진짜인가 — «명령이 있나」가 아니라 «버전을 뱉나」로 본다 ─────────
#   ★윈도우 기본 python 은 Microsoft Store 리다이렉터 껍데기다: Get-Command 는 성공하지만 `python --version` 이
#     «Python» 만 찍고 exit 9009 로 끝난다(2026-09-07 사장님 깨끗한 윈도우 실전). 그걸 «있음」으로 보고 winget 을 건너뛰면
#     5단계 venv 에서 python.exe 가 없어 죽는다. 그래서 «Python 3.x» 를 실제로 뱉는 것만 python 으로 친다.
function Test-Ver($cmd, $argv, $pattern) {   # $args 는 PowerShell 자동 변수라 이름을 피한다
  try { $out = (& $cmd @argv 2>&1 | Out-String).Trim(); if ($LASTEXITCODE -ne 0) { return $null }; if ($out -match $pattern) { return $out.Split("`n")[0].Trim() } } catch {}
  return $null
}
function Find-Python {
  # ① py 런처  ② PATH 의 python  ③ winget/공식 설치 자리(%LOCALAPPDATA%\Programs\Python\Python3xx · Program Files)
  if (Test-Ver "py" @("-3", "--version") "^Python 3\.") { return "py -3" }
  if (Test-Ver "python" @("--version") "^Python 3\.") { return (Get-Command python).Source }
  $cands = @()
  foreach ($root in @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles", "${env:ProgramFiles(x86)}")) {
    if ($root -and (Test-Path $root)) { $cands += Get-ChildItem -Path $root -Directory -Filter "Python3*" -ErrorAction SilentlyContinue | ForEach-Object { Join-Path $_.FullName "python.exe" } }
  }
  foreach ($c in ($cands | Sort-Object -Descending)) { if ((Test-Path $c) -and (Test-Ver $c @("--version") "^Python 3\.")) { return $c } }
  return $null
}
function Invoke-Py { param([string]$py, [string[]]$rest) if ($py -eq "py -3") { & py -3 @rest } else { & $py @rest } }
function Refresh-Path { $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path }

# ── 1. 도구 ───────────────────────────────────────────────────
Say "1/8 node · ffmpeg · python · git (winget) — 진짜 버전을 뱉는지로 본다"
$need = @()
if (-not (Test-Ver "node" @("-v") "^v\d+")) { $need += "OpenJS.NodeJS.LTS" }
if (-not (Test-Ver "ffmpeg" @("-version") "^ffmpeg version")) { $need += "Gyan.FFmpeg" }
if (-not (Test-Ver "git" @("--version") "^git version")) { $need += "Git.Git" }
$py = Find-Python
if (-not $py) { $need += "Python.Python.3.12" }
foreach ($id in $need) { Write-Host "   winget install $id"; winget install -e --id $id --accept-source-agreements --accept-package-agreements | Out-Null }
Refresh-Path
$missing = @()
if (-not (Test-Ver "node" @("-v") "^v\d+")) { $missing += "node" }
if (-not (Test-Ver "ffmpeg" @("-version") "^ffmpeg version")) { $missing += "ffmpeg" }
if (-not (Test-Ver "git" @("--version") "^git version")) { $missing += "git" }
$py = Find-Python
if (-not $py) { $missing += "python" }
if ($missing.Count -gt 0) {
  Stop-Here ("아직 안 잡히는 것: " + ($missing -join ", ") + " — winget 으로 깔았으면 PATH 가 새 셸에서만 보인다. ★PowerShell(또는 VS Code)을 닫고 새로 연 뒤 install.ps1 을 다시 돌려라. (python 이 계속 없으면 Microsoft Store 껍데기가 아니라 https://www.python.org/downloads/ 로 «Add python.exe to PATH» 를 켜고 설치)")
}
Ok ("node " + (Test-Ver "node" @("-v") "^v") + " · " + (Invoke-Py $py @("--version") | Out-String).Trim() + " (" + $py + ") · " + (Test-Ver "git" @("--version") "^git"))

# ── 2. Claude Code ───────────────────────────────────────────
Say "2/8 Claude Code"
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { npm install -g @anthropic-ai/claude-code | Out-Null }
Ok "claude $(claude --version 2>$null)"

# ── 3. 코드 ──────────────────────────────────────────────────
Say "3/8 코드 받기 → $자리"
if (Test-Path "$자리\.git") { Push-Location $자리; git pull -q --ff-only; Ok "이미 있음 — 최신으로 당김 $(git rev-parse --short HEAD)"; Pop-Location }
else { git clone -q $저장소 $자리; Push-Location $자리; Ok "받았다 $(git rev-parse --short HEAD)"; Pop-Location }
if (-not (Test-Path "$자리\서버\runner\기기.mjs")) { Stop-Here "저장소 꼴이 다르다 — 서버\runner\기기.mjs 가 없다" }

# ── 4. 설치 id + 자산 ────────────────────────────────────────
Say "4/8 설치 id · 서버 자산(글꼴 등 · 토큰으로만 받는다)"
Push-Location "$자리\서버\runner"
$dev = (node -e "import('./기기.mjs').then(m=>console.log(m.deviceId()))").Trim()
Pop-Location
if (-not $dev) { Stop-Here "설치 id 를 못 만들었다 (~/.youstudio/device)" }
Ok "설치 id $dev"
$hdr = @{ Authorization = "Bearer $토큰"; "X-Youstudio-Device" = $dev }
try { $man = Invoke-RestMethod -Uri "$서버/asset/$프리셋/_목록.json" -Headers $hdr -TimeoutSec 30 }
catch { Stop-Here "서버가 거부했거나 못 붙었다 — $($_.Exception.Message) · 토큰·만료·기기 초과·«$프리셋 권한» 을 관리자에게 확인하라" }
$adir = "$자리\자산\$프리셋"; New-Item -ItemType Directory -Force -Path $adir | Out-Null
$n = 0; $bad = 0
foreach ($f in $man.files) {
  $out = Join-Path $adir ($f.path -replace "/", "\")
  New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
  if ((Test-Path $out) -and ((Get-FileHash $out -Algorithm SHA256).Hash.ToLower() -eq $f.sha256)) { $n++; continue }
  $enc = ($f.path -split "/" | ForEach-Object { [uri]::EscapeDataString($_) }) -join "/"
  try { Invoke-WebRequest -Uri "$서버/asset/$프리셋/$enc" -Headers $hdr -OutFile $out -TimeoutSec 120 } catch { $bad++; Warn "못 받음: $($f.path)"; continue }
  if ((Get-FileHash $out -Algorithm SHA256).Hash.ToLower() -eq $f.sha256) { $n++ } else { $bad++; Warn "받은 파일이 목록과 다르다: $($f.path)"; Remove-Item $out -Force }
}
if ($bad -gt 0) { Stop-Here "자산 $bad 개를 못 받았다 — 다시 돌려라" }
Ok "자산 $n 개 확인 → $adir"

# ── 5. 러너 파이썬 ───────────────────────────────────────────
Say "5/8 러너 파이썬 ~/.youstudio/venv (pillow · numpy · opencv)"
$py = Find-Python
if (-not $py) { Stop-Here "python 이 없다(Store 껍데기만 있음) — 1단계 안내대로 python 을 깔고 새 셸에서 다시 돌려라" }
$venv = "$HOME\.youstudio\venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) { Invoke-Py $py @("-m", "venv", $venv) }
if (-not (Test-Path "$venv\Scripts\python.exe")) { Stop-Here "venv 를 못 만들었다 ($py -m venv $venv) — python 이 진짜인지(python --version 이 «Python 3.x») 확인" }
& "$venv\Scripts\python.exe" -m pip install -q --upgrade pip pillow numpy opencv-python | Out-Null
& "$venv\Scripts\python.exe" -c "import PIL, numpy, cv2" ; if ($LASTEXITCODE -ne 0) { Stop-Here "venv 모듈이 안 들어갔다 — 인터넷·pip 를 확인" }
Ok ("venv 준비 (" + (& "$venv\Scripts\python.exe" --version) + ")")

# ── 6. API 키 ────────────────────────────────────────────────
Say "6/8 API 키 (본인이 발급 · ~/.volcano/keys/) — 린박스: speechmatics(전사) · typecast(나레)"
$K = "$HOME\.volcano\keys"; New-Item -ItemType Directory -Force -Path $K | Out-Null
$interactive = -not [Console]::IsInputRedirected
if (-not $interactive) { Warn "대화형 터미널이 아니라 키 입력을 건너뛴다 — 나중에 $K\speechmatics · $K\typecast 파일에 키 한 줄씩 넣어라(메모장 · 줄 끝 공백 없이)" }
foreach ($name in @("speechmatics", "typecast")) {
  if ((Test-Path "$K\$name") -and ((Get-Item "$K\$name").Length -gt 0)) { Ok "$name 이미 있음"; continue }
  if (-not $interactive) { continue }
  $val = Read-Host "   $name 키 붙여넣고 엔터 (건너뛰려면 그냥 엔터)"
  if ($val) { [IO.File]::WriteAllText("$K\$name", $val.Trim() + "`n", (New-Object System.Text.UTF8Encoding $false)); Ok "$name 저장" } else { Warn "$name 건너뜀 — 나중에 $K\$name 에 넣으면 된다" }
}
New-Item -ItemType Directory -Force -Path "$HOME\.youstudio" | Out-Null
[IO.File]::WriteAllText("$HOME\.youstudio\env", "YOUSTUDIO_TOKEN=$토큰`n", (New-Object System.Text.UTF8Encoding $false))
[Environment]::SetEnvironmentVariable("YOUSTUDIO_TOKEN", $토큰, "User")
Ok "토큰 → 사용자 환경변수 YOUSTUDIO_TOKEN (러너가 읽는다)"

# ── 7. Claude Code 에 붙이기 ─────────────────────────────────
Say "7/8 Claude Code ← 유스튜디오 (claude mcp add · 토큰 + 설치 id 헤더)"
Push-Location "$자리\서버\runner"; node 설치도우미.mjs $토큰 --서버 $서버 --붙이기; if ($LASTEXITCODE -ne 0) { Warn "붙이기 실패 — 위 명령을 직접 붙여넣어라" }; Pop-Location

# ── 8. 프리미어 + CEP 확장 ───────────────────────────────────
Say "8/8 프리미어 · CEP 확장(com.volcano.prproj · 레지스트리 PlayerDebugMode)"
& "$venv\Scripts\python.exe" "$자리\서버\runner\린박스\도구\프리미어깔기.py" --쓰기
if ($LASTEXITCODE -ne 0) { Warn "프리미어 길이 아직 안 열렸다 — 위 ★ 줄을 보라(프리미어가 없으면 설치 뒤 다시)" }

Say "끝. 이제:  cd `"$자리`" ; claude   →  /mcp 에서 youstudio · 연결됨 확인 → «린박스 EP01 시작» 처럼 말하면 서버가 순서대로 지시한다"
Write-Host "   러너 실행기: $venv\Scripts\python.exe `"$자리\서버\runner\린박스\실행기.py`" --url $서버 --state <상태.json> --source <드라마.mp4> --title <작품> --workdir <드라마 폴더> --ep EP01 --start <초> --end <초> --repo `"$자리`""
