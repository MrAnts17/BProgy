# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font, colorchooser
from PIL import Image, ImageTk, ImageDraw, ImageFont
import numpy as np
import os
import threading
import queue # Obwohl hier nicht aktiv genutzt, gut für komplexere Thread-Kommunikation
import platform
import time
import traceback
import sys
import gc
import ctypes # Für DPI Awareness auf Windows
import subprocess # Für fc-match auf Linux

# --- Konstanten ---
# *** NEUER FENSTERTITEL ***
APP_NAME = "PRO Watermark Software (c) BProgy"
COLOR_CANVAS_BG = "#E0E0E0"
DEFAULT_WATERMARK_TEXT = "© BProgy"
DEFAULT_FONT_SIZE = 40
DEFAULT_FONT_COLOR = "#FFFFFF" # Weiß
PREVIEW_SIZE = (480, 270) # Feste Größe für die initiale Vorschau

# --- FFmpeg Konfiguration ---
FFMPEG_MANUAL_PATH = None # Standard: Automatische Erkennung versuchen

ffmpeg_path_source = "Automatisch via imageio-ffmpeg / System PATH"
# Logic to find FFmpeg (unchanged)
if FFMPEG_MANUAL_PATH and os.path.exists(FFMPEG_MANUAL_PATH):
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_MANUAL_PATH
    ffmpeg_path_source = f"Manuell: {FFMPEG_MANUAL_PATH}"
    print(f"INFO: Manueller FFmpeg Pfad wird verwendet: {FFMPEG_MANUAL_PATH}")
elif FFMPEG_MANUAL_PATH:
    print(f"WARNUNG: Manueller FFmpeg Pfad '{FFMPEG_MANUAL_PATH}' existiert nicht. Versuche automatische Erkennung.")
else:
    if "IMAGEIO_FFMPEG_EXE" in os.environ:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            default_exe = get_ffmpeg_exe()
            print(f"INFO: Verwende FFmpeg von imageio-ffmpeg: {default_exe}")
            os.environ["IMAGEIO_FFMPEG_EXE"] = default_exe
            ffmpeg_path_source = f"Automatisch via imageio-ffmpeg: {default_exe}"
        except Exception:
             if "IMAGEIO_FFMPEG_EXE" in os.environ:
                 del os.environ["IMAGEIO_FFMPEG_EXE"]
             print("INFO: Versuche FFmpeg über System PATH zu finden.")
             ffmpeg_path_source = "System PATH"
    else:
         # Try to get path from imageio-ffmpeg if available but not set in env
         try:
             from imageio_ffmpeg import get_ffmpeg_exe
             default_exe = get_ffmpeg_exe()
             print(f"INFO: Verwende FFmpeg von imageio-ffmpeg (implizit): {default_exe}")
             os.environ["IMAGEIO_FFMPEG_EXE"] = default_exe # Set for consistency
             ffmpeg_path_source = f"Automatisch via imageio-ffmpeg: {default_exe}"
         except Exception:
             print("INFO: Versuche FFmpeg über System PATH zu finden (imageio-ffmpeg nicht gefunden/konfiguriert).")
             ffmpeg_path_source = "System PATH"


# --- MoviePy Setup ---
MOVIEPY_AVAILABLE = False
VideoFileClip = None
ImageClip = None
CompositeVideoClip = None
try:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.video.VideoClip import ImageClip, TextClip
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    MOVIEPY_AVAILABLE = True
    print("INFO: MoviePy erfolgreich importiert.")
except ImportError:
    print("FEHLER: MoviePy konnte nicht importiert werden. Stelle sicher, dass es installiert ist (`pip install moviepy`).")
    messagebox.showerror("Import Fehler", "MoviePy konnte nicht gefunden werden.\nBitte installiere es (`pip install moviepy`) und starte die Anwendung neu.")
except Exception as e:
    print(f"FEHLER beim Import von MoviePy: {e}")
    messagebox.showerror("Import Fehler", f"Ein Fehler ist beim Import von MoviePy aufgetreten:\n{e}")


