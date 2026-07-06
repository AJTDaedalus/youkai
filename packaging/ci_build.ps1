# ci_build.ps1 — CI build path for youkai portable bundle.
# Run from the repo root on a windows-latest runner (repo is already on local NTFS):
#   powershell -ExecutionPolicy Bypass -File packaging\ci_build.ps1 -Version 0.2.0
#
# Unlike build_local.ps1 there is no WSL rsync dance: the GitHub Actions checkout
# already lands the repo on a local NTFS path, so PyInstaller and cargo run in-place.
param(
    [Parameter(Mandatory=$true)]
    [string]$Version,

    [string]$Out = "youkai-portable"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot | Split-Path   # packaging\ -> repo root

Write-Host "=== ci_build.ps1 — youkai $Version ===" -ForegroundColor Cyan
Write-Host ""

# ── 1. Stamp __version__ with the release tag ────────────────────────────────
# Get the short SHA for the build-metadata suffix.
$GitSha = (git -C $RepoRoot rev-parse --short HEAD 2>$null).Trim()
if (-not $GitSha) { $GitSha = "ci" }
$FullVersion = "$Version+$GitSha"

$InitFile = Join-Path $RepoRoot "src\youkai_ocr\__init__.py"
$content  = Get-Content $InitFile -Raw
$patched  = $content -replace '(__version__ = ")[^"]*(")', "`${1}$FullVersion`${2}"
Set-Content $InitFile $patched -NoNewline
Write-Host "Stamped __version__ = `"$FullVersion`"" -ForegroundColor Green

# ── 2. Build Rust GUI exe ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== cargo build --release ===" -ForegroundColor Cyan
cargo build --release --manifest-path (Join-Path $RepoRoot "youkai\Cargo.toml")
if ($LASTEXITCODE -ne 0) { Write-Error "cargo build failed." }

# ── 3. Build Python scanner with PyInstaller ─────────────────────────────────
Write-Host ""
Write-Host "=== PyInstaller ===" -ForegroundColor Cyan
python -m PyInstaller (Join-Path $RepoRoot "packaging\youkai.spec") --clean -y
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller failed." }

# ── 4. Exe version gate ───────────────────────────────────────────────────────
$ExePath = Join-Path $RepoRoot "dist\youkai-ocr\youkai-ocr.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "youkai-ocr.exe not found at $ExePath after build."
}
$ExeVersion = (& $ExePath --version 2>&1).Trim()
Write-Host "Exe reports: $ExeVersion"
if ($ExeVersion -notlike "*$Version*") {
    Write-Error "Version mismatch: exe reports '$ExeVersion', expected '$Version'. Aborting."
}
Write-Host "Version gate passed." -ForegroundColor Green

# ── 5. Ensure Tesseract ───────────────────────────────────────────────────────
$TesseractDest = Join-Path $RepoRoot "dist\youkai-ocr\tesseract"
if (-not (Test-Path (Join-Path $TesseractDest "tesseract.exe"))) {
    Write-Host "Tesseract not found — downloading..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass `
        -File (Join-Path $RepoRoot "packaging\get_tesseract.ps1") `
        -Dest $TesseractDest
    if ($LASTEXITCODE -ne 0) { Write-Error "Tesseract download failed." }
}

# ── 6. Assemble portable folder ───────────────────────────────────────────────
Write-Host ""
Write-Host "=== Assembling portable folder ===" -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass `
    -File (Join-Path $RepoRoot "packaging\assemble.ps1") -Out $Out
if ($LASTEXITCODE -ne 0) { Write-Error "assemble.ps1 failed." }

$OutDir = Join-Path $RepoRoot $Out

# ── 7. Stage provenance files (D-LICENSE, D-CICD-3) ──────────────────────────
Copy-Item (Join-Path $RepoRoot 'LICENSE')                (Join-Path $OutDir 'LICENSE')
Copy-Item (Join-Path $RepoRoot 'THIRD_PARTY_NOTICES.md') (Join-Path $OutDir 'THIRD_PARTY_NOTICES.md')
Copy-Item (Join-Path $RepoRoot 'DISCLAIMER.md')          (Join-Path $OutDir 'DISCLAIMER.md')

# ── 8. Smoke test ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Smoke test ===" -ForegroundColor Cyan
& (Join-Path $OutDir "youkai-ocr\youkai-ocr.exe") --help | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "youkai-ocr.exe --help failed." }

foreach ($f in @('LICENSE', 'THIRD_PARTY_NOTICES.md', 'DISCLAIMER.md')) {
    if (-not (Test-Path (Join-Path $OutDir $f))) {
        Write-Error "Provenance file missing from bundle: $f"
    }
}
Write-Host "Smoke test passed." -ForegroundColor Green

# ── 9. Zip + SHA256 ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Packaging zip ===" -ForegroundColor Cyan
$ZipName = "youkai-portable-$Version.zip"
$ZipPath = Join-Path $RepoRoot $ZipName
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $OutDir '*') -DestinationPath $ZipPath

$Hash = (Get-FileHash $ZipPath -Algorithm SHA256).Hash.ToLower()
$Sha256Path = "$ZipPath.sha256"
Set-Content $Sha256Path "$Hash  $ZipName" -NoNewline

Write-Host "Zip:    $ZipPath" -ForegroundColor Green
Write-Host "SHA256: $Hash"
Write-Host ""
Write-Host "=== ci_build.ps1 complete ===" -ForegroundColor Green
