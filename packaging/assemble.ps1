# Assembles the youkai-portable\ folder from build outputs.
# Run from the repo root (UNC paths supported):
#   powershell -ExecutionPolicy Bypass -File packaging\assemble.ps1
param(
    [string]$Out = "youkai-portable"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path   # packaging\ -> repo root

function Resolve-Repo([string]$rel) { Join-Path $Root $rel }

$GuiExe      = Resolve-Repo "youkai/target/release/youkai.exe"
$ScannerDir  = Resolve-Repo "dist/youkai-ocr"
$TesseractDir= Join-Path $ScannerDir "tesseract"
$OutDir      = Resolve-Repo $Out

Write-Host ""
Write-Host "=== youkai portable assembler ===" -ForegroundColor Cyan
Write-Host "Output: $OutDir"
Write-Host ""

# --- GUI exe ---
if (-not (Test-Path $GuiExe)) {
    # also check cross-compile output
    $cross = Resolve-Repo "youkai/target/x86_64-pc-windows-gnu/release/youkai.exe"
    if (Test-Path $cross) {
        Write-Host "Using cross-compiled GUI exe from $cross" -ForegroundColor Yellow
        $GuiExe = $cross
    } else {
        Write-Error "youkai.exe not found. Run: cargo build --release --manifest-path youkai/Cargo.toml"
    }
}

# --- Scanner ---
if (-not (Test-Path (Join-Path $ScannerDir "youkai-ocr.exe"))) {
    Write-Error ("dist/youkai-ocr/youkai-ocr.exe not found.`n" +
                 "Build it first: python -m PyInstaller packaging/youkai-ocr.spec --clean -y")
}

# --- Tesseract (auto-download if missing) ---
if (-not (Test-Path (Join-Path $TesseractDir "tesseract.exe"))) {
    Write-Host "Tesseract not found - downloading..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Resolve-Repo "packaging/get_tesseract.ps1") -Dest $TesseractDir
    if ($LASTEXITCODE -ne 0) { Write-Error "Tesseract download failed." }
}

# --- Assemble ---
if (Test-Path $OutDir) {
    Write-Host "Removing existing $OutDir ..."
    Remove-Item -Recurse -Force $OutDir
}

Write-Host "Copying GUI exe..."
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Copy-Item $GuiExe (Join-Path $OutDir "youkai.exe")

Write-Host "Copying scanner (onedir)..."
Copy-Item $ScannerDir (Join-Path $OutDir "youkai-ocr") -Recurse

Write-Host "Creating empty export\ ..."
New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "export") | Out-Null

Write-Host ""
Write-Host "=== Assembly complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Layout:"
Write-Host ("  " + (Join-Path $OutDir "youkai.exe"))
Write-Host ("  " + (Join-Path $OutDir "youkai-ocr\youkai-ocr.exe"))
Write-Host ("  " + (Join-Path $OutDir "youkai-ocr\_internal\"))
Write-Host ("  " + (Join-Path $OutDir "youkai-ocr\tesseract\tesseract.exe"))
Write-Host ("  " + (Join-Path $OutDir "youkai-ocr\tesseract\tessdata\eng.traineddata"))
Write-Host ("  " + (Join-Path $OutDir "export\"))
Write-Host ""
Write-Host "Smoke-test:"
Write-Host ("  " + (Join-Path $OutDir "youkai-ocr\youkai-ocr.exe") + " --help")
Write-Host ("  " + (Join-Path $OutDir "youkai.exe"))
