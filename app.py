import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import shutil
import os
import re
import sys
import json
import queue
import ctypes
import webbrowser
import urllib.parse
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image, ImageTk

try:
    from mutagen.easyid3 import EasyID3
    from mutagen.id3 import ID3, TPE1, TPE2, TIT2
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except Exception:
    MUTAGEN_AVAILABLE = False

APP_TITLE = "SoundGO"
SUPPORTED_FORMATS = ["mp3", "m4a", "wav", "flac", "alac", "opus", "aac"]
SEARCH_PAGE_SIZE = 5

CONFIG_DIR = Path.home() / ".soundgo"
CONFIG_FILE = CONFIG_DIR / "settings.json"

def load_settings():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_settings(data):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def hide_console_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

def is_admin():
    if os.name != "nt":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def safe_folder_name(name):
    name = (name or "Downloads").strip()
    return re.sub(r'[<>:"/\\|?*]', "_", name)

def is_url(text):
    try:
        p = urlparse(text.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False

class SoundGO:
    def __init__(self, root):
        self.root = root
        self.root.title("SoundGO")
        self.root.geometry("1180x940")
        self.root.minsize(1060, 820)

        self.settings = load_settings()

        self.url = tk.StringVar()
        self.search = tk.StringVar()
        saved_output = self.settings.get("output_dir")
        if saved_output and Path(saved_output).exists():
            default_output = saved_output
        else:
            # Default collection folder for new users:
            # Desktop/SoundGO Collection
            default_collection = Path.home() / "Desktop" / "SoundGO Collection"
            try:
                default_collection.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            default_output = str(default_collection)

        self.output_dir = tk.StringVar(value=default_output)
        self.mode = tk.StringVar(value="Album / Playlist")
        self.audio_format = tk.StringVar(value="mp3")

        self.album = tk.StringVar()
        self.song_title = tk.StringVar()
        self.artist = tk.StringVar()
        self.album_artist = tk.StringVar()
        self.year = tk.StringVar()
        self.genre = tk.StringVar(value="Hip-Hop/Rap")
        self.cover_url = tk.StringVar()
        self.cover_file = tk.StringVar()

        self.explicit = tk.BooleanVar(value=True)
        self.restrict = tk.BooleanVar(value=False)
        self.no_m4a_source = tk.BooleanVar(value=True)
        self.track_numbers = tk.BooleanVar(value=True)
        self.keep_thumbnail = tk.BooleanVar(value=False)

        self.dep_status = tk.StringVar(value="Checking dependencies...")
        self.search_results = []
        self.search_offset = 0
        self.playlist_tracks = []
        self.track_overrides = {}
        self.current_process = None
        self.loading_overlay = None
        self.spinner_canvas = None
        self.completion_cover_label = None
        self.completion_cover_img = None
        self.missing_tracks_box = None
        self.missing_tracks_box = None
        self.spinner_angle = 0
        self.spinner_running = False
        self.progress_complete = False
        self.progress_label_var = tk.StringVar(value='Preparing download...')
        self.completion_cover_label = None
        self.completion_cover_img = None

        self.playlist_loading_overlay = None
        self.playlist_spinner_canvas = None
        self.playlist_spinner_angle = 0
        self.playlist_spinner_running = False
        self.playlist_loading_complete = False
        self.playlist_loading_var = tk.StringVar(value="Loading songs...")

        self.show_welcome_screen()

    def clear_root(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def draw_logo(self, canvas, scale=1):
        accent = "#ff7700"
        canvas.create_oval(14*scale, 22*scale, 38*scale, 46*scale, fill=accent, outline=accent)
        canvas.create_oval(28*scale, 14*scale, 58*scale, 46*scale, fill=accent, outline=accent)
        canvas.create_oval(46*scale, 23*scale, 72*scale, 46*scale, fill=accent, outline=accent)
        canvas.create_rectangle(18*scale, 30*scale, 66*scale, 46*scale, fill=accent, outline=accent)
        for x in [8, 11, 14]:
            canvas.create_line(x*scale, 28*scale, x*scale, 46*scale, fill=accent, width=3*scale)

    def show_welcome_screen(self):
        self.clear_root()
        self.root.configure(bg="#0f1117")

        frame = tk.Frame(self.root, bg="#0f1117")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        logo = tk.Canvas(frame, width=156, height=108, bg="#0f1117", bd=0, highlightthickness=0)
        logo.pack(pady=(0, 20))
        self.draw_logo(logo, scale=2)

        tk.Label(
            frame,
            text="Welcome to SoundGO!",
            bg="#0f1117",
            fg="#f5f5f5",
            font=("Segoe UI", 32, "bold")
        ).pack(pady=(0, 12))

        tk.Label(
            frame,
            text="SoundCloud downloader + metadata studio",
            bg="#0f1117",
            fg="#b8bcc8",
            font=("Segoe UI", 13)
        ).pack(pady=(0, 28))

        tk.Button(
            frame,
            text="Click to Continue",
            command=self.show_asset_loading_screen,
            bg="#ff7700",
            fg="white",
            activebackground="#d85f00",
            activeforeground="white",
            font=("Segoe UI", 14, "bold"),
            relief="flat",
            padx=38,
            pady=13,
            borderwidth=0
        ).pack()

    def show_asset_loading_screen(self):
        self.clear_root()
        self.root.configure(bg="#0f1117")

        frame = tk.Frame(self.root, bg="#0f1117")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        self.startup_spinner_canvas = tk.Canvas(
            frame,
            width=110,
            height=110,
            bg="#0f1117",
            bd=0,
            highlightthickness=0
        )
        self.startup_spinner_canvas.pack(pady=(0, 22))

        self.startup_spinner_angle = 0
        self.startup_spinner_running = True

        tk.Label(
            frame,
            text="Loading Assets...",
            bg="#0f1117",
            fg="#f5f5f5",
            font=("Segoe UI", 22, "bold")
        ).pack(pady=(0, 10))

        self.startup_status_var = tk.StringVar(value="Preparing SoundGO...")
        tk.Label(
            frame,
            textvariable=self.startup_status_var,
            bg="#0f1117",
            fg="#b8bcc8",
            font=("Segoe UI", 11)
        ).pack()

        self.animate_startup_spinner()

        # Give it a real loading feel while checking dependencies in the background.
        self.root.after(700, lambda: self.startup_status_var.set("Checking dependencies..."))
        self.root.after(1200, self.check_dependencies_silent)
        self.root.after(3000, lambda: self.startup_status_var.set("Loading interface..."))
        self.root.after(5500, self.finish_startup_loading)

    def animate_startup_spinner(self):
        if not getattr(self, "startup_spinner_running", False):
            return
        c = self.startup_spinner_canvas
        c.delete("all")
        c.create_oval(18, 18, 92, 92, outline="#242936", width=8)
        c.create_arc(
            18, 18, 92, 92,
            start=self.startup_spinner_angle,
            extent=95,
            style="arc",
            outline="#ff7700",
            width=8
        )
        self.startup_spinner_angle = (self.startup_spinner_angle + 12) % 360
        self.root.after(35, self.animate_startup_spinner)

    def check_dependencies_silent(self):
        # Store the dependency report without writing to terminal yet.
        self.startup_dependency_report = self.dependency_report()

    def finish_startup_loading(self):
        self.startup_spinner_running = False
        self.clear_root()
        self.build_ui()
        self.check_dependencies()

    def build_ui(self):
        self.root.configure(bg="#0f1117")
        self.accent = "#ff7700"
        self.card_bg = "#181b24"
        self.input_bg = "#242936"
        self.text_main = "#f5f5f5"
        self.text_muted = "#b8bcc8"

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background="#0f1117")
        style.configure("Card.TFrame", background=self.card_bg)
        style.configure("TLabel", background="#0f1117", foreground=self.text_main, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#0f1117", foreground=self.text_muted, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_main, font=("Segoe UI", 10))
        style.configure("CardMuted.TLabel", background=self.card_bg, foreground=self.text_muted, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background="#0f1117", foreground=self.text_main, font=("Segoe UI", 24, "bold"))
        style.configure("SubHeader.TLabel", background="#0f1117", foreground=self.text_muted, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=(10, 7), foreground="#111111", background="#f1efe8")
        style.map("TButton", background=[("active", "#ffffff"), ("!disabled", "#f1efe8")], foreground=[("disabled", "#777777"), ("!disabled", "#111111")])
        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), padding=(12, 9), foreground="white", background=self.accent)
        style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 7), foreground="white", background="#8b1e1e")
        style.map("Danger.TButton", background=[("active", "#b72828"), ("!disabled", "#8b1e1e")], foreground=[("!disabled", "white")])
        style.map("Accent.TButton", background=[("active", "#d85f00"), ("!disabled", self.accent)], foreground=[("!disabled", "white")])
        style.configure("TEntry", fieldbackground=self.input_bg, foreground=self.text_main, insertcolor=self.text_main)
        style.configure("Big.TCombobox", fieldbackground="#ffffff", foreground="#111111", background="#ffffff", arrowcolor=self.accent, padding=6)
        style.configure("TCheckbutton", background=self.card_bg, foreground=self.text_main)
        style.configure("TLabelframe", background="#0f1117", foreground=self.text_main)
        style.configure("TLabelframe.Label", background="#0f1117", foreground=self.accent, font=("Segoe UI", 10, "bold"))

        shell = ttk.Frame(self.root, padding=12)
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg="#0f1117")
        header.pack(fill="x", pady=(0, 8))
        logo = tk.Canvas(header, width=78, height=54, bg="#0f1117", bd=0, highlightthickness=0)
        logo.pack(side="left", padx=(0, 12))
        logo.create_oval(14, 22, 38, 46, fill=self.accent, outline=self.accent)
        logo.create_oval(28, 14, 58, 46, fill=self.accent, outline=self.accent)
        logo.create_oval(46, 23, 72, 46, fill=self.accent, outline=self.accent)
        logo.create_rectangle(18, 30, 66, 46, fill=self.accent, outline=self.accent)
        for x in [8, 11, 14]:
            logo.create_line(x, 28, x, 46, fill=self.accent, width=3)

        title_box = tk.Frame(header, bg="#0f1117")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="SoundGO", style="Header.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="SoundCloud downloader + metadata studio", style="SubHeader.TLabel").pack(anchor="w")
        tk.Label(header, text="MP3 • WAV • FLAC • ALAC", bg="#231a12", fg=self.accent, font=("Segoe UI", 10, "bold"), padx=14, pady=8).pack(side="right")

        tk.Label(shell, text=("Running as admin" if is_admin() else "User install mode") + "  •  Use only for music you own or have permission to download", bg="#12151d", fg=self.text_muted, font=("Segoe UI", 9), padx=12, pady=7).pack(fill="x", pady=(0,8))

        # Top content intentionally fixed height so terminal always stays visible
        content = ttk.Frame(shell)
        content.pack(fill="both", expand=True)
        left = ttk.Frame(content)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ttk.Frame(content)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        self.build_setup(left)
        self.build_source(left)
        self.build_download(left)
        self.build_terminal(left)
        self.build_metadata(right)
        self.build_playlist_editor(right)
        self.build_actions(right)


    def card(self, parent, title):
        box = ttk.LabelFrame(parent, text=title)
        box.pack(fill="x", pady=(0, 8))
        inner = ttk.Frame(box, style="Card.TFrame", padding=10)
        inner.pack(fill="x", padx=6, pady=6)
        return inner

    def build_setup(self, parent):
        inner = self.card(parent, "Setup")
        ttk.Label(inner, textvariable=self.dep_status, style="Card.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        ttk.Button(inner, text="Check", command=self.check_dependencies).grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(inner, text="Install yt-dlp", command=self.install_ytdlp).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(inner, text="Install FFmpeg", command=self.install_ffmpeg).grid(row=1, column=2, sticky="ew", padx=6)
        ttk.Button(inner, text="Install All", command=self.install_all_missing, style="Accent.TButton").grid(row=1, column=3, sticky="ew", padx=(6, 0))
        for i in range(4):
            inner.columnconfigure(i, weight=1)

    def build_source(self, parent):
        inner = self.card(parent, "Find music")
        ttk.Label(inner, text="SoundCloud URL", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(inner, textvariable=self.url).grid(row=1, column=0, columnspan=5, sticky="ew", pady=(3, 9))

        ttk.Label(inner, text="Search by words", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Entry(inner, textvariable=self.search).grid(row=3, column=0, sticky="ew", pady=(3, 8), padx=(0, 8))
        ttk.Button(inner, text="🔎 SEARCH SOUNDCLOUD", command=self.search_soundcloud, style="Accent.TButton").grid(row=3, column=1, columnspan=2, sticky="ew", padx=3)
        self.more_btn = ttk.Button(inner, text="+ LOAD 5 MORE", command=self.load_more_results, state="disabled")
        self.more_btn.grid(row=3, column=3, sticky="ew", padx=(3,0))

        self.results_box = tk.Listbox(inner, height=6, bg="#10131a", fg="#f5f5f5", selectbackground=self.accent, selectforeground="white", activestyle="none", relief="flat", highlightthickness=1, highlightbackground="#303544", font=("Segoe UI", 9))
        self.results_box.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2,0))
        self.results_box.bind("<<ListboxSelect>>", lambda e: self.use_selected_result(silent=True))
        btns = ttk.Frame(inner, style="Card.TFrame")
        btns.grid(row=4, column=3, sticky="nsew", padx=(8,0))
        ttk.Button(btns, text="USE URL", command=self.use_selected_result, style="Accent.TButton").pack(fill="x", pady=(0,6))
        ttk.Button(btns, text="COPY URL", command=self.copy_selected_result).pack(fill="x")
        inner.columnconfigure(0, weight=1)

    def build_download(self, parent):
        inner = self.card(parent, "Download")
        ttk.Label(inner, text="Type", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(inner, textvariable=self.mode, values=["Single", "Album / Playlist"], state="readonly", width=18, style="Big.TCombobox").grid(row=1, column=0, sticky="ew", pady=(3,8), padx=(0,8))
        ttk.Label(inner, text="Format", style="CardMuted.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Combobox(inner, textvariable=self.audio_format, values=SUPPORTED_FORMATS, state="readonly", width=14, style="Big.TCombobox").grid(row=1, column=1, sticky="ew", pady=(3,8), padx=8)
        ttk.Label(inner, text="Save location", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Entry(inner, textvariable=self.output_dir).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(3,8), padx=(0,8))
        ttk.Button(inner, text="Browse", command=self.choose_folder).grid(row=3, column=2, sticky="ew", pady=(3,8))
        opts = ttk.Frame(inner, style="Card.TFrame")
        opts.grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(opts, text="Explicit", variable=self.explicit).pack(side="left", padx=(0,12))
        ttk.Checkbutton(opts, text="Safe filenames", variable=self.restrict).pack(side="left", padx=(0,12))
        ttk.Checkbutton(opts, text="Avoid m4a source", variable=self.no_m4a_source).pack(side="left", padx=(0,12))
        ttk.Checkbutton(opts, text="Track #", variable=self.track_numbers).pack(side="left", padx=(0,12))
        ttk.Checkbutton(opts, text="Keep thumbnail", variable=self.keep_thumbnail).pack(side="left")
        for i in range(3):
            inner.columnconfigure(i, weight=1)


    def build_terminal(self, parent):
        box = ttk.LabelFrame(parent, text="Terminal / progress")
        box.pack(fill="both", expand=True, pady=(0, 8))
        inner = ttk.Frame(box, style="Card.TFrame", padding=8)
        inner.pack(fill="both", expand=True, padx=6, pady=6)
        self.log = tk.Text(
            inner,
            height=13,
            wrap="word",
            bg="#090b10",
            fg="#f2f2f2",
            insertbackground="#f2f2f2",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#303544",
            font=("Cascadia Mono", 9)
        )
        self.log.pack(fill="both", expand=True)

    def build_metadata(self, parent):
        inner = self.card(parent, "Metadata studio")
        rows = [
            ("Album name", self.album),
            ("Song title (optional for singles)", self.song_title),
            ("Artist name", self.artist),
            ("Album artist", self.album_artist),
            ("Release year", self.year),
            ("Genre", self.genre),
            ("Cover art URL", self.cover_url),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(inner, text=label, style="CardMuted.TLabel").grid(row=i*2, column=0, sticky="w")
            ttk.Entry(inner, textvariable=var).grid(row=i*2+1, column=0, sticky="ew", pady=(2,5))
        ttk.Label(inner, text="Cover art file", style="CardMuted.TLabel").grid(row=14, column=0, sticky="w")
        row = ttk.Frame(inner, style="Card.TFrame")
        row.grid(row=15, column=0, sticky="ew", pady=(2,2))
        ttk.Entry(row, textvariable=self.cover_file).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose", command=self.choose_cover_file).pack(side="left", padx=(8,0))
        inner.columnconfigure(0, weight=1)

    def build_playlist_editor(self, parent):
        inner = self.card(parent, "Album / EP contents")
        ttk.Button(inner, text="📋 LOAD ALBUM / EP TRACKLIST FROM URL", command=self.load_playlist_contents, style="Accent.TButton").pack(fill="x", pady=(0,6))
        self.track_box = tk.Listbox(inner, height=5, bg="#10131a", fg="#f5f5f5", selectbackground=self.accent, selectforeground="white", activestyle="none", relief="flat", highlightthickness=1, highlightbackground="#303544", font=("Segoe UI", 9))
        self.track_box.pack(fill="both", expand=True, pady=(0,6))
        self.track_box.bind("<<ListboxSelect>>", lambda e: self.load_track_edit_fields())
        ttk.Label(inner, text="Selected song title override", style="CardMuted.TLabel").pack(anchor="w")
        self.selected_track_title = tk.StringVar()
        ttk.Entry(inner, textvariable=self.selected_track_title).pack(fill="x", pady=(2,6))
        row = ttk.Frame(inner, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="💾 SAVE SONG TITLE EDIT", command=self.save_track_override).pack(side="left", fill="x", expand=True, padx=(0,4))
        ttk.Button(row, text="↩ CLEAR SONG TITLE EDIT", command=self.clear_track_override).pack(side="left", fill="x", expand=True, padx=(4,0))

    def build_actions(self, parent):
        inner = self.card(parent, "Actions")
        ttk.Button(
            inner,
            text="⬇  DOWNLOAD SELECTED URL",
            command=self.start_download,
            style="Accent.TButton"
        ).pack(fill="x", pady=(0, 10))

        row = ttk.Frame(inner, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Button(
            row,
            text="📂 OPEN SAVE FOLDER",
            command=self.open_output_folder
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(
            row,
            text="🧹 CLEAR TERMINAL",
            command=lambda: self.log.delete("1.0", tk.END),
            style="Danger.TButton"
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def write_log(self, text):
        def append():
            self.log.insert(tk.END, str(text) + "\n")
            self.log.see(tk.END)
        self.root.after(0, append)

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get())
        if folder:
            self.output_dir.set(folder)
            self.settings["output_dir"] = folder
            save_settings(self.settings)

    def choose_cover_file(self):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.webp"), ("All files", "*.*")])
        if f:
            self.cover_file.set(f)

    def dependency_report(self):
        return {
            "yt-dlp": shutil.which("yt-dlp"),
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
            "mutagen": "installed" if MUTAGEN_AVAILABLE else None,
        }

    def check_dependencies(self):
        report = self.dependency_report()
        missing = [k for k,v in report.items() if not v]
        if missing:
            self.dep_status.set("Missing: " + ", ".join(missing))
            self.write_log("Dependency check: missing " + ", ".join(missing))
        else:
            self.dep_status.set("Ready: yt-dlp, ffmpeg, ffprobe, mutagen found.")
            self.write_log("Dependency check: all dependencies found.")

    def install_ytdlp(self):
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--user", "-U", "yt-dlp", "mutagen"]
        self.write_log("-"*80)
        self.write_log("Installing/updating yt-dlp + mutagen...")
        threading.Thread(target=self.run_process, args=(cmd, "yt-dlp/mutagen install finished. Restart app if mutagen still shows missing.", self.check_dependencies), daemon=True).start()

    def install_ffmpeg(self):
        if os.name != "nt" or shutil.which("winget") is None:
            self.write_log("Install FFmpeg manually: winget install Gyan.FFmpeg")
            return
        cmd = ["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"]
        self.write_log("-"*80)
        self.write_log("Installing FFmpeg + ffprobe...")
        threading.Thread(target=self.run_process, args=(cmd, "FFmpeg install finished. Restart app if PATH does not refresh.", self.check_dependencies), daemon=True).start()

    def install_all_missing(self):
        self.write_log("-"*80)
        self.write_log("Installing all missing dependencies...")
        def worker():
            r = self.dependency_report()
            if not r["yt-dlp"] or not r["mutagen"]:
                self.run_process([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--user", "-U", "yt-dlp", "mutagen"], "Python packages installed.")
            r = self.dependency_report()
            if (not r["ffmpeg"] or not r["ffprobe"]) and os.name == "nt" and shutil.which("winget"):
                self.run_process(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"], "FFmpeg installed.")
            self.root.after(0, self.check_dependencies)
        threading.Thread(target=worker, daemon=True).start()

    def normalize_soundcloud_url(self, raw):
        raw = (raw or "").replace("\\/", "/").strip().strip('"').strip("'")
        raw = raw.split("?")[0].rstrip("/")

        if raw.startswith("https://soundcloud.com/"):
            return raw

        if raw.startswith("http://soundcloud.com/"):
            return "https://" + raw[len("http://"):]

        if raw.startswith("//soundcloud.com/"):
            return "https:" + raw

        if raw.startswith("/"):
            return "https://soundcloud.com" + raw

        # Fix broken scraped URLs like:
        # https://soundcloud.comusername/sets/name
        if raw.startswith("https://soundcloud.com") and not raw.startswith("https://soundcloud.com/"):
            return "https://soundcloud.com/" + raw[len("https://soundcloud.com"):].lstrip("/")

        if raw.startswith("soundcloud.com") and not raw.startswith("soundcloud.com/"):
            return "https://soundcloud.com/" + raw[len("soundcloud.com"):].lstrip("/")

        if raw.startswith("soundcloud.com/"):
            return "https://" + raw

        return raw

    def soundcloud_url_exists(self, url):
        # Non-blocking validation:
        # Some valid SoundCloud playlist pages return misleading status/HTML to simple requests,
        # while yt-dlp/browser can still access them. So only reject obviously invalid domains.
        url = self.normalize_soundcloud_url(url)
        return url.startswith("https://soundcloud.com/")

    def search_soundcloud(self):
        q = self.search.get().strip()
        if not q:
            messagebox.showwarning("Search needed", "Type words to search.")
            return

        self.search_results = []
        self.search_offset = 0
        self.results_box.delete(0, tk.END)
        self.more_btn.config(state="disabled")

        self.write_log("-" * 80)
        self.write_log(f"Searching SoundCloud broadly for: {q}")
        self.write_log("Using real SoundCloud search page results...")

        url = "https://soundcloud.com/search?q=" + urllib.parse.quote(q)

        threading.Thread(target=self.run_html_search_process, args=(url,), daemon=True).start()

    def run_html_search_process(self, url):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            html = requests.get(url, headers=headers, timeout=15).text

            soup = BeautifulSoup(html, "html.parser")

            found = []
            seen = set()

            for a in soup.find_all("a", href=True):
                href = a["href"]

                if not href.startswith("/"):
                    continue

                full = self.normalize_soundcloud_url(href)

                if full in seen:
                    continue

                # classify
                if "/sets/" in href:
                    kind = "ALBUM/EP"
                else:
                    kind = "SINGLE"

                title = a.get_text(" ", strip=True)

                if not title:
                    continue

                # filter junk/nav links
                lowered = title.lower()
                if lowered in ["home", "feed", "library", "upload", "create account", "sign in"]:
                    continue

                seen.add(full)

                fixed_full = self.normalize_soundcloud_url(full)
                if not self.soundcloud_url_exists(fixed_full):
                    continue

                found.append({
                    "title": title,
                    "url": fixed_full,
                    "kind": kind,
                    "uploader": ""
                })

            # prioritize albums/eps first
            found.sort(key=lambda x: 0 if x["kind"] == "ALBUM/EP" else 1)

            self.root.after(0, lambda: self.finish_search(found))

        except Exception as e:
            self.write_log(f"Search error: {e}")

    def classify_result(self, result):
        url = result.get("url", "").lower()
        title = result.get("title", "").lower()
        if "/sets/" in url or " playlist" in title or " album" in title or " ep" in title or title.endswith(" ep"):
            return "ALBUM/EP"
        return "SINGLE"

    def run_broad_search_process(self, queries):
        results = []
        seen = set()

        for term in queries:
            cmd = ["yt-dlp", term, "--flat-playlist", "--print", "%(title)s\t%(uploader)s\t%(webpage_url)s"]
            for r in self.collect_search_results(cmd):
                url = r.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                r["kind"] = self.classify_result(r)
                results.append(r)

        self.root.after(0, lambda: self.finish_search(results))

    def collect_search_results(self, cmd):
        out = []
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", creationflags=hide_console_flags(), env={**os.environ, "PYTHONUNBUFFERED":"1"})
            for line in p.stdout:
                parts = line.rstrip().split("\t")
                if len(parts) >= 3 and parts[-1].startswith("http"):
                    out.append({"title": parts[0], "uploader": parts[1], "url": parts[-1]})
            p.wait()
        except Exception as e:
            self.write_log(f"Search error: {e}")
        return out

    def finish_search(self, results):
        self.search_results = results
        if not results:
            self.write_log("No yt-dlp results found. Try 'Open SC Sets' for SoundCloud playlist/EP browser search.")
            return
        self.load_more_results()
        self.write_log(f"Loaded {len(results)} results internally.")

    def load_more_results(self):
        start, end = self.search_offset, min(self.search_offset + SEARCH_PAGE_SIZE, len(self.search_results))
        for i in range(start, end):
            r = self.search_results[i]
            label = r.get("kind", self.classify_result(r))
            self.results_box.insert(tk.END, f"{label} - {i+1}. {r['title']} — {r['uploader']}")
        self.search_offset = end
        self.more_btn.config(state="normal" if end < len(self.search_results) else "disabled")

    def selected_result(self, warn=True):
        sel = self.results_box.curselection()
        if not sel:
            if warn:
                messagebox.showwarning("No result selected", "Click a search result first.")
            return None
        return self.search_results[sel[0]] if sel[0] < len(self.search_results) else None

    def use_selected_result(self, silent=False):
        r = self.selected_result(warn=not silent)
        if r:
            self.url.set(self.normalize_soundcloud_url(r["url"]))

    def copy_selected_result(self):
        r = self.selected_result()
        if r:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.normalize_soundcloud_url(r["url"]))
            self.write_log("Copied selected URL.")

    def show_playlist_loading_overlay(self, playlist_name="playlist"):
        if self.playlist_loading_overlay and self.playlist_loading_overlay.winfo_exists():
            return

        self.playlist_loading_complete = False
        self.playlist_loading_var.set(f"Loading songs from {playlist_name}...")

        # Semi-transparent style is limited in Tkinter, so use a centered dark panel.
        self.playlist_loading_overlay = tk.Frame(
            self.root,
            bg="#0f1117",
            highlightbackground="#ff7700",
            highlightthickness=2
        )
        self.playlist_loading_overlay.place(
            relx=0.5,
            rely=0.5,
            anchor="center",
            width=460,
            height=230
        )
        self.playlist_loading_overlay.lift()

        tk.Label(
            self.playlist_loading_overlay,
            text="SoundGO",
            bg="#0f1117",
            fg="#ff7700",
            font=("Segoe UI", 20, "bold")
        ).pack(pady=(20, 8))

        self.playlist_spinner_canvas = tk.Canvas(
            self.playlist_loading_overlay,
            width=70,
            height=70,
            bg="#0f1117",
            bd=0,
            highlightthickness=0
        )
        self.playlist_spinner_canvas.pack(pady=(0, 10))

        tk.Label(
            self.playlist_loading_overlay,
            textvariable=self.playlist_loading_var,
            bg="#0f1117",
            fg="#f5f5f5",
            font=("Segoe UI", 12, "bold"),
            wraplength=400,
            justify="center"
        ).pack(pady=(0, 8))

        self.playlist_spinner_running = True
        self.animate_playlist_spinner()

    def animate_playlist_spinner(self):
        if not self.playlist_spinner_canvas:
            return

        c = self.playlist_spinner_canvas
        c.delete("all")

        if self.playlist_loading_complete:
            # Green completion checkmark
            c.create_oval(
                10, 10, 60, 60,
                fill="#1ed760",
                outline="#1ed760",
                width=0
            )
            c.create_line(
                24, 37,
                33, 46,
                fill="white",
                width=6,
                capstyle="round",
                smooth=True
            )
            c.create_line(
                33, 46,
                50, 25,
                fill="white",
                width=6,
                capstyle="round",
                smooth=True
            )
            return

        if not self.playlist_spinner_running:
            return

        c.create_oval(10, 10, 60, 60, outline="#242936", width=6)
        c.create_arc(
            10,
            10,
            60,
            60,
            start=self.playlist_spinner_angle,
            extent=95,
            style="arc",
            outline="#ff7700",
            width=6
        )

        self.playlist_spinner_angle = (self.playlist_spinner_angle + 14) % 360
        self.root.after(35, self.animate_playlist_spinner)

    def show_playlist_loading_complete(self):
        self.playlist_spinner_running = False
        self.playlist_loading_complete = True
        self.playlist_loading_var.set("Loading Completed!")
        self.animate_playlist_spinner()
        self.root.after(2500, self.close_playlist_loading_overlay)

    def close_playlist_loading_overlay(self):
        self.playlist_spinner_running = False
        if self.playlist_loading_overlay and self.playlist_loading_overlay.winfo_exists():
            self.playlist_loading_overlay.destroy()
        self.playlist_loading_overlay = None
        self.playlist_spinner_canvas = None

    def get_playlist_loading_name(self):
        selected = self.selected_result(warn=False)
        if selected and selected.get("title"):
            return selected["title"]

        if self.album.get().strip():
            return self.album.get().strip()

        url = self.url.get().strip()
        if url:
            name = url.rstrip("/").split("/")[-1]
            return name.replace("-", " ")

        return "playlist"

    def load_playlist_contents(self):
        url = self.normalize_soundcloud_url(self.url.get().strip())
        self.url.set(url)
        if not url:
            messagebox.showwarning("URL needed", "Paste/select a playlist/album URL first.")
            return
        self.track_box.delete(0, tk.END)
        self.playlist_tracks = []
        self.track_overrides = {}
        self.current_process = None
        self.loading_overlay = None
        self.spinner_canvas = None
        self.completion_cover_label = None
        self.completion_cover_img = None
        self.spinner_angle = 0
        self.spinner_running = False
        self.progress_complete = False
        self.progress_label_var = tk.StringVar(value='Preparing download...')
        self.completion_cover_label = None
        self.completion_cover_img = None

        self.playlist_loading_overlay = None
        self.playlist_spinner_canvas = None
        self.playlist_spinner_angle = 0
        self.playlist_spinner_running = False
        self.playlist_loading_complete = False
        self.playlist_loading_var = tk.StringVar(value="Loading songs...")
        self.write_log("-"*80)
        self.write_log("Loading album/EP/playlist contents...")
        self.write_log("Resolving real song titles. This may take a few seconds...")

        self.root.after(0, lambda: self.show_playlist_loading_overlay(self.get_playlist_loading_name()))

        # Use full playlist JSON lines first because flat playlist metadata can return only numeric IDs.
        cmd = ["yt-dlp", "--dump-json", "--yes-playlist", "--skip-download", url]
        threading.Thread(target=self.run_playlist_contents_process, args=(cmd,), daemon=True).start()

    def looks_like_bad_title(self, title):
        if title is None:
            return True
        t = str(title).strip()
        if not t:
            return True
        if t.upper() in {"NA", "N/A", "NONE", "NULL"}:
            return True
        # SoundCloud IDs are often just long numbers; do not show these as names.
        if t.isdigit() and len(t) >= 6:
            return True
        return False

    def run_playlist_contents_process(self, cmd):
        tracks = []
        try:
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=hide_console_flags(),
                env={**os.environ, "PYTHONUNBUFFERED":"1"}
            )

            # yt-dlp --dump-json on playlists usually returns one JSON object per track.
            json_lines = []
            for line in p.stdout:
                clean = line.strip()
                if clean.startswith("{") and clean.endswith("}"):
                    json_lines.append(clean)
            p.wait()

            for i, line in enumerate(json_lines, start=1):
                try:
                    entry = json.loads(line)
                except Exception:
                    continue

                title = (
                    entry.get("title")
                    or entry.get("fulltitle")
                    or entry.get("track")
                    or entry.get("alt_title")
                    or entry.get("display_id")
                    or entry.get("id")
                    or f"Track {i}"
                )

                webpage_url = (
                    entry.get("webpage_url")
                    or entry.get("original_url")
                    or entry.get("url")
                    or ""
                )

                tracks.append({
                    "index": i,
                    "title": str(title).strip(),
                    "url": str(webpage_url).strip()
                })

            # If full JSON did not work, fallback to flat playlist JSON.
            if not tracks:
                url = self.url.get().strip()
                self.write_log("Full metadata scan did not return tracks, trying flat playlist scan...")
                p2 = subprocess.Popen(
                    ["yt-dlp", "--dump-single-json", "--flat-playlist", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=hide_console_flags(),
                    env={**os.environ, "PYTHONUNBUFFERED":"1"}
                )
                output = p2.stdout.read()
                p2.wait()
                data = json.loads(output)
                entries = data.get("entries") or []
                for i, entry in enumerate(entries, start=1):
                    if not entry:
                        continue
                    title = entry.get("title") or entry.get("fulltitle") or entry.get("display_id") or entry.get("id") or f"Track {i}"
                    webpage_url = entry.get("webpage_url") or entry.get("url") or entry.get("original_url") or ""
                    tracks.append({"index": i, "title": str(title).strip(), "url": str(webpage_url).strip()})

            # Resolve bad numeric/NA titles one-by-one using the track URL.
            fixed_tracks = []
            for t in tracks:
                title = t["title"]
                track_url = t.get("url", "")

                if self.looks_like_bad_title(title) and track_url:
                    try:
                        p3 = subprocess.Popen(
                            ["yt-dlp", "--get-title", track_url],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            creationflags=hide_console_flags(),
                            env={**os.environ, "PYTHONUNBUFFERED":"1"}
                        )
                        resolved = p3.stdout.read().strip().splitlines()
                        p3.wait()
                        if resolved and not self.looks_like_bad_title(resolved[0]):
                            title = resolved[0].strip()
                    except Exception:
                        pass

                if self.looks_like_bad_title(title):
                    title = f"Track {t['index']}"

                fixed_tracks.append({
                    "index": t["index"],
                    "title": title,
                    "url": track_url
                })

            self.root.after(0, lambda: self.finish_playlist_contents(fixed_tracks))

        except Exception as e:
            self.root.after(0, self.close_playlist_loading_overlay)
            self.write_log(f"Could not load contents: {e}")

    def finish_playlist_contents(self, tracks):
        self.playlist_tracks = tracks
        self.track_box.delete(0, tk.END)

        if not tracks:
            self.write_log("No playlist contents found.")
            self.show_playlist_loading_complete()
            return

        for t in tracks:
            self.track_box.insert(tk.END, f"{t['index']:02d}. {t['title']}")

        self.write_log(f"Loaded {len(tracks)} songs. Select one to edit its title metadata.")
        self.show_playlist_loading_complete()

    def selected_track(self):
        sel = self.track_box.curselection()
        if not sel: return None
        return self.playlist_tracks[sel[0]] if sel[0] < len(self.playlist_tracks) else None

    def load_track_edit_fields(self):
        t = self.selected_track()
        if t:
            self.selected_track_title.set(self.track_overrides.get(t["index"], {}).get("title", t["title"]))

    def save_track_override(self):
        t = self.selected_track()
        if not t:
            messagebox.showwarning("No song selected", "Select a song first.")
            return
        val = self.selected_track_title.get().strip()
        if not val:
            messagebox.showwarning("Title needed", "Type the new song title.")
            return
        self.track_overrides[t["index"]] = {"title": val}
        row = self.track_box.curselection()[0]
        self.track_box.delete(row)
        self.track_box.insert(row, f"{t['index']:02d}. {val}  ✎")
        self.track_box.selection_set(row)
        self.write_log(f"Saved title override for track {t['index']}: {val}")

    def clear_track_override(self):
        t = self.selected_track()
        if not t: return
        self.track_overrides.pop(t["index"], None)
        row = self.track_box.curselection()[0]
        self.track_box.delete(row)
        self.track_box.insert(row, f"{t['index']:02d}. {t['title']}")
        self.track_box.selection_set(row)
        self.selected_track_title.set(t["title"])

    def get_default_album_title(self):
        """Return user album name, or fallback to loaded playlist/search title."""
        custom = self.album.get().strip()
        if custom:
            return custom

        # If user selected a search result, use selected playlist/track title as fallback.
        selected = self.selected_result(warn=False)
        if selected and selected.get("title"):
            title = selected["title"]
            # remove leading labels that appear in list display, if any
            return title.strip()

        # If tracklist is loaded, use current URL's playlist title if known from yt-dlp later;
        # otherwise use folder placeholder so yt-dlp keeps the playlist title.
        return ""

    def safe_rename_path(self, path, new_title):
        clean = safe_folder_name(new_title).strip()
        if not clean:
            return path
        return path.with_name(clean + path.suffix)

    def output_template(self):
        if self.mode.get() == "Single":
            folder = Path(self.output_dir.get()) / "Singles"
            filename = "%(title)s.%(ext)s"
        else:
            # If Album Name is blank, let yt-dlp create folder from playlist/album title.
            folder = Path(self.output_dir.get()) / (safe_folder_name(self.album.get()) if self.album.get().strip() else "%(playlist_title)s")

            # IMPORTANT:
            # Download with a temporary playlist index prefix so metadata edits map to the correct track.
            # Final cleanup removes this prefix after metadata is rewritten.
            filename = "%(playlist_index)03d - %(title)s.%(ext)s"

        return str(folder / filename), folder

    def build_metadata_args(self):
        artist = self.album_artist.get().strip() or self.artist.get().strip()
        album_artist = self.album_artist.get().strip() or self.artist.get().strip()
        album = self.album.get().strip()
        meta = ["-vn"]
        if artist: meta += ["-metadata", f"artist={artist}"]
        if album_artist: meta += ["-metadata", f"album_artist={album_artist}"]
        if album: meta += ["-metadata", f"album={album}"]
        if self.year.get().strip(): meta += ["-metadata", f"date={self.year.get().strip()}", "-metadata", f"year={self.year.get().strip()}"]
        if self.genre.get().strip(): meta += ["-metadata", f"genre={self.genre.get().strip()}"]
        if self.explicit.get(): meta += ["-metadata", "ITUNESADVISORY=1"]
        return meta

    def quote_args(self, args):
        out = []
        for a in args:
            s = str(a)
            if any(ch in s for ch in [' ', ',', "'", '"', "Ø", "/", "\\"]):
                s = '"' + s.replace('"', '\\"') + '"'
            out.append(s)
        return " ".join(out)

    def build_command(self):
        fmt = self.audio_format.get().lower()
        selector = 'ba[ext!=m4a]/ba' if self.no_m4a_source.get() else "ba"
        out_tmpl, folder = self.output_template()
        cmd = ["yt-dlp", "-f", selector, "-x", "--audio-format", fmt, "--audio-quality", "0", "--no-keep-video", "--embed-metadata"]
        if self.restrict.get(): cmd.append("--restrict-filenames")
        cmd.append("--no-playlist" if self.mode.get() == "Single" else "--yes-playlist")
        if self.mode.get() != "Single" and self.track_numbers.get():
            cmd += ["--parse-metadata", "playlist_index:%(track_number)s"]
        if self.artist.get().strip():
            cmd += ["--replace-in-metadata", "artist", ".*", self.artist.get().strip()]
        cover_url, cover_file = self.cover_url.get().strip(), self.cover_file.get().strip()
        if cover_url:
            cmd += ["--exec", f'before_dl:curl -L "{cover_url}" -o cover.jpg', "--convert-thumbnails", "jpg"]
            meta = ["-i", "cover.jpg", "-map", "0:a", "-map", "1:v", "-c", "copy"] + self.build_metadata_args()
            cmd += ["--postprocessor-args", "ExtractAudio+ffmpeg:" + self.quote_args(meta)]
        elif cover_file:
            meta = ["-i", cover_file, "-map", "0:a", "-map", "1:v", "-c", "copy"] + self.build_metadata_args()
            cmd += ["--postprocessor-args", "ExtractAudio+ffmpeg:" + self.quote_args(meta)]
        else:
            cmd.append("--embed-thumbnail")
            cmd += ["--postprocessor-args", "ExtractAudio+ffmpeg:" + self.quote_args(self.build_metadata_args())]
        if self.keep_thumbnail.get(): cmd.append("--write-thumbnail")
        cmd += ["-o", out_tmpl, self.normalize_soundcloud_url(self.url.get().strip())]
        return cmd, folder

    def get_audio_files_in_folder(self, folder):
        files = []
        try:
            folder = Path(folder)
            for ext in ("*.mp3", "*.m4a", "*.mp4", "*.flac", "*.wav", "*.aac", "*.opus"):
                files.extend(folder.rglob(ext))
        except Exception:
            pass
        return sorted(files, key=lambda p: p.name.lower())

    def expected_playlist_tracks(self):
        # Uses the album/EP contents already loaded in the app.
        tracks = []
        try:
            for t in self.playlist_tracks:
                idx = t.get("index")
                title = t.get("title", "")
                if idx and title:
                    tracks.append({"index": int(idx), "title": str(title)})
        except Exception:
            pass
        return sorted(tracks, key=lambda x: x["index"])

    def detect_missing_tracks(self, folder):
        """
        Compare expected loaded playlist tracks against downloaded files.
        Since album/EP downloads use a temporary index prefix before cleanup, this checks:
        1. title match against final filenames
        2. order fallback if names were changed by user edits
        """
        expected = self.expected_playlist_tracks()
        audio_files = self.get_audio_files_in_folder(folder)

        if self.mode.get() == "Single" or not expected:
            return {
                "downloaded": len(audio_files),
                "total": len(audio_files) if audio_files else 1,
                "missing": []
            }

        file_stems = [safe_folder_name(p.stem).lower() for p in audio_files]
        downloaded_count = len(audio_files)

        missing = []

        # Best-effort title matching. If user edited titles, fallback count still protects summary.
        for track in expected:
            normalized_title = safe_folder_name(track["title"]).lower()
            found = any(
                normalized_title in stem or stem in normalized_title
                for stem in file_stems
            )
            if not found:
                missing.append(track["title"])

        # If matching over-reports missing due to renamed files, use count-based fallback:
        # assume the missing tracks are the last unmatched needed to make total accurate.
        total = len(expected)
        if len(missing) > max(0, total - downloaded_count):
            missing = missing[:max(0, total - downloaded_count)]

        return {
            "downloaded": min(downloaded_count, total),
            "total": total,
            "missing": missing
        }

    def get_completion_title(self, folder=None):
        if self.mode.get() == "Single":
            return (
                self.song_title.get().strip()
                or self.album.get().strip()
                or "song"
            )

        if self.album.get().strip():
            return self.album.get().strip()

        selected = self.selected_result(warn=False)
        if selected and selected.get("title"):
            return selected["title"]

        if folder:
            try:
                return Path(folder).name
            except Exception:
                pass

        return "album"

    def get_cover_art_path_for_completion(self, folder=None):
        # 1. User-selected local cover art wins.
        cover_file = self.cover_file.get().strip()
        if cover_file and Path(cover_file).exists():
            return Path(cover_file)

        # 2. Try downloading cover art URL if provided.
        cover_url = self.cover_url.get().strip()
        if cover_url:
            try:
                tmp = CONFIG_DIR / "last_cover.jpg"
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                r = requests.get(cover_url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
                if r.ok and r.content:
                    tmp.write_bytes(r.content)
                    return tmp
            except Exception:
                pass

        # 3. Try thumbnail files saved by yt-dlp in the output folder.
        if folder:
            try:
                folder = Path(folder)
                for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                    found = list(folder.rglob(ext))
                    if found:
                        return found[0]
            except Exception:
                pass

        # 4. Ask yt-dlp for thumbnail URL and download it.
        try:
            url = self.url.get().strip()
            if url:
                p = subprocess.Popen(
                    ["yt-dlp", "--get-thumbnail", url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=hide_console_flags(),
                    env={**os.environ, "PYTHONUNBUFFERED": "1"}
                )
                thumb_url = p.stdout.read().strip().splitlines()
                p.wait()

                if thumb_url:
                    tmp = CONFIG_DIR / "last_cover_from_source.jpg"
                    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                    r = requests.get(thumb_url[0], timeout=12, headers={"User-Agent": "Mozilla/5.0"})
                    if r.ok and r.content:
                        tmp.write_bytes(r.content)
                        return tmp
        except Exception:
            pass

        return None

    def set_completion_cover_art(self, cover_path):
        if not self.completion_cover_label:
            return

        if not cover_path:
            self.completion_cover_label.config(text="COVER ART", image="", fg="#b8bcc8")
            return

        try:
            img = Image.open(cover_path).convert("RGB")
            img.thumbnail((190, 190))
            self.completion_cover_img = ImageTk.PhotoImage(img)
            self.completion_cover_label.config(image=self.completion_cover_img, text="")
        except Exception:
            self.completion_cover_label.config(text="COVER ART", image="", fg="#b8bcc8")

    def show_progress_window(self, song_name="Download"):
        # Full-window in-app loading overlay; no separate popup window.
        if self.loading_overlay and self.loading_overlay.winfo_exists():
            return

        self.progress_complete = False

        self.loading_overlay = tk.Frame(self.root, bg="#0f1117")
        self.loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.loading_overlay.lift()

        center = tk.Frame(self.loading_overlay, bg="#0f1117")
        center.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            center,
            text="SoundGO",
            bg="#0f1117",
            fg="#ff7700",
            font=("Segoe UI", 30, "bold")
        ).pack(pady=(0, 14))

        self.spinner_canvas = tk.Canvas(
            center,
            width=110,
            height=110,
            bg="#0f1117",
            highlightthickness=0,
            bd=0
        )
        self.spinner_canvas.pack(pady=(0, 18))

        self.progress_text_label = tk.Label(
            center,
            textvariable=self.progress_label_var,
            bg="#0f1117",
            fg="#f5f5f5",
            font=("Segoe UI", 15, "bold"),
            wraplength=720,
            justify="center"
        )
        self.progress_text_label.pack(pady=(0, 14))

        self.completion_cover_label = tk.Label(
            center,
            text="",
            bg="#0f1117",
            fg="#b8bcc8",
            font=("Segoe UI", 11, "bold")
        )
        self.completion_cover_label.pack(pady=(0, 16))
        self.completion_cover_label.pack_forget()

        self.progress_button = tk.Button(
            center,
            text="Cancel Download",
            command=self.cancel_download,
            bg="#8b1e1e",
            fg="white",
            activebackground="#b72828",
            activeforeground="white",
            font=("Segoe UI", 12, "bold"),
            relief="flat",
            padx=34,
            pady=10,
            borderwidth=0
        )
        self.progress_button.pack()

        self.spinner_running = True
        self.animate_spinner()

    def animate_spinner(self):
        if not self.spinner_running or not self.spinner_canvas:
            return

        self.spinner_canvas.delete("all")

        if self.progress_complete:
            self.draw_completion_checkmark()
            return

        # YouTube-style spinner
        x0, y0, x1, y1 = 18, 18, 92, 92

        self.spinner_canvas.create_oval(
            x0, y0, x1, y1,
            outline="#242936",
            width=8
        )

        self.spinner_canvas.create_arc(
            x0,
            y0,
            x1,
            y1,
            start=self.spinner_angle,
            extent=95,
            style="arc",
            outline="#ff7700",
            width=8
        )

        self.spinner_angle = (self.spinner_angle + 12) % 360
        self.root.after(35, self.animate_spinner)

    def show_download_complete(self, folder=None, stats=None):
        self.progress_complete = True
        self.spinner_running = False

        downloaded_name = self.get_completion_title(folder)

        if stats and stats.get("total"):
            self.progress_label_var.set(
                f"Download Complete!\nDownloaded {downloaded_name}\n"
                f"{stats.get('downloaded', 0)}/{stats.get('total', 0)} tracks downloaded"
            )
        else:
            self.progress_label_var.set(f"Download Complete!\nDownloaded {downloaded_name}")

        if hasattr(self, "progress_text_label"):
            self.progress_text_label.config(
                fg="#1ed760",
                font=("Segoe UI", 17, "bold")
            )

        if self.completion_cover_label:
            self.completion_cover_label.pack(pady=(0, 16))
            cover_path = self.get_cover_art_path_for_completion(folder)
            self.set_completion_cover_art(cover_path)

        # Add/refresh missing tracks side list.
        if hasattr(self, "missing_tracks_box") and self.missing_tracks_box:
            try:
                self.missing_tracks_box.destroy()
            except Exception:
                pass
            self.missing_tracks_box = None

        missing = stats.get("missing", []) if stats else []
        if missing and self.loading_overlay:
            self.missing_tracks_box = tk.Frame(
                self.loading_overlay,
                bg="#111722",
                highlightbackground="#2B3342",
                highlightthickness=1
            )
            self.missing_tracks_box.place(relx=0.82, rely=0.5, anchor="center", width=300, height=360)

            tk.Label(
                self.missing_tracks_box,
                text="Missing Tracks",
                bg="#111722",
                fg="#ff7700",
                font=("Segoe UI", 14, "bold")
            ).pack(anchor="w", padx=14, pady=(14, 8))

            list_frame = tk.Frame(self.missing_tracks_box, bg="#111722")
            list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

            for i, title in enumerate(missing, start=1):
                tk.Label(
                    list_frame,
                    text=f"{i}. {title}",
                    bg="#111722",
                    fg="#f5f5f5",
                    font=("Segoe UI", 10),
                    anchor="w",
                    justify="left",
                    wraplength=260
                ).pack(fill="x", anchor="w", pady=3)

        elif stats and stats.get("total") and self.loading_overlay:
            self.missing_tracks_box = tk.Frame(
                self.loading_overlay,
                bg="#102219",
                highlightbackground="#1ed760",
                highlightthickness=1
            )
            self.missing_tracks_box.place(relx=0.82, rely=0.5, anchor="center", width=300, height=170)

            tk.Label(
                self.missing_tracks_box,
                text="All Tracks Downloaded",
                bg="#102219",
                fg="#1ed760",
                font=("Segoe UI", 14, "bold")
            ).pack(expand=True)

        if hasattr(self, "progress_button"):
            self.progress_button.config(
                text="OK",
                command=self.close_progress_window,
                bg="#000000",
                fg="#ffffff",
                activebackground="#222222",
                activeforeground="#ffffff",
                padx=60
            )

        self.draw_completion_checkmark()

    def draw_completion_checkmark(self):
        if not self.spinner_canvas:
            return

        c = self.spinner_canvas
        c.delete("all")

        # Green circle
        c.create_oval(
            18, 18, 92, 92,
            fill="#1ed760",
            outline="#1ed760",
            width=0
        )

        # White checkmark
        c.create_line(
            38, 57,
            50, 69,
            fill="white",
            width=9,
            capstyle="round",
            smooth=True
        )

        c.create_line(
            50, 69,
            74, 43,
            fill="white",
            width=9,
            capstyle="round",
            smooth=True
        )

    def close_progress_window(self):
        self.spinner_running = False
        if self.loading_overlay and self.loading_overlay.winfo_exists():
            self.loading_overlay.destroy()
        self.loading_overlay = None
        self.spinner_canvas = None
        self.completion_cover_label = None
        self.completion_cover_img = None

    def cancel_download(self):
        if self.current_process and self.current_process.poll() is None:
            self.write_log("Cancel requested. Stopping download...")
            try:
                self.current_process.terminate()
            except Exception:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
        self.progress_label_var.set("Cancelling download...")
        self.close_progress_window()

    def parse_download_progress(self, line):
        # Example yt-dlp line:
        # [download]  42.5% of 3.10MiB at 1.25MiB/s ETA 00:03
        percent_match = re.search(r'\[download\]\s+(\d+(?:\.\d+)?)%', line)
        if percent_match:
            try:
                percent = float(percent_match.group(1))
                name = self.song_title.get().strip() or self.album.get().strip() or "Song"
                self.progress_label_var.set(f"{name} is downloading ({percent:.1f}%)")
            except Exception:
                pass

        dest_match = re.search(r'\[download\] Destination: (.+)', line)
        if dest_match:
            file_name = Path(dest_match.group(1)).stem
            self.progress_label_var.set(f"{file_name} is downloading (0%)")

        complete_match = re.search(r'\[ExtractAudio\]|Deleting original file|has already been downloaded', line)
        if complete_match:
            self.progress_label_var.set("Finishing metadata and conversion...")

    def start_download(self):
        fixed_url = self.normalize_soundcloud_url(self.url.get().strip())
        self.url.set(fixed_url)

        if not fixed_url or not is_url(fixed_url):
            messagebox.showwarning("URL needed", "Paste/select a valid SoundCloud URL.")
            return


        self.settings["output_dir"] = self.output_dir.get().strip()
        save_settings(self.settings)

        threading.Thread(target=self.download, daemon=True).start()

    def download(self):
        try:
            cmd, folder = self.build_command()
            # Do not literally create %(playlist_title)s if album is blank; yt-dlp will make the real folder.
            if "%(playlist_title)s" not in str(folder):
                folder.mkdir(parents=True, exist_ok=True)

            before_dirs = set(Path(self.output_dir.get()).glob("*"))

            self.write_log("-"*80)
            self.write_log("Starting download...")
            self.write_log(f"Format: {self.audio_format.get().upper()} | Mode: {self.mode.get()}")
            code = self.run_process_return_code(cmd)

            if code == 0:
                actual_folder = folder

                # If folder used yt-dlp playlist placeholder, detect the newly created folder.
                if "%(playlist_title)s" in str(folder):
                    after_dirs = set(Path(self.output_dir.get()).glob("*"))
                    new_dirs = [p for p in (after_dirs - before_dirs) if p.is_dir()]
                    if new_dirs:
                        actual_folder = max(new_dirs, key=lambda p: p.stat().st_mtime)
                    else:
                        # fallback: newest directory in output folder
                        dirs = [p for p in Path(self.output_dir.get()).glob("*") if p.is_dir()]
                        actual_folder = max(dirs, key=lambda p: p.stat().st_mtime) if dirs else Path(self.output_dir.get())

                self.rewrite_metadata(actual_folder)
                stats = self.detect_missing_tracks(actual_folder)
                self.root.after(0, lambda f=actual_folder, s=stats: self.show_download_complete(f, s))
                self.write_log(
                    f"Done. Files saved near: {actual_folder} "
                    f"({stats.get('downloaded', 0)}/{stats.get('total', 0)} tracks downloaded)"
                )
                if stats.get("missing"):
                    self.write_log("Missing tracks:")
                    for missing_title in stats["missing"]:
                        self.write_log(f" - {missing_title}")
            else:
                # yt-dlp can return a non-zero code even after partial playlist success.
                actual_folder = folder
                if "%(playlist_title)s" in str(folder):
                    dirs = [p for p in Path(self.output_dir.get()).glob("*") if p.is_dir()]
                    actual_folder = max(dirs, key=lambda p: p.stat().st_mtime) if dirs else Path(self.output_dir.get())

                audio_files = self.get_audio_files_in_folder(actual_folder)
                if audio_files:
                    self.rewrite_metadata(actual_folder)
                    stats = self.detect_missing_tracks(actual_folder)
                    self.root.after(0, lambda f=actual_folder, s=stats: self.show_download_complete(f, s))
                    self.write_log(
                        f"Partial download completed: {stats.get('downloaded', 0)}/{stats.get('total', 0)} tracks downloaded."
                    )
                    if stats.get("missing"):
                        self.write_log("Missing tracks:")
                        for missing_title in stats["missing"]:
                            self.write_log(f" - {missing_title}")
                else:
                    self.root.after(0, self.close_progress_window)
                    self.write_log(f"Download exited with code {code}")
        except Exception as e:
            self.root.after(0, self.close_progress_window)
            self.write_log(f"Download setup error: {e}")

    def refresh_ytdlp_for_soundcloud(self):
        # SoundCloud extraction breaks often when yt-dlp is outdated.
        # Silently try to update before retrying a SoundCloud 404 metadata failure.
        try:
            self.write_log("Trying yt-dlp update before retry...")
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--user", "-U", "yt-dlp"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=hide_console_flags(),
                env={**os.environ, "PYTHONUNBUFFERED":"1"}
            )
            for line in proc.stdout:
                clean = line.rstrip()
                if "Successfully installed" in clean or "Requirement already satisfied" in clean:
                    self.write_log(clean)
            proc.wait()
        except Exception as e:
            self.write_log(f"yt-dlp update skipped: {e}")

    def run_process_return_code(self, cmd):
        def run_once(command):
            captured = []
            try:
                self.current_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=hide_console_flags(),
                    env={**os.environ, "PYTHONUNBUFFERED":"1"}
                )

                for line in self.current_process.stdout:
                    clean = line.rstrip()
                    captured.append(clean)

                    if clean.startswith("[download]"):
                        self.root.after(0, lambda l=clean: self.parse_download_progress(l))
                    elif "ERROR:" in clean or "WARNING:" in clean:
                        self.write_log(clean)
                    elif any(tag in clean for tag in ["[ExtractAudio]", "[Metadata]", "[EmbedThumbnail]", "Deleting original file"]):
                        self.root.after(0, lambda l=clean: self.parse_download_progress(l))

                code = self.current_process.wait()
                self.current_process = None
                return code, "\n".join(captured)

            except Exception as e:
                self.write_log(f"Error: {e}")
                self.current_process = None
                return 1, str(e)

        try:
            self.root.after(0, lambda: self.show_progress_window())
            self.root.after(0, lambda: self.progress_label_var.set("Preparing download..."))

            code, output = run_once(cmd)

            # SoundCloud sometimes fails with JSON metadata 404 when yt-dlp is outdated
            # or when the API endpoint fails even though the web page is valid.
            # Update yt-dlp and retry once automatically.
            needs_retry = (
                code != 0
                and "soundcloud" in output.lower()
                and (
                    "unable to download json metadata" in output.lower()
                    or "http error 404" in output.lower()
                    or "not found" in output.lower()
                )
            )

            if needs_retry:
                self.write_log("SoundCloud metadata failed. Retrying once with refreshed yt-dlp...")
                self.refresh_ytdlp_for_soundcloud()
                code, output = run_once(cmd)

            if code == 0:
                self.root.after(0, lambda: self.progress_label_var.set("Download complete. Finalizing..."))
            else:
                self.write_log("Download still failed after retry.")
                self.write_log("Try opening the URL in a browser, copying the final URL from the address bar, and pasting it directly.")
                self.write_log(f"Download process exited with code {code}")

            return code

        except Exception as e:
            self.write_log(f"Error: {e}")
            self.current_process = None
            return 1

    def rewrite_metadata(self, folder):
        if not MUTAGEN_AVAILABLE:
            self.write_log("Mutagen missing, skipping final metadata rewrite.")
            return

        album_artist = self.album_artist.get().strip() or self.artist.get().strip()
        custom_album = self.album.get().strip()

        files = []
        for ext in ("*.mp3", "*.m4a", "*.mp4", "*.flac"):
            files.extend(Path(folder).rglob(ext))

        self.write_log("Rewriting final metadata...")

        album_override = custom_album if custom_album else None
        renamed_files = []

        def index_from_filename(path):
            # Matches temp filenames like "001 - song.mp3"
            m = re.match(r"^(\d{1,4})\s*-\s*(.+)$", path.stem)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    return None
            return None

        def clean_original_title_from_filename(path):
            # Remove temporary "001 - " prefix.
            m = re.match(r"^(\d{1,4})\s*-\s*(.+)$", path.stem)
            if m:
                return m.group(2).strip()
            return path.stem.strip()

        sorted_files = sorted(
            files,
            key=lambda p: (
                index_from_filename(p) if index_from_filename(p) is not None else 999999,
                p.name.lower()
            )
        )

        for fallback_order, f in enumerate(sorted_files, start=1):
            track_index = index_from_filename(f) or fallback_order
            title_override = None

            if self.mode.get() == "Single":
                title_override = self.song_title.get().strip() or custom_album or None
            else:
                override = self.track_overrides.get(track_index)
                if override:
                    title_override = override.get("title")

            # Final file title:
            # - if user edited song title, use that
            # - otherwise remove temporary track number prefix and keep original title
            final_title_for_filename = title_override or clean_original_title_from_filename(f)

            try:
                suffix = f.suffix.lower()

                if suffix == ".mp3":
                    try:
                        audio = EasyID3(str(f))
                    except Exception:
                        audio = EasyID3()

                    if album_artist:
                        audio["artist"] = [album_artist]
                        audio["albumartist"] = [album_artist]

                    if album_override:
                        audio["album"] = [album_override]

                    if title_override:
                        audio["title"] = [title_override]
                    elif self.mode.get() != "Single":
                        # Remove temp prefix from title metadata if yt-dlp inserted it.
                        audio["title"] = [final_title_for_filename]

                    if self.year.get().strip():
                        audio["date"] = [self.year.get().strip()]

                    if self.genre.get().strip():
                        audio["genre"] = [self.genre.get().strip()]

                    audio.save(str(f), v2_version=3)

                    id3 = ID3(str(f))

                    if album_artist:
                        id3.setall("TPE1", [TPE1(encoding=3, text=[album_artist])])
                        id3.setall("TPE2", [TPE2(encoding=3, text=[album_artist])])

                    if title_override or self.mode.get() != "Single":
                        id3.setall("TIT2", [TIT2(encoding=3, text=[final_title_for_filename])])

                    id3.save(str(f), v2_version=3)

                elif suffix in (".m4a", ".mp4"):
                    audio = MP4(str(f))

                    if album_artist:
                        audio["\xa9ART"] = [album_artist]
                        audio["aART"] = [album_artist]

                    if album_override:
                        audio["\xa9alb"] = [album_override]

                    if title_override or self.mode.get() != "Single":
                        audio["\xa9nam"] = [final_title_for_filename]

                    if self.year.get().strip():
                        audio["\xa9day"] = [self.year.get().strip()]

                    if self.genre.get().strip():
                        audio["\xa9gen"] = [self.genre.get().strip()]

                    audio.save()

                elif suffix == ".flac":
                    audio = FLAC(str(f))

                    if album_artist:
                        audio["artist"] = [album_artist]
                        audio["albumartist"] = [album_artist]

                    if album_override:
                        audio["album"] = [album_override]

                    if title_override or self.mode.get() != "Single":
                        audio["title"] = [final_title_for_filename]

                    if self.year.get().strip():
                        audio["date"] = [self.year.get().strip()]

                    if self.genre.get().strip():
                        audio["genre"] = [self.genre.get().strip()]

                    audio.save()

                # Rename final file:
                # - albums/EPs always remove temp index prefix
                # - singles rename only if custom song title/album-as-title exists
                should_rename = False

                if self.mode.get() != "Single":
                    should_rename = True
                elif title_override:
                    should_rename = True

                final_path = f

                if should_rename and final_title_for_filename:
                    new_path = self.safe_rename_path(f, final_title_for_filename)

                    if new_path != f:
                        counter = 1
                        candidate = new_path

                        while candidate.exists() and candidate != f:
                            candidate = new_path.with_name(
                                f"{new_path.stem} ({counter}){new_path.suffix}"
                            )
                            counter += 1

                        f.rename(candidate)
                        final_path = candidate
                        renamed_files.append((f.name, candidate.name))

                self.write_log(f"Retagged: {final_path.name}")

            except Exception as e:
                self.write_log(f"Could not retag {f.name}: {e}")

        for old, new in renamed_files:
            self.write_log(f"Renamed file: {old} -> {new}")

    def run_process(self, cmd, done_message, callback=None):
        code = self.run_process_return_code(cmd)
        self.write_log(done_message if code == 0 else f"Process exited with code {code}")
        if callback:
            self.root.after(0, callback)

    def open_output_folder(self):
        folder = Path(self.output_dir.get())
        if folder.exists():
            os.startfile(folder)
        else:
            messagebox.showerror("Folder missing", "Output folder does not exist.")

if __name__ == "__main__":
    root = tk.Tk()
    app = SoundGO(root)
    root.mainloop()
