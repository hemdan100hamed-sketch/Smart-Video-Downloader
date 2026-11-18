# -*- coding: utf-8 -*-

import os
import sys
import json
import threading
import queue
import time
import urllib.request
from urllib.parse import urlparse
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from io import BytesIO

try:
    from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    DND_TEXT = None
    TkinterDnD = None
    DND_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import winsound
except ImportError:
    winsound = None

try:
    import vlc
    VLC_AVAILABLE = True
except Exception:
    vlc = None
    VLC_AVAILABLE = False


# =========================================================
# إعدادات البرنامج
# =========================================================

APP_VERSION = "2.5.3 Custom File Names"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YTDLP_PATH = r"C:\SmartVideo\yt-dlp-source"
CURL_CFFI_PATH = r"C:\SmartVideo\curlcffi-test\installed"
SETTINGS_FILE = os.path.join(BASE_DIR, "smart_video_settings.json")

DEFAULT_FOLDER = os.path.join(
    os.path.expanduser("~"),
    "Downloads"
)

QUALITY_OPTIONS = [
    "أفضل جودة",
    "1080p",
    "720p",
    "480p",
    "360p",
    "240p"
]

PREVIEW_SECONDS = 10
PLAYER_SEEK_SECONDS = 10


# =========================================================
# البرنامج الرئيسي
# =========================================================

