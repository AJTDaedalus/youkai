@echo off
:: Assembles the youkai-portable\ folder from build outputs.
:: Run from the repo root after:
::   1. cargo build --release  (produces youkai\target\release\youkai.exe)
::   2. pyinstaller packaging\youkai-ocr.spec  (produces dist\youkai-ocr\)
::   3. Copy UB-Mannheim Tesseract into dist\youkai-ocr\tesseract\
::        (see RUNBOOK.md "Bundle Tesseract" for the required layout)
::
:: Usage:
::   packaging\assemble.bat [OUTPUT_DIR]
:: Output dir defaults to .\youkai-portable\

setlocal EnableDelayedExpansion

set "OUT=%~1"
if "%OUT%"=="" set "OUT=youkai-portable"

set "GUI_EXE=youkai\target\release\youkai.exe"
set "SCANNER_DIR=dist\youkai-ocr"
set "TESSERACT_DIR=dist\youkai-ocr\tesseract"

echo.
echo === youkai portable assembler ===
echo Output: %OUT%\
echo.

:: --- Preflight checks ---

if not exist "%GUI_EXE%" (
    echo ERROR: %GUI_EXE% not found.
    echo Run: cargo build --release  (inside the youkai\ directory on Windows^)
    exit /b 1
)

if not exist "%SCANNER_DIR%\youkai-ocr.exe" (
    echo ERROR: %SCANNER_DIR%\youkai-ocr.exe not found.
    echo Run: pyinstaller packaging\youkai-ocr.spec
    exit /b 1
)

if not exist "%TESSERACT_DIR%\tesseract.exe" (
    echo Tesseract not found — running get_tesseract.ps1 to download it...
    powershell -ExecutionPolicy Bypass -File "packaging\get_tesseract.ps1" -Dest "%TESSERACT_DIR%"
    if errorlevel 1 ( echo ERROR: Tesseract download failed. & exit /b 1 )
)

:: --- Assemble ---

if exist "%OUT%" (
    echo Removing existing %OUT%\ ...
    rd /s /q "%OUT%"
)

echo Copying GUI exe...
md "%OUT%"
copy /y "%GUI_EXE%" "%OUT%\youkai.exe" >nul

echo Copying scanner (onedir)...
xcopy /e /i /q "%SCANNER_DIR%" "%OUT%\youkai-ocr\" >nul

echo Creating empty export\ directory...
md "%OUT%\export"

echo.
echo === Assembly complete ===
echo.
echo Layout:
echo   %OUT%\youkai.exe
echo   %OUT%\youkai-ocr\youkai-ocr.exe
echo   %OUT%\youkai-ocr\_internal\
echo   %OUT%\youkai-ocr\tesseract\tesseract.exe
echo   %OUT%\youkai-ocr\tesseract\tessdata\eng.traineddata
echo   %OUT%\export\
echo.
echo Next: smoke-test on a machine with no dev Python and no installed Tesseract.
echo   %OUT%\youkai.exe
echo   -- or --
echo   %OUT%\youkai-ocr\youkai-ocr.exe --help
echo.
endlocal
