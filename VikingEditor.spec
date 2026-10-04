# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


project_dir = Path(SPECPATH)


unitypy_datas, unitypy_binaries, unitypy_hiddenimports = collect_all(
    "UnityPy"
)

data_hiddenimports = collect_submodules("data")


a = Analysis(
    ["main.py"],
    pathex=[str(project_dir)],
    binaries=unitypy_binaries,
    datas=[
        ("assets", "assets"),
        *unitypy_datas,
    ],
    hiddenimports=[
        *unitypy_hiddenimports,
        *data_hiddenimports,
    ],
    hookspath=[str(project_dir / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VikingEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
