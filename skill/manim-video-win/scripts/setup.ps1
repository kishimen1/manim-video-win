# manim-video-win のセットアップ（Windows 10/11, x64）
#
# 動画づくりに必要なツールを、管理者権限なしでユーザー領域に入れ、スキルを Codex に登録する。
# 何度実行してもよい（入っているものは飛ばす）。
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1 [-SkipVoices] [-SkipAivis] [-SkipLatex] [-Root <フォルダ>]
#
# 入るもの
#   uv + Python 3.12 + Manim     %USERPROFILE%\.local\bin, %APPDATA%\uv
#   ffmpeg / TinyTeX / AivisSpeech  <Root>（既定 %LOCALAPPDATA%\manim-video。日本語を含むなら C:\Users\Public\manim-video）
#   スキル本体                    %USERPROFILE%\.agents\skills\manim-video-win
param(
  [switch]$SkipVoices,
  [switch]$SkipAivis,
  [switch]$SkipLatex,
  [string]$Root = ""
)

# 外部コマンドが標準エラーに進捗を書くだけで止まらないよう Continue にし、失敗は終了コードとファイルの有無で判定する
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"   # 進捗表示を切ると Invoke-WebRequest が大幅に速くなる
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---- 取得先（更新するときはここを変える） ----
$FFMPEG_URL  = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-win64-gpl-8.1.zip"
$TINYTEX_URL = "https://github.com/rstudio/tinytex-releases/releases/download/daily/TinyTeX-1-windows.exe"
$AIVIS_URL   = "https://github.com/Aivis-Project/AivisSpeech/releases/download/1.0.0/AivisSpeech-Windows-x64-1.0.0.zip"
$UV_INSTALL  = "https://astral.sh/uv/install.ps1"
$TEX_PKGS = @("standalone", "preview", "doublestroke", "setspace", "rsfs", "relsize", "ragged2e",
  "fundus-calligra", "microtype", "wasysym", "physics", "jknapltx", "wasy", "cm-super", "babel-english",
  "gnu-freefont", "mathastext", "cbfonts-fd", "dvisvgm")
# 追加の声（AivisHub のモデル UUID）: fumifumi / 阿井田 茂 / Lux。既定の「まお」はエンジンが最初に自動で入れる
$VOICES = @("71e72188-2726-4739-9aa9-39567396fb2a", "47e53151-a378-46f3-abee-ce13aa07feb1",
  "3dabea2b-cc10-41da-955b-4618ce84e716")

$SkillName = "manim-video-win"
$SrcSkill = Split-Path -Parent $PSScriptRoot
$Step = 0
$Total = 7

function Step($msg) { $script:Step++; Write-Host ""; Write-Host "[$script:Step/$Total] $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !   $msg" -ForegroundColor Yellow }
function IsAscii($s) { return -not ($s -match "[^\x00-\x7F]") }

function Download($url, $out) {
  Write-Host "  ダウンロード中: $url"
  for ($i = 1; $i -le 3; $i++) {
    try { Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -ErrorAction Stop; return }
    catch {
      if ($i -eq 3) { throw "ダウンロードに失敗しました: $url`n$($_.Exception.Message)" }
      Write-Host "  失敗したので再試行します（$i/3）..."; Start-Sleep -Seconds 5
    }
  }
}

function Unzip($zip, $dest) {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [IO.Compression.ZipFile]::ExtractToDirectory($zip, $dest)
}

if (-not [Environment]::Is64BitOperatingSystem) { throw "64 ビット版の Windows が必要です" }

# ---- 置き場所を決める（LaTeX は日本語を含むパスで失敗するため、英数字だけの場所にする） ----
if (-not $Root) {
  $Root = Join-Path $env:LOCALAPPDATA "manim-video"
  if (-not (IsAscii $Root)) { $Root = Join-Path $env:PUBLIC "manim-video" }
}
$Work = Join-Path $env:USERPROFILE "manim-videos"
if (-not (IsAscii $Work)) { $Work = Join-Path $env:PUBLIC "manim-videos" }
New-Item -ItemType Directory -Force -Path $Root, $Work | Out-Null
$Tmp = Join-Path $Root "download"
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
Write-Host "ツールの場所: $Root"
Write-Host "動画の作業フォルダ: $Work"

# ---- 1. uv（Python の管理ツール）と Manim ----
Step "uv と Manim（Python 3.12 も自動で入ります）"
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
if (-not (Test-Path $uv)) {
  $installer = Join-Path $Tmp "uv-install.ps1"
  Download $UV_INSTALL $installer
  & powershell -NoProfile -ExecutionPolicy Bypass -File $installer
  if (-not (Test-Path $uv)) { throw "uv のインストールに失敗しました" }
}
Ok (& $uv --version)
& $uv python install 3.12
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 の取得に失敗しました" }
$tools = & $uv tool list
if (-not ($tools -match "^manim ")) {
  & $uv tool install --python 3.12 manim
  if ($LASTEXITCODE -ne 0) { throw "Manim のインストールに失敗しました" }
}
Ok "Manim"

