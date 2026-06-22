# Locates tesseract.exe + tessdata/eng.traineddata and copies them to $Dest.
# Checks in order: existing install at Program Files, PATH, then downloads installer.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File packaging\get_tesseract.ps1
param(
    [string]$Dest = "dist\youkai-ocr\tesseract"
)

$ErrorActionPreference = "Stop"

$tessExe = Join-Path $Dest "tesseract.exe"
$engData = Join-Path $Dest "tessdata\eng.traineddata"

if ((Test-Path $tessExe) -and (Test-Path $engData)) {
    Write-Host "Tesseract already present at $Dest - skipping." -ForegroundColor Green
    exit 0
}

# --- locate an existing Tesseract install ---

function Find-TesseractDir {
    # 1. Standard UB-Mannheim install location
    $candidate = "C:\Program Files\Tesseract-OCR"
    if (Test-Path (Join-Path $candidate "tesseract.exe")) { return $candidate }

    # 2. 32-bit install on 64-bit Windows
    $candidate = "C:\Program Files (x86)\Tesseract-OCR"
    if (Test-Path (Join-Path $candidate "tesseract.exe")) { return $candidate }

    # 3. Registry
    $regPaths = @(
        "HKLM:\SOFTWARE\Tesseract-OCR",
        "HKLM:\SOFTWARE\WOW6432Node\Tesseract-OCR"
    )
    foreach ($rp in $regPaths) {
        if (Test-Path $rp) {
            $val = (Get-ItemProperty $rp -ErrorAction SilentlyContinue).InstallDir
            if ($val -and (Test-Path (Join-Path $val "tesseract.exe"))) { return $val }
        }
    }

    # 4. PATH
    $onPath = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($onPath) { return (Split-Path $onPath.Source) }

    return $null
}

$src = Find-TesseractDir

if ($src) {
    Write-Host "Found Tesseract at $src - copying files..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    # Copy the full install dir so all DLLs (libleptonica, libtesseract, etc.) are present.
    # A partial copy (exe + tessdata only) causes DLL-not-found errors at runtime.
    Copy-Item (Join-Path $src "*") $Dest -Recurse -Force
    Write-Host "Done - Tesseract ready at $Dest" -ForegroundColor Green
    exit 0
}

# --- no existing install: download ---

Write-Host "No Tesseract install found - downloading UB-Mannheim release..." -ForegroundColor Cyan
$rel   = Invoke-RestMethod "https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"
$asset = $rel.assets | Where-Object { $_.name -match "w64-setup" } | Select-Object -First 1
if (-not $asset) { Write-Error "No w64-setup asset found in latest release."; exit 1 }

$installer = Join-Path $env:TEMP $asset.name
Write-Host "Downloading $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB)..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installer -UseBasicParsing

# Install to a fresh temp dir with a name the NSIS installer has never seen
$tmp    = Join-Path $env:TEMP ("tess_portable_" + [System.Guid]::NewGuid().ToString("N"))
$absTmp = $tmp   # must be absolute for NSIS /D=
New-Item -ItemType Directory -Force -Path $absTmp | Out-Null

Write-Host "Installing to temp dir $absTmp ..." -ForegroundColor Cyan
Start-Process -Wait -FilePath $installer -ArgumentList "/S", "/D=$absTmp"

if (-not (Test-Path (Join-Path $absTmp "tesseract.exe"))) {
    Write-Error "Silent install did not produce tesseract.exe in $absTmp"
    exit 1
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item (Join-Path $absTmp "*") $Dest -Recurse -Force

Remove-Item -Recurse -Force $absTmp
Remove-Item -Force $installer

Write-Host "Done - Tesseract ready at $Dest" -ForegroundColor Green
