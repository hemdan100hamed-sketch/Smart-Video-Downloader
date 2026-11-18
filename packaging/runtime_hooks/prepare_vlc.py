# -*- coding: utf-8 -*-
"""Prepare bundled VLC native runtime before the application imports python-vlc."""
from __future__ import print_function
import os
import sys

if getattr(sys, "frozen", False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
else:
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

vlc_dir = os.path.join(app_dir, "vlc")
if not os.path.isdir(vlc_dir):
    candidate = os.path.join(getattr(sys, "_MEIPASS", app_dir), "vlc")
    if os.path.isdir(candidate):
        vlc_dir = candidate

if os.path.isdir(vlc_dir):
    os.environ["VLC_PLUGIN_PATH"] = os.path.join(vlc_dir, "plugins")
    os.environ["PATH"] = vlc_dir + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(vlc_dir)
        except (OSError, AttributeError):
            pass
