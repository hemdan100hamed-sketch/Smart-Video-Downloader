# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
BUILD_SCRIPT = os.path.join(ROOT, "build", "Smart_Video_Downloader_2.5.3_Windows.py")
VENDOR = os.path.join(ROOT, "vendor")
YTDLP_VENDOR = os.path.join(VENDOR, "yt-dlp-source")
CURL_VENDOR = os.path.join(VENDOR, "curlcffi")
VLC_VENDOR = os.path.join(VENDOR, "vlc")
FFMPEG_VENDOR = os.path.join(VENDOR, "ffmpeg")

required = [
    os.path.join(YTDLP_VENDOR, "yt_dlp", "__init__.py"),
    os.path.join(CURL_VENDOR, "curl_cffi", "__init__.py"),
    os.path.join(VLC_VENDOR, "libvlc.dll"),
    os.path.join(VLC_VENDOR, "plugins"),
    os.path.join(FFMPEG_VENDOR, "bin", "ffmpeg.exe"),
]
missing = [path for path in required if not os.path.exists(path)]
if missing:
    raise SystemExit("Required runtime component missing: " + "; ".join(missing))

sys.path.insert(0, YTDLP_VENDOR)
sys.path.insert(0, CURL_VENDOR)

datas = [
    (YTDLP_VENDOR, "vendor/yt-dlp-source"),
    (CURL_VENDOR, "vendor/curlcffi"),
    (VLC_VENDOR, "vlc"),
    (FFMPEG_VENDOR, "ffmpeg"),
]
binaries = []
hiddenimports = ["vlc"]

for package_name in ("yt_dlp", "curl_cffi", "PIL", "tkinterdnd2"):
    package_datas, package_binaries, package_hidden = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [BUILD_SCRIPT],
    pathex=[ROOT, YTDLP_VENDOR, CURL_VENDOR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(ROOT, "packaging", "runtime_hooks", "prepare_vlc.py")],
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
