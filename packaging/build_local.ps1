# build_local.ps1 — Build youkai-ocr.exe locally (never over UNC) and assemble
# the portable folder. Run from the repo root on Windows:
#   powershell -ExecutionPolicy Bypass -File packaging\build_local.ps1
#
# WHY WSL rsync instead of robocopy: robocopy reading from \\wsl.localhost\ UNC
# stalls indefinitely due to the WSL UNC-mount driver. Instead we call `wsl rsync`
# to copy entirely inside WSL, writing to /mnt/c/... (= C:\). PyInstaller then
# only ever reads true local NTFS paths, which also avoids the stale-.pyc class.
param(
    [string]$BuildRoot = "C:\Temp\youkai-build",
    [string]$Out       = "youkai-portable"
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot | Split-Path   # packaging\ -> repo root

# ── 1. Get git SHA for version stamp ─────────────────────────────────────────
# Use `wsl git` — Windows git refuses UNC (\\wsl.localhost\) paths due to
# safe.directory checks. WSL git runs in the Linux context where the path is trusted.
$GitSha = (wsl git -C /root/youkai rev-parse --short HEAD 2>$null).Trim()
if (-not $GitSha) {
    # Fallback: try native git with safe.directory override
    $GitSha = (git -C $RepoRoot --no-pager -c safe.directory=* rev-parse --short HEAD 2>$null).Trim()
}
if (-not $GitSha) { $GitSha = "unknown" }
$Version = "0.2.0+$GitSha"
Write-Host "Build version: $Version" -ForegroundColor Cyan

# ── 2. Copy repo to local temp via wsl rsync (avoids UNC stall) ──────────────
# Convert C:\Temp\youkai-build to /mnt/c/Temp/youkai-build for WSL.
$BuildRootWsl = "/mnt/" + $BuildRoot.Substring(0,1).ToLower() + $BuildRoot.Substring(2).Replace("\", "/")
Write-Host ""
Write-Host "=== Copying repo to $BuildRoot (via wsl rsync) ===" -ForegroundColor Cyan
wsl bash -c "rm -rf '$BuildRootWsl' && mkdir -p '$BuildRootWsl' && rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.egg-info' --exclude='youkai/target' --exclude='archive' --exclude='screenshots' --exclude='dist' --exclude='build' --exclude='youkai-portable' /root/youkai/ '$BuildRootWsl/'"
if ($LASTEXITCODE -ne 0) { Write-Error "wsl rsync failed." }

# ── 3. Patch __version__ with the real SHA ───────────────────────────────────
$InitFile = Join-Path $BuildRoot "src\youkai_ocr\__init__.py"
$content  = Get-Content $InitFile -Raw
# Replace the sentinel line exactly — the comment above it tags the line.
$patched  = $content -replace '(__version__ = "0\.2\.0\+)[^"]*(")', "`${1}$GitSha`${2}"
Set-Content $InitFile $patched -NoNewline
Write-Host "Patched __version__ = `"$Version`" in $InitFile" -ForegroundColor Green

# ── 4. Build with PyInstaller (--clean to ignore any stale .spec cache) ───────
Write-Host ""
Write-Host "=== Running PyInstaller ===" -ForegroundColor Cyan
Push-Location $BuildRoot
python -m PyInstaller packaging\youkai.spec --clean -y
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "PyInstaller failed." }
Pop-Location

# ── 5. Version gate — abort if exe reports wrong id ──────────────────────────
$ExePath = Join-Path $BuildRoot "dist\youkai-ocr\youkai-ocr.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "youkai-ocr.exe not found at $ExePath after build."
}
Write-Host ""
Write-Host "=== Verifying freshness ===" -ForegroundColor Cyan
$ExeVersion = (& $ExePath --version 2>&1).Trim()
Write-Host "Exe reports: $ExeVersion"
if ($ExeVersion -notlike "*$Version*") {
    Write-Error "Version mismatch: exe reports '$ExeVersion', expected '$Version'. Aborting."
}
Write-Host "Version gate passed." -ForegroundColor Green

# ── 6. Stage the GUI exe for assemble.ps1 ────────────────────────────────────
# assemble.ps1 looks for youkai/target/release/youkai.exe (inside the build root).
# youkai/target is excluded from the rsync (17 GB); copy the pre-built exe from
# the repo root if it exists, otherwise require a cargo build first.
$GuiExeSrc = Join-Path $RepoRoot "youkai.exe"
$GuiExeDst = Join-Path $BuildRoot "youkai\target\release\youkai.exe"
if (Test-Path $GuiExeSrc) {
    New-Item -ItemType Directory -Force -Path (Split-Path $GuiExeDst) | Out-Null
    Copy-Item $GuiExeSrc $GuiExeDst
    Write-Host "Staged GUI exe from repo root." -ForegroundColor Green
} else {
    Write-Error ("youkai.exe not found at $GuiExeSrc.`n" +
                 "Build it first: cargo build --release --manifest-path youkai/Cargo.toml")
}

# ── 7. Run assemble.ps1 using the local build outputs ────────────────────────
Write-Host ""
Write-Host "=== Assembling portable folder ===" -ForegroundColor Cyan
$AssembleScript = Join-Path $BuildRoot "packaging\assemble.ps1"
# Pass $Out as a relative name — assemble.ps1 resolves it against its own repo root
# ($BuildRoot), so passing an absolute path would double the prefix.
& powershell -ExecutionPolicy Bypass -File $AssembleScript -Out $Out
if ($LASTEXITCODE -ne 0) { Write-Error "assemble.ps1 failed." }

# ── 8. Copy assembled portable folder back to the repo ───────────────────────
$LocalOut = Join-Path $BuildRoot $Out
$RepoOut  = Join-Path $RepoRoot $Out
Write-Host ""
Write-Host "=== Copying portable folder back to repo ===" -ForegroundColor Cyan
if (Test-Path $RepoOut) {
    Remove-Item -Recurse -Force $RepoOut
}
Copy-Item $LocalOut $RepoOut -Recurse

# ── 9. Zip the portable folder for release ───────────────────────────────────
# Stage license + notices + disclaimer INTO the portable folder so they ship inside the zip (see D-LICENSE, D-CICD-3).
Copy-Item (Join-Path $RepoRoot 'LICENSE') (Join-Path $RepoOut 'LICENSE')
Copy-Item (Join-Path $RepoRoot 'THIRD_PARTY_NOTICES.md') (Join-Path $RepoOut 'THIRD_PARTY_NOTICES.md')
Copy-Item (Join-Path $RepoRoot 'DISCLAIMER.md') (Join-Path $RepoOut 'DISCLAIMER.md')
$ZipPath = Join-Path $RepoRoot "youkai-portable.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $RepoOut '*') -DestinationPath $ZipPath
Write-Host "Release zip: $ZipPath" -ForegroundColor Green

Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Green
Write-Host "Portable folder: $RepoOut"
Write-Host "Release zip:     $ZipPath"
Write-Host ""
Write-Host "Verification steps (paste output back):"
Write-Host "  $RepoOut\youkai-ocr\youkai-ocr.exe --version"
Write-Host "  $RepoOut\youkai-ocr\youkai-ocr.exe scan-all"
