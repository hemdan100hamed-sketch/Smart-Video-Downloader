# -*- coding: utf-8 -*-
"""Isolated Windows MFPlay proof-of-concept for Smart Video Downloader.

This is an experiment only. It does not modify the production application.
Run: python experiments/mfplay_probe.py <local-file-or-direct-http-url>
"""
from __future__ import print_function

import ctypes
import os
import sys
import time
import tkinter as tk


STATE_NAMES = {
    0: "EMPTY",
    1: "STOPPED",
    2: "PLAYING",
    3: "PAUSED",
    4: "SHUTDOWN",
}


class MFPlayError(RuntimeError):
    pass


class MFPlayPlayer(object):
    def __init__(self, media_url, video_hwnd):
        if os.name != "nt":
            raise MFPlayError("MFPlay is available only on Windows.")

        self._ole32 = ctypes.WinDLL("ole32")
        self._mfplay = ctypes.WinDLL("mfplay.dll")
        self._player = ctypes.c_void_p()
        self._com_initialized = False

        self._ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._ole32.CoInitializeEx.restype = ctypes.c_long
        hr = self._ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        if hr not in (0, 1):
            raise MFPlayError("CoInitializeEx failed: 0x%08X" % (hr & 0xFFFFFFFF))
        self._com_initialized = True

        create = self._mfplay.MFPCreateMediaPlayer
        create.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        create.restype = ctypes.c_long

        # MFPlay loads media asynchronously. Tk's event loop must keep pumping
        # Windows messages while playback initializes.
        hr = create(media_url, 1, 0, None, ctypes.c_void_p(video_hwnd),
                    ctypes.byref(self._player))
        if hr < 0 or not self._player:
            self.close()
            raise MFPlayError("MFPCreateMediaPlayer failed: 0x%08X" %
                              (hr & 0xFFFFFFFF))

    def _call(self, index, restype, argtypes, *args):
        if not self._player:
            raise MFPlayError("The MFPlay player is already closed.")
        vtable = ctypes.cast(
            self._player, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        function = prototype(vtable[index])
        return function(self._player, *args)

    def _check(self, hr, operation):
        if hr < 0:
            raise MFPlayError("%s failed: 0x%08X" %
                              (operation, hr & 0xFFFFFFFF))

    def state(self):
        value = ctypes.c_int(-1)
        hr = self._call(13, ctypes.c_long, [ctypes.POINTER(ctypes.c_int)],
                        ctypes.byref(value))
        self._check(hr, "GetState")
        return value.value

    def play(self):
        self._check(self._call(3, ctypes.c_long, []), "Play")

    def pause(self):
        self._check(self._call(4, ctypes.c_long, []), "Pause")

    def stop(self):
        self._check(self._call(5, ctypes.c_long, []), "Stop")

    def set_volume(self, value):
        volume = max(0.0, min(1.0, float(value)))
        # IMFPMediaPlayer::SetVolume takes a DOUBLE, not a FLOAT.
        self._check(self._call(20, ctypes.c_long, [ctypes.c_double],
                               ctypes.c_double(volume)), "SetVolume")

    def close(self):
        if self._player:
            try:
                self._call(5, ctypes.c_long, [])
            except Exception:
                pass
            try:
                self._call(38, ctypes.c_long, [])
            except Exception:
                pass
            try:
                self._call(2, ctypes.c_ulong, [])
            except Exception:
                pass
            self._player = ctypes.c_void_p()
        if self._com_initialized:
            try:
                self._ole32.CoUninitialize()
            except Exception:
                pass
            self._com_initialized = False


def main():
    if len(sys.argv) != 2:
        print("Usage: python mfplay_probe.py <local-file-or-direct-http-url>")
        return 2

    media_url = sys.argv[1]
    if not (media_url.startswith("http://") or media_url.startswith("https://")):
        media_url = os.path.abspath(media_url)
        if not os.path.isfile(media_url):
            print("ERROR: media file not found: " + media_url)
            return 2

    root = tk.Tk()
    root.title("Smart Video Downloader - MFPlay experiment")
    root.geometry("800x520")
    root.configure(bg="#151923")

    video = tk.Frame(root, bg="black", width=760, height=410)
    video.pack(fill="both", expand=True, padx=16, pady=16)
    video.pack_propagate(False)

    status = tk.StringVar(value="Initializing Windows Media Foundation...")
    tk.Label(root, textvariable=status, bg="#151923", fg="white",
             font=("Arial", 11)).pack(fill="x", padx=16, pady=(0, 12))

    root.update_idletasks()
    player = None
    started_at = time.time()
    phase = {"value": "wait_playing", "phase_started": started_at}
    result = {"code": 1}

    try:
        player = MFPlayPlayer(media_url, video.winfo_id())
        status.set("Waiting for MFPlay to load and start the video...")

        def finish(code, message):
            result["code"] = code
            status.set(message)
            print(message)
            root.after(1200, root.destroy)

        def poll():
            try:
                current = player.state()
                now = time.time()
                current_name = STATE_NAMES.get(current, str(current))
                status.set("MFPlay state: " + current_name +
                           " | Test: " + phase["value"])

                if now - started_at > 30:
                    finish(1, "MFPLAY_TEST_FAILED: startup timed out; state=" +
                           current_name)
                    return

                if phase["value"] == "wait_playing":
                    if current == 2:
                        player.set_volume(0.35)
                        player.pause()
                        phase["value"] = "wait_paused"
                        phase["phase_started"] = now
                    elif current in (1, 4):
                        finish(1, "MFPLAY_TEST_FAILED: playback stopped before starting")
                        return

                elif phase["value"] == "wait_paused":
                    if current == 3:
                        player.play()
                        phase["value"] = "wait_resumed"
                        phase["phase_started"] = now

                elif phase["value"] == "wait_resumed":
                    if current == 2:
                        player.stop()
                        phase["value"] = "wait_stopped"
                        phase["phase_started"] = now

                elif phase["value"] == "wait_stopped":
                    if current == 1:
                        finish(0, "PASS: embedded playback, pause, resume, volume and stop")
                        return

                if now - phase["phase_started"] > 12:
                    finish(1, "MFPLAY_TEST_FAILED: timeout during " +
                           phase["value"] + "; state=" + current_name)
                    return

                root.after(200, poll)

            except Exception as exc:
                finish(1, "MFPLAY_TEST_FAILED: " + str(exc))

        root.after(300, poll)
        root.mainloop()

    except Exception as exc:
        print("MFPLAY_TEST_FAILED: " + str(exc))
        result["code"] = 1
    finally:
        if player is not None:
            player.close()
        try:
            root.destroy()
        except Exception:
            pass

    return result["code"]


if __name__ == "__main__":
    sys.exit(main())