class VideoDownloader:

    def __init__(self, root):

        self.root = root
        self.root.title("Smart Video Downloader " + APP_VERSION)
        self.root.geometry("950x790")
        # السماح بالتصغير مع إبقاء المحتوى قابلاً للتمرير بدلاً من إخفاء الأزرار.
        self.root.minsize(850, 600)
        self.root.configure(bg="#151923")

        self.messages = queue.Queue()

        self.downloading = False
        self.download_paused = False
        self.checking_info = False

        # قائمة انتظار التنزيل: لا يعمل أكثر من عنصر واحد في الوقت نفسه.
        self.download_queue = []
        self.queue_counter = 0
        self.queue_running = False
        self.pending_custom_filename = None
        self.pending_custom_filename_url = None
        self.queue_success_count = 0
        self.queue_error_count = 0
        self.queue_current_id = None

        self.download_pause_event = threading.Event()
        self.download_pause_event.set()

        self.current_url = ""
        self.pending_url = ""

        self.info_data = None
        self.thumbnail_image = None

        self.last_file = ""
        self.download_started_at = 0
        self.last_clipboard_text = ""

        # FFmpeg: اكتشاف تلقائي دون افتراض وجوده
        self.ffmpeg_path = self.find_ffmpeg()

        # معاينة الإطارات عند تمرير الماوس فوق شريط تشغيل الفيديو
        self.hover_preview_window = None
        self.hover_preview_label = None
        self.hover_preview_photo = None
        self.hover_preview_after = None
        self.hover_preview_token = 0
        self.hover_preview_last_key = None
        # ذاكرة مؤقتة لإطارات المعاينة: تعرض الإطار فوراً عند العودة لموضع سبق زيارته.
        self.hover_preview_cache = {}
        self.hover_preview_cache_limit = 120

        # مشغل المعاينة
        self.preview_instance = None
        self.preview_player = None
        self.preview_media = None
        self.preview_busy = False
        self.preview_timer = None
        self.preview_volume = tk.IntVar(value=75)

        # المشغل المستقل
        self.player_window = None
        self.player_notebook = None
        self.player_tabs = {}
        self.player_tab_counter = 0
        self.player_fullscreen_window = None
        self.player_fullscreen_tab = None
        self.player_top_frame = None
        self.player_bottom_frame = None

        self.settings = self.load_settings()

        self.download_folder = self.settings.get(
            "download_folder",
            DEFAULT_FOLDER
        )

        if not os.path.isdir(self.download_folder):
            self.download_folder = DEFAULT_FOLDER

        self.quality_var = tk.StringVar(
            value=self.settings.get("quality", "أفضل جودة")
        )

        if self.quality_var.get() not in QUALITY_OPTIONS:
            self.quality_var.set("أفضل جودة")

        self.type_var = tk.StringVar(
            value=self.settings.get("download_type", "فيديو")
        )

        self.playlist_var = tk.BooleanVar(
            value=self.settings.get("playlist", False)
        )

        self.folder_var = tk.StringVar(
            value=self.download_folder
        )

        self.title_var = tk.StringVar(
            value="انسخ رابط فيديو من المتصفح أو أدخله هنا"
        )

        self.size_var = tk.StringVar(value="الحجم المتوقع: --")
        self.duration_var = tk.StringVar(value="المدة: --")
        self.percent_var = tk.StringVar(value="0%")

        self.progress_info_var = tk.StringVar(
            value="لم يبدأ التحميل"
        )

        self.speed_var = tk.StringVar(value="السرعة: --")
        self.eta_var = tk.StringVar(value="الوقت المتبقي: --")
        self.status_var = tk.StringVar(value="جاهز")

        self.build_interface()
        self.setup_drag_drop()
        self.save_settings()

        self.last_clipboard_text = self.read_clipboard()

        self.root.after(100, self.process_messages)
        self.root.after(700, self.monitor_clipboard)
        self.root.after(500, self.attach_preview_window)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # =====================================================
    # الإعدادات
    # =====================================================

    def load_settings(self):

        try:
            if os.path.isfile(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass

        return {}

    def save_settings(self):

        self.settings = {
            "download_folder": self.download_folder,
            "quality": self.quality_var.get(),
            "download_type": self.type_var.get(),
            "playlist": self.playlist_var.get()
        }

        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    self.settings,
                    f,
                    ensure_ascii=False,
                    indent=4
                )
        except Exception:
            pass

    def on_settings_changed(self):

        self.save_settings()

        if self.info_data:
            self.display_info(self.info_data)

    # =====================================================
    # الواجهة الرئيسية - الإصدار 1.9
    # =====================================================

    def build_interface(self):

        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "TCombobox",
            fieldbackground="#252d3b",
            background="#252d3b",
            foreground="white",
            arrowcolor="white"
        )

        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#252d3b",
            background="#20b486",
            bordercolor="#252d3b",
            lightcolor="#20b486",
            darkcolor="#20b486"
        )

        # الشريط السفلي الثابت: التقدم والحالة
        # إنشاؤه أولاً وتثبيته أسفل النافذة
        footer = tk.Frame(
            self.root,
            bg="#151923",
            padx=18,
            pady=7
        )
        footer.pack(
            side="bottom",
            fill="x"
        )

        self.section(footer, "تقدم التحميل")

        progress_box = tk.Frame(
            footer,
            bg="#202735",
            padx=10,
            pady=6
        )
        progress_box.pack(fill="x")

        top = tk.Frame(progress_box, bg="#202735")
        top.pack(fill="x")

        tk.Label(
            top,
            textvariable=self.percent_var,
            bg="#202735",
            fg="#20b486",
            font=("Arial", 12, "bold")
        ).pack(side="right")

        self.progress = ttk.Progressbar(
            progress_box,
            maximum=100,
            mode="determinate",
            style="Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x", ipady=3, pady=4)

        tk.Label(
            progress_box,
            textvariable=self.progress_info_var,
            bg="#202735",
            fg="white",
            anchor="e",
            font=("Arial", 8)
        ).pack(fill="x")

        bottom = tk.Frame(progress_box, bg="#202735")
        bottom.pack(fill="x", pady=(2, 0))

        tk.Label(
            bottom,
            textvariable=self.speed_var,
            bg="#202735",
            fg="#20b486",
            font=("Arial", 8)
        ).pack(side="right", padx=10)

        tk.Label(
            bottom,
            textvariable=self.eta_var,
            bg="#202735",
            fg="#cbd5e1",
            font=("Arial", 8)
        ).pack(side="right", padx=10)

        tk.Label(
            footer,
            textvariable=self.status_var,
            bg="#151923",
            fg="#94a3b8",
            font=("Arial", 8),
            anchor="e"
        ).pack(fill="x", pady=(4, 0))

        # شريط ثابت لأزرار قائمة التحميلات؛ يظل ظاهراً مهما كان موضع تمرير المحتوى.
        self.queue_action_bar = tk.Frame(
            self.root,
            bg="#202735",
            padx=8,
            pady=6
        )
        self.queue_action_bar.pack(side="bottom", fill="x")

        self.button(self.queue_action_bar, "إضافة الرابط الحالي", self.add_to_queue, "#2878d0", 16).pack(side="right", padx=2)
        self.button(self.queue_action_bar, "حذف المحدد", self.remove_queue_item, "#a34b4b", 11).pack(side="right", padx=2)
        self.button(self.queue_action_bar, "لأعلى", lambda: self.move_queue_item(-1), "#495365", 7).pack(side="right", padx=2)
        self.button(self.queue_action_bar, "لأسفل", lambda: self.move_queue_item(1), "#495365", 7).pack(side="right", padx=2)
        self.button(self.queue_action_bar, "مسح القائمة", self.clear_queue, "#495365", 10).pack(side="right", padx=2)
        self.button(self.queue_action_bar, "إضافة روابط متعددة", self.add_multiple_to_queue, "#495365", 16).pack(side="left", padx=2)
        self.start_queue_button = self.button(self.queue_action_bar, "بدء تحميل قائمة الانتظار", self.start_queue_download, "#159b70", 22)
        self.start_queue_button.pack(side="left", padx=2)

        # المحتوى الرئيسي داخل مساحة قابلة للتمرير.
        # هذا يمنع اختفاء أزرار قائمة الانتظار على الشاشات الأقصر.
        content_host = tk.Frame(self.root, bg="#151923")
        content_host.pack(side="top", fill="both", expand=True)

        content_canvas = tk.Canvas(
            content_host,
            bg="#151923",
            highlightthickness=0,
            borderwidth=0
        )
        content_scrollbar = ttk.Scrollbar(
            content_host,
            orient="vertical",
            command=content_canvas.yview
        )
        content_canvas.configure(yscrollcommand=content_scrollbar.set)
        content_scrollbar.pack(side="right", fill="y")
        content_canvas.pack(side="left", fill="both", expand=True)

        main = tk.Frame(
            content_canvas,
            bg="#151923",
            padx=14,
            pady=6
        )
        main_window = content_canvas.create_window(
            (0, 0), window=main, anchor="nw"
        )

        def update_scroll_region(_event=None):
            content_canvas.configure(scrollregion=content_canvas.bbox("all"))

        def resize_main(event):
            content_canvas.itemconfigure(main_window, width=event.width)
            update_scroll_region()

        main.bind("<Configure>", update_scroll_region)
        content_canvas.bind("<Configure>", resize_main)

        def on_mousewheel(event):
            if getattr(event, "delta", 0):
                content_canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                content_canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                content_canvas.yview_scroll(3, "units")
            return "break"

        def bind_wheel(_event=None):
            content_canvas.bind_all("<MouseWheel>", on_mousewheel)
            content_canvas.bind_all("<Button-4>", on_mousewheel)
            content_canvas.bind_all("<Button-5>", on_mousewheel)

        def unbind_wheel(_event=None):
            content_canvas.unbind_all("<MouseWheel>")
            content_canvas.unbind_all("<Button-4>")
            content_canvas.unbind_all("<Button-5>")

        content_canvas.bind("<Enter>", bind_wheel)
        content_canvas.bind("<Leave>", unbind_wheel)
        main.bind("<Enter>", bind_wheel)
        main.bind("<Leave>", unbind_wheel)

        header = tk.Frame(main, bg="#151923")
        header.pack(fill="x", pady=(0, 5))

        tk.Label(
            header,
            text="Smart Video Downloader",
            font=("Arial", 20, "bold"),
            fg="#20b486",
            bg="#151923"
        ).pack(side="right")

        tk.Label(
            header,
            text="الإصدار " + APP_VERSION,
            font=("Arial", 9),
            fg="#94a3b8",
            bg="#151923"
        ).pack(side="left", pady=7)

        # الرابط
        self.section(main, "رابط الفيديو")

        url_box = tk.Frame(
            main,
            bg="#202735",
            padx=9,
            pady=7
        )
        url_box.pack(fill="x", pady=(0, 5))

        self.url_entry = tk.Entry(
            url_box,
            font=("Arial", 11),
            bg="#111722",
            fg="white",
            insertbackground="white",
            relief="flat"
        )

        self.url_entry.pack(fill="x", ipady=7, pady=(0, 6))
        self.add_context_menu(self.url_entry)

        self.url_entry.bind("<Return>", self.on_url_enter)
        self.url_entry.bind("<FocusOut>", self.on_url_focus_out)

        url_buttons = tk.Frame(url_box, bg="#202735")
        url_buttons.pack(fill="x")

        self.button(
            url_buttons, "فحص الرابط",
            self.check_info, "#2878d0"
        ).pack(side="right", padx=3)

        self.button(
            url_buttons, "مسح",
            self.clear_url, "#495365"
        ).pack(side="right", padx=3)

        self.button(
            url_buttons, "تعديل اسم التنزيل",
            self.edit_pending_download_name, "#8b5cf6", 15
        ).pack(side="right", padx=3)

        tk.Label(
            url_buttons,
            text="سيتم التقاط الرابط تلقائيا عند نسخه",
            bg="#202735",
            fg="#20b486",
            font=("Arial", 8)
        ).pack(side="left", padx=5)

        # معلومات الملف
        self.section(main, "معلومات الملف")

        info_box = tk.Frame(
            main,
            bg="#202735",
            padx=9,
            pady=6
        )
        info_box.pack(fill="x", pady=(0, 5))

        self.preview_side = tk.Frame(
            info_box,
            bg="#202735",
            width=230,
            height=145
        )

        self.preview_side.pack(
            side="left",
            padx=(0, 10),
            anchor="n"
        )

        self.preview_side.pack_propagate(False)

        self.thumb_label = tk.Label(
            self.preview_side,
            text="الصورة\nالمصغرة",
            width=22,
            height=6,
            bg="#111722",
            fg="#94a3b8",
            font=("Arial", 9)
        )

        self.thumb_label.pack(fill="both", expand=True)

        self.preview_frame = tk.Frame(
            self.preview_side,
            bg="black",
            width=225,
            height=125
        )
        self.preview_frame.pack_propagate(False)

        self.preview_controls = tk.Frame(
            self.preview_side,
            bg="#202735"
        )

        controls_row = tk.Frame(
            self.preview_controls,
            bg="#202735"
        )
        controls_row.pack(fill="x", pady=(3, 1))

        self.button(
            controls_row, "استئناف",
            self.preview_play, "#159b70", 8
        ).pack(side="right", padx=2)

        self.button(
            controls_row, "إيقاف مؤقت",
            self.preview_pause, "#2878d0", 8
        ).pack(side="right", padx=2)

        self.button(
            controls_row, "إيقاف",
            self.stop_preview, "#495365", 7
        ).pack(side="right", padx=2)

        volume_row = tk.Frame(
            self.preview_controls,
            bg="#202735"
        )
        volume_row.pack(fill="x")

        tk.Label(
            volume_row,
            text="الصوت",
            bg="#202735",
            fg="white",
            font=("Arial", 8)
        ).pack(side="right", padx=3)

        self.volume_scale = tk.Scale(
            volume_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.preview_volume,
            command=self.change_preview_volume,
            bg="#202735",
            fg="white",
            troughcolor="#111722",
            highlightthickness=0,
            showvalue=False,
            length=120
        )

        self.volume_scale.pack(
            side="right",
            fill="x",
            expand=True
        )

        self.preview_status = tk.Label(
            self.preview_side,
            text="",
            bg="#202735",
            fg="#20b486",
            font=("Arial", 8)
        )

        info_text = tk.Frame(info_box, bg="#202735")
        info_text.pack(side="right", fill="both", expand=True)

        tk.Label(
            info_text,
            textvariable=self.title_var,
            bg="#202735",
            fg="white",
            font=("Arial", 10, "bold"),
            anchor="e",
            justify="right",
            wraplength=650
        ).pack(fill="x", pady=(3, 6))

        tk.Label(
            info_text,
            textvariable=self.size_var,
            bg="#202735",
            fg="#20b486",
            font=("Arial", 10),
            anchor="e"
        ).pack(fill="x", pady=2)

        tk.Label(
            info_text,
            textvariable=self.duration_var,
            bg="#202735",
            fg="#cbd5e1",
            font=("Arial", 9),
            anchor="e"
        ).pack(fill="x", pady=2)

        # إعدادات التحميل
        self.section(main, "إعدادات التحميل")

        options = tk.Frame(
            main,
            bg="#202735",
            padx=9,
            pady=6
        )
        options.pack(fill="x", pady=(0, 5))

        row = tk.Frame(options, bg="#202735")
        row.pack(fill="x")

        tk.Label(
            row,
            text="نوع الملف:",
            bg="#202735",
            fg="white"
        ).pack(side="right", padx=(8, 4))

        type_box = ttk.Combobox(
            row,
            textvariable=self.type_var,
            values=["فيديو", "MP3"],
            state="readonly",
            width=10,
            justify="center"
        )

        type_box.pack(side="right", padx=4)
        type_box.bind(
            "<<ComboboxSelected>>",
            lambda e: self.on_settings_changed()
        )

        tk.Label(
            row,
            text="الجودة:",
            bg="#202735",
            fg="white"
        ).pack(side="right", padx=(18, 4))

        quality_box = ttk.Combobox(
            row,
            textvariable=self.quality_var,
            values=QUALITY_OPTIONS,
            state="readonly",
            width=13,
            justify="center"
        )

        quality_box.pack(side="right", padx=4)
        quality_box.bind(
            "<<ComboboxSelected>>",
            lambda e: self.on_settings_changed()
        )

        checks = tk.Frame(options, bg="#202735")
        checks.pack(fill="x", pady=(5, 0))

        tk.Checkbutton(
            checks,
            text="قائمة تشغيل كاملة",
            variable=self.playlist_var,
            command=self.on_settings_changed,
            bg="#202735",
            fg="white",
            activebackground="#202735",
            activeforeground="white",
            selectcolor="#111722",
            font=("Arial", 9)
        ).pack(side="right", padx=5)

        tk.Label(
            checks,
            text="التشغيل بعد التحميل يدوي فقط",
            bg="#202735",
            fg="#20b486",
            font=("Arial", 9)
        ).pack(side="right", padx=15)

        # أزرار العمليات
        action = tk.Frame(main, bg="#151923")
        action.pack(fill="x", pady=(2, 5))

        self.download_button = self.button(
            action, "بدء التحميل",
            self.start_download, "#159b70", 14
        )
        self.download_button.pack(
            side="right",
            fill="x",
            expand=True,
            padx=(0, 4),
            ipady=4
        )

        self.pause_download_button = self.button(
            action, "إيقاف مؤقت",
            self.pause_download, "#c66a00", 12
        )
        # إبقاء النص واضحاً حتى عندما يكون الزر معطلاً قبل بدء التحميل.
        self.pause_download_button.configure(
            fg="#ffffff",
            disabledforeground="#ffffff",
            activebackground="#e07b08",
            activeforeground="#ffffff",
            font=("Arial", 10, "bold")
        )
        self.pause_download_button.pack(
            side="right",
            padx=3,
            ipady=4
        )
        self.pause_download_button.configure(state="disabled")

        self.resume_download_button = self.button(
            action, "استئناف",
            self.resume_download, "#087f5b", 10
        )
        # لون أبيض عالي التباين للنص في حالتي التفعيل والتعطيل.
        self.resume_download_button.configure(
            fg="#ffffff",
            disabledforeground="#ffffff",
            activebackground="#0a9b6e",
            activeforeground="#ffffff",
            font=("Arial", 10, "bold")
        )
        self.resume_download_button.pack(
            side="right",
            padx=3,
            ipady=4
        )
        self.resume_download_button.configure(state="disabled")

        self.preview_button = self.button(
            action, "معاينة 10 ثوانٍ",
            self.start_preview, "#8b5cf6", 15
        )
        self.preview_button.pack(
            side="right",
            padx=3,
            ipady=4
        )

        self.stream_button = self.button(
            action, "تشغيل أثناء التحميل",
            self.start_stream_player, "#c056d8", 17
        )
        self.stream_button.pack(
            side="right",
            padx=3,
            ipady=4
        )

        self.open_button = self.button(
            action, "تشغيل آخر ملف",
            self.open_last_file, "#2878d0", 13
        )
        self.open_button.pack(
            side="right",
            padx=3,
            ipady=4
        )

        self.player_button = self.button(
            action, "فتح المشغل",
            self.open_player_window, "#495365", 11
        )
        self.player_button.pack(
            side="right",
            padx=3,
            ipady=4
        )

        if not VLC_AVAILABLE:
            self.preview_button.configure(state="disabled")
            self.stream_button.configure(state="disabled")
            self.player_button.configure(state="disabled")

        # قائمة انتظار التنزيل
        self.section(main, "قائمة انتظار التنزيل")

        queue_box = tk.Frame(main, bg="#202735", padx=8, pady=6)
        queue_box.pack(fill="both", pady=(0, 5))

        queue_columns = ("number", "title", "filename", "status")
        self.queue_tree = ttk.Treeview(
            queue_box,
            columns=queue_columns,
            show="headings",
            height=5
        )
        self.queue_tree.heading("number", text="#")
        self.queue_tree.heading("title", text="الرابط / اسم الفيديو")
        self.queue_tree.heading("filename", text="اسم الملف عند الحفظ")
        self.queue_tree.heading("status", text="الحالة")
        self.queue_tree.column("number", width=38, anchor="center", stretch=False)
        self.queue_tree.column("title", width=390, anchor="e")
        self.queue_tree.column("filename", width=220, anchor="e")
        self.queue_tree.column("status", width=90, anchor="center", stretch=False)
        self.queue_tree.pack(fill="both", expand=True)

        queue_name_buttons = tk.Frame(queue_box, bg="#202735")
        queue_name_buttons.pack(fill="x", pady=(6, 0))
        self.button(
            queue_name_buttons, "تعديل اسم العنصر المحدد",
            self.edit_selected_queue_filename, "#8b5cf6", 22
        ).pack(side="right", padx=3)
        self.button(
            queue_name_buttons, "استخدام الاسم الأصلي",
            self.clear_selected_queue_filename, "#495365", 18
        ).pack(side="right", padx=3)
        self.queue_tree.bind("<Double-1>", self.edit_selected_queue_filename)

        # مجلد الحفظ
        self.section(main, "مجلد الحفظ")

        folder_box = tk.Frame(
            main,
            bg="#202735",
            padx=9,
            pady=6
        )
        folder_box.pack(fill="x", pady=(0, 5))

        tk.Entry(
            folder_box,
            textvariable=self.folder_var,
            state="readonly",
            bg="#111722",
            fg="white",
            relief="flat",
            font=("Arial", 9)
        ).pack(
            side="right",
            fill="x",
            expand=True,
            ipady=5,
            padx=(0, 8)
        )

        self.button(
            folder_box, "اختيار المجلد",
            self.choose_folder, "#495365"
        ).pack(side="left", padx=3)

        self.button(
            folder_box, "فتح المجلد",
            self.open_folder, "#495365"
        ).pack(side="left", padx=3)

        # السجل يتمدد داخل المساحة المتبقية
        self.section(main, "سجل العمليات")

        self.log_box = ScrolledText(
            main,
            height=3,
            bg="#111722",
            fg="#cbd5e1",
            insertbackground="white",
            font=("Consolas", 8),
            relief="flat",
            wrap="word"
        )

        self.log_box.pack(fill="both", expand=True)
        self.add_context_menu(self.log_box)

        if not VLC_AVAILABLE:
            self.log("تحذير: لم يتم العثور على مكتبة python-vlc أو VLC.")

    def section(self, parent, title):

        tk.Label(
            parent,
            text=title,
            bg="#151923",
            fg="#20b486",
            font=("Arial", 10, "bold"),
            anchor="e"
        ).pack(fill="x", pady=(2, 3))

    def button(self, parent, text, command, color, width=12):

        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Arial", 9, "bold"),
            width=width,
            padx=7,
            pady=5
        )

    # =====================================================
    # اكتشاف FFmpeg والسحب والإفلات
    # =====================================================

    def find_ffmpeg(self):

        candidates = []

        env_path = os.environ.get("FFMPEG_PATH")
        if env_path:
            candidates.append(env_path)

        found = shutil.which("ffmpeg")
        if found:
            candidates.append(found)

        candidates.extend([
            os.path.join(BASE_DIR, "ffmpeg.exe"),
            os.path.join(BASE_DIR, "bin", "ffmpeg.exe"),
            os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(YTDLP_PATH, "ffmpeg.exe"),
            os.path.join(YTDLP_PATH, "bin", "ffmpeg.exe")
        ])

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)

        return None

    def refresh_ffmpeg(self):

        self.ffmpeg_path = self.find_ffmpeg()

        if self.ffmpeg_path:
            self.log("تم اكتشاف FFmpeg: " + self.ffmpeg_path)
        else:
            self.log(
                "لم يتم العثور على FFmpeg. تنزيل الفيديو العادي متاح، "
                "لكن تحويل MP3 ومعاينات الإطارات قد لا تعمل."
            )

        return self.ffmpeg_path

    def setup_drag_drop(self):

        if not DND_AVAILABLE:
            self.log(
                "السحب والإفلات يحتاج إلى تثبيت tkinterdnd2. "
                "نفّذ: python -m pip install tkinterdnd2"
            )
            return

        try:
            # تسجيل الهدف على النافذة الرئيسية وخانة الرابط نفسها.
            for widget in (self.root, self.url_entry):
                try:
                    widget.drop_target_register(DND_FILES, DND_TEXT)
                    widget.dnd_bind("<<Drop>>", self.handle_drop)
                except Exception as exc:
                    self.log("تعذر تسجيل السحب والإفلات على عنصر: " + str(exc))
            self.log("تم تفعيل استقبال الروابط والملفات بالسحب والإفلات.")
        except Exception as exc:
            self.log("تعذر تفعيل السحب والإفلات: " + str(exc))

    def handle_drop(self, event):

        try:
            items = list(self.root.tk.splitlist(event.data))
        except Exception:
            items = [str(event.data)]

        if not items:
            return "break"

        # نقبل أول عنصر مسحوب؛ الروابط والملفات ذات المسافات
        # يعالجها splitlist دون تقسيمها إلى أجزاء.
        value = str(items[0]).strip().strip('{}').strip()
        if not value:
            return "break"

        if value.lower().startswith(("http://", "https://")):
            if self.downloading:
                self.log("لا يمكن تغيير الرابط أثناء التحميل.")
                return "break"
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, value)
            self.url_entry.icursor(tk.END)
            self.accept_copied_url(value)
            self.log("تم استقبال الرابط بالسحب والإفلات.")
            return "break"

        path = os.path.abspath(value)
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            video_exts = (
                ".mp4", ".mkv", ".avi", ".mov", ".wmv",
                ".flv", ".webm", ".mpeg", ".mpg", ".m4v", ".3gp"
            )
            if ext in video_exts:
                if not VLC_AVAILABLE:
                    messagebox.showwarning(
                        "مشغل الفيديو",
                        "تم استلام الملف، لكن تشغيله يحتاج إلى VLC."
                    )
                    return "break"
                if self.player_window is None or not self.player_window.winfo_exists():
                    self.open_player_window()
                if self.player_window and self.player_window.winfo_exists():
                    self.player_create_tab(path)
                return "break"

        messagebox.showinfo(
            "السحب والإفلات",
            "اسحب رابط HTTP/HTTPS أو ملف فيديو مدعوم."
        )
        return "break"

    def enable_drop_on_player_frame(self, widget):

        if not DND_AVAILABLE:
            return

        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.handle_drop)
        except Exception:
            pass

    # =====================================================
    # إعداد VLC والمعاينة
    # =====================================================

    def attach_preview_window(self):

        if not VLC_AVAILABLE:
            return

        try:
            self.root.update_idletasks()

            if self.preview_player:
                self.preview_player.set_hwnd(
                    self.preview_frame.winfo_id()
                )

        except Exception as exc:
            self.log("تعذر تجهيز نافذة المعاينة: " + str(exc))

    def ensure_vlc_player(self):

        if not VLC_AVAILABLE:
            raise Exception("مكتبة python-vlc أو VLC غير متاحة.")

        if self.preview_instance is None:

            self.preview_instance = vlc.Instance(
                "--no-video-title-show",
                "--avcodec-hw=none"
            )

            if self.preview_instance is None:
                raise Exception("تعذر تشغيل محرك VLC.")

            self.preview_player = (
                self.preview_instance.media_player_new()
            )

            self.preview_player.audio_set_volume(
                int(self.preview_volume.get())
            )

        return self.preview_player

    def start_preview(self):

        url = self.url_entry.get().strip()

        if not url:
            messagebox.showwarning("تنبيه", "أدخل رابط الفيديو أولاً.")
            return

        if self.preview_busy:
            return

        if not VLC_AVAILABLE:
            messagebox.showerror("VLC", "مشغل VLC غير متاح.")
            return

        if url != self.current_url or not self.info_data:
            self.check_info()
            self.log("انتظر انتهاء فحص الرابط ثم اضغط المعاينة.")
            return

        if self.info_data.get("_type") == "playlist":
            messagebox.showinfo(
                "المعاينة",
                "افتح رابط فيديو منفرداً للمعاينة."
            )
            return

        self.stop_preview()
        self.preview_busy = True

        self.preview_button.configure(
            state="disabled",
            text="جارٍ تجهيز المعاينة..."
        )

        threading.Thread(
            target=self.preview_worker,
            args=(url,),
            daemon=True
        ).start()

    def preview_worker(self, url):

        try:
            module = self.prepare_ytdlp()

            options = self.base_options({
                "skip_download": True,
                "quiet": True,
                "no_warnings": True
            })

            with module.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)

            stream_url = self.choose_preview_stream(info)

            if not stream_url:
                raise Exception("لم يعثر البرنامج على بث مناسب.")

            self.messages.put(("preview_ready", (url, stream_url)))

        except Exception as exc:
            self.messages.put(("preview_error", (url, str(exc))))

    def choose_preview_stream(self, info):

        formats = info.get("formats") or []
        quality = self.quality_var.get()

        max_height = (
            99999 if quality == "أفضل جودة"
            else int(quality.replace("p", ""))
        )

        candidates = []

        for fmt in formats:

            stream_url = fmt.get("url")
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            height = fmt.get("height") or 0

            if not stream_url:
                continue

            if vcodec in (None, "none"):
                continue

            if acodec in (None, "none"):
                continue

            if height and height > max_height:
                continue

            candidates.append(fmt)

        if candidates:

            candidates.sort(
                key=lambda f: (
                    f.get("height") or 0,
                    f.get("tbr") or 0
                ),
                reverse=True
            )

            return candidates[0].get("url")

        direct_url = info.get("url")

        if (
            direct_url
            and info.get("vcodec") not in (None, "none")
            and info.get("acodec") not in (None, "none")
        ):
            return direct_url

        return None

    def play_preview_stream(self, stream_url):

        try:
            player = self.ensure_vlc_player()

            self.preview_frame.pack(
                side="top",
                fill="both",
                expand=True
            )

            self.preview_controls.pack(
                side="top",
                fill="x"
            )

            self.preview_status.pack(
                side="top",
                fill="x"
            )

            self.thumb_label.pack_forget()
            self.root.update_idletasks()

            player.stop()

            media = self.preview_instance.media_new(stream_url)
            media.add_option(":network-caching=1500")
            media.add_option(":no-video-title-show")
            media.add_option(":stop-time=" + str(PREVIEW_SECONDS))

            self.preview_media = media
            player.set_media(media)
            player.set_hwnd(self.preview_frame.winfo_id())

            player.audio_set_volume(
                int(self.preview_volume.get())
            )

            player.play()

            self.preview_busy = False

            self.preview_button.configure(
                state="normal",
                text="معاينة 10 ثوانٍ"
            )

            self.preview_status.configure(
                text="المعاينة تعمل - تتوقف بعد 10 ثوانٍ"
            )

            if self.preview_timer:
                try:
                    self.root.after_cancel(self.preview_timer)
                except Exception:
                    pass

            self.preview_timer = self.root.after(
                PREVIEW_SECONDS * 1000,
                self.stop_preview
            )

        except Exception as exc:

            self.preview_busy = False

            self.preview_button.configure(
                state="normal",
                text="معاينة 10 ثوانٍ"
            )

            self.stop_preview()

            messagebox.showerror("خطأ المعاينة", str(exc))
            self.log("تعذر تشغيل المعاينة: " + str(exc))

    def preview_play(self):

        if self.preview_player:
            try:
                self.preview_player.play()
            except Exception:
                pass

    def preview_pause(self):

        if self.preview_player:
            try:
                self.preview_player.pause()
            except Exception:
                pass

    def change_preview_volume(self, value):

        if self.preview_player:
            try:
                self.preview_player.audio_set_volume(int(float(value)))
            except Exception:
                pass

    def stop_preview(self):

        if self.preview_timer:
            try:
                self.root.after_cancel(self.preview_timer)
            except Exception:
                pass
            self.preview_timer = None

        if self.preview_player:
            try:
                self.preview_player.stop()
            except Exception:
                pass

        self.preview_media = None
        self.preview_busy = False

        try:
            self.preview_frame.pack_forget()
            self.preview_controls.pack_forget()
            self.preview_status.pack_forget()
            self.thumb_label.pack(fill="both", expand=True)

            self.preview_button.configure(
                state="normal",
                text="معاينة 10 ثوانٍ"
            )
        except Exception:
            pass    # =====================================================
    # تشغيل الفيديو أثناء التحميل
    # =====================================================

    def start_stream_player(self):

        url = self.url_entry.get().strip()

        if not url:
            messagebox.showwarning(
                "تنبيه",
                "أدخل رابط الفيديو أولاً."
            )
            return

        if not VLC_AVAILABLE:
            messagebox.showerror(
                "مشغل الفيديو",
                "تأكد من تثبيت VLC ومكتبة python-vlc."
            )
            return

        if self.type_var.get() == "MP3":
            messagebox.showinfo(
                "التشغيل أثناء التحميل",
                "هذه الميزة مخصصة للفيديو وليست لتحميل MP3."
            )
            return

        if self.info_data and self.info_data.get("_type") == "playlist":
            messagebox.showinfo(
                "التشغيل أثناء التحميل",
                "افتح رابط فيديو منفرداً بدلاً من رابط قائمة التشغيل."
            )
            return

        self.stream_button.configure(
            state="disabled",
            text="جارٍ استخراج البث..."
        )

        self.log("جارٍ استخراج رابط البث المباشر للفيديو...")

        threading.Thread(
            target=self.stream_worker,
            args=(url,),
            daemon=True
        ).start()

    def stream_worker(self, url):

        try:
            module = self.prepare_ytdlp()

            options = self.base_options({
                "skip_download": True,
                "quiet": True,
                "no_warnings": True
            })

            with module.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                raise Exception("تعذر استخراج معلومات البث.")

            stream_url = self.choose_preview_stream(info)

            if not stream_url:
                raise Exception(
                    "لم يعثر البرنامج على رابط بث يجمع الصوت والصورة."
                )

            title = info.get("title") or "بث مباشر"

            # استخدم ترويسات الصيغة المختارة إن وجدت، وإلا ترويسات yt-dlp العامة.
            http_headers = dict(info.get("http_headers") or {})
            for fmt in (info.get("formats") or []):
                if fmt.get("url") == stream_url and fmt.get("http_headers"):
                    http_headers.update(fmt.get("http_headers") or {})
                    break

            self.messages.put((
                "stream_ready",
                (url, stream_url, title, http_headers)
            ))

        except Exception as exc:
            self.messages.put(("stream_error", (url, str(exc))))

    # =====================================================
    # المشغل المستقل متعدد التبويبات
    # =====================================================

    def open_player_window(self):

        if not VLC_AVAILABLE:
            messagebox.showerror(
                "مشغل الفيديو",
                "لم يتم العثور على VLC أو مكتبة python-vlc."
            )
            return

        if (
            self.player_window is not None
            and self.player_window.winfo_exists()
        ):
            self.player_window.deiconify()
            self.player_window.lift()
            self.player_window.focus_force()
            return

        self.player_window = tk.Toplevel(self.root)
        self.player_window.title(
            "Smart Video Player - مشغل الفيديو"
        )
        self.player_window.geometry("950x650")
        self.player_window.minsize(650, 420)
        self.player_window.configure(bg="#151923")
        self.enable_drop_on_player_frame(self.player_window)

        self.player_window.protocol(
            "WM_DELETE_WINDOW",
            self.close_player_window
        )

        self.player_window.bind(
            "<Escape>",
            self.player_exit_fullscreen
        )

        self.player_window.bind(
            "<F11>",
            self.player_toggle_fullscreen
        )

        top = tk.Frame(
            self.player_window,
            bg="#202735",
            padx=8,
            pady=8
        )
        self.player_top_frame = top
        top.pack(fill="x")

        self.button(
            top, "فتح فيديو",
            self.player_open_file, "#159b70"
        ).pack(side="right", padx=4)

        self.button(
            top, "إغلاق التبويب",
            self.player_close_current_tab, "#495365"
        ).pack(side="right", padx=4)

        self.button(
            top, "ملء الشاشة F11",
            self.player_toggle_fullscreen, "#2878d0"
        ).pack(side="right", padx=4)

        self.player_notebook = ttk.Notebook(
            self.player_window
        )
        self.player_notebook.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=8
        )

        bottom = tk.Frame(
            self.player_window,
            bg="#202735",
            padx=8,
            pady=8
        )
        self.player_bottom_frame = bottom
        bottom.pack(fill="x")

        self.player_status = tk.StringVar(
            value="افتح ملف فيديو للبدء"
        )

        tk.Label(
            bottom,
            textvariable=self.player_status,
            bg="#202735",
            fg="#20b486",
            font=("Arial", 9)
        ).pack(side="right", padx=8)

        self.player_notebook.bind(
            "<<NotebookTabChanged>>",
            self.player_tab_changed
        )

        # الإصدار 1.9:
        # لا نفتح نافذة اختيار الملفات تلقائياً عند فتح المشغل.
        # المستخدم يضغط زر "فتح فيديو" بنفسه عند الحاجة.

    def player_open_file(self):

        if not self.player_window:
            return

        file_path = filedialog.askopenfilename(
            parent=self.player_window,
            title="اختر ملف فيديو",
            filetypes=[
                (
                    "ملفات الفيديو",
                    "*.mp4 *.mkv *.avi *.mov *.wmv *.flv "
                    "*.webm *.mpeg *.mpg *.m4v *.3gp"
                ),
                ("جميع الملفات", "*.*")
            ]
        )

        if file_path:
            self.player_create_tab(file_path)

    def player_create_tab(self, file_path):

        self.player_create_media_tab(
            media_source=os.path.abspath(file_path),
            title=os.path.basename(file_path),
            is_stream=False
        )

    def player_create_stream_tab(self, stream_url, title, http_headers=None):

        self.player_create_media_tab(
            media_source=stream_url,
            title=title,
            is_stream=True,
            http_headers=http_headers or {}
        )

    def player_create_media_tab(
        self,
        media_source,
        title,
        is_stream=False,
        http_headers=None
    ):

        if not VLC_AVAILABLE:
            return

        instance = None
        player = None
        media = None

        try:

            self.player_tab_counter += 1
            tab_id = self.player_tab_counter

            tab = tk.Frame(
                self.player_notebook,
                bg="#111111"
            )

            video_frame = tk.Frame(
                tab,
                bg="black"
            )
            video_frame.pack(
                fill="both",
                expand=True
            )
            self.enable_drop_on_player_frame(video_frame)

            controls = tk.Frame(
                tab,
                bg="#202735",
                padx=8,
                pady=7
            )
            controls.pack(fill="x")

            instance = vlc.Instance(
                "--no-video-title-show",
                "--avcodec-hw=none"
            )

            if instance is None:
                raise Exception("تعذر إنشاء محرك VLC.")

            player = instance.media_player_new()

            if is_stream:
                media = instance.media_new(media_source)
                media.add_option(":network-caching=1500")
                media.add_option(":no-video-title-show")
            else:
                media = instance.media_new_path(
                    os.path.abspath(media_source)
                )

            player.set_media(media)

            video_frame.update_idletasks()
            player.set_hwnd(video_frame.winfo_id())
            player.audio_set_volume(75)

            item = {
                "id": tab_id,
                "path": media_source,
                "title": title,
                "is_stream": is_stream,
                "http_headers": dict(http_headers or {}),
                "frame": tab,
                "video_frame": video_frame,
                "controls": controls,
                "seek_row": None,
                "player": player,
                "media": media,
                "instance": instance,
                "playing": False,
                "fullscreen": False,
                "seek_scale": None,
                "seek_dragging": False,
                "time_label": None,
                "seek_after": None
            }

            self.player_tabs[tab_id] = item

            self.player_notebook.add(
                tab,
                text=title[:30]
            )
            self.player_notebook.select(tab)

            self.button(
                controls,
                "تشغيل",
                lambda i=tab_id: self.player_play(i),
                "#159b70",
                8
            ).pack(side="right", padx=2)

            self.button(
                controls,
                "إيقاف مؤقت",
                lambda i=tab_id: self.player_pause(i),
                "#2878d0",
                9
            ).pack(side="right", padx=2)

            self.button(
                controls,
                "إيقاف",
                lambda i=tab_id: self.player_stop(i),
                "#495365",
                7
            ).pack(side="right", padx=2)

            self.button(
                controls,
                "رجوع 10 ث",
                lambda i=tab_id: self.player_seek_relative(i, -10),
                "#495365",
                9
            ).pack(side="right", padx=2)

            self.button(
                controls,
                "تقديم 10 ث",
                lambda i=tab_id: self.player_seek_relative(i, 10),
                "#495365",
                9
            ).pack(side="right", padx=2)

            self.button(
                controls,
                "ملء الشاشة",
                lambda i=tab_id: self.player_fullscreen(i),
                "#8b5cf6",
                10
            ).pack(side="right", padx=2)

            # شريط التقدم
            seek_row = tk.Frame(
                tab,
                bg="#202735",
                padx=10,
                pady=3
            )
            seek_row.pack(fill="x", before=controls)
            item["seek_row"] = seek_row

            time_label = tk.Label(
                seek_row,
                text="00:00 / 00:00",
                bg="#202735",
                fg="white",
                font=("Arial", 8),
                width=18
            )
            time_label.pack(side="right", padx=5)

            seek_scale = tk.Scale(
                seek_row,
                from_=0,
                to=1000,
                orient="horizontal",
                showvalue=False,
                resolution=1,
                bg="#202735",
                fg="white",
                troughcolor="#111722",
                activebackground="#20b486",
                highlightthickness=0,
                command=lambda value, i=tab_id:
                    self.player_seek_changed(i, value)
            )
            seek_scale.pack(
                side="right",
                fill="x",
                expand=True
            )

            seek_scale.bind(
                "<ButtonPress-1>",
                lambda event, i=tab_id:
                    self.player_seek_start(i)
            )

            seek_scale.bind(
                "<ButtonRelease-1>",
                lambda event, i=tab_id:
                    self.player_seek_end(i, event)
            )
            seek_scale.bind(
                "<Motion>",
                lambda event, i=tab_id:
                    self.player_hover_seek(i, event)
            )
            seek_scale.bind(
                "<Leave>",
                lambda event:
                    self.hide_hover_preview()
            )

            item["seek_scale"] = seek_scale
            item["time_label"] = time_label

            # الصوت
            tk.Label(
                controls,
                text="الصوت",
                bg="#202735",
                fg="white",
                font=("Arial", 8)
            ).pack(side="right", padx=(8, 2))

            volume = tk.Scale(
                controls,
                from_=0,
                to=100,
                orient="horizontal",
                bg="#202735",
                fg="white",
                troughcolor="#111722",
                highlightthickness=0,
                showvalue=True,
                length=90,
                command=lambda value, i=tab_id:
                    self.player_set_volume(i, value)
            )
            volume.set(75)
            volume.pack(side="right", padx=2)

            player.play()
            item["playing"] = True

            self.player_status.set(
                "يعمل الآن: " + title
            )

            self.player_schedule_seek_update(tab_id)

            self.log(
                "تم فتح تبويب مشغل: " + title
            )

        except Exception as exc:

            try:
                if player:
                    player.stop()
                    player.release()
            except Exception:
                pass

            try:
                if media:
                    media.release()
            except Exception:
                pass

            try:
                if instance:
                    instance.release()
            except Exception:
                pass

            messagebox.showerror(
                "تعذر فتح الفيديو",
                str(exc),
                parent=self.player_window
            )

    # =====================================================
    # شريط التقدم والتحكم في موضع الفيديو
    # =====================================================

    def format_time(self, milliseconds):

        try:
            seconds = max(0, int(milliseconds / 1000))
        except Exception:
            seconds = 0

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours:
            return "{:02d}:{:02d}:{:02d}".format(
                hours, minutes, secs
            )

        return "{:02d}:{:02d}".format(minutes, secs)

    def player_seek_start(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if item:
            item["seek_dragging"] = True

    def player_seek_changed(self, tab_id, value):

        item = self.player_tabs.get(tab_id)

        if not item or not item.get("seek_dragging"):
            return

        try:
            player = item["player"]
            length = player.get_length()

            if length > 0:
                target = int(float(value) * length / 1000.0)

                item["time_label"].configure(
                    text=self.format_time(target)
                    + " / "
                    + self.format_time(length)
                )
        except Exception:
            pass

    def player_seek_end(self, tab_id, event=None):

        # حساب الموضع من مكان المؤشر نفسه يجعل النقر على الشريط
        # يعمل حتى إذا لم يكن المستخدم قد سحب مقبض Scale.
        item = self.player_tabs.get(tab_id)
        if item and event is not None:
            try:
                scale = item["seek_scale"]
                x0 = scale.coords(0)[0]
                x1 = scale.coords(1000)[0]
                if x1 != x0:
                    fraction = max(0.0, min(1.0,
                        (float(event.x) - x0) / float(x1 - x0)))
                    scale.set(fraction * 1000.0)
            except Exception:
                pass

        # نؤجل التنفيذ حتى تنتهي Tkinter من تحديث قيمة الشريط.
        self.root.after_idle(
            lambda i=tab_id: self._player_seek_commit(i)
        )

    def _player_seek_commit(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        item["seek_dragging"] = False

        try:
            player = item["player"]
            length = player.get_length()

            if length <= 0:
                self.player_status.set(
                    "لا يدعم هذا البث الانتقال إلى موضع محدد."
                )
                return

            value = float(item["seek_scale"].get())
            target = int(value * length / 1000.0)

            player.set_time(target)

        except Exception as exc:
            self.log("تعذر تغيير موضع الفيديو: " + str(exc))

    def player_hover_seek(self, tab_id, event):

        item = self.player_tabs.get(tab_id)
        if not item or not PIL_AVAILABLE:
            return

        if not self.ffmpeg_path:
            self.ffmpeg_path = self.find_ffmpeg()
            if not self.ffmpeg_path:
                return

        try:
            length = item["player"].get_length()
            if length <= 0:
                return

            scale = item["seek_scale"]
            x0 = scale.coords(0)[0]
            x1 = scale.coords(1000)[0]
            if x1 == x0:
                return
            fraction = max(0.0, min(1.0,
                (float(event.x) - x0) / float(x1 - x0)))
            target_ms = int(length * fraction)
            target_seconds = max(0.0, target_ms / 1000.0)

            # نقسم الشريط إلى خانات ثانيتين لتقليل عمليات FFmpeg المتكررة.
            bucket = int(target_seconds / 2.0)
            key = (tab_id, bucket)
            if key == self.hover_preview_last_key:
                return

            self.hover_preview_last_key = key

            # اعرض أقرب إطار محفوظ فوراً، دون انتظار FFmpeg.
            cached = self.hover_preview_cache.get(key)
            if cached is None:
                nearby = [
                    (abs(k[1] - bucket), image)
                    for k, image in self.hover_preview_cache.items()
                    if k[0] == tab_id and abs(k[1] - bucket) <= 2
                ]
                if nearby:
                    nearby.sort(key=lambda pair: pair[0])
                    cached = nearby[0][1]

            if cached is not None:
                self.render_hover_preview(tab_id, target_seconds, cached)
                # إذا كانت الخانة نفسها محفوظة فلا داعي لاستخراجها مرة أخرى.
                if key in self.hover_preview_cache:
                    return

            self.hover_preview_token += 1
            token = self.hover_preview_token

            if self.hover_preview_after:
                try:
                    self.root.after_cancel(self.hover_preview_after)
                except Exception:
                    pass

            # تقليل التأخير قبل بدء الاستخراج من 350 إلى 100 مللي ثانية.
            self.hover_preview_after = self.root.after(
                100,
                lambda: self.start_hover_frame_job(
                    tab_id, target_seconds, token
                )
            )
        except Exception:
            pass

    def start_hover_frame_job(self, tab_id, seconds, token):

        item = self.player_tabs.get(tab_id)
        if not item or not self.ffmpeg_path:
            return

        source = item.get("path")
        if not source:
            return
        if not item.get("is_stream") and not os.path.isfile(source):
            return

        headers = item.get("http_headers") or {}
        threading.Thread(
            target=self.hover_frame_worker,
            args=(tab_id, source, seconds, token, headers),
            daemon=True
        ).start()

    def hover_frame_worker(self, tab_id, source, seconds, token, http_headers=None):

        temp_path = None
        try:
            handle, temp_path = tempfile.mkstemp(
                prefix="svd_hover_", suffix=".jpg"
            )
            os.close(handle)

            command = [
                self.ffmpeg_path,
                "-hide_banner",
                "-loglevel", "error",
                "-nostdin",
                "-rw_timeout", "15000000",
                "-probesize", "32768",
                "-analyzeduration", "0",
            ]

            # روابط YouTube المباشرة قد ترفض FFmpeg ما لم تُرسل
            # ترويسات HTTP نفسها التي استخرجها yt-dlp.
            headers = http_headers or {}
            header_lines = []
            for header_name, header_value in headers.items():
                if header_value is None:
                    continue
                header_name = str(header_name).strip()
                header_value = str(header_value).replace("\r", "").replace("\n", "").strip()
                if header_name and header_value:
                    header_lines.append(header_name + ": " + header_value)

            if header_lines:
                command.extend(["-headers", "\r\n".join(header_lines) + "\r\n"])

            # وضع -ss قبل -i يطلب الإطار المطلوب مباشرة بدلاً من
            # قراءة البث من بدايته حتى الزمن المحدد.
            command.extend([
                "-ss", "{:.3f}".format(seconds),
                "-i", source,
                "-frames:v", "1",
                "-vf", "scale=220:-2",
                "-q:v", "5",
                "-y", temp_path
            ])

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=12,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            if (
                result.returncode == 0
                and os.path.isfile(temp_path)
                and os.path.getsize(temp_path) > 0
            ):
                self.messages.put((
                    "hover_thumb_ok",
                    (tab_id, token, seconds, temp_path)
                ))
                return

            error_text = result.stderr.decode("utf-8", "replace").strip()
            if not error_text:
                error_text = "تعذر استخراج إطار المعاينة من مصدر الفيديو."
            raise Exception(error_text[-900:])

        except Exception as exc:
            try:
                self.messages.put((
                    "hover_thumb_error",
                    (tab_id, token, str(exc))
                ))
            except Exception:
                pass
            if temp_path and os.path.isfile(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def show_hover_preview(self, tab_id, seconds, image_path):

        if not PIL_AVAILABLE:
            return

        try:
            image = Image.open(image_path).convert("RGB")
            image.thumbnail((220, 125), Image.LANCZOS)
            cached_image = image.copy()

            item = self.player_tabs.get(tab_id)
            if item:
                length = item["player"].get_length()
                bucket = int(max(0.0, seconds) / 2.0)
                key = (tab_id, bucket)
                self.hover_preview_cache[key] = cached_image

                # حد أقصى للذاكرة حتى لا يتضخم استهلاك البرنامج مع الفيديوهات الطويلة.
                while len(self.hover_preview_cache) > self.hover_preview_cache_limit:
                    oldest_key = next(iter(self.hover_preview_cache))
                    self.hover_preview_cache.pop(oldest_key, None)

            self.render_hover_preview(tab_id, seconds, cached_image)

        except Exception as exc:
            self.log("تعذر عرض معاينة الإطار: " + str(exc))
        finally:
            try:
                os.remove(image_path)
            except Exception:
                pass

    def render_hover_preview(self, tab_id, seconds, image):

        if not PIL_AVAILABLE:
            return

        try:
            photo = ImageTk.PhotoImage(image)

            if self.hover_preview_window is None or not self.hover_preview_window.winfo_exists():
                self.hover_preview_window = tk.Toplevel(self.root)
                self.hover_preview_window.overrideredirect(True)
                self.hover_preview_window.attributes("-topmost", True)
                self.hover_preview_window.configure(bg="#202735")

                self.hover_preview_label = tk.Label(
                    self.hover_preview_window,
                    bg="#202735",
                    fg="white",
                    font=("Arial", 8),
                    compound="top",
                    padx=4,
                    pady=4
                )
                self.hover_preview_label.pack()

            self.hover_preview_photo = photo
            self.hover_preview_label.configure(
                image=photo,
                text=self.format_time(int(seconds * 1000))
            )

            item = self.player_tabs.get(tab_id)
            if item:
                scale = item["seek_scale"]
                length = item["player"].get_length()
                x0 = scale.coords(0)[0]
                x1 = scale.coords(1000)[0]
                if length > 0 and x1 > x0:
                    fraction = max(0.0, min(1.0,
                        (seconds * 1000.0) / float(length)))
                    cursor_x = scale.winfo_rootx() + int(
                        x0 + fraction * (x1 - x0)
                    )
                else:
                    cursor_x = scale.winfo_rootx()
                x = cursor_x - 110
                y = scale.winfo_rooty() - 145
                self.hover_preview_window.geometry(
                    "+{}+{}".format(max(0, x), max(0, y))
                )
                self.hover_preview_window.deiconify()
                self.hover_preview_window.lift()

        except Exception as exc:
            self.log("تعذر عرض معاينة الإطار: " + str(exc))

    def hide_hover_preview(self):

        if self.hover_preview_after:
            try:
                self.root.after_cancel(self.hover_preview_after)
            except Exception:
                pass
            self.hover_preview_after = None

        self.hover_preview_last_key = None
        self.hover_preview_token += 1

        try:
            if (
                self.hover_preview_window is not None
                and self.hover_preview_window.winfo_exists()
            ):
                self.hover_preview_window.withdraw()
        except Exception:
            pass

    def player_seek_relative(self, tab_id, seconds):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        try:
            player = item["player"]

            current = player.get_time()
            length = player.get_length()

            if current < 0 or length <= 0:
                self.player_status.set(
                    "الانتقال غير متاح لهذا البث حالياً."
                )
                return

            target = current + int(seconds * 1000)
            target = max(0, min(length, target))

            player.set_time(target)

        except Exception as exc:
            self.log("تعذر تقديم أو ترجيع الفيديو: " + str(exc))

    def player_schedule_seek_update(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        try:

            player = item["player"]

            if not item["seek_dragging"]:

                current = player.get_time()
                length = player.get_length()

                if current >= 0 and length > 0:

                    value = int(current * 1000.0 / length)

                    item["seek_scale"].set(
                        max(0, min(1000, value))
                    )

                    item["time_label"].configure(
                        text=self.format_time(current)
                        + " / "
                        + self.format_time(length)
                    )

                elif current >= 0:

                    item["time_label"].configure(
                        text=self.format_time(current)
                        + " / LIVE"
                    )

            item["seek_after"] = self.root.after(
                500,
                lambda i=tab_id:
                    self.player_schedule_seek_update(i)
            )

        except Exception:
            pass

    # =====================================================
    # وظائف المشغل
    # =====================================================

    def player_get_current_id(self):

        if not self.player_notebook:
            return None

        try:
            selected = self.player_notebook.select()

            if not selected:
                return None

            for tab_id, item in self.player_tabs.items():
                if str(item["frame"]) == str(selected):
                    return tab_id

        except Exception:
            pass

        return None

    def player_tab_changed(self, event=None):

        tab_id = self.player_get_current_id()

        # لا نترك نافذة ملء الشاشة مرتبطة بتبويب لم يعد هو المحدد.
        if (
            self.player_fullscreen_tab is not None
            and self.player_fullscreen_tab != tab_id
        ):
            self.player_exit_fullscreen()

        if tab_id is not None:
            item = self.player_tabs.get(tab_id)

            if item:
                self.player_status.set(
                    "الملف الحالي: " + item["title"]
                )

    def player_play(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        try:
            item["player"].play()
            item["playing"] = True

            self.player_status.set(
                "يعمل الآن: " + item["title"]
            )

        except Exception as exc:
            self.log("خطأ تشغيل المشغل: " + str(exc))

    def player_pause(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        try:
            item["player"].pause()
        except Exception as exc:
            self.log("خطأ الإيقاف المؤقت: " + str(exc))

    def player_stop(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        try:
            item["player"].stop()
            item["playing"] = False
        except Exception as exc:
            self.log("خطأ إيقاف الفيديو: " + str(exc))

    def player_set_volume(self, tab_id, value):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        try:
            item["player"].audio_set_volume(
                int(float(value))
            )
        except Exception:
            pass

    def player_fullscreen(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        if self.player_fullscreen_tab == tab_id:
            self.player_exit_fullscreen()
            return

        if self.player_fullscreen_tab is not None:
            self.player_exit_fullscreen()

        try:
            if not self.player_window or not self.player_window.winfo_exists():
                return

            # لا ننقل HWND الخاص بالفيديو إلى نافذة أخرى؛ فهذا قد يجعل
            # إخراج VLC أسود على بعض إصدارات Windows/VLC.
            # نوسّع النافذة الأصلية ونمدد نفس إطار الفيديو دون تغيير HWND.
            self.player_window.update_idletasks()
            item["fullscreen_geometry"] = self.player_window.geometry()

            # أثناء ملء الشاشة نمدد الفيديو على كامل النافذة، ثم نضع
            # شريط التقدم وأزرار التحكم فوقه في الأسفل (وليس أعلى الشاشة).
            video_frame = item["video_frame"]
            seek_row = item.get("seek_row")
            controls = item.get("controls")

            video_frame.pack_forget()
            video_frame.place(
                x=0, y=0, relwidth=1, relheight=1
            )

            # أزل إدارة pack مؤقتاً عن أشرطة التحكم حتى نحدد موضعها
            # صراحةً في أسفل مساحة الفيديو أثناء الشاشة الكاملة.
            if seek_row is not None and seek_row.winfo_exists():
                seek_row.pack_forget()
            if controls is not None and controls.winfo_exists():
                controls.pack_forget()

            if self.player_top_frame is not None:
                self.player_top_frame.pack_forget()
            if self.player_bottom_frame is not None:
                self.player_bottom_frame.pack_forget()

            self.player_notebook.pack_forget()
            self.player_notebook.place(
                x=0, y=0, relwidth=1, relheight=1
            )

            self.player_fullscreen_tab = tab_id
            item["fullscreen"] = True

            try:
                self.player_window.attributes("-fullscreen", True)
            except Exception:
                sw = self.player_window.winfo_screenwidth()
                sh = self.player_window.winfo_screenheight()
                self.player_window.geometry(
                    "{}x{}+0+0".format(sw, sh)
                )

            self.player_window.update_idletasks()

            # ثبّت أشرطة التحكم أسفل الشاشة، مع إبقائها فوق إطار الفيديو.
            controls_height = (
                controls.winfo_reqheight()
                if controls is not None and controls.winfo_exists()
                else 0
            )
            seek_height = (
                seek_row.winfo_reqheight()
                if seek_row is not None and seek_row.winfo_exists()
                else 0
            )

            if seek_row is not None and seek_row.winfo_exists():
                seek_row.place(
                    relx=0, rely=1, x=0, y=-controls_height,
                    anchor="sw", relwidth=1
                )
            if controls is not None and controls.winfo_exists():
                controls.place(
                    relx=0, rely=1, x=0, y=0,
                    anchor="sw", relwidth=1
                )

            # ارفع الأشرطة بعد إطار الفيديو حتى لا يغطيها إخراج VLC.
            if seek_row is not None and seek_row.winfo_exists():
                seek_row.lift()
            if controls is not None and controls.winfo_exists():
                controls.lift()

            self.player_window.lift()
            self.player_window.focus_force()
            self.player_window.bind(
                "<Escape>", self.player_exit_fullscreen
            )
            self.player_window.bind(
                "<F11>", self.player_toggle_fullscreen
            )

        except Exception as exc:
            self.player_exit_fullscreen()
            self.log("تعذر تفعيل ملء الشاشة: " + str(exc))

    def player_toggle_fullscreen(self, event=None):

        if self.player_fullscreen_tab is not None:
            self.player_exit_fullscreen()
        else:
            tab_id = self.player_get_current_id()
            if tab_id is not None:
                self.player_fullscreen(tab_id)

        return "break"

    def player_exit_fullscreen(self, event=None):

        tab_id = self.player_fullscreen_tab
        item = self.player_tabs.get(tab_id) if tab_id is not None else None
        restore_geometry = item.get("fullscreen_geometry") if item else None

        if item:
            try:
                # أعد إطار الفيديو إلى مدير التخطيط الأصلي مع الاحتفاظ
                # بنفس نافذة Windows التي يستخدمها VLC.
                item["video_frame"].place_forget()
                seek_row = item.get("seek_row")
                controls = item.get("controls")

                # أعد أشرطة التحكم إلى pack في ترتيبها الأصلي أسفل الفيديو:
                # الفيديو أولاً، ثم شريط التقدم، ثم أزرار التحكم.
                if seek_row is not None and seek_row.winfo_exists():
                    seek_row.place_forget()
                if controls is not None and controls.winfo_exists():
                    controls.place_forget()

                item["video_frame"].pack(fill="both", expand=True)
                if controls is not None and controls.winfo_exists():
                    controls.pack(fill="x")
                if seek_row is not None and seek_row.winfo_exists():
                    if controls is not None and controls.winfo_exists():
                        seek_row.pack(fill="x", before=controls)
                    else:
                        seek_row.pack(fill="x")
            except Exception as exc:
                self.log("تعذر استعادة إطار الفيديو: " + str(exc))

            item["fullscreen"] = False
            item.pop("fullscreen_geometry", None)

        try:
            if self.player_notebook is not None:
                self.player_notebook.place_forget()

            if self.player_top_frame is not None and self.player_top_frame.winfo_exists():
                self.player_top_frame.pack(fill="x")

            if self.player_notebook is not None and self.player_notebook.winfo_exists():
                self.player_notebook.pack(
                    fill="both", expand=True, padx=8, pady=8
                )

            if self.player_bottom_frame is not None and self.player_bottom_frame.winfo_exists():
                self.player_bottom_frame.pack(fill="x")

            if self.player_window is not None and self.player_window.winfo_exists():
                try:
                    self.player_window.attributes("-fullscreen", False)
                except Exception:
                    pass

                if restore_geometry:
                    self.player_window.geometry(restore_geometry)

                self.player_window.lift()
                self.player_window.focus_force()
        except Exception as exc:
            self.log("تعذر الخروج من ملء الشاشة: " + str(exc))

        self.player_fullscreen_window = None
        self.player_fullscreen_tab = None
        return "break"

    def player_close_current_tab(self):

        tab_id = self.player_get_current_id()

        if tab_id is not None:
            self.player_release_tab(tab_id)

    def player_release_tab(self, tab_id):

        item = self.player_tabs.get(tab_id)

        if not item:
            return

        if item.get("seek_after"):
            try:
                self.root.after_cancel(item["seek_after"])
            except Exception:
                pass

        if self.player_fullscreen_tab == tab_id:
            self.player_exit_fullscreen()

        try:
            item["player"].stop()
        except Exception:
            pass

        try:
            item["player"].release()
        except Exception:
            pass

        try:
            item["media"].release()
        except Exception:
            pass

        try:
            item["instance"].release()
        except Exception:
            pass

        try:
            self.player_notebook.forget(item["frame"])
        except Exception:
            pass

        del self.player_tabs[tab_id]

        self.player_status.set(
            "افتح ملف فيديو للبدء"
            if not self.player_tabs
            else "تم إغلاق التبويب"
        )

        self.log("تم إغلاق تبويب الفيديو وتحرير موارده.")

    def close_player_window(self):

        if self.player_window is None:
            return

        if self.player_fullscreen_tab is not None:
            self.player_exit_fullscreen()

        for tab_id in list(self.player_tabs.keys()):
            self.player_release_tab(tab_id)

        self.player_fullscreen_window = None
        self.player_fullscreen_tab = None
        self.player_notebook = None

        try:
            if self.player_window.winfo_exists():
                self.player_window.destroy()
        except Exception:
            pass

        self.player_window = None

        self.log("تم إغلاق مشغل الفيديو المستقل.")    # =====================================================
    # مراقبة الحافظة
    # =====================================================

    def read_clipboard(self):

        try:
            return self.root.clipboard_get().strip()
        except Exception:
            return ""

    def is_valid_url(self, text):

        if not text:
            return False

        text = text.strip()

        return (
            text.startswith("https://")
            or text.startswith("http://")
        )

    def monitor_clipboard(self):

        try:
            clipboard_text = self.read_clipboard()

            if clipboard_text != self.last_clipboard_text:

                self.last_clipboard_text = clipboard_text

                if self.is_valid_url(clipboard_text):
                    self.accept_copied_url(clipboard_text)

        except Exception:
            pass

        try:
            self.root.after(700, self.monitor_clipboard)
        except Exception:
            pass

    def accept_copied_url(self, url):

        url = url.strip()

        if not self.is_valid_url(url):
            return

        if self.downloading:
            self.log(
                "تم نسخ رابط جديد، لكن التحميل الحالي لم ينته بعد."
            )
            return

        current_entry = self.url_entry.get().strip()

        if url == current_entry and (
            url == self.current_url or self.checking_info
        ):
            return

        self.stop_preview()

        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, url)
        self.url_entry.icursor(tk.END)

        self.log("تم التقاط رابط جديد من الحافظة تلقائيا")

        self.pending_url = url

        if self.checking_info:
            return

        self.root.after(250, self.check_info)

    # =====================================================
    # قائمة الماوس الأيمن
    # =====================================================

    def add_context_menu(self, widget):

        menu = tk.Menu(
            widget,
            tearoff=0,
            bg="#202735",
            fg="white",
            activebackground="#2878d0",
            activeforeground="white"
        )

        menu.add_command(
            label="قص",
            command=lambda: widget.event_generate("<<Cut>>")
        )

        menu.add_command(
            label="نسخ",
            command=lambda: widget.event_generate("<<Copy>>")
        )

        menu.add_command(
            label="لصق",
            command=lambda: widget.event_generate("<<Paste>>")
        )

        menu.add_separator()

        if isinstance(widget, tk.Text):
            menu.add_command(
                label="تحديد الكل",
                command=lambda: widget.tag_add("sel", "1.0", "end")
            )
        else:
            menu.add_command(
                label="تحديد الكل",
                command=lambda: widget.select_range(0, tk.END)
            )

        def show(event):
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
            menu.grab_release()

        widget.bind("<Button-3>", show)

    # =====================================================
    # yt-dlp
    # =====================================================

    def prepare_ytdlp(self):

        if not os.path.isdir(YTDLP_PATH):
            raise Exception(
                "لم يتم العثور على مجلد yt-dlp المحلي:\n"
                + YTDLP_PATH
            )

        # إتاحة curl_cffi قبل استيراد yt-dlp لاكتشافها كمكتبة اختيارية.
        if os.path.isdir(CURL_CFFI_PATH) and CURL_CFFI_PATH not in sys.path:
            sys.path.insert(0, CURL_CFFI_PATH)

        if YTDLP_PATH not in sys.path:
            sys.path.insert(0, YTDLP_PATH)

        try:
            import yt_dlp
            return yt_dlp
        except Exception as exc:
            raise Exception(
                "تعذر تحميل مكتبة yt-dlp المحلية:\n" + str(exc)
            )

    def apply_site_options(self, options, url):

        """تفعيل محاكاة Chrome لموقع Dailymotion فقط."""
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""

        if host == "dailymotion.com" or host.endswith(".dailymotion.com"):
            if not os.path.isdir(CURL_CFFI_PATH):
                raise Exception(
                    "دعم Dailymotion يحتاج مكتبة curl_cffi.\n"
                    "لم يتم العثور عليها في: " + CURL_CFFI_PATH
                )

            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget
                options["impersonate"] = ImpersonateTarget.from_str("chrome-110")
            except Exception as exc:
                raise Exception(
                    "تعذر تفعيل محاكاة Chrome لموقع Dailymotion: " + str(exc)
                )

        return options

    def get_youtube_options(self):

        return {
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"]
                }
            }
        }

    def selected_format(self):

        if self.type_var.get() == "MP3":
            return "bestaudio/best"

        quality = self.quality_var.get()

        if quality == "أفضل جودة":
            return "best"

        height = quality.replace("p", "")

        return "best[height<=" + height + "]/best"

    def base_options(self, extra=None):

        options = {
            "quiet": True,
            "no_warnings": False,
            "ignoreerrors": False,
            "noplaylist": not self.playlist_var.get(),
            "outtmpl": os.path.join(
                self.download_folder,
                "%(title)s.%(ext)s"
            ),
            "continuedl": True,
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 30,
            "windowsfilenames": True
        }

        options.update(self.get_youtube_options())

        ffmpeg_path = self.ffmpeg_path or self.refresh_ffmpeg()
        if ffmpeg_path:
            options["ffmpeg_location"] = ffmpeg_path

        if extra:
            options.update(extra)

        return options

    # =====================================================
    # فحص الرابط
    # =====================================================

    def on_url_enter(self, event=None):
        self.check_info()
        return "break"

    def on_url_focus_out(self, event=None):

        url = self.url_entry.get().strip()

        if url and url != self.current_url:
            self.root.after(350, self.check_info)

    def clear_url(self):

        if self.downloading:
            return

        self.stop_preview()

        self.url_entry.delete(0, tk.END)

        self.current_url = ""
        self.pending_url = ""
        self.pending_custom_filename = None
        self.pending_custom_filename_url = None
        self.info_data = None
        self.last_clipboard_text = ""

        self.title_var.set(
            "انسخ رابط فيديو من المتصفح أو أدخله هنا"
        )

        self.size_var.set("الحجم المتوقع: --")
        self.duration_var.set("المدة: --")

        self.thumb_label.configure(
            image="",
            text="الصورة\nالمصغرة"
        )

        self.thumbnail_image = None

    def check_info(self):

        url = self.url_entry.get().strip()

        if not url or self.downloading:
            return

        if self.checking_info:

            if url != self.current_url:
                self.pending_url = url

            return

        if url == self.current_url and self.info_data:
            return

        self.stop_preview()

        self.current_url = url
        self.pending_url = ""

        self.info_data = None
        self.checking_info = True

        self.title_var.set("جارٍ فحص الرابط...")
        self.size_var.set("الحجم المتوقع: جارٍ الحساب...")
        self.duration_var.set("المدة: --")
        self.status_var.set("جارٍ فحص معلومات الفيديو")

        self.thumbnail_image = None

        self.thumb_label.configure(
            image="",
            text="جارٍ تحميل\nالصورة..."
        )

        self.log("جارٍ فحص الرابط...")

        threading.Thread(
            target=self.info_worker,
            args=(url,),
            daemon=True
        ).start()

    def info_worker(self, url):

        try:
            module = self.prepare_ytdlp()

            options = self.base_options({
                "skip_download": True,
                "extract_flat": False
            })
            options = self.apply_site_options(options, url)

            with module.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                raise Exception("لم يرجع الموقع معلومات للفيديو")

            self.messages.put(("info_ok", (url, info)))

        except Exception as exc:
            self.messages.put(("info_error", (url, str(exc))))

        finally:
            self.messages.put(("info_done", url))

    # =====================================================
    # حساب الحجم والمدة
    # =====================================================

    def format_size(self, size):

        if size is None:
            return "غير متاح"

        try:
            size = float(size)
        except Exception:
            return "غير متاح"

        if size < 0:
            return "غير متاح"

        for unit in ("B", "KB", "MB", "GB", "TB"):

            if size < 1024:
                return "{:.2f} {}".format(size, unit)

            size /= 1024.0

        return "{:.2f} TB".format(size)

    def format_duration(self, seconds):

        if seconds is None:
            return "--"

        try:
            seconds = int(seconds)
        except Exception:
            return "--"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours:
            return "{:02d}:{:02d}:{:02d}".format(
                hours, minutes, secs
            )

        return "{:02d}:{:02d}".format(minutes, secs)

    def estimate_size(self, info):

        if not isinstance(info, dict):
            return None

        if info.get("_type") == "playlist":
            return None

        formats = info.get("formats") or []

        if not formats:
            return (
                info.get("filesize")
                or info.get("filesize_approx")
            )

        if self.type_var.get() == "MP3":

            audio = [
                f for f in formats
                if f.get("acodec") not in (None, "none")
            ]

            audio.sort(
                key=lambda f: f.get("abr") or 0,
                reverse=True
            )

            for fmt in audio:
                size = (
                    fmt.get("filesize")
                    or fmt.get("filesize_approx")
                )

                if size:
                    return size

            return None

        quality = self.quality_var.get()

        max_height = (
            99999
            if quality == "أفضل جودة"
            else int(quality.replace("p", ""))
        )

        video_candidates = [
            f for f in formats
            if f.get("vcodec") not in (None, "none")
            and (f.get("height") or 0) <= max_height
        ]

        video_candidates.sort(
            key=lambda f: (
                f.get("height") or 0,
                f.get("tbr") or 0
            ),
            reverse=True
        )

        audio_candidates = [
            f for f in formats
            if f.get("vcodec") in (None, "none")
            and f.get("acodec") not in (None, "none")
        ]

        audio_candidates.sort(
            key=lambda f: f.get("abr") or f.get("tbr") or 0,
            reverse=True
        )

        for fmt in video_candidates:

            if fmt.get("acodec") not in (None, "none"):

                size = (
                    fmt.get("filesize")
                    or fmt.get("filesize_approx")
                )

                if size:
                    return size

        if video_candidates and audio_candidates:

            video = video_candidates[0]
            audio = audio_candidates[0]

            video_size = (
                video.get("filesize")
                or video.get("filesize_approx")
            )

            audio_size = (
                audio.get("filesize")
                or audio.get("filesize_approx")
            )

            if video_size and audio_size:
                return video_size + audio_size

            if video_size:
                return video_size

        for fmt in video_candidates:

            size = (
                fmt.get("filesize")
                or fmt.get("filesize_approx")
            )

            if size:
                return size

        return (
            info.get("filesize")
            or info.get("filesize_approx")
        )

    def display_info(self, info):

        self.info_data = info

        self.title_var.set(
            info.get("title") or "بدون عنوان"
        )

        if info.get("_type") == "playlist":

            self.size_var.set(
                "الحجم المتوقع: غير متاح لقائمة التشغيل"
            )

        else:

            size = self.estimate_size(info)

            if size:
                self.size_var.set(
                    "الحجم المتوقع: "
                    + self.format_size(size)
                    + " (تقديري)"
                )
            else:
                self.size_var.set(
                    "الحجم المتوقع: غير متاح من الموقع"
                )

        self.duration_var.set(
            "المدة: "
            + self.format_duration(info.get("duration"))
        )

        thumbnails = self.get_thumbnail_candidates(info)

        self.thumbnail_image = None

        if thumbnails:

            self.thumb_label.configure(
                image="",
                text="جارٍ تحميل\nالصورة..."
            )

            threading.Thread(
                target=self.thumbnail_worker,
                args=(thumbnails, self.current_url),
                daemon=True
            ).start()

        else:

            self.thumb_label.configure(
                image="",
                text="لا توجد\nصورة مصغرة"
            )

            self.log("لم يعثر yt-dlp على روابط صور مصغرة.")

        self.status_var.set("تم فحص الرابط")
        self.log("تم استخراج معلومات الرابط")

    # =====================================================
    # الصور المصغرة
    # =====================================================

    def get_thumbnail_candidates(self, info):

        candidates = []
        seen = set()

        thumbnails = info.get("thumbnails") or []

        if isinstance(thumbnails, list):

            valid = []

            for item in thumbnails:

                if not isinstance(item, dict):
                    continue

                url = item.get("url")

                if not url:
                    continue

                width = item.get("width") or 0
                height = item.get("height") or 0

                try:
                    area = int(width) * int(height)
                except Exception:
                    area = 0

                valid.append((area, url))

            valid.sort(reverse=True)

            for area, url in valid:

                if url not in seen:
                    candidates.append(url)
                    seen.add(url)

        thumbnail = info.get("thumbnail")

        if thumbnail and thumbnail not in seen:
            candidates.append(thumbnail)
            seen.add(thumbnail)

        youtube_url = (
            info.get("webpage_url")
            or info.get("original_url")
            or ""
        )

        extractor = (
            info.get("extractor_key")
            or info.get("extractor")
            or ""
        ).lower()

        video_id = info.get("id")

        is_youtube = (
            "youtube" in extractor
            or "youtube.com" in youtube_url.lower()
            or "youtu.be" in youtube_url.lower()
        )

        if is_youtube and video_id:

            video_id = str(video_id).strip()

            if video_id and video_id not in (".", ".."):

                backup_urls = [
                    "https://i.ytimg.com/vi/"
                    + video_id
                    + "/maxresdefault.jpg",

                    "https://i.ytimg.com/vi/"
                    + video_id
                    + "/hqdefault.jpg",

                    "https://i.ytimg.com/vi/"
                    + video_id
                    + "/mqdefault.jpg"
                ]

                for url in backup_urls:

                    if url not in seen:
                        candidates.append(url)
                        seen.add(url)

        return candidates

    def thumbnail_worker(self, urls, source_url):

        if not PIL_AVAILABLE:

            self.messages.put((
                "thumb_error",
                (source_url, "مكتبة Pillow غير مثبتة")
            ))

            return

        if isinstance(urls, str):
            urls = [urls]

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 6.1; WOW64) "
                "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
            ),
            "Accept": (
                "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            ),
            "Referer": "https://www.youtube.com/"
        }

        errors = []

        for url in urls:

            try:

                request = urllib.request.Request(
                    url,
                    headers=headers
                )

                with urllib.request.urlopen(
                    request,
                    timeout=20
                ) as response:
                    raw = response.read()

                if not raw:
                    raise Exception("الصورة المستلمة فارغة")

                image = Image.open(BytesIO(raw))
                image.load()
                image = image.convert("RGB")

                if image.width < 40 or image.height < 30:
                    raise Exception("أبعاد الصورة صغيرة أو غير صالحة")

                image.thumbnail((220, 145), Image.LANCZOS)

                self.messages.put((
                    "thumb_ok",
                    (source_url, image.copy())
                ))

                return

            except Exception as exc:
                errors.append("{}: {}".format(url, str(exc)))

        error_message = "فشلت جميع محاولات تحميل الصورة."

        if errors:
            error_message += "\n" + errors[-1]

        self.messages.put((
            "thumb_error",
            (source_url, error_message)
        ))

    # =====================================================
    # مجلد التحميل
    # =====================================================

    def choose_folder(self):

        folder = filedialog.askdirectory(
            initialdir=self.download_folder,
            title="اختر مجلد التحميل"
        )

        if folder:
            self.download_folder = folder
            self.folder_var.set(folder)
            self.save_settings()
            self.log("تم حفظ مجلد التحميل: " + folder)

    def open_folder(self):

        try:

            if not os.path.isdir(self.download_folder):
                os.makedirs(self.download_folder)

            os.startfile(self.download_folder)

        except Exception as exc:
            messagebox.showerror("خطأ", str(exc))

    # =====================================================
    # بدء التحميل وإيقافه مؤقتاً واستئنافه
    # =====================================================

    def refresh_queue_view(self):

        if not hasattr(self, "queue_tree"):
            return
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        for index, item in enumerate(self.download_queue, 1):
            title = item.get("title") or item.get("url") or ""
            self.queue_tree.insert(
                "", "end", iid=str(item["id"]),
                values=(
                    index,
                    title,
                    item.get("custom_filename") or "الاسم الأصلي",
                    item.get("status", "في الانتظار")
                )
            )

    def add_queue_urls(self, urls):

        added = 0
        for url in urls:
            url = url.strip()
            if not url or not url.lower().startswith(("http://", "https://")):
                continue
            self.queue_counter += 1
            self.download_queue.append({
                "id": self.queue_counter,
                "url": url,
                "title": url,
                "custom_filename": None,
                "status": "في الانتظار"
            })
            added += 1
        self.refresh_queue_view()
        if added:
            self.status_var.set("تمت إضافة {} عنصر إلى قائمة الانتظار".format(added))
            self.log("تمت إضافة {} رابط إلى قائمة الانتظار.".format(added))
        return added

    def add_to_queue(self):

        if self.downloading:
            return
        url = self.url_entry.get().strip()
        added = self.add_queue_urls(url.splitlines())
        if added and self.pending_custom_filename and self.pending_custom_filename_url == url:
            for item in reversed(self.download_queue):
                if item.get("url") in [part.strip() for part in url.splitlines() if part.strip()]:
                    item["custom_filename"] = self.pending_custom_filename
                    break
            self.pending_custom_filename = None
            self.pending_custom_filename_url = None
            self.refresh_queue_view()
        if not added:
            messagebox.showwarning("تنبيه", "أدخل رابطاً صحيحاً أولاً.")

    def add_multiple_to_queue(self):

        if self.downloading:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("إضافة روابط متعددة")
        dialog.geometry("650x430")
        dialog.minsize(520, 340)
        dialog.configure(bg="#202735")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog,
            text="الصق الروابط أو اسحبها إلى المربع — رابط واحد في كل سطر:",
            bg="#202735",
            fg="white",
            font=("Arial", 11, "bold"),
            anchor="e"
        ).pack(fill="x", padx=12, pady=(10, 5))

        text_box = ScrolledText(
            dialog,
            bg="#111722",
            fg="white",
            insertbackground="white",
            font=("Arial", 10),
            wrap="word",
            undo=True
        )
        text_box.pack(fill="both", expand=True, padx=12, pady=5)
        text_box.focus_set()

        # قائمة تحرير صريحة مع دعم Ctrl+V و Shift+Insert.
        self.add_context_menu(text_box)

        def paste_clipboard(_event=None):
            try:
                clipboard_text = dialog.clipboard_get()
                if clipboard_text:
                    text_box.insert("insert", clipboard_text)
                return "break"
            except tk.TclError:
                return "break"

        text_box.bind("<Control-v>", paste_clipboard)
        text_box.bind("<Control-V>", paste_clipboard)
        text_box.bind("<Shift-Insert>", paste_clipboard)

        def receive_dialog_drop(event):
            """إدراج كل الروابط المسحوبة داخل مربع النص دون إسقاط العناصر."""
            raw = str(getattr(event, "data", "")).strip()
            if not raw:
                return "break"
            try:
                dropped_items = list(dialog.tk.splitlist(raw))
            except Exception:
                dropped_items = [raw]

            cleaned = []
            for entry in dropped_items:
                entry = str(entry).strip().strip("{}")
                if not entry:
                    continue
                # بعض أنظمة DND_TEXT ترسل عدة روابط في نص واحد.
                if "\n" in entry or "\r" in entry:
                    cleaned.extend(line.strip() for line in entry.splitlines() if line.strip())
                else:
                    cleaned.append(entry)

            if cleaned:
                text_box.insert("insert", "\n".join(cleaned) + "\n")
                text_box.focus_set()
            return "break"

        if DND_AVAILABLE:
            try:
                text_box.drop_target_register(DND_FILES, DND_TEXT)
                text_box.dnd_bind("<<Drop>>", receive_dialog_drop)
                tk.Label(
                    dialog,
                    text="السحب والإفلات مفعّل — اسحب الروابط من المتصفح أو ملفاً نصياً يحتوي على روابط",
                    bg="#202735",
                    fg="#20b486",
                    font=("Arial", 8)
                ).pack(fill="x", padx=12, pady=(0, 3))
            except Exception as exc:
                self.log("تعذر تفعيل السحب والإفلات في نافذة الروابط: " + str(exc))
        else:
            tk.Label(
                dialog,
                text="السحب والإفلات غير متاح: تأكد من تثبيت tkinterdnd2",
                bg="#202735",
                fg="#f0ad4e",
                font=("Arial", 8)
            ).pack(fill="x", padx=12, pady=(0, 3))

        def add_and_close():
            raw_text = text_box.get("1.0", "end-1c")
            # قبول الروابط المفصولة بأسطر أو مسافات أو فواصل منسوخة.
            import re
            candidates = re.split(r"[\s,;]+", raw_text)
            count = self.add_queue_urls(candidates)
            if count:
                dialog.grab_release()
                dialog.destroy()
            else:
                messagebox.showwarning(
                    "تنبيه",
                    "لم يتم العثور على روابط صحيحة. تأكد أن كل رابط يبدأ بـ http:// أو https://",
                    parent=dialog
                )

        buttons = tk.Frame(dialog, bg="#202735")
        buttons.pack(fill="x", padx=12, pady=(5, 10))
        self.button(
            buttons, "إضافة إلى قائمة الانتظار", add_and_close, "#159b70", 24
        ).pack(side="right", padx=4)
        self.button(
            buttons, "إغلاق", dialog.destroy, "#495365", 10
        ).pack(side="left", padx=4)

    def remove_queue_item(self):

        if self.downloading:
            return
        selected = self.queue_tree.selection()
        if not selected:
            return
        selected_ids = {int(value) for value in selected}
        self.download_queue = [item for item in self.download_queue if item["id"] not in selected_ids]
        self.refresh_queue_view()

    def move_queue_item(self, direction):

        if self.downloading:
            return
        selected = self.queue_tree.selection()
        if not selected:
            return
        item_id = int(selected[0])
        index = next((i for i, item in enumerate(self.download_queue) if item["id"] == item_id), -1)
        target = index + direction
        if index < 0 or target < 0 or target >= len(self.download_queue):
            return
        self.download_queue[index], self.download_queue[target] = self.download_queue[target], self.download_queue[index]
        self.refresh_queue_view()
        self.queue_tree.selection_set(str(item_id))

    def clear_queue(self):

        if self.downloading:
            return
        self.download_queue.clear()
        self.refresh_queue_view()
        self.status_var.set("قائمة الانتظار فارغة")

    def start_queue_download(self):

        if self.downloading:
            return
        if not self.download_queue:
            # تسهيل الاستخدام: إذا لم تتم إضافة عناصر يدوياً، أضف الرابط الموجود بالأعلى.
            url = self.url_entry.get().strip()
            if url:
                added = self.add_queue_urls(url.splitlines())
                if added and self.pending_custom_filename and self.pending_custom_filename_url == url:
                    for item in reversed(self.download_queue):
                        if item.get("url") == url:
                            item["custom_filename"] = self.pending_custom_filename
                            break
                    self.pending_custom_filename = None
                    self.pending_custom_filename_url = None
                    self.refresh_queue_view()
        if not self.download_queue:
            messagebox.showwarning("قائمة الانتظار فارغة", "أضف رابطاً واحداً على الأقل قبل بدء التحميل.")
            return
        if self.type_var.get() == "MP3":
            ffmpeg_path = self.refresh_ffmpeg()
            if not ffmpeg_path:
                messagebox.showerror("FFmpeg غير موجود", "تحويل الملفات إلى MP3 يحتاج إلى FFmpeg.")
                return
        if not os.path.isdir(self.download_folder):
            try:
                os.makedirs(self.download_folder)
            except Exception as exc:
                messagebox.showerror("خطأ", str(exc))
                return

        self.stop_preview()
        self.save_settings()
        self.downloading = True
        self.queue_running = True
        self.download_paused = False
        self.download_pause_event.set()
        self.queue_success_count = 0
        self.queue_error_count = 0
        self.last_file = ""
        self.download_started_at = time.time()

        for item in self.download_queue:
            item["status"] = "في الانتظار"
        self.refresh_queue_view()

        self.download_button.configure(text="التحميل عبر قائمة الانتظار...", state="disabled")
        self.start_queue_button.configure(state="disabled")
        self.pause_download_button.configure(state="normal")
        self.resume_download_button.configure(state="disabled")
        self.progress["value"] = 0
        self.percent_var.set("0%")
        self.progress_info_var.set("جارٍ تجهيز قائمة الانتظار...")
        self.speed_var.set("السرعة: --")
        self.eta_var.set("الوقت المتبقي: --")
        self.status_var.set("قائمة الانتظار تعمل")
        self.log("بدأت قائمة الانتظار: سيتم تنزيل عنصر واحد في كل مرة.")

        threading.Thread(target=self.download_worker, args=(None,), daemon=True).start()

    def start_download(self):

        # زر التحميل الفردي يضيف الرابط الحالي ثم يشغّل قائمة الانتظار.
        if self.downloading:
            return
        url = self.url_entry.get().strip()
        if url:
            added = self.add_queue_urls(url.splitlines())
            if added and self.pending_custom_filename and self.pending_custom_filename_url == url:
                for item in reversed(self.download_queue):
                    if item.get("url") in [part.strip() for part in url.splitlines() if part.strip()]:
                        item["custom_filename"] = self.pending_custom_filename
                        break
                self.pending_custom_filename = None
                self.pending_custom_filename_url = None
                self.refresh_queue_view()
        self.start_queue_download()

    def pause_download(self):

        if not self.downloading or self.download_paused:
            return

        self.download_paused = True
        self.download_pause_event.clear()

        self.pause_download_button.configure(state="disabled")
        self.resume_download_button.configure(state="normal")

        self.status_var.set("التحميل متوقف مؤقتاً")
        self.progress_info_var.set("التحميل متوقف مؤقتاً")

        self.log("تم إيقاف التحميل مؤقتاً.")

    def resume_download(self):

        if not self.downloading or not self.download_paused:
            return

        self.download_paused = False
        self.download_pause_event.set()

        self.pause_download_button.configure(state="normal")
        self.resume_download_button.configure(state="disabled")

        self.status_var.set("استؤنف التحميل")
        self.progress_info_var.set("استؤنف التحميل...")

        self.log("تم استئناف التحميل.")

    # =====================================================
    # محرك التحميل
    # =====================================================

    def download_worker(self, url=None):

        try:
            module = self.prepare_ytdlp()
            # نعالج العناصر بالتتابع داخل Thread واحد؛ لذلك لا يوجد تنزيلان متزامنان.
            worklist = list(self.download_queue)
            position = 0
            while position < len(worklist):
                item = worklist[position]
                item_id = item["id"]
                source_url = item["url"]

                self.messages.put(("queue_item_status", (item_id, "جارٍ فحص الرابط")))
                urls_to_download = [(source_url, item.get("title") or source_url)]

                if self.playlist_var.get():
                    try:
                        inspect_options = self.base_options({
                            "skip_download": True,
                            "extract_flat": True,
                            "noplaylist": False
                        })
                        inspect_options = self.apply_site_options(inspect_options, source_url)
                        with module.YoutubeDL(inspect_options) as ydl:
                            playlist_info = ydl.extract_info(source_url, download=False)
                        entries = playlist_info.get("entries") if isinstance(playlist_info, dict) else None
                        if entries:
                            expanded = []
                            for entry in entries:
                                if not entry:
                                    continue
                                video_url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url")
                                if video_url and not str(video_url).startswith(("http://", "https://")):
                                    video_id = entry.get("id") or video_url
                                    video_url = "https://www.youtube.com/watch?v=" + str(video_id)
                                if video_url:
                                    expanded.append((str(video_url), entry.get("title") or str(video_url)))
                            if expanded:
                                urls_to_download = expanded
                    except Exception as playlist_error:
                        self.messages.put(("log", "تعذر توسيع القائمة أو لم يكن الرابط قائمة تشغيل؛ ستتم محاولة تنزيل الرابط كما هو: " + str(playlist_error)))

                # تحويل رابط القائمة إلى عناصر مستقلة ظاهرة في الواجهة.
                work_items = []
                if len(urls_to_download) > 1:
                    child_rows = []
                    for video_url, video_title in urls_to_download:
                        self.queue_counter += 1
                        child_id = self.queue_counter
                        work_items.append((child_id, video_url, video_title))
                        child_rows.append({"id": child_id, "url": video_url, "title": video_title, "status": "في الانتظار"})
                    self.messages.put(("queue_expand", (item_id, child_rows)))
                else:
                    work_items = [(item_id, urls_to_download[0][0], urls_to_download[0][1])]

                item_had_error = False
                for video_index, (work_id, video_url, video_title) in enumerate(work_items, 1):
                    try:
                        self.download_started_at = time.time()
                        self.messages.put(("queue_item_status", (work_id, "جارٍ التحميل")))
                        options = self.base_options({
                            "format": self.selected_format(),
                            "progress_hooks": [self.progress_hook],
                            "postprocessor_hooks": [self.postprocessor_hook],
                            "logger": self.make_logger(),
                            "noplaylist": True
                        })
                        options = self.apply_site_options(options, video_url)
                        custom_filename = next(
                            (
                                queued.get("custom_filename")
                                for queued in self.download_queue
                                if queued.get("id") == work_id
                            ),
                            None
                        )
                        if custom_filename:
                            options["outtmpl"] = self.unique_output_template(custom_filename)
                        if self.type_var.get() == "MP3":
                            options["format"] = "bestaudio/best"
                            options["postprocessors"] = [{
                                "key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "192"
                            }]
                        try:
                            with module.YoutubeDL(options) as ydl:
                                info = ydl.extract_info(video_url, download=True)
                                filename = self.resolve_filename(ydl, info)
                        except Exception as first_error:
                            error_text = str(first_error).lower()
                            unavailable = (
                                "requested format is not available" in error_text
                                or "format is not available" in error_text
                                or "no video formats found" in error_text
                            )
                            if not unavailable or self.type_var.get() == "MP3":
                                raise
                            self.messages.put(("log", "الجودة المختارة غير متاحة؛ ستتم إعادة المحاولة بأفضل صيغة."))
                            retry_options = dict(options)
                            retry_options["format"] = "best"
                            with module.YoutubeDL(retry_options) as ydl:
                                info = ydl.extract_info(video_url, download=True)
                                filename = self.resolve_filename(ydl, info)
                        if not self.is_valid_download_file(filename):
                            raise RuntimeError(
                                "لم يتم العثور على ملف ناتج صالح بعد انتهاء yt-dlp؛ "
                                "لن يتم تسجيل العنصر كمكتمل."
                            )

                        self.messages.put(("queue_file_ok", (work_id, filename, video_title)))
                        self.messages.put(("queue_item_success", work_id))

                    except Exception as item_error:
                        item_had_error = True
                        self.queue_error_count += 1
                        self.messages.put(("queue_item_status", (work_id, "فشل")))
                        self.messages.put(("log", "فشل تنزيل {}: {}".format(video_title, item_error)))

                position += 1

        except Exception as exc:
            # الخطأ على مستوى عنصر واحد يُعالج في مسار العنصر؛ هذا المسار احتياطي لأخطاء المحرك.
            self.messages.put(("download_error", str(exc)))
        finally:
            self.messages.put(("download_done", None))

    def sanitize_custom_filename(self, value):
        """تنظيف الاسم المخصص مع ترك امتداد الملف الأصلي لـ yt-dlp."""
        import re
        name = str(value or "").strip()
        known_extensions = {
            ".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".opus", ".wav",
            ".mov", ".avi", ".flv", ".m4v", ".3gp", ".mpeg", ".mpg"
        }
        extension = os.path.splitext(name)[1].lower()
        if extension in known_extensions:
            name = name[:-len(extension)]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = name.strip().rstrip(". ")
        if not name:
            raise ValueError("اكتب اسماً صالحاً للملف.")
        if name.upper() in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))
        }:
            name = "_" + name
        return name[:180]

    def unique_output_template(self, filename):
        """اختيار اسم غير مستخدم لمنع استبدال ملف موجود دون تنبيه."""
        stem = self.sanitize_custom_filename(filename)
        try:
            existing = os.listdir(self.download_folder)
        except OSError:
            existing = []
        candidate = stem
        suffix = 1
        while any(
            entry.casefold().startswith((candidate + ".").casefold())
            or entry.casefold() == candidate.casefold()
            for entry in existing
        ):
            candidate = "{} ({})".format(stem, suffix)
            suffix += 1
        return os.path.join(self.download_folder, candidate + ".%(ext)s")

    def edit_pending_download_name(self):
        """تحديد اسم مخصص للرابط الحالي قبل إضافته أو بدء تنزيله مباشرة."""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("تعديل اسم الملف", "أدخل رابط الفيديو أولاً.")
            return
        initial = self.pending_custom_filename or self.title_var.get()
        value = simpledialog.askstring(
            "تعديل اسم الملف",
            "اكتب الاسم المطلوب بدون الامتداد:",
            initialvalue=initial if initial and not initial.startswith("انسخ رابط") else "",
            parent=self.root
        )
        if value is None:
            return
        try:
            self.pending_custom_filename = self.sanitize_custom_filename(value)
            self.pending_custom_filename_url = url
        except ValueError as exc:
            messagebox.showwarning("اسم غير صالح", str(exc))
            return
        self.status_var.set("اسم الحفظ المخصص: " + self.pending_custom_filename)
        self.log("تم تحديد اسم مخصص للرابط الحالي: " + self.pending_custom_filename)

    def edit_selected_queue_filename(self, event=None):
        if self.downloading:
            return "break" if event else None
        selected = self.queue_tree.selection()
        if not selected:
            return "break" if event else None
        item_id = int(selected[0])
        item = next((entry for entry in self.download_queue if entry["id"] == item_id), None)
        if not item:
            return "break" if event else None
        value = simpledialog.askstring(
            "تعديل اسم الملف",
            "اكتب الاسم المطلوب بدون الامتداد:",
            initialvalue=item.get("custom_filename") or item.get("title") or "",
            parent=self.root
        )
        if value is None:
            return "break" if event else None
        try:
            item["custom_filename"] = self.sanitize_custom_filename(value)
        except ValueError as exc:
            messagebox.showwarning("اسم غير صالح", str(exc), parent=self.root)
            return "break" if event else None
        self.refresh_queue_view()
        self.queue_tree.selection_set(str(item_id))
        self.log("تم تعديل اسم ملف عنصر في قائمة الانتظار إلى: " + item["custom_filename"])
        return "break" if event else None

    def clear_selected_queue_filename(self):
        if self.downloading:
            return
        selected = self.queue_tree.selection()
        if not selected:
            return
        item_id = int(selected[0])
        for item in self.download_queue:
            if item["id"] == item_id:
                item["custom_filename"] = None
                break
        self.refresh_queue_view()
        self.queue_tree.selection_set(str(item_id))
        self.log("سيتم تنزيل العنصر المحدد باسمه الأصلي.")

    def is_valid_download_file(self, path):
        """الملف لا يُعد ناتجاً ناجحاً إلا إذا كان موجوداً وحجمه أكبر من صفر."""
        try:
            return bool(
                path
                and os.path.isfile(path)
                and os.path.getsize(path) > 0
            )
        except (OSError, TypeError):
            return False

    def resolve_filename(self, ydl, info):

        if not isinstance(info, dict) or not info:
            return ""

        candidates = []

        # المسارات النهائية التي يضعها yt-dlp بعد النقل والمعالجة.
        for key in ("filepath", "_filename", "filename"):
            value = info.get(key)
            if value:
                candidates.append(value)

        # بعض مواقع التحميل تعيد مسار كل صيغة ضمن requested_downloads.
        for requested in (info.get("requested_downloads") or []):
            if isinstance(requested, dict):
                for key in ("filepath", "_filename", "filename"):
                    value = requested.get(key)
                    if value:
                        candidates.append(value)

        # اسم الملف المتوقع من yt-dlp، مع مراعاة تحويل MP3.
        try:
            prepared = ydl.prepare_filename(info)
        except Exception:
            prepared = ""

        if prepared:
            candidates.append(prepared)
            if self.type_var.get() == "MP3":
                candidates.append(os.path.splitext(prepared)[0] + ".mp3")

        # إزالة التكرار مع الحفاظ على ترتيب أولوية المسارات.
        seen = set()
        for candidate in candidates:
            if not candidate:
                continue
            candidate = os.path.abspath(os.path.expanduser(str(candidate)))
            if candidate in seen:
                continue
            seen.add(candidate)
            if self.is_valid_download_file(candidate):
                return candidate

        return ""

    # =====================================================
    # سجل yt-dlp
    # =====================================================

    def make_logger(self):

        app = self

        class Logger:

            def debug(self, message):
                pass

            def warning(self, message):
                app.messages.put(("log", str(message)))

            def error(self, message):
                app.messages.put(("log", str(message)))

        return Logger()

    # =====================================================
    # متابعة تقدم التحميل
    # =====================================================

    def progress_hook(self, data):

        while not self.download_pause_event.wait(0.2):
            pass

        if data.get("status") == "downloading":

            downloaded = data.get("downloaded_bytes") or 0

            total = (
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or 0
            )

            percent = 0

            if total:
                percent = downloaded * 100.0 / total

            self.messages.put((
                "progress",
                {
                    "percent": percent,
                    "downloaded": downloaded,
                    "total": total,
                    "filename": os.path.basename(
                        data.get("filename") or ""
                    ),
                    "speed": data.get("speed"),
                    "eta": data.get("eta")
                }
            ))

        elif data.get("status") == "finished":

            filename = data.get("filename") or ""

            self.messages.put((
                "file_finished",
                filename
            ))

    def postprocessor_hook(self, data):

        while not self.download_pause_event.wait(0.2):
            pass

        info = data.get("info_dict") or {}

        filename = (
            info.get("filepath")
            or info.get("_filename")
            or ""
        )

        if filename:
            self.messages.put(("file_finished", filename))

    def find_latest_file(self):

        try:

            candidates = []

            for name in os.listdir(self.download_folder):

                path = os.path.join(self.download_folder, name)

                if self.is_valid_download_file(path):

                    modified = os.path.getmtime(path)

                    if modified >= self.download_started_at - 5:
                        candidates.append((modified, path))

            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][1]

        except Exception:
            pass

        return ""

    # =====================================================
    # استقبال تحديثات البرنامج
    # =====================================================

    def process_messages(self):

        try:

            while True:

                kind, data = self.messages.get_nowait()

                if kind == "log":
                    self.log(data)

                elif kind == "info_ok":

                    source_url, info = data

                    if source_url == self.current_url:
                        self.display_info(info)

                elif kind == "info_error":

                    source_url, error = data

                    if source_url == self.current_url:

                        self.title_var.set(
                            "تعذر استخراج معلومات الرابط"
                        )

                        self.size_var.set(
                            "الحجم المتوقع: غير متاح"
                        )

                        self.duration_var.set("المدة: --")

                        self.thumb_label.configure(
                            image="",
                            text="لا توجد\nصورة متاحة"
                        )

                        self.status_var.set("فشل فحص الرابط")
                        self.log("خطأ فحص الرابط: " + str(error))

                elif kind == "info_done":

                    finished_url = data
                    self.checking_info = False

                    current_entry = self.url_entry.get().strip()

                    if current_entry and current_entry != finished_url:
                        self.root.after(200, self.check_info)

                elif kind == "thumb_ok":

                    source_url, image = data

                    if source_url == self.current_url:

                        self.thumbnail_image = ImageTk.PhotoImage(image)

                        self.thumb_label.configure(
                            image=self.thumbnail_image,
                            text=""
                        )

                        self.log("تم تحميل الصورة المصغرة بنجاح")

                elif kind == "thumb_error":

                    source_url, error = data

                    if source_url == self.current_url:

                        self.thumb_label.configure(
                            image="",
                            text="تعذر عرض\nالصورة"
                        )

                        self.log(
                            "تعذر تحميل الصورة المصغرة: " + str(error)
                        )

                elif kind == "hover_thumb_ok":

                    tab_id, token, seconds, image_path = data
                    if token == self.hover_preview_token:
                        self.show_hover_preview(
                            tab_id, seconds, image_path
                        )
                    else:
                        try:
                            os.remove(image_path)
                        except Exception:
                            pass

                elif kind == "hover_thumb_error":

                    tab_id, token, error = data
                    if token == self.hover_preview_token:
                        self.log("تعذر إنشاء الصورة المصغرة من بث YouTube: " + error)

                elif kind == "preview_ready":

                    source_url, stream_url = data

                    if source_url == self.current_url:
                        self.play_preview_stream(stream_url)
                    else:
                        self.preview_busy = False

                        self.preview_button.configure(
                            state="normal",
                            text="معاينة 10 ثوانٍ"
                        )

                elif kind == "preview_error":

                    source_url, error = data

                    if source_url == self.current_url:

                        self.preview_busy = False

                        self.preview_button.configure(
                            state="normal",
                            text="معاينة 10 ثوانٍ"
                        )

                        self.log("فشلت المعاينة: " + str(error))

                        messagebox.showerror(
                            "تعذر تشغيل المعاينة",
                            str(error)
                        )

                elif kind == "stream_ready":

                    source_url, stream_url, title, http_headers = data

                    self.stream_button.configure(
                        state="normal",
                        text="تشغيل أثناء التحميل"
                    )

                    # تجاهل نتيجة استخراج بث لرابط قديم
                    if source_url != self.url_entry.get().strip():
                        continue

                    if (
                        self.player_window is None
                        or not self.player_window.winfo_exists()
                    ):
                        self.open_player_window()

                    if (
                        self.player_window is not None
                        and self.player_window.winfo_exists()
                    ):
                        self.player_create_stream_tab(
                            stream_url,
                            title,
                            http_headers
                        )

                        self.log(
                            "تم فتح بث الفيديو في المشغل المستقل."
                        )

                elif kind == "stream_error":

                    self.stream_button.configure(
                        state="normal",
                        text="تشغيل أثناء التحميل"
                    )

                    self.log("تعذر استخراج البث: " + str(data))

                    messagebox.showerror(
                        "تعذر تشغيل البث",
                        str(data)
                    )

                elif kind == "queue_item_status":
                    item_id, status = data
                    for item in self.download_queue:
                        if item["id"] == item_id:
                            item["status"] = status
                            break
                    self.refresh_queue_view()

                elif kind == "queue_expand":
                    parent_id, new_items = data
                    parent = next((item for item in self.download_queue if item["id"] == parent_id), None)
                    if parent:
                        insert_at = self.download_queue.index(parent)
                        self.download_queue.pop(insert_at)
                        self.download_queue[insert_at:insert_at] = new_items
                        self.refresh_queue_view()

                elif kind == "queue_file_ok":
                    item_id, filename, video_title = data
                    self.last_file = filename or self.last_file
                    self.queue_success_count += 1
                    self.log("اكتمل: " + str(video_title))

                elif kind == "queue_item_success":
                    item_id = data
                    for item in self.download_queue:
                        if item["id"] == item_id:
                            item["status"] = "مكتمل"
                            break
                    self.refresh_queue_view()

                elif kind == "progress":
                    self.update_progress(data)

                elif kind == "file_finished":

                    if data:
                        self.last_file = data

                elif kind == "download_ok":

                    self.last_file = data or self.find_latest_file()
                    self.download_complete()

                elif kind == "download_error":
                    self.download_failed(data)

                elif kind == "download_done":

                    self.downloading = False
                    self.queue_running = False
                    self.download_paused = False
                    self.download_pause_event.set()

                    self.download_button.configure(text="بدء التحميل", state="normal")
                    self.start_queue_button.configure(state="normal")
                    self.pause_download_button.configure(state="disabled")
                    self.resume_download_button.configure(state="disabled")

                    completed = sum(1 for item in self.download_queue if item.get("status") == "مكتمل")
                    failed = sum(1 for item in self.download_queue if item.get("status") == "فشل")
                    self.status_var.set("انتهت قائمة الانتظار: {} مكتمل، {} فشل".format(completed, failed))
                    self.progress_info_var.set("انتهت قائمة الانتظار")
                    if completed:
                        self.progress["value"] = 100
                        self.percent_var.set("100%")
                        self.download_complete()
                    elif failed:
                        self.log("انتهت قائمة الانتظار دون نجاح أي عنصر.")

        except queue.Empty:
            pass

        try:
            self.root.after(100, self.process_messages)
        except Exception:
            pass

    # =====================================================
    # تحديث شريط التقدم
    # =====================================================

    def update_progress(self, data):

        percent = max(
            0,
            min(100, data.get("percent") or 0)
        )

        self.progress["value"] = percent

        self.percent_var.set(
            "{:.1f}%".format(percent)
        )

        self.progress_info_var.set(
            "{} | {} من {}".format(
                data.get("filename") or "جاري تنزيل الملف",
                self.format_size(data.get("downloaded")),
                self.format_size(data.get("total"))
            )
        )

        speed = data.get("speed")

        if speed:
            self.speed_var.set(
                "السرعة: {}/ث".format(
                    self.format_size(speed)
                )
            )
        else:
            self.speed_var.set("السرعة: --")

        eta = data.get("eta")

        if eta is not None:
            self.eta_var.set(
                "الوقت المتبقي: "
                + self.format_duration(eta)
            )
        else:
            self.eta_var.set("الوقت المتبقي: --")

    # =====================================================
    # اكتمال التحميل
    # =====================================================

    def download_complete(self):

        self.progress["value"] = 100
        self.percent_var.set("100%")

        self.progress_info_var.set("اكتمل التحميل")
        self.speed_var.set("السرعة: مكتمل")
        self.eta_var.set("الوقت المتبقي: 00:00")

        if self.queue_error_count:
            self.status_var.set("اكتمل بعض التحميلات مع وجود ملفات فاشلة")
            self.log("انتهت قائمة الانتظار مع {} إخفاق.".format(self.queue_error_count))
        else:
            self.status_var.set("اكتمل التحميل بنجاح")
            self.log("اكتمل التحميل بنجاح")

        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                self.root.bell()
        else:
            self.root.bell()

        self.show_completion()

    def show_completion(self):

        popup = tk.Toplevel(self.root)

        popup.title("اكتمل التحميل")
        popup.geometry("580x280")
        popup.minsize(540, 260)
        popup.resizable(True, True)
        popup.configure(bg="#202735")

        popup.transient(self.root)
        popup.grab_set()

        tk.Label(
            popup,
            text="✓",
            bg="#202735",
            fg="#20b486",
            font=("Arial", 34, "bold")
        ).pack(pady=(12, 0))

        tk.Label(
            popup,
            text=("انتهت قائمة الانتظار مع بعض الإخفاقات" if self.queue_error_count else "اكتمل التحميل بنجاح"),
            bg="#202735",
            fg="white",
            font=("Arial", 15, "bold")
        ).pack(pady=5)

        if self.last_file and os.path.isfile(self.last_file):
            filename = os.path.basename(self.last_file)
        else:
            filename = "تم إنهاء عملية التحميل"

        tk.Label(
            popup,
            text=filename,
            bg="#202735",
            fg="#cbd5e1",
            font=("Arial", 8),
            wraplength=490
        ).pack(pady=5)

        row = tk.Frame(popup, bg="#202735")
        row.pack(pady=16)

        self.button(
            row,
            "تشغيل الفيديو",
            lambda: self.open_from_popup(popup),
            "#159b70"
        ).pack(side="right", padx=5, ipadx=8, ipady=3)

        self.button(
            row,
            "فتح مجلد التحميل",
            lambda: self.open_folder_from_popup(popup),
            "#2878d0"
        ).pack(side="right", padx=5, ipadx=8, ipady=3)

    def open_from_popup(self, popup):

        self.open_last_file()

        try:
            popup.destroy()
        except Exception:
            pass

    def open_folder_from_popup(self, popup):

        try:
            folder = self.download_folder
            if not folder or not os.path.isdir(folder):
                raise Exception("مجلد التحميل غير موجود.")
            os.startfile(folder)
        except Exception as exc:
            messagebox.showerror(
                "تعذر فتح مجلد التحميل",
                str(exc),
                parent=popup
            )

    # =====================================================
    # تشغيل الملف يدوياً
    # =====================================================

    def open_last_file(self):

        path = self.last_file

        if not path or not os.path.isfile(path):

            messagebox.showwarning(
                "تنبيه",
                "لم يتم العثور على مسار الملف النهائي.\n"
                "راجع مجلد التحميل للتأكد من وجود الملف."
            )

            return

        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("تعذر تشغيل الملف", str(exc))

    # =====================================================
    # فشل التحميل
    # =====================================================

    def download_failed(self, error):

        self.status_var.set("حدث خطأ في قائمة الانتظار")
        self.progress_info_var.set("تعذر إكمال أحد عناصر القائمة")
        self.log("خطأ في قائمة الانتظار: " + str(error))
        for item in self.download_queue:
            if item.get("status") in ("جارٍ التحميل", "جارٍ فحص الرابط"):
                item["status"] = "فشل"
        self.refresh_queue_view()
        messagebox.showerror("تعذر إكمال عنصر", str(error))

    # =====================================================
    # سجل العمليات
    # =====================================================

    def log(self, message):

        try:
            self.log_box.insert(
                tk.END,
                str(message) + "\n"
            )

            self.log_box.see(tk.END)

        except Exception:
            pass

    # =====================================================
    # إغلاق البرنامج
    # =====================================================

    def on_close(self):

        self.save_settings()
        self.hide_hover_preview()

        self.download_pause_event.set()

        try:
            self.close_player_window()
        except Exception:
            pass

        try:

            if self.preview_timer:
                self.root.after_cancel(self.preview_timer)

            if self.preview_player:
                self.preview_player.stop()
                self.preview_player.release()

            if self.preview_media:
                self.preview_media.release()

            if self.preview_instance:
                self.preview_instance.release()

        except Exception:
            pass

        self.root.destroy()


# =========================================================
# تشغيل البرنامج
# =========================================================

if __name__ == "__main__":

    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = VideoDownloader(root)

    root.mainloop()