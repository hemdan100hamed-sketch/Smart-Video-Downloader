# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
BUILD_SCRIPT = os.path.join(ROOT, "build", "Smart_Video_Downloader_2.5.3_Windows.py")
VENDOR = os.path.join(ROOT, "vendor")
sys.path.insert(0, os.path.join(VENDOR, "yt-dlp-source"))
sys.path.insert(0, os.path.join(VENDOR, "curlcffi"))

datas = [
    (os.path.join(VENDOR, "yt-dlp-source"), "vendor/yt-dlp-source"),
    (os.path.join(VENDOR, "curlcffi"), "vendor/curlcffi"),
]
binaries = []
hiddenimports = []

for package_name in ("yt_dlp", "curl_cffi"):
    package_datas, package_binaries, package_hidden = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

for package_name in ("PIL", "tkinterdnd2", "vlc"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package_name)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
    except Exception:
        pass

a = Analysis(
    [BUILD_SCRIPT],
    pathex=[ROOT, os.path.join(VENDOR, "yt-dlp-source"), os.path.join(VENDOR, "curlcffi")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SmartVideoDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="SmartVideoDownloader",
)
