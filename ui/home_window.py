import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont
import os
import json
import time
from datetime import datetime
import webbrowser
from tkinter import messagebox

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS, "fonts")
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")

FONT_DEMI = os.path.join(FONTS_DIR, "ITCAvantGardeStd-Demi.ttf")
FONT_MD = os.path.join(FONTS_DIR, "ITCAvantGardeStd-Md.ttf")
FONT_BOOK = os.path.join(FONTS_DIR, "ITCAvantGardeStd-Bk.ttf")

BG = "#0e0e0e"
SIDEBAR = "#1a1a1a"
PANEL = "#2a2a2a"
TEXT = "#ffffff"

PROJECT_BTN = "#3a3a3a"
CREATE_BTN = "#4a4a4a"
BTN_TEXT = "#eeeeee"
SEPARATOR = "#555555"
SCROLL_BTN = "#5a5a5a"
SCROLL_HOVER = "#6a6a6a"

# ---------- Параметры анимации ----------
SLIDE = 30          # на сколько пикселей элементы «проезжают» вниз
BTN_SLIDE = 12      # у кнопки путь короче, чтобы она не наезжала на панель (зазор 18 px)
CENTER_W = 480
TOP_PAD = 50        # запас сверху, чтобы элементы не обрезались при въезде
GREETING_Y = TOP_PAD
PANEL_Y = TOP_PAD + 66
PANEL_W, PANEL_H = 460, 240
BUTTON_Y = PANEL_Y + PANEL_H + 18
CENTER_H = BUTTON_Y + 42 + 12


# ==========================================================
#   Вспомогательные функции для анимации
# ==========================================================
def hex_to_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def blend(c1, c2, t):
    """Плавный переход цвета c1 -> c2 (t от 0 до 1)."""
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out(t):
    """Быстро начинает, плавно тормозит в конце."""
    return 1 - (1 - t) ** 3


def linear(t):
    return t


def with_alpha(img, a):
    """Копия RGBA-картинки с прозрачностью, умноженной на a (0..1)."""
    out = img.copy()
    alpha = out.getchannel("A").point(lambda p: int(p * a))
    out.putalpha(alpha)
    return out


def safe_cfg(widget, **kw):
    """configure(), который не падает, если в этой версии customtkinter нет какого-то параметра."""
    try:
        widget.configure(**kw)
    except (ValueError, TypeError, tk.TclError):
        for k, v in kw.items():
            try:
                widget.configure(**{k: v})
            except (ValueError, TypeError, tk.TclError):
                pass


class Animator:
    """Запускает набор анимаций с задержками. Каждая получает прогресс p от 0 до 1."""

    def __init__(self, widget):
        self.widget = widget
        self.items = []
        self.t0 = None

    def add(self, delay, duration, fn, easing=ease_out):
        self.items.append({"delay": delay, "dur": duration, "fn": fn, "ease": easing, "done": False})
        fn(0.0)  # сразу выставляем начальное (невидимое) состояние

    def start(self):
        self.t0 = time.perf_counter()
        self._tick()

    def _tick(self):
        try:
            if not self.widget.winfo_exists():
                return
        except tk.TclError:
            return

        now = time.perf_counter() - self.t0
        pending = False
        for it in self.items:
            if it["done"]:
                continue
            p = (now - it["delay"]) / it["dur"]
            if p < 0:
                pending = True
                continue
            try:
                if p >= 1:
                    it["fn"](1.0)
                    it["done"] = True
                else:
                    it["fn"](it["ease"](p))
                    pending = True
            except tk.TclError:
                return
        if pending:
            self.widget.after(16, self._tick)


# ==========================================================
#   Остальной код
# ==========================================================
def make_text_image(text, font_path, size, color=(255, 255, 255)):
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:
        font = ImageFont.load_default()
    dummy = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(dummy)
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 6
    h = bbox[3] - bbox[1] + 6
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((3, 1), text, font=font, fill=color)
    return img


def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good Morning!"
    elif 12 <= hour < 17:
        return "Good Afternoon!"
    elif 17 <= hour < 22:
        return "Good Evening!"
    else:
        return "Night!"


def get_projects():
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR, exist_ok=True)
        return []
    projects = []
    for f in os.listdir(PROJECTS_DIR):
        if f.endswith(".json"):
            path = os.path.join(PROJECTS_DIR, f)
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    projects.append({
                        "name": data.get("name", f[:-5]),
                        "file": path,
                        "created": data.get("created", "")
                    })
            except Exception:
                pass
    projects.sort(key=lambda x: x.get("created", ""), reverse=True)
    return projects


class CreateProjectDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_created):
        super().__init__(parent)
        self.on_created = on_created
        self.title("New Project")
        self.geometry("400x210")
        self.resizable(False, False)
        self.configure(fg_color="#1c1c1c")
        self.transient(parent)
        self.after(100, self.grab_set)

        self.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width() // 2 - 200
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - 105
        self.geometry(f"+{x}+{y}")

        ctk.CTkLabel(self, text="Project name", font=("Segoe UI", 15),
                     text_color=TEXT).pack(pady=(26, 8))
        self.entry = ctk.CTkEntry(self, width=280, height=38,
                                  fg_color="#2a2a2a", border_color="#444",
                                  placeholder_text="My Show")
        self.entry.pack()
        self.entry.focus()

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=18)
        ctk.CTkButton(row, text="Create", width=110, height=34,
                      fg_color="#3a3a3a", hover_color="#4a4a4a",
                      command=self.create).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancel", width=110, height=34,
                      fg_color="#2a2a2a", hover_color="#3a3a3a",
                      command=self.destroy).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self.create())

    def create(self):
        name = self.entry.get().strip()
        if not name:
            messagebox.showwarning("LiveControl", "Enter a project name", parent=self)
            return
        safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_") or "project"
        path = os.path.join(PROJECTS_DIR, f"{safe}.json")
        if os.path.exists(path):
            messagebox.showwarning("LiveControl", "Project already exists", parent=self)
            return
        data = {
            "name": name,
            "created": datetime.now().isoformat(),
            "obs": {"host": "localhost", "port": 4455, "password": ""},
            "emergency_scene": "",
            "custom_buttons": [],
            "cameras": {str(i): f"CAM{i}" for i in range(1, 11)}
        }
        os.makedirs(PROJECTS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.destroy()
        self.on_created(path)


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, images):
        super().__init__(parent)
        self._images = images
        self.title("Settings")
        self.geometry("520x340")
        self.resizable(False, False)
        self.configure(fg_color="#1c1c1c")
        self.transient(parent)
        self.after(100, self.grab_set)

        self.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width() // 2 - 260
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - 170
        self.geometry(f"+{x}+{y}")

        img = make_text_image("Settings", FONT_DEMI, 20)
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self._images.append(photo)
        ctk.CTkLabel(self, image=photo, text="").pack(anchor="w", padx=28, pady=(22, 4))

        ctk.CTkFrame(self, height=1, fg_color="#444").pack(fill="x", padx=28, pady=(0, 18))

        row1 = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=10, height=48)
        row1.pack(fill="x", padx=28, pady=6)
        row1.pack_propagate(False)
        img = make_text_image("Language:", FONT_DEMI, 14)
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self._images.append(photo)
        ctk.CTkLabel(row1, image=photo, text="").pack(side="left", padx=16)
        ctk.CTkOptionMenu(row1, values=["English", "Русский"], width=120, height=32,
                          fg_color="#3a3a3a", button_color="#4a4a4a").pack(side="right", padx=12)

        row2 = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=10, height=48)
        row2.pack(fill="x", padx=28, pady=6)
        row2.pack_propagate(False)
        img = make_text_image("Check for latest version:", FONT_DEMI, 14)
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self._images.append(photo)
        ctk.CTkLabel(row2, image=photo, text="").pack(side="left", padx=16)
        ctk.CTkButton(row2, text="Check", width=90, height=32, fg_color="#3a3a3a",
                      hover_color="#4a4a4a", command=self.open_github).pack(side="right", padx=12)

        img = make_text_image("Made by StickBuug. All rights reserved.", FONT_BOOK, 11, (100, 100, 100))
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self._images.append(photo)
        ctk.CTkLabel(self, image=photo, text="").pack(side="bottom", pady=16)

    def open_github(self):
        webbrowser.open("https://github.com/StickBuugGyvas")
        self.destroy()


