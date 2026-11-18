# Smart Video Downloader 2.5.3 — Windows packaging

## Target and build method

The first deliverable is an onedir portable application, not a single-file EXE.
Build it on Windows with 64-bit Python 3.8 and PyInstaller 5.13.2. This keeps
the first packaging pass aligned with the project's previously tested
Windows 7 SP1 / Python 3.8 environment. The generated folder can later be
wrapped in an installer.

The preparation step creates a separate build copy and changes only the
hard-coded development library paths. The tested application source is not
modified.

## Required vendor files

The app currently loads yt-dlp and curl_cffi dynamically from local folders.
Those dependencies are not stored in this repository. Copy the exact tested
folders from the Windows development machine:

- C:\SmartVideo\yt-dlp-source to vendor\yt-dlp-source
  (must contain yt_dlp\__init__.py).
- C:\SmartVideo\curlcffi-test\installed to vendor\curlcffi.
- Keep the exact tested versions. Do not replace them with latest packages.

The application can locate FFmpeg in its application folder or under the
yt-dlp vendor folder. Include the tested ffmpeg.exe and required DLLs if MP3
conversion and frame-preview functions are to be part of the distribution.

The standalone player uses python-vlc and the VLC native runtime. The Python
binding alone does not contain libvlc or its plugins. A matching VLC runtime
must also be installed or packaged and tested on target computers. This first
build recipe does not claim that the VLC runtime is bundled.

## Build

1. Use a Windows machine with 64-bit Python 3.8 installed.
2. Place the two tested dependency folders in the exact vendor paths above.
3. Run packaging\build_windows.bat.
4. Output: dist\SmartVideoDownloader\SmartVideoDownloader.exe plus supporting
   files. Distribute the entire folder, not the EXE by itself.

## Compatibility validation — required before release

A successful PyInstaller build does not prove Windows 7–11 compatibility.
Test the complete output folder on clean machines or VMs for:

- Windows 7 SP1 x64
- Windows 8 / 8.1
- Windows 10
- Windows 11

On each system verify startup, URL inspection, a real video download, custom
filename handling for single and queued downloads, queue completion/failure
reporting, MP3 conversion, thumbnail and frame preview, drag-and-drop, and
player playback. Record optional features separately if a required native
runtime is not installed.

Do not label the release compatible with all target Windows versions until
the Windows 7 SP1 test has passed. Some modern websites and TLS/security
requirements may also stop working on an unsupported operating system even
when the application itself starts.

## Next packaging stage

After the onedir folder passes the compatibility matrix, create and test an
Inno Setup installer with shortcuts, install/uninstall support, and
preservation of the user's settings and download folder.
