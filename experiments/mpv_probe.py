# -*- coding: utf-8 -*-
"""Minimal libmpv embedding probe for local files and network streams."""
import ctypes
import os
import sys
import time
import tkinter as tk
from ctypes import c_char_p, c_double, c_int, c_void_p, byref
from urllib.parse import urlparse


def fail(message):
    print("MPV_TEST_FAILED: " + message, flush=True)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("--local", "--network"):
        fail("Usage: mpv_probe.py --local <file> OR --network <url>")
    mode, target = sys.argv[1], sys.argv[2]
    if mode == "--local":
        target = os.path.abspath(target)
        if not os.path.isfile(target):
            fail("Test video does not exist: " + target)
    else:
        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            fail("Network test target must be an HTTP(S) URL")

    dll_dir = os.path.abspath(os.environ.get(
        "MPV_DLL_DIR", os.path.join(os.path.dirname(__file__), "..", "vendor", "mpv")))
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(dll_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
    dll_path = os.path.join(dll_dir, "libmpv-2.dll")
    if not os.path.isfile(dll_path):
        fail("libmpv-2.dll was not found in " + dll_dir)

    mpv = ctypes.WinDLL(dll_path)
    mpv.mpv_create.restype = c_void_p
    mpv.mpv_set_option_string.argtypes = [c_void_p, c_char_p, c_char_p]
    mpv.mpv_set_option_string.restype = c_int
    mpv.mpv_initialize.argtypes = [c_void_p]
    mpv.mpv_initialize.restype = c_int
    mpv.mpv_command.argtypes = [c_void_p, ctypes.POINTER(c_char_p)]
    mpv.mpv_command.restype = c_int
    mpv.mpv_get_property.argtypes = [c_void_p, c_char_p, c_int, c_void_p]
    mpv.mpv_get_property.restype = c_int
    mpv.mpv_terminate_destroy.argtypes = [c_void_p]
    mpv.mpv_terminate_destroy.restype = None

    root = tk.Tk()
    root.title("Smart Video Downloader - MPV probe")
    root.geometry("640x360")
    frame = tk.Frame(root, background="black")
    frame.pack(fill="both", expand=True)
    root.update()
    handle = mpv.mpv_create()
    if not handle:
        root.destroy()
        fail("mpv_create returned NULL")
    try:
        options = [
            (b"wid", str(frame.winfo_id()).encode("ascii")),
            (b"config", b"no"), (b"terminal", b"no"),
            (b"input-default-bindings", b"no"), (b"osc", b"no"),
            (b"hwdec", b"no"), (b"keep-open", b"yes"),
            (b"network-timeout", b"15")
        ]
        for name, value in options:
            rc = mpv.mpv_set_option_string(handle, name, value)
            if rc < 0:
                fail("mpv_set_option_string failed for %s: %d" % (name.decode(), rc))
        rc = mpv.mpv_initialize(handle)
        if rc < 0:
            fail("mpv_initialize failed: %d" % rc)
        command = (c_char_p * 3)(b"loadfile", target.encode("utf-8"), None)
        rc = mpv.mpv_command(handle, command)
        if rc < 0:
            fail("loadfile command failed: %d" % rc)

        started = time.time()
        last_time = None
        while time.time() - started < 35:
            root.update()
            position = c_double()
            rc = mpv.mpv_get_property(handle, b"time-pos", 5, byref(position))
            if rc == 0:
                last_time = position.value
                if position.value > 0.5:
                    break
            time.sleep(0.05)
        if last_time is None or last_time <= 0.25:
            fail("%s playback position did not advance; last=%r" % (mode, last_time))

        pause = (c_char_p * 4)(b"set", b"pause", b"yes", None)
        if mpv.mpv_command(handle, pause) < 0:
            fail("Could not pause playback")
        time.sleep(0.25)
        resume = (c_char_p * 4)(b"set", b"pause", b"no", None)
        if mpv.mpv_command(handle, resume) < 0:
            fail("Could not resume playback")
        print("MPV_%s_PLAYBACK_OK: position advanced in embedded Tkinter HWND; pause/resume accepted." %
              ("LOCAL" if mode == "--local" else "NETWORK"), flush=True)
    finally:
        mpv.mpv_terminate_destroy(handle)
        root.destroy()


if __name__ == "__main__":
    main()