class HomeWindow(ctk.CTk):

    def __init__(self, on_open_project):
        super().__init__()
        self.on_open_project = on_open_project
        self._images = []

        # окно стартует прозрачным и плавно проявляется
        self._set_window_alpha(0.0)

        self.title("LiveControl")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")

        self.create_sidebar()
        self.create_main()

        self.build_intro()
        # Разворачиваем на весь экран (с рамкой и кнопками окна) и только потом запускаем анимацию.
        # Окно в это время ещё прозрачное, поэтому скачка размера не видно.
        self.after(300, self._maximize)
        self.after(500, self.anim.start)
        self.after(3000, lambda: self._set_window_alpha(1.0))   # страховка: окно точно станет видимым

    # ---------- утилиты ----------
    def _maximize(self):
        try:
            self.state("zoomed")                # Windows
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)    # Linux
            except Exception:
                pass

    def _set_window_alpha(self, a):
        try:
            self.attributes("-alpha", max(0.0, min(1.0, a)))
        except Exception:
            pass

    def _label(self, parent, text, font_path, size, color=(255, 255, 255)):
        img = make_text_image(text, font_path, size, color)
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self._images.append(photo)
        lbl = ctk.CTkLabel(parent, image=photo, text="")
        lbl._base_img = img          # оригинал, из него делаем кадры с прозрачностью
        return lbl

    def _set_label_alpha(self, lbl, a):
        img = with_alpha(lbl._base_img, a)
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        lbl.configure(image=photo)
        lbl._photo = photo           # держим ссылку, чтобы картинку не удалил сборщик мусора

    def _greeting_photo(self, p):
        """Кадр приветствия: текст сдвинут вниз на SLIDE*p и прозрачный на (1-p)."""
        base = self._greet_base
        frame = Image.new("RGBA", (base.width, base.height + SLIDE), (0, 0, 0, 0))
        frame.paste(with_alpha(base, p), (0, int(round(SLIDE * p))))
        return ctk.CTkImage(light_image=frame, dark_image=frame, size=(frame.width, frame.height))

    def _set_greeting(self, p):
        photo = self._greeting_photo(p)
        self.greeting.configure(image=photo)
        self._greet_photo = photo

    # ---------- боковая панель ----------
    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=56, fg_color=SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self._icon(self.sidebar, "personicon.png", self.on_profile, (20, 10))
        self._icon(self.sidebar, "connectionicon.png", self.on_connection, 8)
        self._icon(self.sidebar, "infoicon.png", self.on_settings, 8)

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", pady=18)
        self._icon(bottom, "infoicon.png", self.on_info)

    def _icon(self, parent, name, cmd, pady=0):
        path = os.path.join(ASSETS, name)
        try:
            img = Image.open(path).convert("RGBA").resize((24, 24), Image.Resampling.LANCZOS)
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=(24, 24))
            self._images.append(photo)
            ctk.CTkButton(parent, image=photo, text="", width=40, height=40,
                          fg_color="transparent", hover_color="#2a2a2a",
                          command=cmd).pack(pady=pady)
        except Exception as e:
            print("icon error", e)
            ctk.CTkButton(parent, text="•", width=40, height=40,
                          fg_color="transparent", command=cmd).pack(pady=pady)

    # ---------- главный экран ----------
    def create_main(self):
        main = ctk.CTkFrame(self, fg_color=BG)
        main.pack(side="left", fill="both", expand=True)

        # Все элементы ставятся через place(), чтобы их можно было двигать
        self.center = ctk.CTkFrame(main, fg_color="transparent", width=CENTER_W, height=CENTER_H)
        self.center.place(relx=0.5, rely=0.46, anchor="center")

        # Приветствие. Виджет НЕ двигается: «езда» нарисована внутри самой картинки
        # (текст сдвигается в прозрачном поле высотой SLIDE) — так не остаётся следов.
        self._greet_base = make_text_image(get_greeting(), FONT_DEMI, 32)
        self._greet_photo = self._greeting_photo(1.0)
        self.greeting = ctk.CTkLabel(self.center, image=self._greet_photo, text="")
        self.greeting.place(relx=0.5, y=GREETING_Y - SLIDE, anchor="n")

        # Панель проектов
        self._panel_c = BG          # текущий цвет панели (меняется во время анимации)
        self.panel = ctk.CTkFrame(self.center, width=PANEL_W, height=PANEL_H,
                                  fg_color=PANEL, corner_radius=14)
        self.panel.place(relx=0.5, y=PANEL_Y, anchor="n")
        self.panel.pack_propagate(False)

        self.panel_title = self._label(self.panel, "Your projects:", FONT_DEMI, 16)
        self.panel_title.pack(pady=(16, 6))

        self.separator = ctk.CTkFrame(self.panel, height=1, fg_color=SEPARATOR)
        self.separator.pack(fill="x", padx=40, pady=(0, 8))

        self.projects_frame = ctk.CTkScrollableFrame(self.panel, width=400, height=150,
                                                     fg_color="transparent",
                                                     scrollbar_button_color=SCROLL_BTN,
                                                     scrollbar_button_hover_color=SCROLL_HOVER)
        self.projects_frame.pack(padx=20, pady=(0, 10))
        self.refresh_projects()

        # Кнопка создания проекта — под панелью
        self.create_btn = ctk.CTkButton(
            self.center,
            text="Create project",
            font=("Segoe UI", 14),
            width=180,
            height=42,
            fg_color=CREATE_BTN,
            hover_color="#5a5a5a",
            corner_radius=8,
            text_color=BTN_TEXT,
            command=self.open_create_dialog
        )
        self.create_btn.place(relx=0.5, y=BUTTON_Y, anchor="n")

    # ---------- АНИМАЦИЯ ПОЯВЛЕНИЯ ----------
    def build_intro(self):
        a = self.anim = Animator(self)

        # 1. Всё окно плавно проявляется
        a.add(0.00, 0.40, lambda p: self._set_window_alpha(p), linear)

        # 2. Боковая панель выезжает слева
        a.add(0.05, 0.60, lambda p: self.sidebar.configure(width=max(1, int(56 * p))))

        # 3. Good Evening — проявляется и плавно «опускается» (внутри картинки)
        a.add(0.20, 0.80, self._set_greeting)

        # 4. Серая панель — проявляется и едет вниз.
        #    Прозрачные дети панели получают тот же цвет, иначе они были бы светлее неё.
        def panel_fn(p):
            c = blend(BG, PANEL, p)
            self._panel_c = c
            self.panel.configure(fg_color=c)
            self.panel_title.configure(fg_color=c)
            safe_cfg(self.projects_frame, fg_color=c, scrollbar_fg_color=c)
            for ch in self.projects_frame.winfo_children():
                if hasattr(ch, "_base_img"):
                    ch.configure(fg_color=c)
            self.panel.place(relx=0.5, y=PANEL_Y - SLIDE * (1 - p), anchor="n")
        a.add(0.38, 0.80, panel_fn)

        # 5. Содержимое панели появляется по очереди
        a.add(0.70, 0.50, lambda p: self._set_label_alpha(self.panel_title, p))
        a.add(0.78, 0.50, lambda p: self.separator.configure(
            fg_color=blend(self._panel_c, SEPARATOR, p)))
        a.add(0.90, 0.50, lambda p: safe_cfg(
            self.projects_frame,
            scrollbar_button_color=blend(self._panel_c, SCROLL_BTN, p),
            scrollbar_button_hover_color=blend(self._panel_c, SCROLL_HOVER, p)))

        for i, child in enumerate(self.projects_frame.winfo_children()):
            delay = 0.88 + i * 0.07
            if hasattr(child, "_base_img"):
                a.add(delay, 0.50, lambda p, c=child: self._set_label_alpha(c, p))
            else:
                a.add(delay, 0.50, lambda p, c=child: c.configure(
                    fg_color=blend(self._panel_c, PROJECT_BTN, p),
                    text_color=blend(self._panel_c, BTN_TEXT, p)))

        # 6. Кнопка Create project — последней, сверху вниз, не заходя на панель
        def button_fn(p):
            self.create_btn.configure(fg_color=blend(BG, CREATE_BTN, p),
                                      text_color=blend(BG, BTN_TEXT, p))
            self.create_btn.place(relx=0.5, y=BUTTON_Y - BTN_SLIDE * (1 - p), anchor="n")
        a.add(1.05, 0.70, button_fn)

    # ---------- проекты ----------
    def refresh_projects(self):
        for w in self.projects_frame.winfo_children():
            w.destroy()
        projects = get_projects()
        if not projects:
            self._label(self.projects_frame, "No projects yet", FONT_BOOK, 13,
                        (150, 150, 150)).pack(pady=20)
            return
        for p in projects:
            ctk.CTkButton(
                self.projects_frame, text=p["name"], font=("Segoe UI", 13),
                height=32, fg_color=PROJECT_BTN, hover_color="#4a4a4a",
                text_color=BTN_TEXT, anchor="w",
                command=lambda path=p["file"]: self.open_project(path)
            ).pack(fill="x", pady=3)

    def open_create_dialog(self):
        CreateProjectDialog(self, self.on_project_created)

    def on_project_created(self, path):
        self.refresh_projects()
        self.open_project(path)

    def open_project(self, path):
        self.destroy()
        self.on_open_project(path)

    def on_profile(self):
        messagebox.showinfo("LiveControl", "Registration is not available on this version")

    def on_connection(self):
        messagebox.showinfo("LiveControl", "Not available")

    def on_settings(self):
        SettingsDialog(self, self._images)

    def on_info(self):
        messagebox.showinfo("LiveControl", "LiveControl v1.0.0\nMade by StickBuug")