# ---- 2. ffmpeg ----
Step "ffmpeg（動画と音声の合成）"
$ffmpeg = Join-Path $Root "ffmpeg\bin\ffmpeg.exe"
if (-not (Test-Path $ffmpeg)) {
  $zip = Join-Path $Tmp "ffmpeg.zip"
  Download $FFMPEG_URL $zip
  $x = Join-Path $Tmp "ffmpeg-x"
  if (Test-Path $x) { Remove-Item $x -Recurse -Force }
  Unzip $zip $x
  $inner = Get-ChildItem $x -Directory | Select-Object -First 1
  if (Test-Path (Join-Path $Root "ffmpeg")) { Remove-Item (Join-Path $Root "ffmpeg") -Recurse -Force }
  Move-Item $inner.FullName (Join-Path $Root "ffmpeg") -ErrorAction Stop
  Remove-Item $zip, $x -Recurse -Force
}
Ok $ffmpeg

# ---- 3. LaTeX（数式） ----
Step "LaTeX / TinyTeX（数式の表示）"
$tlmgr = Join-Path $Root "TinyTeX\bin\windows\tlmgr.bat"
if ($SkipLatex) { Warn "飛ばしました（数式 MathTex は使えません）" }
else {
  if (-not (Test-Path $tlmgr)) {
    $exe = Join-Path $Tmp "TinyTeX-1-windows.exe"
    Download $TINYTEX_URL $exe
    Unblock-File $exe
    # 7-Zip 自己展開形式。<Root>\TinyTeX に展開される（終わるまで待つ）
    Start-Process -FilePath $exe -ArgumentList @("-y", "-o`"$Root`"") -Wait -NoNewWindow
    Remove-Item $exe -Force
    if (-not (Test-Path $tlmgr)) { throw "TinyTeX の展開に失敗しました" }
  }
  Write-Host "  数式用のパッケージを確認しています（初回は数分かかります）..."
  & $tlmgr install @TEX_PKGS | Out-Null
  if (-not (Test-Path (Join-Path $Root "TinyTeX\bin\windows\dvisvgm.exe"))) {
    Warn "数式用パッケージの一部が入っていない可能性があります（最後の診断で確認します）"
  }
  Ok (Join-Path $Root "TinyTeX")
}

# ---- 4. AivisSpeech（音声合成） ----
Step "AivisSpeech（ナレーションの音声）"
$engine = Join-Path $Root "AivisSpeech\AivisSpeech-Engine\run.exe"
if ($SkipAivis) { Warn "飛ばしました（Windows 標準音声 --engine sapi を使えます）" }
elseif (-not (Test-Path $engine)) {
  $zip = Join-Path $Tmp "aivisspeech.zip"
  Download $AIVIS_URL $zip   # 約 390 MB
  if (Test-Path (Join-Path $Root "AivisSpeech")) { Remove-Item (Join-Path $Root "AivisSpeech") -Recurse -Force }
  Write-Host "  展開しています..."
  Unzip $zip $Root   # zip の中身は AivisSpeech\ フォルダ
  Remove-Item $zip -Force
  Get-ChildItem (Join-Path $Root "AivisSpeech") -Recurse -File | Unblock-File
  if (-not (Test-Path $engine)) { throw "AivisSpeech の展開に失敗しました" }
}
if (-not $SkipAivis) { Ok $engine }

# ---- 5. スキルを Codex に登録 ----
Step "スキルを Codex に登録"
$skillsDir = Join-Path $env:USERPROFILE ".agents\skills"
$Dest = Join-Path $skillsDir $SkillName
New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
if ((Resolve-Path $SrcSkill).Path -ne $Dest) {
  if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
  Copy-Item $SrcSkill $Dest -Recurse -ErrorAction Stop
}
Get-ChildItem $Dest -Recurse -File | Unblock-File
$cfg = [ordered]@{ root = $Root; work = $Work }
[IO.File]::WriteAllText((Join-Path $Dest "tools.json"), ($cfg | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
$build = Join-Path $Dest "scripts\build.cmd"
Ok $Dest

# ---- 6. 声の準備 ----
Step "声の準備（初回はエンジンが声を取得するため数分かかります）"
Push-Location $Root
try {
  if ($SkipAivis) { Warn "AivisSpeech を飛ばしたので省略" }
  else {
    & $build voices | Out-Null
    if ($LASTEXITCODE -ne 0) { Warn "AivisSpeech エンジンの起動に失敗しました（最後の診断で確認します）" }
    elseif (-not $SkipVoices) {
      foreach ($v in $VOICES) {
        & $build install-voice $v
        if ($LASTEXITCODE -ne 0) { Warn "声 $v を追加できませんでした（あとから追加できます）" }
      }
    }
  }
} finally { Pop-Location }

# ---- 7. 診断 ----
Step "動作の確認"
Push-Location $Work
try { & $build doctor; $ok = ($LASTEXITCODE -eq 0) } finally { Pop-Location }
if (Test-Path $Tmp) { Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host ""
if ($ok) {
  Write-Host "セットアップが終わりました。" -ForegroundColor Green
  Write-Host "Codex を開き直して、たとえば「3b1b風の動画で三平方の定理を解説して」と頼んでください。"
  Write-Host "動画は $Work の中に作られます。"
} else {
  Write-Host "一部うまく入っていません。上の NG の案内を確認し、もう一度 setup.bat を実行してください。" -ForegroundColor Yellow
  exit 1
}
