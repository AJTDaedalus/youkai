# -*- mode: python ; coding: utf-8 -*-
#
# Build command (run from the repo root on Windows):
#
#   python -m PyInstaller packaging/youkai.spec --clean
#
# Output: dist/youkai-ocr/youkai-ocr.exe  (onedir layout)
#
# Tesseract is bundled automatically by packaging/assemble.ps1.

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT     = Path(SPECPATH).parent           # packaging/../  = repo root
SRC      = ROOT / "src"
DATA_DIR = ROOT / "data"

# Make youkai_ocr importable during spec analysis (no pip install -e . required)
sys.path.insert(0, str(SRC))

# cv2 has a native-extension bootstrapper that recurses if its DLLs are not
# all present together. collect_all gathers binaries + datas + hiddenimports.
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")

# Enumerate every youkai_ocr submodule explicitly so PyInstaller
# cannot miss any of them, regardless of import-graph analysis.
YOUKAI_MODS = [
    "youkai_ocr",
    "youkai_ocr.agent_scanner",
    "youkai_ocr.capture",
    "youkai_ocr.cli",
    "youkai_ocr.debug_overlay",
    "youkai_ocr.disc_scanner",
    "youkai_ocr.fields",
    "youkai_ocr.grid",
    "youkai_ocr.input_utils",
    "youkai_ocr.matchers",
    "youkai_ocr.normalizer",
    "youkai_ocr.progress",
    "youkai_ocr.recognize",
    "youkai_ocr.wengine_scanner",
    "youkai_ocr.zod",
]

a = Analysis(
    [str(ROOT / "packaging" / "run.py")],
    pathex=[str(SRC)],
    binaries=cv2_binaries,
    datas=[
        (str(DATA_DIR), "data"),
    ] + cv2_datas,
    hiddenimports=YOUKAI_MODS + cv2_hiddenimports + [
        "pytesseract",
        "rapidfuzz.process",
        "rapidfuzz.fuzz",
        "PIL",
        "PIL.Image",
        "PIL.ImageOps",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "win32api",
        "win32con",
        "win32gui",
        "win32process",
        "pywintypes",
        "dxcam",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_cov",
        "IPython",
        "matplotlib",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="youkai-ocr",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="youkai-ocr",
)
