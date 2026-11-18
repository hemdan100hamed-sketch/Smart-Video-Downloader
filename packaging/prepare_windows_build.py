# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(ROOT)
SOURCE_NAME = "Smart_Video_Downloader_2.5.3_Custom_File_Names.py"
BUILD_DIR = os.path.join(REPO_ROOT, "build")
OUTPUT_NAME = "Smart_Video_Downloader_2.5.3_Windows.py"
YTDLP_VENDOR = os.path.join(REPO_ROOT, "vendor", "yt-dlp-source")
CURL_VENDOR = os.path.join(REPO_ROOT, "vendor", "curlcffi")

def fail(message):
    print("ERROR: " + message)
    sys.exit(1)

def main():
    source_path = os.path.join(REPO_ROOT, SOURCE_NAME)
    if not os.path.isfile(source_path):
        fail("Source file not found: " + source_path)
    if not os.path.isfile(os.path.join(YTDLP_VENDOR, "yt_dlp", "__init__.py")):
        fail("Missing vendor\\yt-dlp-source\\yt_dlp\\__init__.py. Copy the tested local yt-dlp package here.")
    if not os.path.isdir(CURL_VENDOR):
        fail("Missing vendor\\curlcffi directory. Copy the tested curl_cffi installation here.")

    with open(source_path, "r", encoding="utf-8") as handle:
        source = handle.read()

    old_block = (
        'BASE_DIR = os.path.dirname(os.path.abspath(__file__))\n'
        'YTDLP_PATH = r"C:\\SmartVideo\\yt-dlp-source"\n'
        'CURL_CFFI_PATH = r"C:\\SmartVideo\\curlcffi-test\\installed"'
    )
    new_block = (
        'BASE_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)\n'
        '            else os.path.dirname(os.path.abspath(__file__)))\n'
        'RESOURCE_DIR = os.path.join(BASE_DIR, "vendor")\n'
        'YTDLP_PATH = os.path.join(RESOURCE_DIR, "yt-dlp-source")\n'
        'CURL_CFFI_PATH = os.path.join(RESOURCE_DIR, "curlcffi")'
    )
    if source.count(old_block) != 1:
        fail("Expected runtime-path block was not found exactly once. No source was changed.")

    packaged_source = source.replace(old_block, new_block, 1)
    if not os.path.isdir(BUILD_DIR):
        os.makedirs(BUILD_DIR)
    output_path = os.path.join(BUILD_DIR, OUTPUT_NAME)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(packaged_source)

    print("Prepared: " + output_path)
    print("Original application source remains unchanged.")

if __name__ == "__main__":
    main()
