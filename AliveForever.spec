# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


# SPECPATH is where this file lives, so the build no longer depends on the
# directory it happens to be invoked from.
project_dir = Path(SPECPATH).resolve()
icon_file = project_dir / "icon.ico"

if not icon_file.exists():
    raise SystemExit(
        "icon.ico is missing. Run `python create_icon.py` first "
        "(build.ps1 does this for you)."
    )

datas = [(str(project_dir / "icon.png"), ".")]
hiddenimports = ["pystray._win32", "PIL._tkinter_finder"]

# Pillow and pystray declare these as optional dependencies, so PyInstaller
# pulls them in even though nothing here imports them. numpy alone -- with its
# bundled OpenBLAS -- was around 27 MB of a 71 MB build.
excludes = [
    "numpy",
    "scipy",
    "pandas",
    "matplotlib",
    "psutil",
    "IPython",
    "pytest",
    "setuptools",
    "pydoc_data",
    "PIL.ImageQt",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    # The tray icon is drawn with rectangles, lines and ellipses only, so
    # Pillow's image codecs are never reached. _avif alone was 7.5 MB.
    # PIL.ImageFont must NOT be excluded: ImageDraw imports ImageText, which
    # imports ImageFont at module level, so dropping it breaks icon drawing.
    "PIL.AvifImagePlugin",
    "PIL.WebPImagePlugin",
    "PIL.ImageCms",
    "PIL.ImageShow",
]

a = Analysis(
    [str(project_dir / "keep_alive.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AliveForever",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX is deliberately off. UPX-packed PyInstaller binaries are a reliable
    # Defender heuristic trigger, and an app that synthesises keyboard input is
    # already starting from an unfavourable prior. The size saving is not worth
    # the false positives.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AliveForever",
)