# --- Hauptklasse ---
class VideoWatermarkerApp:
    def __init__(self, root):
        self.root = root
        # *** FENSTERTITEL GESETZT ***
        self.root.title(APP_NAME)
        self.root.minsize(950, 650)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        if platform.system() == "Windows":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
                print("INFO: DPI Awareness für Windows aktiviert.")
            except Exception as e:
                print(f"WARNUNG: Konnte DPI Awareness nicht setzen: {e}")

        self._setup_variables()
        self._create_widgets()
        # Add FFmpeg path info to status bar initially
        self.status_var.set(f"Bereit. (FFmpeg: {ffmpeg_path_source})")
        self._update_preview()

        self.processing_thread = None
        self.stop_processing_flag = threading.Event()

        if not MOVIEPY_AVAILABLE:
             self.status_var.set("FEHLER: MoviePy nicht verfügbar! Verarbeitung nicht möglich.")
             if hasattr(self, 'start_button'):
                self.start_button.config(state=tk.DISABLED)


    def _setup_variables(self):
        """Initialisiert die Tkinter-Variablen und Zustandsvariablen."""
        self.video_files = []
        self.output_folder = tk.StringVar(value="")
        self.watermark_text = tk.StringVar(value=DEFAULT_WATERMARK_TEXT)
        self.font_size = tk.IntVar(value=DEFAULT_FONT_SIZE)
        self.selected_font = tk.StringVar(value="Arial")
        self.font_color = tk.StringVar(value=DEFAULT_FONT_COLOR)
        self.font_style = tk.StringVar(value="Normal")

        self.preview_image = None
        self.preview_photo = None
        self.watermark_preview_image = None
        self.watermark_preview_photo = None
        self.preview_position = (0.5, 0.5)
        self.preview_drag_start_pos = None
        self.preview_wm_item = None

        self.scale_x = 1.0
        self.scale_y = 1.0

        self.status_var = tk.StringVar(value="Initialisiere...") # Wird in __init__ überschrieben
        self.progress_var = tk.DoubleVar(value=0.0)


    def _create_widgets(self):
        """Erstellt die GUI-Elemente."""
        # Haupt-Frames (Links für Steuerung, Rechts für Vorschau)
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame, width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Linker Bereich: Steuerung ---

        # 1. Datei Sektion
        file_frame = ttk.LabelFrame(left_frame, text="Dateien & Ordner", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        btn_select_videos = ttk.Button(file_frame, text="1. Videos auswählen", command=self.select_videos)
        btn_select_videos.pack(fill=tk.X, pady=2)

        self.video_listbox = tk.Listbox(file_frame, height=6, selectmode=tk.SINGLE)
        self.video_listbox.pack(fill=tk.X, expand=True, pady=2)
        list_scrollbar = ttk.Scrollbar(self.video_listbox, orient=tk.VERTICAL, command=self.video_listbox.yview)
        list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.video_listbox.config(yscrollcommand=list_scrollbar.set)

        btn_clear_list = ttk.Button(file_frame, text="Liste leeren", command=self.clear_video_list)
        btn_clear_list.pack(fill=tk.X, pady=2)

        btn_select_output = ttk.Button(file_frame, text="2. Ausgabeordner wählen", command=self.select_output_folder)
        btn_select_output.pack(fill=tk.X, pady=2)
        output_entry = ttk.Entry(file_frame, textvariable=self.output_folder, state="readonly")
        output_entry.pack(fill=tk.X, pady=2)


        # 2. Wasserzeichen Sektion
        wm_frame = ttk.LabelFrame(left_frame, text="Wasserzeichen Einstellungen", padding="10")
        wm_frame.pack(fill=tk.X, pady=(0, 10))

        # Text
        ttk.Label(wm_frame, text="Text:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        wm_text_entry = ttk.Entry(wm_frame, textvariable=self.watermark_text)
        wm_text_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=2, pady=2)
        self.watermark_text.trace_add("write", lambda *args: self._update_preview_safe())

        # Schriftart
        ttk.Label(wm_frame, text="Schriftart:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        try:
            available_fonts = sorted([f for f in font.families() if not f.startswith('@')])
        except Exception as e:
             print(f"WARNUNG: Konnte System-Schriftarten nicht laden: {e}. Verwende Standardliste.")
             available_fonts = ["Arial", "Times New Roman", "Verdana", "Tahoma", "Courier New"]
        if not available_fonts: available_fonts = ["Arial", "Times New Roman", "Verdana"]
        if self.selected_font.get() not in available_fonts:
            self.selected_font.set(available_fonts[0])

        self.font_combo = ttk.Combobox(wm_frame, textvariable=self.selected_font, values=available_fonts, state="readonly")
        self.font_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=2, pady=2)
        self.font_combo.bind("<<ComboboxSelected>>", lambda event: self._update_preview_safe())

        # Schriftgröße
        ttk.Label(wm_frame, text="Größe:").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        size_spinbox = ttk.Spinbox(wm_frame, from_=8, to=200, textvariable=self.font_size, command=self._update_preview_safe, width=6)
        size_spinbox.grid(row=2, column=1, sticky="w", padx=2, pady=2)
        size_spinbox.bind("<KeyRelease>", lambda event: self.root.after(300, self._update_preview_safe))
        size_spinbox.bind("<ButtonRelease-1>", self._update_preview_safe)


        # Farbe
        ttk.Label(wm_frame, text="Farbe:").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.color_label = tk.Label(wm_frame, text="     ", bg=self.font_color.get(), relief="sunken")
        self.color_label.grid(row=3, column=1, sticky="ew", padx=2, pady=2)
        color_button = ttk.Button(wm_frame, text="Wählen", command=self.select_color)
        color_button.grid(row=3, column=2, sticky="e", padx=2, pady=2)


        # 3. Prozess Sektion
        process_frame = ttk.LabelFrame(left_frame, text="Verarbeitung", padding="10")
        process_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_button = ttk.Button(process_frame, text="3. Wasserzeichen hinzufügen", command=self.start_processing_thread)
        self.start_button.pack(fill=tk.X, pady=5)
        if not MOVIEPY_AVAILABLE: self.start_button.config(state=tk.DISABLED)

        self.stop_button = ttk.Button(process_frame, text="Verarbeitung abbrechen", command=self.stop_processing, state=tk.DISABLED)
        self.stop_button.pack(fill=tk.X, pady=5)

        # Statusleiste
        status_label = ttk.Label(left_frame, textvariable=self.status_var, relief="sunken", anchor="w", padding=5)
        status_label.pack(fill=tk.X, pady=(10, 0))

        # Fortschrittsbalken
        self.progress_bar = ttk.Progressbar(left_frame, orient="horizontal", mode="determinate", variable=self.progress_var)
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))


        # --- Rechter Bereich: Vorschau ---
        preview_frame = ttk.LabelFrame(right_frame, text="Vorschau & Positionierung (Ziehen zum Verschieben)", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_canvas = tk.Canvas(preview_frame, bg=COLOR_CANVAS_BG, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
        self.preview_canvas.bind("<ButtonPress-1>", self._start_drag)
        self.preview_canvas.bind("<B1-Motion>", self._on_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._end_drag)


    # --- GUI Callbacks ---
    # select_videos, clear_video_list, select_output_folder, select_color (Unchanged)
    def select_videos(self):
        """Öffnet den Dateidialog zur Auswahl von Videodateien."""
        filetypes = [
            ("Video Dateien", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
            ("Alle Dateien", "*.*")
        ]
        initial_dir = getattr(self, "_last_video_dir", "/")
        selected_files = filedialog.askopenfilenames(title="Videodateien auswählen", filetypes=filetypes, initialdir=initial_dir)
        if selected_files:
            self._last_video_dir = os.path.dirname(selected_files[0])
            current_files = set(self.video_files)
            new_files_added = False
            for f in selected_files:
                if f not in current_files:
                    self.video_files.append(f)
                    self.video_listbox.insert(tk.END, os.path.basename(f))
                    current_files.add(f)
                    new_files_added = True
            if new_files_added:
                self.status_var.set(f"{len(self.video_files)} Video(s) ausgewählt.")
            else:
                 self.status_var.set(f"Keine neuen Videos hinzugefügt. Gesamt: {len(self.video_files)}")


    def clear_video_list(self):
        """Entfernt alle Videos aus der Liste."""
        self.video_files = []
        self.video_listbox.delete(0, tk.END)
        self.status_var.set("Videoliste geleert.")

    def select_output_folder(self):
        """Öffnet den Dialog zur Auswahl des Ausgabeordners."""
        initial_dir = getattr(self, "_last_output_dir", "/")
        folder = filedialog.askdirectory(title="Ausgabeordner wählen", initialdir=initial_dir)
        if folder:
            self.output_folder.set(folder)
            self._last_output_dir = folder
            self.status_var.set(f"Ausgabeordner: {folder}")

    def select_color(self):
        """Öffnet den Farbauswahldialog und aktualisiert die Farbe."""
        try:
            color_code = colorchooser.askcolor(title="Wasserzeichenfarbe wählen", initialcolor=self.font_color.get())
            if color_code and color_code[1]:
                self.font_color.set(color_code[1])
                self.color_label.config(bg=self.font_color.get())
                self._update_preview_safe()
        except Exception as e:
             messagebox.showerror("Farbwahl Fehler", f"Konnte die Farbauswahl nicht öffnen:\n{e}")
             print(f"ERROR: Color Chooser failed: {e}")

    def _on_canvas_resize(self, event):
        """Wird aufgerufen, wenn die Größe des Canvas geändert wird."""
        if hasattr(self, "_resize_job"):
             self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(100, self._update_preview_safe)


    def _start_drag(self, event):
        """Speichert die Startposition des Ziehens, wenn auf das Wasserzeichen geklickt wird."""
        items = self.preview_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        if self.preview_wm_item in items:
            self.preview_drag_start_pos = (event.x, event.y)
            self.preview_canvas.config(cursor="fleur")
        else:
             self.preview_drag_start_pos = None


    def _on_drag(self, event):
        """Verschiebt das Wasserzeichen-Vorschaubild auf dem Canvas, wenn gezogen wird."""
        if not self.preview_wm_item or self.preview_drag_start_pos is None: return

        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1: return

        dx = event.x - self.preview_drag_start_pos[0]
        dy = event.y - self.preview_drag_start_pos[1]

        current_coords = self.preview_canvas.coords(self.preview_wm_item)
        new_x = current_coords[0] + dx
        new_y = current_coords[1] + dy

        if self.watermark_preview_image:
            wm_width = self.watermark_preview_image.width
            wm_height = self.watermark_preview_image.height
            new_x = max(0, min(new_x, canvas_width - wm_width))
            new_y = max(0, min(new_y, canvas_height - wm_height))
        else:
            wm_width, wm_height = 0, 0

        self.preview_canvas.coords(self.preview_wm_item, new_x, new_y)

        center_x = new_x + wm_width / 2
        center_y = new_y + wm_height / 2
        self.preview_position = (center_x / canvas_width, center_y / canvas_height)
        self.preview_drag_start_pos = (event.x, event.y)


    def _end_drag(self, event):
         """Wird aufgerufen, wenn das Ziehen beendet wird."""
         if self.preview_drag_start_pos is not None:
             self.preview_canvas.config(cursor="")
             self.preview_drag_start_pos = None


    def _update_preview_safe(self, *args):
         """Wrapper für _update_preview, um Fehler abzufangen und schnelle Änderungen zu bündeln."""
         try:
              if hasattr(self, "_update_job"):
                   self.root.after_cancel(self._update_job)
              self._update_job = self.root.after(50, self._update_preview)
         except Exception as e:
              print(f"WARNUNG: Fehler beim Planen des Preview-Updates (ignoriert): {e}")

    # --- Kernlogik ---

    def create_watermark_image(self, text, font_name, font_size, font_color_hex):
        """Erstellt ein PIL Bild mit dem Wasserzeichentext. Verbesserte Font-Suche."""
        pil_font = None
        font_path_used = "PIL Standard (Fallback)"

        if not text or font_size <= 0: return None

        try:
            print(f"INFO: Versuche Font '{font_name}' direkt zu laden...")
            pil_font = ImageFont.truetype(font_name, font_size)
            font_path_used = f"'{font_name}' (direkt gefunden)"
            print(f"INFO: Font '{font_name}' direkt geladen.")
        except IOError:
            print(f"INFO: Font '{font_name}' nicht direkt gefunden. Versuche Varianten...")
            common_extensions = ['.ttf', '.otf']
            font_search_paths = []
            system = platform.system()

            # Add system font directories
            if system == "Windows":
                win_font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
                if os.path.isdir(win_font_dir): font_search_paths.append(win_font_dir)
            elif system == "Linux":
                linux_paths = [os.path.expanduser("~/.fonts"), "/usr/local/share/fonts", "/usr/share/fonts"]
                font_search_paths.extend([p for p in linux_paths if os.path.isdir(p)])
            elif system == "Darwin":
                 mac_paths = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts", "/System/Library/Fonts"]
                 font_search_paths.extend([p for p in mac_paths if os.path.isdir(p)])

            found_path = None
            variations = [font_name, font_name.lower()]
            if ' ' in font_name: variations.append(font_name.replace(" ", ""))

            for name_var in variations:
                 if found_path: break
                 for ext in common_extensions:
                    if found_path: break
                    font_filename = f"{name_var}{ext}"
                    try:
                        print(f"INFO: Versuche '{font_filename}'...")
                        pil_font = ImageFont.truetype(font_filename, font_size)
                        font_path_used = f"'{font_filename}' (mit Endung gefunden)"
                        print(f"INFO: Font '{font_filename}' geladen.")
                        found_path = font_filename
                        break
                    except IOError:
                        for search_dir in font_search_paths:
                            # Recursive search within the directory
                            for root_dir, _, files in os.walk(search_dir):
                                if font_filename.lower() in [f.lower() for f in files]: # Case-insensitive check
                                    # Find the exact filename match (case might matter for loading)
                                    matching_files = [f for f in files if f.lower() == font_filename.lower()]
                                    if not matching_files: continue
                                    explicit_path = os.path.join(root_dir, matching_files[0])

                                    if found_path: break # Already found in a previous iteration
                                    try:
                                        print(f"INFO: Versuche expliziten Pfad '{explicit_path}'...")
                                        pil_font = ImageFont.truetype(explicit_path, font_size)
                                        font_path_used = f"'{explicit_path}' (explizit gefunden)"
                                        print(f"INFO: Font '{explicit_path}' geladen.")
                                        found_path = explicit_path
                                        break
                                    except IOError:
                                        print(f"WARNUNG: Font existiert bei '{explicit_path}', aber Laden fehlgeschlagen.")
                                        continue # Check next potential match
                            if found_path: break
                 if found_path: break

            if not pil_font and system == "Linux":
                 # fc-match logic (unchanged)
                 try:
                     print(f"INFO: Versuche Font '{font_name}' via fc-match...")
                     search_name = font_name # Use original name for fc-match
                     proc = subprocess.Popen(['fc-match', '--format=%{file}', search_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     stdout, stderr = proc.communicate(timeout=2) # Add timeout
                     fc_path = stdout.decode().strip()
                     if fc_path and os.path.exists(fc_path):
                         try:
                             pil_font = ImageFont.truetype(fc_path, font_size)
                             font_path_used = f"'{fc_path}' (via fc-match)"
                             print(f"INFO: Font '{font_name}' via fc-match gefunden und geladen: {fc_path}")
                         except IOError as fc_load_err:
                              print(f"WARNUNG: Font '{fc_path}' via fc-match gefunden, aber Laden fehlgeschlagen: {fc_load_err}")
                     else:
                          # Try lowercase for fc-match as well
                          search_name_lower = font_name.lower()
                          if search_name != search_name_lower:
                            print(f"INFO: Versuche Font '{search_name_lower}' via fc-match...")
                            proc = subprocess.Popen(['fc-match', '--format=%{file}', search_name_lower], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            stdout, stderr = proc.communicate(timeout=2)
                            fc_path = stdout.decode().strip()
                            if fc_path and os.path.exists(fc_path):
                                try:
                                    pil_font = ImageFont.truetype(fc_path, font_size)
                                    font_path_used = f"'{fc_path}' (via fc-match, lowercase)"
                                    print(f"INFO: Font '{font_name}' via fc-match (lowercase) gefunden und geladen: {fc_path}")
                                except IOError as fc_load_err:
                                    print(f"WARNUNG: Font '{fc_path}' via fc-match (lowercase) gefunden, aber Laden fehlgeschlagen: {fc_load_err}")
                            else:
                                 print(f"INFO: fc-match für '{font_name}'/'{search_name_lower}' fehlgeschlagen oder Pfad ungültig. Stderr: {stderr.decode().strip()}")
                          else:
                                print(f"INFO: fc-match für '{font_name}' fehlgeschlagen oder Pfad ungültig. Stderr: {stderr.decode().strip()}")

                 except (ImportError, FileNotFoundError, subprocess.TimeoutExpired, Exception) as fc_e:
                      print(f"INFO: fc-match Versuch fehlgeschlagen: {fc_e}")


        if not pil_font:
            try:
                print(f"WARNUNG: Konnte Font '{font_name}' nach mehreren Versuchen nicht finden. Verwende PIL Standard-Font (Größe wird ignoriert!).")
                pil_font = ImageFont.load_default()
                font_path_used = "PIL Standard (Fallback - keine Größenänderung)"
            except Exception as def_e:
                print(f"FATAL: Konnte auch Standard-Font nicht laden: {def_e}")
                if hasattr(self, 'root'):
                     self.root.after(0, messagebox.showerror, "Schriftart Fehler", f"Konnte weder '{font_name}' noch die Standard-Schriftart laden.\n{def_e}")
                return None

        try:
            text_bbox = pil_font.getbbox(text)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            padding_x = max(5, int(font_size * 0.1))
            padding_y = max(3, int(font_size * 0.05))
            img_width = text_width + 2 * padding_x
            img_height = text_height + 2 * padding_y

            image = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw_x = padding_x - text_bbox[0]
            draw_y = padding_y - text_bbox[1]
            draw.text((draw_x, draw_y), text, font=pil_font, fill=font_color_hex)

            print(f"INFO: Wasserzeichenbild erstellt mit Font: {font_path_used}, Größe: {font_size}")
            return image

        except Exception as e:
            print(f"FEHLER beim Erstellen des Wasserzeichenbildes mit Font '{font_path_used}': {e}\n{traceback.format_exc()}")
            if hasattr(self, 'root'):
                 self.root.after(0, messagebox.showerror, "Bild Erstellungsfehler", f"Fehler beim Zeichnen des Wasserzeichens:\n{e}")
            return None


    def _update_preview(self):
        """Aktualisiert das Vorschau-Canvas mit dem aktuellen Wasserzeichen."""
        # Logic unchanged, uses create_watermark_image
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
             if not hasattr(self, "_update_preview_pending") or not self._update_preview_pending:
                  self._update_preview_pending = True
                  self.root.after(100, self._update_preview)
             return
        self._update_preview_pending = False

        wm_text = self.watermark_text.get()
        font_name = self.selected_font.get()
        font_size_val = self.font_size.get()
        font_color_val = self.font_color.get()

        try:
            if len(font_color_val) == 7: font_color_rgba = font_color_val + "FF"
            elif len(font_color_val) == 9: font_color_rgba = font_color_val
            else: font_color_rgba = "#FFFFFFFF"
        except Exception: font_color_rgba = "#FFFFFFFF"

        self.watermark_preview_image = self.create_watermark_image(
            wm_text, font_name, font_size_val, font_color_rgba
        )

        if self.preview_wm_item:
            self.preview_canvas.delete(self.preview_wm_item)
            self.preview_wm_item = None
            self.watermark_preview_photo = None # Wichtig!

        if not self.watermark_preview_image:
             print("INFO: Kein Wasserzeichen-Vorschau-Bild vorhanden.")
             return

        try:
             self.watermark_preview_photo = ImageTk.PhotoImage(self.watermark_preview_image)
        except Exception as e:
             print(f"FEHLER bei ImageTk Erstellung: {e}")
             return

        wm_width = self.watermark_preview_image.width
        wm_height = self.watermark_preview_image.height
        target_center_x = self.preview_position[0] * canvas_width
        target_center_y = self.preview_position[1] * canvas_height
        target_x = target_center_x - wm_width / 2
        target_y = target_center_y - wm_height / 2
        target_x = max(0, min(target_x, canvas_width - wm_width))
        target_y = max(0, min(target_y, canvas_height - wm_height))

        self.preview_wm_item = self.preview_canvas.create_image(
            target_x, target_y, anchor=tk.NW, image=self.watermark_preview_photo
        )
        self.preview_canvas.lift(self.preview_wm_item)


    def start_processing_thread(self):
        """Startet den Thread für die Videoverarbeitung."""
        # Logic unchanged
        if not MOVIEPY_AVAILABLE:
             messagebox.showerror("Fehler", "MoviePy ist nicht verfügbar. Verarbeitung nicht möglich.")
             return
        if self.processing_thread and self.processing_thread.is_alive():
            messagebox.showwarning("Läuft bereits", "Die Verarbeitung läuft bereits.")
            return
        if not self.video_files:
            messagebox.showwarning("Keine Videos", "Bitte wählen Sie zuerst Videodateien aus.")
            return
        output_dir = self.output_folder.get()
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("Kein Ausgabeordner", "Bitte wählen Sie einen gültigen Ausgabeordner.")
            return

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress_var.set(0.0)
        self.status_var.set("Starte Verarbeitung...")
        self.stop_processing_flag.clear()

        self.processing_thread = threading.Thread(target=self.process_videos, daemon=True)
        self.processing_thread.start()

    def stop_processing(self):
         """Setzt das Flag, um den Verarbeitungsthread (bald) zu stoppen."""
         # Logic unchanged
         if self.processing_thread and self.processing_thread.is_alive():
              self.stop_processing_flag.set()
              self.status_var.set("Versuche Verarbeitung abzubrechen...")
              self.stop_button.config(state=tk.DISABLED)
              print("INFO: Abbruchsignal gesendet.")
         else:
              print("INFO: Kein aktiver Verarbeitungsthread zum Abbrechen.")


    def process_videos(self):
        """Führt die eigentliche Videoverarbeitung im Hintergrund durch."""
        output_dir = self.output_folder.get()
        wm_text = self.watermark_text.get()
        font_name = self.selected_font.get()
        font_size_val = self.font_size.get()
        font_color_val = self.font_color.get()
        relative_pos = self.preview_position

        total_videos = len(self.video_files)
        processed_count = 0
        errors = []

        try:
            if len(font_color_val) == 7: font_color_rgba = font_color_val + "FF"
            elif len(font_color_val) == 9: font_color_rgba = font_color_val
            else: font_color_rgba = "#FFFFFFFF"
        except Exception: font_color_rgba = "#FFFFFFFF"

        try:
             print("INFO: Erstelle finales Wasserzeichenbild für Verarbeitung...")
             wm_pil_image = self.create_watermark_image(wm_text, font_name, font_size_val, font_color_rgba)
             if not wm_pil_image:
                  raise ValueError("Konnte Wasserzeichenbild nicht erstellen (siehe vorherige Logs).")
             wm_numpy_image = np.array(wm_pil_image)
             print(f"INFO: Wasserzeichen Numpy Array Shape: {wm_numpy_image.shape}")
        except Exception as img_e:
             error_msg = f"Fehler beim Erstellen des Wasserzeichen-Bildes vor der Verarbeitung: {img_e}"
             print(f"ERROR: {error_msg}\n{traceback.format_exc()}")
             self.root.after(0, messagebox.showerror, "Vorbereitungsfehler", error_msg)
             self.root.after(0, self._processing_finished, False, ["Wasserzeichen-Erstellung fehlgeschlagen."], False, False)
             return

        for i, video_path in enumerate(self.video_files):
            if self.stop_processing_flag.is_set():
                 print("INFO: Verarbeitungsschleife wegen Abbruchsignal verlassen.")
                 errors.append("Prozess durch Benutzer abgebrochen.")
                 break

            filename = os.path.basename(video_path)
            output_filename = f"{os.path.splitext(filename)[0]}_wasserzeichen.mp4"
            output_path = os.path.join(output_dir, output_filename)

            # Update Status before starting the heavy load
            self.root.after(0, lambda i=i, f=filename: self.status_var.set(f"Verarbeite ({i+1}/{total_videos}): {f}"))
            # Set progress slightly above the previous video's completion
            self.root.after(0, lambda i=i: self.progress_var.set((i / total_videos) * 100))

            clip = None
            watermark_clip = None
            final = None

            try:
                print(f"INFO [{filename}]: Lade Video...")
                clip = VideoFileClip(video_path)
                video_w, video_h = clip.size
                print(f"INFO [{filename}]: Video Größe: {video_w}x{video_h}, Dauer: {clip.duration}s")

                print(f"INFO [{filename}]: Erstelle Wasserzeichen Clip...")
                watermark_clip = ImageClip(wm_numpy_image, transparent=True)
                watermark_clip = watermark_clip.with_duration(clip.duration)

                wm_w, wm_h = wm_pil_image.size
                target_center_x = relative_pos[0] * video_w
                target_center_y = relative_pos[1] * video_h
                pos_x = target_center_x - wm_w / 2
                pos_y = target_center_y - wm_h / 2
                margin = 5
                pos_x = max(margin, min(pos_x, video_w - wm_w - margin))
                pos_y = max(margin, min(pos_y, video_h - wm_h - margin))

                watermark_clip = watermark_clip.with_position((pos_x, pos_y))
                print(f"INFO [{filename}]: Wasserzeichen Position (px): ({pos_x:.1f}, {pos_y:.1f})")

                print(f"INFO [{filename}]: Kombiniere Clips...")
                final = CompositeVideoClip([clip, watermark_clip])

                # *** FORTSCHRITTSBALKEN-WORKAROUND (Start) ***
                # Update status and give a small progress bump before writing starts
                self.root.after(0, self.status_var.set, f"Schreibe Datei ({i+1}/{total_videos}): {filename}...")
                # Set progress to slightly *more* than the start of this video's section
                self.root.after(0, lambda i=i: self.progress_var.set(((i + 0.05) / total_videos) * 100))


                print(f"INFO [{filename}]: Schreibe Ergebnis nach '{output_path}' mit optimierten Parametern...")
                # *** OPTIMIERTE FFmpeg PARAMETER ***
                final.write_videofile(
                    output_path,
                    codec='libx264',         # Standard H.264
                    audio_codec='aac',       # Standard AAC Audio
                    threads=os.cpu_count() or 4, # Mehr Threads nutzen (oder 4 als Fallback)
                    preset='ultrafast',      # Schnellstes Encoding (größere Dateien mögl.)
                    ffmpeg_params=[
                        "-crf", "23",        # Qualität (18=besser, 28=schlechter)
                        "-pix_fmt", "yuv420p",# Maximale Kompatibilität
                        "-movflags", "+faststart" # Für Web-Streaming optimiert
                    ],
                    logger=None #'bar'      # Kein Konsolen-Logger, da wir GUI haben
                )

                # *** FORTSCHRITTSBALKEN-WORKAROUND (Ende) ***
                # Set progress to almost complete for this video after writing finishes
                self.root.after(0, lambda i=i: self.progress_var.set(((i + 0.95) / total_videos) * 100))

                print(f"INFO [{filename}]: Erfolgreich abgeschlossen.")
                processed_count += 1

            except Exception as e:
                # Error handling (unchanged)
                error_type = type(e).__name__
                error_details = str(e)
                tb_str = traceback.format_exc()
                print(f"FEHLER bei Verarbeitung von '{filename}': {error_type}: {error_details}\n{tb_str}")
                error_msg = f"FEHLER '{filename}': {error_type}"
                if isinstance(e, (FileNotFoundError, OSError)) and ('ffmpeg' in error_details.lower() or 'ffprobe' in error_details.lower()):
                    error_msg += f" -> FFmpeg/FFprobe nicht gefunden oder Pfad falsch? (Pfad: {os.environ.get('IMAGEIO_FFMPEG_EXE', 'System PATH / imageio')})"
                elif isinstance(e, OSError) and ("Permission denied" in error_details or "Errno 13" in error_details):
                    error_msg += " -> Keine Schreibrechte im Ausgabeordner?"
                elif "Unknown encoder" in error_details:
                     error_msg += f" -> FFmpeg kennt Codec nicht ({'libx264' if 'libx264' in error_details else 'aac'}?). FFmpeg aktuell?"
                elif "AttributeError" in error_type and ("with_position" in error_details or "with_duration" in error_details):
                     error_msg += " -> MoviePy API Fehler. Bitte melden."
                elif "MemoryError" in error_type:
                     error_msg += " -> Nicht genug Arbeitsspeicher. Versuche kleinere Videos."
                else:
                     detail_snippet = error_details.replace('\n', ' ').strip()[:100]
                     error_msg += f" -> Details: {detail_snippet}..."
                errors.append(error_msg)

            finally:
                # Resource cleanup (unchanged)
                try:
                    if final: final.close()
                    if watermark_clip: watermark_clip.close()
                    if clip: clip.close()
                    gc.collect()
                    print(f"INFO [{filename}]: Ressourcen freigegeben, GC durchgeführt.")
                except Exception as close_e:
                     print(f"WARNUNG [{filename}]: Fehler beim Schließen der Clips (ignoriert): {close_e}")
            time.sleep(0.01) # Kleine Pause

        # GUI Update after loop (unchanged logic, _processing_finished handles final state)
        was_stopped = self.stop_processing_flag.is_set()
        error_list = [e for e in errors if "Benutzer abgebrochen" not in e]
        success = not error_list and not was_stopped
        partial_success = was_stopped and not error_list
        self.root.after(0, self._processing_finished, success, errors, was_stopped, partial_success)


    def _processing_finished(self, success, errors, was_stopped, partial_success):
        """Wird aufgerufen, wenn der Verarbeitungsthread beendet ist."""
        # Final GUI state update (unchanged logic)
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.progress_var.set(100.0) # Ensure it ends at 100%
        self.processing_thread = None

        total_files = len(self.video_files)
        error_list = [e for e in errors if "Benutzer abgebrochen" not in e]
        error_count = len(error_list)
        # Correctly calculate processed count considering stops and errors
        processed_count = total_files - error_count
        if was_stopped and not partial_success and errors: # If stopped AND other errors occurred, don't double-count the stop implicit failure
             processed_count = total_files - error_count -1 # Reduce by one more if stop caused the loop break before last error
        elif was_stopped:
             # Find index where stop occurred if possible (crude estimate)
             stop_index = -1
             for idx, err in enumerate(errors):
                  if "Benutzer abgebrochen" in err:
                       stop_index = idx # Index relative to file list where stop was recorded
                       break
             # Estimate processed count based on when stop occurred
             processed_count = stop_index if stop_index != -1 else total_files - error_count -1


        if processed_count < 0: processed_count = 0 # Sanity check

        if was_stopped:
             self.status_var.set(f"Verarbeitung abgebrochen. {processed_count}/{total_files} Videos bearbeitet.")
             messagebox.showwarning("Abgebrochen", f"Die Videoverarbeitung wurde abgebrochen.\n{processed_count} von {total_files} Videos wurden bis dahin (möglicherweise) bearbeitet.")
        elif success:
            self.status_var.set(f"Verarbeitung abgeschlossen ({total_files}/{total_files} erfolgreich).")
            messagebox.showinfo("Fertig", f"Alle {total_files} Videos wurden erfolgreich bearbeitet!")
        else: # Fehler aufgetreten
            self.status_var.set(f"Verarbeitung mit {error_count} Fehlern beendet.")
            error_summary = f"{error_count} Fehler sind aufgetreten ({processed_count}/{total_files} erfolgreich):\n\n" + "\n".join(f"- {e}" for e in error_list)
            if len(error_summary) > 1000:
                 error_summary = error_summary[:1000] + "\n\n... (Weitere Fehler in Konsole)"
            messagebox.showerror("Fehler bei Verarbeitung", error_summary)

        self.stop_processing_flag.clear()


    def _on_closing(self):
        """Wird aufgerufen, wenn das Fenster geschlossen wird."""
        # Logic unchanged
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askyesno("Verarbeitung läuft", "Die Videoverarbeitung läuft noch.\nWollen Sie wirklich beenden? Der aktuelle Vorgang wird abgebrochen."):
                print("INFO: Schließen bestätigt, sende Abbruchsignal...")
                self.stop_processing_flag.set()
                self.root.after(150, self.root.destroy)
            else:
                print("INFO: Schließen abgelehnt.")
                return
        else:
            print("INFO: Anwendung wird geschlossen.")
            self.root.destroy()


# --- Hauptausführung ---
if __name__ == "__main__":
    # from multiprocessing import freeze_support
    # freeze_support()

    root = tk.Tk()
    app = VideoWatermarkerApp(root)
    root.mainloop()