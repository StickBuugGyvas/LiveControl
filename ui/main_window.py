import sys
import os
import io
import json
import time
import base64
import threading
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk
from obswebsocket import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
ASSETS = os.path.join(BASE_DIR, "assets")

from core.config_manager import ConfigManager
from core.obs_controller import OBSController
from core.osc_listener import OSCListener

# ================== ЦВЕТА (серая палитра) ==================
BG_DARK = "#1e1e1e"        # фон окна
BG_HEADER = "#242424"      # верхняя полоса
BG_SIDEBAR = "#262626"     # боковая панель
BG_PANEL = "#2a2a2a"       # нижние панели
BG_PANEL_HEAD = "#343434"  # заголовки панелей
BG_INSET = "#202020"       # «утопленные» зоны (лог, микшер)
BG_STRIP = "#252a33"       # дорожка микшера
BG_BUTTON = "#2c2c2c"      # обычные кнопки
BG_ACCENT = "#4a4a4a"      # главные кнопки
BG_HOVER = "#3d3d3d"       # наведение
TEXT_MAIN = "#ececec"
TEXT_DIM = "#8c8c8c"
BORDER = "#444444"

SUCCESS = "#2ecc71"        # только индикаторы
WARNING = "#f39c12"        # ручной режим
LIVE_RED = "#b13a3a"       # Emergency и «В эфире»
LIVE_RED_HOVER = "#963030"
BTN_ACTIVE = "#5e5e5e"     # включено
BTN_SAVE = "#6b6b6b"
BTN_SAVE_HOVER = "#7b7b7b"
IDLE_GRAY = "#333333"

# Серый фон мультипросмотра, как в OBS
MV_BG = "#8c8c8c"
PROGRAM_COLOR = "#e0151b"   # красная рамка = в эфире
PREVIEW_COLOR = "#2ecc40"   # зелёная рамка = предпросмотр
CAM_COLUMNS = 5
MAX_TILES = 20

# Цвета для своих кнопок
BUTTON_COLORS = {
    "gray": ("Серая", "#3d3d3d", "#4d4d4d"),
    "dark": ("Тёмная", "#2c2c2c", "#3b3b3b"),
    "red": ("Красная", "#8f3030", "#a43a3a"),
    "orange": ("Оранжевая", "#a8690f", "#bd7a1a"),
    "green": ("Зелёная", "#2f6b45", "#3a7f55"),
    "blue": ("Синяя", "#33527f", "#3f6296"),
}

# Типы действий для своих кнопок
ACTION_TYPES = [
    ("scene", "Переключить сцену"),
    ("mute", "Заглушить аудиопоток"),
    ("unmute", "Включить звук аудиопотока"),
    ("toggle_mute", "Вкл/выкл звук аудиопотока"),
    ("volume", "Установить громкость аудиопотока"),
    ("source", "Показать / скрыть источник"),
    ("mute_all", "Заглушить всё"),
    ("unmute_all", "Вернуть звук (после «Заглушить всё»)"),
    ("emergency", "Emergency break"),
    ("stream_start", "Начать трансляцию"),
    ("stream_stop", "Остановить трансляцию"),
]
ACTION_LABELS = dict(ACTION_TYPES)

SOURCE_MODES = [("show", "Показать"), ("hide", "Скрыть"), ("toggle", "Переключить")]

ROW_ORDER = ["scene", "show", "hide", "ret", "ascene", "input", "db", "sscene", "source", "mode"]
FIELDS_FOR = {
    "scene": ["scene", "show", "hide", "ret"],
    "mute": ["ascene", "input"],
    "unmute": ["ascene", "input"],
    "toggle_mute": ["ascene", "input"],
    "volume": ["ascene", "input", "db"],
    "source": ["sscene", "source", "mode"],
}

COMBO_STYLE = dict(fg_color=BG_INSET, border_color=BORDER, button_color=BG_ACCENT,
                   button_hover_color=BG_HOVER, dropdown_fg_color=BG_PANEL,
                   dropdown_hover_color=BG_BUTTON, text_color=TEXT_MAIN, height=34)
ENTRY_STYLE = dict(fg_color=BG_INSET, border_color=BORDER, text_color=TEXT_MAIN, height=34)
OPTION_STYLE = dict(fg_color=BG_INSET, button_color=BG_ACCENT, button_hover_color=BG_HOVER,
                    dropdown_fg_color=BG_PANEL, dropdown_hover_color=BG_BUTTON,
                    text_color=TEXT_MAIN, height=34)


# ==================== вспомогательные ====================
def short(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def db_text(db):
    if db is None or db <= -99:
        return "-inf"
    return f"{db:.1f} dB"


def split_list(text):
    return [p.strip() for p in str(text).split(",") if p.strip()]


def parse_source_ref(text, default_scene):
    """«Источник» или «Сцена/Источник» -> (сцена, источник)."""
    if "/" in text:
        scene, source = text.split("/", 1)
        return scene.strip() or default_scene, source.strip()
    return default_scene, text.strip()


def make_menu(parent):
    return tk.Menu(parent, tearoff=0, bg=BG_PANEL, fg=TEXT_MAIN, activebackground=BG_ACCENT,
                   activeforeground="#ffffff", bd=0, relief="flat")


# ==========================================================
#   КОНФИГ ПРОЕКТА (projects/<имя>.json)
# ==========================================================
class ProjectConfig:
    """Тот же интерфейс, что у ConfigManager, но работает с файлом проекта."""

    def __init__(self, path):
        self.path = path
        self.config = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки проекта: {e}")
            self.config = {}

        self.config.setdefault("obs", {"host": "localhost", "port": 4455, "password": ""})
        self.config.setdefault("osc", {"listen_ip": "0.0.0.0", "listen_port": 3333})
        self.config.setdefault("custom_buttons", [])
        self.config.setdefault("manual_mode", True)

    def get(self, *keys, default=None):
        data = self.config
        for key in keys:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return default
        return data

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения проекта: {e}")
            return False


# ==========================================================
#   OBS
# ==========================================================
class ObsLink(OBSController):
    """OBSController + всё, что нужно приложению: сцены, звук, источники, трансляция."""

    def connect(self):
        ok = super().connect()
        if ok:
            self._lock = threading.RLock()
            raw_call = self.ws.call

            def locked_call(req):
                with self._lock:
                    return raw_call(req)

            # все запросы (в т.ч. из других потоков) идут по очереди
            self.ws.call = locked_call
        return ok

    def _call(self, req):
        """None — ошибка запроса, dict (возможно пустой) — успех."""
        resp = self.ws.call(req)
        if resp is None or not getattr(resp, "status", True):
            return None
        return getattr(resp, "datain", None) or {}

    # ---------- сцены ----------
    def program_scene(self):
        d = self._call(requests.GetCurrentProgramScene())
        if not d:
            return None
        return d.get("currentProgramSceneName") or d.get("sceneName")

    def preview_scene(self):
        """Работает только при включённом Studio Mode, иначе None."""
        try:
            d = self._call(requests.GetCurrentPreviewScene())
        except Exception:
            return None
        if not d:
            return None
        return d.get("currentPreviewSceneName") or d.get("sceneName")

    def scene_names(self):
        d = self._call(requests.GetSceneList())
        if d is None:
            return None
        return [s.get("sceneName") for s in d.get("scenes", []) if s.get("sceneName")]

    def set_program_scene(self, name):
        return self._call(requests.SetCurrentProgramScene(sceneName=name)) is not None

    def screenshot(self, name, width, height, quality=60):
        d = self._call(requests.GetSourceScreenshot(
            sourceName=name, imageFormat="jpg",
            imageWidth=width, imageHeight=height,
            imageCompressionQuality=quality))
        if not d:
            return None
        data = d.get("imageData")
        if not data:
            return None
        if "," in data:
            data = data.split(",", 1)[1]
        return base64.b64decode(data)

    # ---------- источники в сцене ----------
    def scene_items(self, scene, group=False):
        req = (requests.GetGroupSceneItemList(sceneName=scene) if group
               else requests.GetSceneItemList(sceneName=scene))
        d = self._call(req)
        return (d or {}).get("sceneItems", [])

    def scene_item_id(self, scene, source):
        d = self._call(requests.GetSceneItemId(sceneName=scene, sourceName=source))
        return d.get("sceneItemId") if d else None

    def set_item_enabled(self, scene, source, enabled=None):
        """enabled=None — переключить. Возвращает новое состояние или None при ошибке."""
        item_id = self.scene_item_id(scene, source)
        if item_id is None:
            return None
        if enabled is None:
            d = self._call(requests.GetSceneItemEnabled(sceneName=scene, sceneItemId=item_id))
            enabled = not bool(d.get("sceneItemEnabled")) if d else True
        ok = self._call(requests.SetSceneItemEnabled(
            sceneName=scene, sceneItemId=item_id, sceneItemEnabled=enabled))
        return enabled if ok is not None else None

    # ---------- звук ----------
    def audio_candidates(self, scene):
        """Источники сцены (включая вложенные сцены и группы), у которых может быть звук."""
        names = []
        seen = set()

        def walk(scene_name, is_group, depth):
            key = (scene_name, is_group)
            if depth > 3 or key in seen:
                return
            seen.add(key)
            for it in self.scene_items(scene_name, group=is_group):
                if not it.get("sceneItemEnabled", True):
                    continue
                name = it.get("sourceName")
                if not name:
                    continue
                if it.get("isGroup"):
                    walk(name, True, depth + 1)
                elif it.get("sourceType") == "OBS_SOURCE_TYPE_SCENE":
                    walk(name, False, depth + 1)
                elif it.get("inputKind") and name not in names:
                    names.append(name)

        walk(scene, False, 0)
        return names

    def special_inputs(self):
        d = self._call(requests.GetSpecialInputs()) or {}
        out = []
        for key in ("desktop1", "desktop2", "mic1", "mic2", "mic3", "mic4"):
            name = d.get(key)
            if name and name not in out:
                out.append(name)
        return out

    def input_state(self, name):
        """(muted, db) или None, если у источника нет звука."""
        m = self._call(requests.GetInputMute(inputName=name))
        if m is None:
            return None
        v = self._call(requests.GetInputVolume(inputName=name)) or {}
        db = v.get("inputVolumeDb")
        return bool(m.get("inputMuted")), (0.0 if db is None else float(db))

    def mixer_snapshot(self, scene):
        """Что сейчас в микшере: глобальные устройства + звук из сцены в эфире."""
        names = list(self.special_inputs())
        if scene:
            for n in self.audio_candidates(scene):
                if n not in names:
                    names.append(n)
        items = []
        for n in names:
            st = self.input_state(n)
            if st is None:
                continue
            items.append({"name": n, "muted": st[0], "db": st[1]})
        return items

    def all_audio_inputs(self):
        """[(имя, заглушен)] для всех входов OBS, у которых есть звук."""
        d = self._call(requests.GetInputList()) or {}
        out = []
        for inp in d.get("inputs", []):
            n = inp.get("inputName")
            if not n:
                continue
            st = self.input_state(n)
            if st is not None:
                out.append((n, st[0]))
        return out

    def set_input_mute(self, name, muted):
        return self._call(requests.SetInputMute(inputName=name, inputMuted=bool(muted))) is not None

    def toggle_input_mute(self, name):
        st = self.input_state(name)
        if st is None:
            return None
        new = not st[0]
        return new if self.set_input_mute(name, new) else None

    def set_input_volume_db(self, name, db):
        return self._call(requests.SetInputVolume(inputName=name, inputVolumeDb=float(db))) is not None

    # ---------- трансляция ----------
    def stream_active(self):
        d = self._call(requests.GetStreamStatus())
        if d is None:
            return None
        return bool(d.get("outputActive"))

    def start_stream(self):
        return self._call(requests.StartStream()) is not None

    def stop_stream(self):
        return self._call(requests.StopStream()) is not None


class ObsWorker(threading.Thread):
    """Фоновый поток: картинки сцен, список сцен, микшер, статус трансляции."""

    def __init__(self, obs):
        super().__init__(daemon=True)
        self.obs = obs
        self.latest = {}   # "program" / "preview" / "cam:<сцена>" -> jpeg bytes
        self.state = {
            "program": None, "preview": None, "scenes": [],
            "streaming": False, "mixer": [], "mixer_rev": 0,
        }
        self.running = True
        self.lost = False
        self.want_tiles = False   # нужны ли миниатюры (открыт мультипросмотр)

    def stop(self):
        self.running = False

    def _slow(self, prog):
        scenes = self.obs.scene_names()
        if scenes is not None:
            self.state["scenes"] = scenes
        streaming = self.obs.stream_active()
        if streaming is not None:
            self.state["streaming"] = streaming
        self.state["mixer"] = self.obs.mixer_snapshot(prog)
        self.state["mixer_rev"] += 1

    def run(self):
        idx = 0
        cycle = 0
        studio = True
        last_slow = 0.0
        last_prog = object()
        fails = 0
        while self.running and self.obs.connected:
            try:
                prog = self.obs.program_scene()
                if prog is None:
                    fails += 1
                    if fails >= 6:
                        self.lost = True
                        break
                    time.sleep(0.5)
                    continue
                fails = 0
                self.state["program"] = prog

                now = time.time()
                if prog != last_prog or now - last_slow > 1.2:
                    last_prog = prog
                    last_slow = now
                    self._slow(prog)

                img = self.obs.screenshot(prog, 800, 450, 55)
                if img:
                    self.latest["program"] = img

                if self.want_tiles:
                    if studio or cycle % 25 == 0:
                        prev = self.obs.preview_scene()
                        studio = prev is not None
                        self.state["preview"] = prev
                        if prev:
                            img = self.obs.screenshot(prev, 640, 360, 60)
                            if img:
                                self.latest["preview"] = img
                        else:
                            self.latest.pop("preview", None)

                    scenes = self.state["scenes"][:MAX_TILES]
                    for _ in range(3):
                        if not scenes:
                            break
                        name = scenes[idx % len(scenes)]
                        idx += 1
                        img = self.obs.screenshot(name, 320, 180, 50)
                        if img:
                            self.latest["cam:" + name] = img
            except Exception as e:
                print(f"[Worker] {e}")
                fails += 1
                if fails >= 6:
                    self.lost = True
                    break
                time.sleep(0.5)
            cycle += 1
            time.sleep(0.02 if self.want_tiles else 0.04)


# ==========================================================
#   РАМКА С КАРТИНКОЙ (мультипросмотр и окно эфира)
# ==========================================================
class Tile(tk.Canvas):
    """Рамка: картинка сцены + подпись + цветная обводка."""

    def __init__(self, master, title="", big=False, ph_size=11, ph_color="#555555"):
        super().__init__(master, bg="black", highlightthickness=0, bd=0)
        self.title = title
        self.big = big
        self.ph_size = ph_size
        self.ph_color = ph_color
        self.placeholder = ""
        self.border = None
        self._raw = None
        self._img = None
        self._photo = None
        self.bind("<Configure>", lambda e: self._redraw())

    def set_image(self, raw, placeholder=""):
        if raw is self._raw and placeholder == self.placeholder:
            return
        self._raw = raw
        self.placeholder = placeholder
        self._img = None
        if raw:
            try:
                self._img = Image.open(io.BytesIO(raw))
                self._img.load()
            except Exception:
                self._img = None
        self._redraw()

    def set_border(self, color):
        if color != self.border:
            self.border = color
            self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return

        if self._img is not None:
            iw, ih = self._img.size
            scale = min(w / iw, h / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            self._photo = ImageTk.PhotoImage(self._img.resize((nw, nh), Image.Resampling.BILINEAR))
            self.create_image(w // 2, h // 2, image=self._photo)
        elif self.placeholder:
            self.create_text(w // 2, h // 2, text=self.placeholder, fill=self.ph_color,
                             font=("Segoe UI", self.ph_size))

        if self.border:
            self.create_rectangle(2, 2, w - 2, h - 2, outline=self.border, width=4)

        if self.title:
            size = 14 if self.big else 10
            self.create_text(w // 2, h - (18 if self.big else 12), text=self.title,
                             fill="#c8c8c8", font=("Segoe UI", size, "bold"))


# ==========================================================
#   ДИАЛОГИ
# ==========================================================
class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, width, height):
        super().__init__(parent)
        self.title(title)
        try:
            height = min(height, max(360, self.winfo_screenheight() - 120))
        except Exception:
            pass
        self.geometry(f"{width}x{height}")
        self.minsize(width, min(height, 360))
        self.configure(fg_color=BG_DARK)
        self.transient(parent)
        self.after(100, self._grab)
        try:
            self.geometry(f"+{parent.winfo_rootx() + 40}+{parent.winfo_rooty() + 40}")
        except Exception:
            pass

    def _grab(self):
        try:
            self.grab_set()
        except Exception:
            pass


class OBSConnectDialog(BaseDialog):
    """Подключение к OBS (с кнопкой «Сохранить»)"""

    def __init__(self, parent, config, on_connect):
        super().__init__(parent, "Подключение к OBS", 420, 520)
        self.config = config
        self.on_connect = on_connect
        self.create_widgets()

    def create_widgets(self):
        # Кнопки упакованы ПЕРВЫМИ и прижаты к низу — их всегда видно
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=20, pady=(8, 18))

        ctk.CTkButton(buttons, text="Сохранить", height=42, font=("Segoe UI", 14, "bold"),
                      fg_color=BTN_SAVE, hover_color=BTN_SAVE_HOVER, text_color="#ffffff",
                      command=self.save_only).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(buttons, text="Подключить", height=42, font=("Segoe UI", 14, "bold"),
                      fg_color=BG_ACCENT, hover_color=BG_HOVER,
                      command=self.connect).pack(side="left", expand=True, fill="x", padx=(5, 0))

        ctk.CTkLabel(self, text="Подключение к OBS", font=("Segoe UI", 16, "bold"),
                     text_color=TEXT_MAIN).pack(pady=(16, 8))

        form = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=10)
        form.pack(fill="both", expand=True, padx=20, pady=5)

        def field(label, value, show=None):
            ctk.CTkLabel(form, text=label, font=("Segoe UI", 12), text_color=TEXT_DIM).pack(
                anchor="w", padx=15, pady=(12, 2))
            e = ctk.CTkEntry(form, fg_color=BG_INSET, border_color=BORDER, text_color=TEXT_MAIN,
                             height=36, **({"show": show} if show else {}))
            e.pack(fill="x", padx=15)
            e.insert(0, str(value))
            return e

        self.host_entry = field("Host", self.config.get("obs", "host", default="localhost"))
        self.port_entry = field("Port", self.config.get("obs", "port", default=4455))
        self.pass_entry = field("Password", self.config.get("obs", "password", default=""), show="•")

        self.show_pass = ctk.CTkCheckBox(
            form, text="Показать пароль", font=("Segoe UI", 12), text_color=TEXT_DIM,
            fg_color=BG_ACCENT, hover_color=BG_HOVER, border_color="#777777",
            command=self.toggle_password)
        self.show_pass.pack(anchor="w", padx=15, pady=(10, 12))

    def toggle_password(self):
        self.pass_entry.configure(show="" if self.show_pass.get() else "•")

    def _read_and_save(self):
        host = self.host_entry.get().strip() or "localhost"
        try:
            port = int(self.port_entry.get().strip() or "4455")
        except ValueError:
            port = 4455
        password = self.pass_entry.get()
        self.config.config.setdefault("obs", {})
        self.config.config["obs"].update({"host": host, "port": port, "password": password})
        self.config.save()
        return host, port, password

    def save_only(self):
        self._read_and_save()
        messagebox.showinfo("Сохранено", "Настройки OBS сохранены в проект.", parent=self)

    def connect(self):
        host, port, password = self._read_and_save()
        self.destroy()
        self.on_connect(host, port, password)


class EmergencyDialog(BaseDialog):
    """Что делает кнопка Emergency break"""

    ACTIONS = [("scene", "Переключить на сцену"),
               ("mute_all", "Заглушить всё"),
               ("scene_mute", "Сцена + заглушить всё")]

    def __init__(self, parent, app, current, on_save):
        super().__init__(parent, "Emergency break", 440, 360)
        self.on_save = on_save
        current = current or {}

        ctk.CTkButton(self, text="Сохранить", height=42, font=("Segoe UI", 14, "bold"),
                      fg_color=BTN_SAVE, hover_color=BTN_SAVE_HOVER, text_color="#ffffff",
                      command=self.save).pack(side="bottom", fill="x", padx=20, pady=(8, 18))

        ctk.CTkLabel(self, text="Настройка Emergency break", font=("Segoe UI", 16, "bold"),
                     text_color=TEXT_MAIN).pack(pady=(16, 4))
        ctk.CTkLabel(self, text="Что должно произойти при нажатии кнопки", font=("Segoe UI", 12),
                     text_color=TEXT_DIM).pack()

        form = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=10)
        form.pack(fill="both", expand=True, padx=20, pady=12)

        ctk.CTkLabel(form, text="Действие", font=("Segoe UI", 12), text_color=TEXT_DIM).pack(
            anchor="w", padx=15, pady=(14, 2))
        self.action_var = ctk.StringVar(value=dict(self.ACTIONS).get(current.get("action"), self.ACTIONS[0][1]))
        ctk.CTkOptionMenu(form, variable=self.action_var, values=[l for _, l in self.ACTIONS],
                          **OPTION_STYLE).pack(fill="x", padx=15)

        ctk.CTkLabel(form, text="Сцена (из OBS или впиши название)", font=("Segoe UI", 12),
                     text_color=TEXT_DIM).pack(anchor="w", padx=15, pady=(14, 2))
        self.scene_combo = ctk.CTkComboBox(form, values=app.scene_choices(), **COMBO_STYLE)
        self.scene_combo.pack(fill="x", padx=15)
        self.scene_combo.set(current.get("scene", ""))

    def save(self):
        label = self.action_var.get()
        action = next((k for k, l in self.ACTIONS if l == label), "scene")
        scene = self.scene_combo.get().strip()
        if action in ("scene", "scene_mute") and not scene:
            messagebox.showwarning("Emergency break", "Укажи сцену", parent=self)
            return
        self.destroy()
        self.on_save({"action": action, "scene": scene})


class SettingsDialog(BaseDialog):
    """Настройки проекта: Emergency break, подключение OBS, LiveEdit"""

    def __init__(self, parent, app):
        super().__init__(parent, "Настройки", 480, 480)
        self.app = app

        ctk.CTkButton(self, text="Сохранить", height=42, font=("Segoe UI", 14, "bold"),
                      fg_color=BTN_SAVE, hover_color=BTN_SAVE_HOVER, text_color="#ffffff",
                      command=self.save).pack(side="bottom", fill="x", padx=20, pady=(8, 18))

        ctk.CTkLabel(self, text="Настройки", font=("Segoe UI", 16, "bold"),
                     text_color=TEXT_MAIN).pack(pady=(16, 8))

        # Emergency
        box = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=10)
        box.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(box, text="Emergency break", font=("Segoe UI", 13, "bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=14, pady=(10, 0))
        self.em_label = ctk.CTkLabel(box, text=app.emergency_text(), font=("Segoe UI", 12),
                                     text_color=TEXT_DIM, anchor="w", justify="left")
        self.em_label.pack(anchor="w", padx=14, pady=(2, 6))
        ctk.CTkButton(box, text="Изменить…", height=32, fg_color=BG_BUTTON, hover_color=BG_HOVER,
                      command=self.edit_emergency).pack(anchor="w", padx=14, pady=(0, 12))

        # OBS
        box = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=10)
        box.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(box, text="Подключение к OBS", font=("Segoe UI", 13, "bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkButton(box, text="Настроить подключение…", height=32, fg_color=BG_BUTTON,
                      hover_color=BG_HOVER, command=self.open_obs).pack(anchor="w", padx=14, pady=(0, 12))

        # LiveEdit
        box = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=10)
        box.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(box, text="LiveEdit (OSC)", font=("Segoe UI", 13, "bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=14, pady=(10, 4))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 4))
        ctk.CTkLabel(row, text="Слушать на IP", font=("Segoe UI", 12), text_color=TEXT_DIM).pack(side="left")
        self.ip_entry = ctk.CTkEntry(row, width=120, **ENTRY_STYLE)
        self.ip_entry.pack(side="left", padx=(8, 14))
        self.ip_entry.insert(0, str(app.config.get("osc", "listen_ip", default="0.0.0.0")))
        ctk.CTkLabel(row, text="Порт", font=("Segoe UI", 12), text_color=TEXT_DIM).pack(side="left")
        self.port_entry = ctk.CTkEntry(row, width=80, **ENTRY_STYLE)
        self.port_entry.pack(side="left", padx=8)
        self.port_entry.insert(0, str(app.config.get("osc", "listen_port", default=3333)))
        ctk.CTkLabel(box, text="Новый порт применится после повторного включения LiveEdit.",
                     font=("Segoe UI", 11), text_color="#707070").pack(anchor="w", padx=14, pady=(0, 10))

    def edit_emergency(self):
        self.app.open_emergency_settings(parent=self, after=self._refresh_em)

    def _refresh_em(self):
        self.em_label.configure(text=self.app.emergency_text())

    def open_obs(self):
        self.app.open_obs_connect()

    def save(self):
        ip = self.ip_entry.get().strip() or "0.0.0.0"
        try:
            port = int(self.port_entry.get().strip() or "3333")
        except ValueError:
            messagebox.showwarning("Настройки", "Порт должен быть числом", parent=self)
            return
        self.app.config.config.setdefault("osc", {}).update({"listen_ip": ip, "listen_port": port})
        self.app.config.save()
        self.app.control.log("Настройки сохранены")
        self.destroy()


class AddButtonDialog(BaseDialog):
    """Создание / редактирование своей кнопки"""

    def __init__(self, parent, app, on_save, data=None):
        super().__init__(parent, "Кнопка", 540, 720)
        self.app = app
        self.on_save = on_save
        self.editing = data is not None
        self.rows = {}
        self.w = {}

        self.scene_values = app.scene_choices()
        connected = app.obs_connected()

        # ---- низ: сохранить + шаблоны (упакованы первыми) ----
        ctk.CTkButton(self, text="Сохранить", height=44, font=("Segoe UI", 14, "bold"),
                      fg_color=BTN_SAVE, hover_color=BTN_SAVE_HOVER, text_color="#ffffff",
                      command=self.save).pack(side="bottom", fill="x", padx=20, pady=(6, 16))

        tpl = ctk.CTkFrame(self, fg_color="transparent")
        tpl.pack(side="bottom", fill="x", padx=20, pady=(6, 0))
        ctk.CTkButton(tpl, text="Загрузить кнопки из файла", height=32, fg_color=BG_BUTTON,
                      hover_color=BG_HOVER, font=("Segoe UI", 12),
                      command=self.load_file).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(tpl, text="Сохранить все кнопки в файл", height=32, fg_color=BG_BUTTON,
                      hover_color=BG_HOVER, font=("Segoe UI", 12),
                      command=self.save_file).pack(side="left", expand=True, fill="x", padx=(4, 0))

        ctk.CTkLabel(self, text="Изменить кнопку" if self.editing else "Новая кнопка",
                     font=("Segoe UI", 16, "bold"), text_color=TEXT_MAIN).pack(pady=(14, 2))
        if not connected:
            ctk.CTkLabel(self, text="OBS не подключен — названия сцен и источников вводи вручную",
                         font=("Segoe UI", 11), text_color=WARNING).pack()

        self.form = ctk.CTkScrollableFrame(self, fg_color=BG_PANEL, corner_radius=10)
        self.form.pack(fill="both", expand=True, padx=20, pady=8)

        # ---- общие поля ----
        self.name_entry = self._common_row("Название кнопки",
                                           lambda p: ctk.CTkEntry(p, placeholder_text="Например: Заставка",
                                                                  **ENTRY_STYLE))
        self.color_var = ctk.StringVar(value=BUTTON_COLORS["gray"][0])
        self._common_row("Цвет", lambda p: ctk.CTkOptionMenu(
            p, variable=self.color_var, values=[v[0] for v in BUTTON_COLORS.values()], **OPTION_STYLE))
        self.type_var = ctk.StringVar(value=ACTION_TYPES[0][1])
        self._common_row("Тип действия", lambda p: ctk.CTkOptionMenu(
            p, variable=self.type_var, values=[l for _, l in ACTION_TYPES],
            command=lambda _v: self.update_rows(), **OPTION_STYLE))

        # ---- поля, зависящие от типа ----
        self._row("scene", "Сцена", lambda p: ctk.CTkComboBox(p, values=self.scene_values, **COMBO_STYLE))
        self._row("show", "Включить источники при нажатии",
                  lambda p: ctk.CTkEntry(p, **ENTRY_STYLE),
                  "Через запятую. Источник из другой сцены: Сцена/Источник")
        self._row("hide", "Выключить источники при нажатии",
                  lambda p: ctk.CTkEntry(p, **ENTRY_STYLE),
                  "Через запятую. Источник из другой сцены: Сцена/Источник")
        self._row("ret", "Вернуться на прошлую сцену через, сек",
                  lambda p: ctk.CTkEntry(p, **ENTRY_STYLE), "0 — не возвращаться")
        self._row("ascene", "Сцена, где находится аудиопоток",
                  lambda p: ctk.CTkComboBox(p, values=self.scene_values,
                                            command=lambda _v: self.refresh_audio_values(), **COMBO_STYLE),
                  "Можно не указывать — тогда в списке все аудиопотоки OBS")
        self._row("input", "Аудиопоток", lambda p: ctk.CTkComboBox(p, values=[], **COMBO_STYLE))
        self._row("db", "Громкость, dB (от -60 до 0)", lambda p: ctk.CTkEntry(p, **ENTRY_STYLE))
        self._row("sscene", "Сцена с источником",
                  lambda p: ctk.CTkComboBox(p, values=self.scene_values,
                                            command=lambda _v: self.refresh_source_values(), **COMBO_STYLE))
        self._row("source", "Источник", lambda p: ctk.CTkComboBox(p, values=[], **COMBO_STYLE))
        self.mode_var = ctk.StringVar(value=SOURCE_MODES[0][1])
        self._row("mode", "Действие с источником", lambda p: ctk.CTkOptionMenu(
            p, variable=self.mode_var, values=[l for _, l in SOURCE_MODES], **OPTION_STYLE))

        self.w["ret"].insert(0, "0")
        self.w["db"].insert(0, "0")
        self.refresh_audio_values()

        if data:
            self.load(data)
        self.update_rows()

    # ---------- построение ----------
    def _common_row(self, label, factory):
        row = ctk.CTkFrame(self.form, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 12), text_color=TEXT_DIM, anchor="w").pack(
            fill="x", padx=4)
        w = factory(row)
        w.pack(fill="x", padx=4, pady=(2, 0))
        return w

    def _row(self, key, label, factory, hint=None):
        row = ctk.CTkFrame(self.form, fg_color="transparent")
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 12), text_color=TEXT_DIM, anchor="w").pack(
            fill="x", padx=4)
        w = factory(row)
        w.pack(fill="x", padx=4, pady=(2, 0))
        if hint:
            ctk.CTkLabel(row, text=hint, font=("Segoe UI", 10), text_color="#707070",
                         anchor="w", justify="left", wraplength=420).pack(fill="x", padx=4)
        self.rows[key] = row
        self.w[key] = w

    def type_key(self):
        label = self.type_var.get()
        return next((k for k, l in ACTION_TYPES if l == label), "scene")

    def color_key(self):
        label = self.color_var.get()
        return next((k for k, v in BUTTON_COLORS.items() if v[0] == label), "gray")

    def update_rows(self):
        for key in ROW_ORDER:
            self.rows[key].pack_forget()
        wanted = FIELDS_FOR.get(self.type_key(), [])
        for key in ROW_ORDER:
            if key in wanted:
                self.rows[key].pack(fill="x", pady=(8, 0))

    def refresh_audio_values(self):
        scene = self.w["ascene"].get().strip()
        self.w["input"].configure(values=self.app.audio_choices(scene))

    def refresh_source_values(self):
        scene = self.w["sscene"].get().strip()
        self.w["source"].configure(values=self.app.source_choices(scene))

    # ---------- загрузка / сбор ----------
    def load(self, d):
        t = d.get("type", "scene")
        legacy = d.get("value", "")
        self.name_entry.insert(0, d.get("name", ""))
        self.color_var.set(BUTTON_COLORS.get(d.get("color", "gray"), BUTTON_COLORS["gray"])[0])
        self.type_var.set(ACTION_LABELS.get(t, ACTION_TYPES[0][1]))
        if t == "scene":
            self.w["scene"].set(d.get("scene") or legacy)
            self.w["show"].insert(0, ", ".join(d.get("show_sources", [])))
            self.w["hide"].insert(0, ", ".join(d.get("hide_sources", [])))
            self.w["ret"].delete(0, "end")
            self.w["ret"].insert(0, str(d.get("return_after", 0)))
        elif t in ("mute", "unmute", "toggle_mute", "volume"):
            self.w["ascene"].set(d.get("scene", ""))
            self.refresh_audio_values()
            self.w["input"].set(d.get("input") or legacy)
            if t == "volume":
                self.w["db"].delete(0, "end")
                self.w["db"].insert(0, str(d.get("db", 0)))
        elif t == "source":
            self.w["sscene"].set(d.get("scene", ""))
            self.refresh_source_values()
            self.w["source"].set(d.get("source", ""))
            self.mode_var.set(dict(SOURCE_MODES).get(d.get("mode"), SOURCE_MODES[0][1]))

    def _warn(self, text):
        messagebox.showwarning("Кнопка", text, parent=self)
        return None

    def collect(self):
        t = self.type_key()
        name = self.name_entry.get().strip()
        if not name:
            return self._warn("Впиши название кнопки")
        d = {"name": name, "type": t, "color": self.color_key()}

        if t == "scene":
            scene = self.w["scene"].get().strip()
            if not scene:
                return self._warn("Укажи сцену")
            try:
                ret = float(self.w["ret"].get().replace(",", ".") or 0)
            except ValueError:
                return self._warn("«Вернуться через» должно быть числом")
            d.update(scene=scene, show_sources=split_list(self.w["show"].get()),
                     hide_sources=split_list(self.w["hide"].get()), return_after=max(0.0, ret))
        elif t in ("mute", "unmute", "toggle_mute", "volume"):
            inp = self.w["input"].get().strip()
            if not inp:
                return self._warn("Укажи аудиопоток")
            d.update(input=inp, scene=self.w["ascene"].get().strip())
            if t == "volume":
                try:
                    db = float(self.w["db"].get().replace(",", ".") or 0)
                except ValueError:
                    return self._warn("Громкость должна быть числом (dB)")
                d["db"] = max(-60.0, min(0.0, db))
        elif t == "source":
            scene = self.w["sscene"].get().strip()
            source = self.w["source"].get().strip()
            if not scene or not source:
                return self._warn("Укажи сцену и источник")
            mode = next((k for k, l in SOURCE_MODES if l == self.mode_var.get()), "show")
            d.update(scene=scene, source=source, mode=mode)
        return d

    def save(self):
        d = self.collect()
        if d is None:
            return
        self.destroy()
        self.on_save(d)

    def load_file(self):
        self.app.load_template(parent=self)
        self.destroy()

    def save_file(self):
        self.app.save_template(parent=self)


# ==========================================================
#   МИКШЕР ЗВУКА
# ==========================================================
class MixerView:
    """Дорожки звука: громкость, mute, меню. Данные берутся из OBS."""

    def __init__(self, parent, app):
        self.app = app
        self.order = []
        self.strips = {}
        self._touch = {}
        self._after = {}

        self.scroll = ctk.CTkScrollableFrame(
            parent, orientation="horizontal", fg_color=BG_INSET, corner_radius=6,
            scrollbar_button_color="#555555", scrollbar_button_hover_color="#6a6a6a")
        self.scroll.pack(fill="both", expand=True, padx=6, pady=6)
        self.msg = None

    def _clear(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self.strips = {}
        self.order = []
        self.msg = None

    def show_message(self, text):
        self._clear()
        self.msg = ctk.CTkLabel(self.scroll, text=text, font=("Segoe UI", 12), text_color=TEXT_DIM,
                                wraplength=300)
        self.msg.pack(padx=20, pady=40)

    def update(self, items):
        if not items:
            if self.msg is None or self.order:
                self.show_message("На этой сцене нету аудиопотока")
            return
        names = [i["name"] for i in items]
        if names != self.order:
            self._clear()
            self.order = names
            for it in items:
                self._build_strip(it)
        for it in items:
            self._refresh_strip(it)

    # ---------- одна дорожка ----------
    def _build_strip(self, it):
        name = it["name"]
        f = ctk.CTkFrame(self.scroll, fg_color=BG_STRIP, corner_radius=4, width=84, height=142)
        f.pack(side="left", padx=3, pady=2)
        f.pack_propagate(False)

        ctk.CTkLabel(f, text=short(name, 11), font=("Segoe UI", 10, "bold"),
                     text_color=TEXT_MAIN).pack(pady=(4, 0))
        db_lbl = ctk.CTkLabel(f, text=db_text(it["db"]), font=("Segoe UI", 10), text_color=TEXT_DIM)
        db_lbl.pack()

        slider = ctk.CTkSlider(
            f, orientation="vertical", from_=-60, to=0, number_of_steps=120, width=14, height=64,
            fg_color="#444444", progress_color="#8a8a8a", button_color="#d0d0d0",
            button_hover_color="#ffffff",
            command=lambda v, n=name: self._on_slide(n, v))
        slider.pack(pady=(2, 2))
        slider.set(max(-60, min(0, it["db"])))

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(pady=(0, 3))
        mute_btn = ctk.CTkButton(row, text="♪", width=30, height=22, font=("Segoe UI", 12),
                                 fg_color="#3a3f4a", hover_color="#4a505c",
                                 command=lambda n=name: self._toggle_mute(n))
        mute_btn.pack(side="left", padx=(0, 3))
        ctk.CTkButton(row, text="⋮", width=24, height=22, font=("Segoe UI", 12, "bold"),
                      fg_color="#3a3f4a", hover_color="#4a505c",
                      command=lambda n=name: self._menu(n)).pack(side="left")

        self.strips[name] = {"slider": slider, "db": db_lbl, "mute": mute_btn,
                             "muted": it["muted"], "menu_anchor": f}
        self._paint_mute(name, it["muted"])

    def _paint_mute(self, name, muted):
        s = self.strips.get(name)
        if not s:
            return
        s["muted"] = muted
        if muted:
            s["mute"].configure(text="✖", fg_color="#7a2b2b", hover_color="#8f3535")
        else:
            s["mute"].configure(text="♪", fg_color="#3a3f4a", hover_color="#4a505c")

    def _refresh_strip(self, it):
        name = it["name"]
        s = self.strips.get(name)
        if not s:
            return
        if time.time() - self._touch.get(name, 0) < 2.0:   # пользователь только что крутил
            return
        s["slider"].set(max(-60, min(0, it["db"])))
        s["db"].configure(text=db_text(it["db"]))
        if s["muted"] != it["muted"]:
            self._paint_mute(name, it["muted"])

    # ---------- действия ----------
    def _on_slide(self, name, value):
        self._touch[name] = time.time()
        s = self.strips.get(name)
        if s:
            s["db"].configure(text=db_text(value))
        old = self._after.get(name)
        if old:
            try:
                self.scroll.after_cancel(old)
            except Exception:
                pass
        self._after[name] = self.scroll.after(70, lambda: self.app.set_input_volume(name, value))

    def _toggle_mute(self, name):
        s = self.strips.get(name)
        if not s:
            return
        self._touch[name] = time.time()
        new = not s["muted"]
        if self.app.set_input_mute(name, new):
            self._paint_mute(name, new)

    def _menu(self, name):
        m = make_menu(self.scroll)
        for label, db in (("0 dB", 0.0), ("-10 dB", -10.0), ("-20 dB", -20.0), ("Минимум (-inf)", -100.0)):
            m.add_command(label=label, command=lambda d=db, n=name: self._set_db(n, d))
        s = self.strips.get(name)
        try:
            anchor = s["mute"]
            m.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + 24)
        finally:
            m.grab_release()

    def _set_db(self, name, db):
        self._touch[name] = time.time()
        s = self.strips.get(name)
        if s:
            s["slider"].set(max(-60, db))
            s["db"].configure(text=db_text(db))
        self.app.set_input_volume(name, db)


# ==========================================================
#   «МОИ КНОПКИ»
# ==========================================================
class ButtonsView:
    def __init__(self, parent, app):
        self.app = app
        self.holder = ctk.CTkFrame(parent, fg_color="transparent")
        self.holder.pack(fill="both", expand=True)
        self.scroll = None
        self.empty_btn = None

    def refresh(self, buttons):
        for w in self.holder.winfo_children():
            w.destroy()
        self.scroll = None
        self.empty_btn = None

        if not buttons:
            self.empty_btn = ctk.CTkButton(
                self.holder, text="Добавить", width=190, height=40, font=("Segoe UI", 14),
                fg_color=BTN_SAVE, hover_color=BTN_SAVE_HOVER, text_color="#ffffff",
                command=self.app.open_add_button)
            self.empty_btn.place(relx=0.5, rely=0.5, anchor="center")
            return

        self.scroll = ctk.CTkScrollableFrame(
            self.holder, fg_color="transparent",
            scrollbar_button_color="#555555", scrollbar_button_hover_color="#6a6a6a")
        self.scroll.pack(fill="both", expand=True, padx=4, pady=4)
        self.scroll.grid_columnconfigure(0, weight=1, uniform="b")
        self.scroll.grid_columnconfigure(1, weight=1, uniform="b")

        for i, data in enumerate(buttons):
            color = BUTTON_COLORS.get(data.get("color", "gray"), BUTTON_COLORS["gray"])
            btn = ctk.CTkButton(
                self.scroll, text=short(data.get("name", "?"), 16), height=36, font=("Segoe UI", 12),
                fg_color=color[1], hover_color=color[2], text_color=TEXT_MAIN,
                command=lambda d=data: self.app.execute_custom_button(d))
            btn.grid(row=i // 2, column=i % 2, padx=3, pady=3, sticky="ew")
            btn.bind("<Button-3>", lambda e, idx=i: self._context(e, idx))

    def _context(self, event, idx):
        m = make_menu(self.holder)
        m.add_command(label="Изменить…", command=lambda: self.app.open_add_button(edit_index=idx))
        m.add_command(label="Дублировать", command=lambda: self.app.duplicate_button(idx))
        m.add_separator()
        m.add_command(label="Удалить", command=lambda: self.app.remove_button(idx))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()


# ==========================================================
#   ОКНО УПРАВЛЕНИЯ (главное)
# ==========================================================
def make_panel(parent, title):
    outer = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=4)
    head = ctk.CTkFrame(outer, fg_color=BG_PANEL_HEAD, corner_radius=4, height=28)
    head.pack(fill="x")
    head.pack_propagate(False)
    ctk.CTkLabel(head, text=title, font=("Segoe UI", 15), text_color=TEXT_MAIN).pack(side="left", padx=7)
    body = ctk.CTkFrame(outer, fg_color="transparent")
    body.pack(fill="both", expand=True)
    return outer, body, head


class ControlWindow(ctk.CTk):
    """Главное окно: кнопки управления, окно эфира, микшер, лог, свои кнопки"""

    LEFT_W = 263

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._icons = []

        self.title("ShowControl")
        self.configure(fg_color=BG_DARK)
        ctk.set_appearance_mode("dark")

        w, h = 1264, 880
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(w, sw - 40), min(h, sh - 80)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")
        self.minsize(min(1100, w), min(760, h))

        self.create_widgets()

    # ---------- построение ----------
    def create_widgets(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=BG_HEADER, height=58, corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.pack_propagate(False)
        self.title_label = ctk.CTkLabel(header, text="ShowControl", font=("Segoe UI", 24),
                                        text_color=TEXT_MAIN)
        self.title_label.pack(side="left", padx=12)

        self.create_sidebar()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=1, sticky="nsew", padx=(13, 13), pady=(26, 10))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.create_top(content)
        self.create_bottom(content)

    def _icon(self, parent, names, cmd, pady=0):
        for name in names:
            path = os.path.join(ASSETS, name)
            if os.path.exists(path):
                try:
                    img = Image.open(path).convert("RGBA").resize((20, 20), Image.Resampling.LANCZOS)
                    photo = ctk.CTkImage(light_image=img, dark_image=img, size=(20, 20))
                    self._icons.append(photo)
                    ctk.CTkButton(parent, image=photo, text="", width=30, height=30,
                                  fg_color="transparent", hover_color="#333333",
                                  command=cmd).pack(pady=pady)
                    return
                except Exception as e:
                    print("icon error", e)
        ctk.CTkButton(parent, text="•", width=30, height=30, fg_color="transparent",
                      hover_color="#333333", command=cmd).pack(pady=pady)

    def create_sidebar(self):
        sb = ctk.CTkFrame(self, width=40, fg_color=BG_SIDEBAR, corner_radius=0)
        sb.grid(row=1, column=0, sticky="ns")
        sb.pack_propagate(False)
        self._icon(sb, ["personicon.png"], self.app.on_profile, (12, 2))
        self._icon(sb, ["connectionicon.png"], self.app.open_obs_connect, 2)
        self._icon(sb, ["databaseicon.png", "dbicon.png", "infoicon.png"], self.app.open_settings, 2)
        bottom = ctk.CTkFrame(sb, fg_color="transparent")
        bottom.pack(side="bottom", pady=10)
        self._icon(bottom, ["infoicon.png"], self.app.on_info)

    def _lbtn(self, parent, text, command, fg=BG_BUTTON, hover=BG_HOVER, text_color=TEXT_MAIN):
        b = ctk.CTkButton(parent, text=text, width=self.LEFT_W, height=40, corner_radius=6,
                          font=("Segoe UI", 14), fg_color=fg, hover_color=hover,
                          text_color=text_color, command=command)
        b.pack(pady=(0, 9))
        return b

    def create_top(self, content):
        top = ctk.CTkFrame(content, fg_color="transparent")
        top.grid(row=0, column=0, sticky="nsew")
        top.grid_columnconfigure(0, weight=0)
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(2, weight=3, minsize=380)
        top.grid_rowconfigure(0, weight=1)

        # ----- левая колонка кнопок -----
        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw")

        self.mode_btn = self._lbtn(left, "Режим: Ручной", self.app.toggle_manual_mode,
                                   fg=WARNING, hover="#d9870c", text_color="#ffffff")
        self.emergency_btn = self._lbtn(left, "Emergency break", self.app.trigger_emergency,
                                        fg=LIVE_RED, hover=LIVE_RED_HOVER)
        self.mute_all_btn = self._lbtn(left, "Заглушить всё", self.app.toggle_mute_all)
        self.obs_btn = self._lbtn(left, "OBS не подключен", self.app.open_obs_connect)
        self.liveedit_btn = self._lbtn(left, "LiveEdit: Выкл", self.app.toggle_liveedit)
        self.scenes_btn = self._lbtn(left, "Сцены/Камеры", self.app.show_scenes)
        self.multiview_btn = self._lbtn(left, "Мультипросмотр", self.app.show_multiview)

        # ----- середина: пояснение для авто-режима -----
        self.auto_label = ctk.CTkLabel(top, text="", anchor="w", justify="left", wraplength=230,
                                       font=("Segoe UI", 13), text_color=TEXT_DIM)
        self.auto_label.grid(row=0, column=1, sticky="nw", padx=(20, 10), pady=(10, 0))

        # ----- справа: окно эфира + «В эфире» -----
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        self.program_tile = Tile(right, "", ph_size=20, ph_color="#bdbdbd")
        self.program_tile.grid(row=0, column=0, sticky="nsew")

        self.live_label = ctk.CTkLabel(right, text="Простаивает", width=245, height=40, corner_radius=6,
                                       font=("Segoe UI", 22), text_color=TEXT_MAIN, fg_color=IDLE_GRAY)
        self.live_label.grid(row=1, column=0, sticky="e", pady=(10, 0))

    def create_bottom(self, content):
        bottom = ctk.CTkFrame(content, fg_color="transparent", height=215)
        bottom.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        bottom.grid_propagate(False)
        for col, weight in enumerate((2, 4, 4, 2)):
            bottom.grid_columnconfigure(col, weight=weight, uniform="panels")
        bottom.grid_rowconfigure(0, weight=1)

        # Лог
        panel, body, _ = make_panel(bottom, "Лог")
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.log_text = ctk.CTkTextbox(body, font=("Consolas", 10), fg_color=BG_INSET, text_color=TEXT_MAIN,
                                       corner_radius=6, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

        # Микшер звука
        panel, body, _ = make_panel(bottom, "Микшер звука")
        panel.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        self.mixer = MixerView(body, self.app)
        self.mixer.show_message("OBS не подключен")

        # Мои кнопки
        panel, body, head = make_panel(bottom, "Мои кнопки")
        panel.grid(row=0, column=2, sticky="nsew", padx=(0, 8))
        ctk.CTkButton(head, text="+", width=24, height=20, font=("Segoe UI", 14, "bold"),
                      fg_color=BG_ACCENT, hover_color=BG_HOVER, corner_radius=4,
                      command=self.app.open_add_button).pack(side="right", padx=5)
        self.buttons_view = ButtonsView(body, self.app)

        # Управление эфиром
        panel, body, _ = make_panel(bottom, "Управление эфиром")
        panel.grid(row=0, column=3, sticky="nsew")
        self.stream_btn = ctk.CTkButton(body, text="Начать трансляцию", height=30, font=("Segoe UI", 13),
                                        fg_color=BG_PANEL_HEAD, hover_color=BG_ACCENT, corner_radius=4,
                                        command=self.app.toggle_stream)
        self.stream_btn.pack(fill="x", padx=6, pady=(8, 3))
        ctk.CTkButton(body, text="Настройки", height=30, font=("Segoe UI", 13),
                      fg_color=BG_PANEL_HEAD, hover_color=BG_ACCENT, corner_radius=4,
                      command=self.app.open_settings).pack(fill="x", padx=6, pady=3)

    # ---------- методы интерфейса ----------
    def log(self, msg: str):
        self.log_text.insert("end", f"[{now_str()}] {msg}\n")
        self.log_text.see("end")

    def set_project_name(self, name):
        self.title(f"ShowControl — {name}")

    def set_obs_status(self, connected: bool):
        if connected:
            self.obs_btn.configure(text="OBS подключен", fg_color=BTN_ACTIVE)
        else:
            self.obs_btn.configure(text="OBS не подключен", fg_color=BG_BUTTON)

    def set_liveedit_status(self, active: bool):
        if active:
            self.liveedit_btn.configure(text="LiveEdit: Вкл", fg_color=BTN_ACTIVE)
        else:
            self.liveedit_btn.configure(text="LiveEdit: Выкл", fg_color=BG_BUTTON)

    def set_mode(self, manual: bool):
        if manual:
            self.mode_btn.configure(text="Режим: Ручной", fg_color=WARNING, hover_color="#d9870c")
        else:
            self.mode_btn.configure(text="Режим: Авто", fg_color=BG_ACCENT, hover_color=BG_HOVER)

    def set_auto_note(self, text):
        self.auto_label.configure(text=text)

    def set_mute_all_state(self, muted: bool):
        if muted:
            self.mute_all_btn.configure(text="Вернуть звук", fg_color=BTN_ACTIVE)
        else:
            self.mute_all_btn.configure(text="Заглушить всё", fg_color=BG_BUTTON)

    def set_live(self, live: bool):
        if live:
            self.live_label.configure(text="В эфире", fg_color=LIVE_RED)
        else:
            self.live_label.configure(text="Простаивает", fg_color=IDLE_GRAY)

    def set_stream_btn(self, streaming: bool):
        if streaming:
            self.stream_btn.configure(text="Остановить трансляцию", fg_color="#7a2b2b", hover_color="#8f3535")
        else:
            self.stream_btn.configure(text="Начать трансляцию", fg_color=BG_PANEL_HEAD, hover_color=BG_ACCENT)

    def show_program(self, raw, placeholder):
        self.program_tile.set_image(raw, placeholder)

    def refresh_custom_buttons(self, buttons: list):
        self.buttons_view.refresh(buttons)


# ==========================================================
#   МУЛЬТИПРОСМОТР (как в OBS: рамки с живыми сценами)
# ==========================================================
class MultiviewWindow(ctk.CTkToplevel):
    """Предпросмотр + Передача + рамки всех сцен OBS (названия как в OBS)"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.title("Мультипросмотр")
        self.geometry("1100x640+20+20")
        self.minsize(640, 400)
        self.configure(fg_color=MV_BG)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.scenes = None
        self.cam_tiles = {}

        self.wrap = tk.Frame(self, bg=MV_BG)
        self.wrap.pack(fill="both", expand=True, padx=4, pady=4)
        for c in range(CAM_COLUMNS * 2):
            self.wrap.grid_columnconfigure(c, weight=1, uniform="mv")

        self.preview_tile = Tile(self.wrap, "Предпросмотр", big=True)
        self.preview_tile.grid(row=0, column=0, columnspan=CAM_COLUMNS, sticky="nsew", padx=3, pady=3)
        self.program_tile = Tile(self.wrap, "Передача", big=True)
        self.program_tile.grid(row=0, column=CAM_COLUMNS, columnspan=CAM_COLUMNS, sticky="nsew", padx=3, pady=3)
        self.wrap.grid_rowconfigure(0, weight=5)

        self.build_tiles([])

    def close(self):
        self.app.multiview = None
        self.destroy()

    def build_tiles(self, scenes):
        for tile in self.cam_tiles.values():
            tile.destroy()
        self.cam_tiles = {}
        self.scenes = list(scenes)

        for r in range(1, 12):
            self.wrap.grid_rowconfigure(r, weight=0)
        rows = max(1, (len(scenes) + CAM_COLUMNS - 1) // CAM_COLUMNS)
        for r in range(rows):
            self.wrap.grid_rowconfigure(1 + r, weight=2)

        for i, name in enumerate(scenes):
            tile = Tile(self.wrap, short(name, 22))
            tile.grid(row=1 + i // CAM_COLUMNS, column=(i % CAM_COLUMNS) * 2, columnspan=2,
                      sticky="nsew", padx=3, pady=3)
            self.cam_tiles[name] = tile

    def apply(self, latest, state, connected):
        scenes = list(state.get("scenes") or [])[:MAX_TILES] if connected else []
        if scenes != self.scenes:
            self.build_tiles(scenes)

        program = state.get("program") if connected else None
        preview = state.get("preview") if connected else None

        if not connected:
            self.program_tile.set_image(None, "OBS не подключен")
            self.preview_tile.set_image(None, "OBS не подключен")
        else:
            self.program_tile.set_image(latest.get("program"), "нет сигнала")
            if preview:
                self.preview_tile.set_image(latest.get("preview"), "нет сигнала")
            else:
                self.preview_tile.set_image(None, "Studio Mode выключен")

        for name, tile in self.cam_tiles.items():
            tile.set_image(latest.get("cam:" + name))
            if name == program:
                tile.set_border(PROGRAM_COLOR)
            elif name == preview:
                tile.set_border(PREVIEW_COLOR)
            else:
                tile.set_border(None)


# ==========================================================
#   ОКНО «СЦЕНЫ / КАМЕРЫ» (названия из OBS)
# ==========================================================
class ScenesWindow(ctk.CTkToplevel):
    COLS = 3

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.buttons = {}
        self._shown = None

        self.title("Сцены / Камеры")
        self.geometry("470x380")
        self.minsize(380, 240)
        self.configure(fg_color=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.live_label = ctk.CTkLabel(self, text="В эфире: —", font=("Segoe UI", 13, "bold"),
                                       text_color=TEXT_MAIN)
        self.live_label.pack(pady=(12, 6))

        self.body = ctk.CTkScrollableFrame(self, fg_color=BG_PANEL, corner_radius=8,
                                           scrollbar_button_color="#555555",
                                           scrollbar_button_hover_color="#6a6a6a")
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for c in range(self.COLS):
            self.body.grid_columnconfigure(c, weight=1, uniform="sc")

    def close(self):
        self.app.scenes_win = None
        self.destroy()

    def refresh(self, connected, scenes, program):
        key = (connected, tuple(scenes))
        if key != self._shown:
            self._shown = key
            self._rebuild(connected, scenes)
        for name, btn in self.buttons.items():
            if name == program:
                btn.configure(fg_color=LIVE_RED, hover_color=LIVE_RED_HOVER)
            else:
                btn.configure(fg_color=BG_BUTTON, hover_color=BG_HOVER)
        self.live_label.configure(text=f"В эфире: {program or '—'}")

    def _rebuild(self, connected, scenes):
        for w in self.body.winfo_children():
            w.destroy()
        self.buttons = {}

        if not connected:
            ctk.CTkLabel(self.body, text="OBS не подключен", font=("Segoe UI", 15),
                         text_color=TEXT_DIM).grid(row=0, column=0, columnspan=self.COLS, pady=(40, 10))
            ctk.CTkButton(self.body, text="Подключить OBS", height=36, fg_color=BG_ACCENT,
                          hover_color=BG_HOVER, command=self.app.open_obs_connect).grid(
                row=1, column=0, columnspan=self.COLS)
            return
        if not scenes:
            ctk.CTkLabel(self.body, text="В OBS нет сцен", font=("Segoe UI", 14),
                         text_color=TEXT_DIM).grid(row=0, column=0, columnspan=self.COLS, pady=40)
            return

        for i, name in enumerate(scenes):
            btn = ctk.CTkButton(self.body, text=short(name, 15), height=34, font=("Segoe UI", 12),
                                fg_color=BG_BUTTON, hover_color=BG_HOVER, text_color=TEXT_MAIN,
                                command=lambda n=name: self.app.switch_scene(n))
            btn.grid(row=i // self.COLS, column=i % self.COLS, padx=4, pady=4, sticky="ew")
            self.buttons[name] = btn


# ==========================================================
#   ГЛАВНЫЙ КЛАСС ПРИЛОЖЕНИЯ
# ==========================================================
class App:
    def __init__(self, project_path=None):
        self.project_path = project_path
        self.config = ProjectConfig(project_path) if project_path else ConfigManager()

        self.obs = None
        self.osc = None
        self.worker = None
        self.multiview = None
        self.scenes_win = None

        self.manual_mode = bool(self.config.get("manual_mode", default=True))
        self.liveedit_active = False
        self.all_muted = False
        self._prev_unmuted = []
        self._streaming = None
        self._mixer_rev = -1
        self._mixer_off = True
        self.custom_buttons = self.config.get("custom_buttons", default=[]) or []

        self.control = ControlWindow(self)
        name = self.config.get("name", default=None)
        if name:
            self.control.set_project_name(name)

        self.control.protocol("WM_DELETE_WINDOW", self.on_close)
        self.control.set_mode(self.manual_mode)
        self._update_auto_note()
        self.control.refresh_custom_buttons(self.custom_buttons)
        self.control.set_stream_btn(False)
        self.control.log("Проект открыт. Подключи OBS.")

        self.control.after(150, self.tick)

    # ---------- общие помощники ----------
    def obs_connected(self):
        return bool(self.obs and self.obs.connected and self.worker and not self.worker.lost)

    def require_obs(self, quiet=False):
        if self.obs_connected():
            return True
        if quiet:
            self.control.log("[!] OBS не подключен")
        else:
            messagebox.showwarning("OBS", "OBS не подключен.\nНажми «OBS не подключен» и подключись.",
                                   parent=self.control)
        return False

    def scene_choices(self):
        if self.obs_connected():
            return list(self.worker.state.get("scenes") or [])
        return []

    def audio_choices(self, scene=""):
        if not self.obs_connected():
            return []
        try:
            if scene:
                return [i["name"] for i in self.obs.mixer_snapshot(scene)]
            return [n for n, _ in self.obs.all_audio_inputs()]
        except Exception:
            return []

    def source_choices(self, scene):
        if not (scene and self.obs_connected()):
            return []
        try:
            return [it.get("sourceName") for it in self.obs.scene_items(scene) if it.get("sourceName")]
        except Exception:
            return []

    def current_program(self):
        if self.worker:
            return self.worker.state.get("program")
        return None

    # ---------- обновление окна (каждые ~80 мс) ----------
    def tick(self):
        try:
            self._tick()
        except Exception as e:
            print(f"[tick] {e}")
        try:
            self.control.after(80, self.tick)
        except Exception:
            pass

    def _tick(self):
        w = self.worker
        if w and w.lost:
            self.handle_lost()
            w = None
        connected = self.obs_connected()
        latest = w.latest if (w and connected) else {}
        state = w.state if (w and connected) else {}

        # окно эфира
        if connected:
            self.control.show_program(latest.get("program"), "")
        else:
            self.control.show_program(None, "OBS не подключен")

        # «В эфире» / «Простаивает»
        streaming = bool(state.get("streaming")) if connected else False
        if streaming != self._streaming:
            self._streaming = streaming
            self.control.set_live(streaming)
            self.control.set_stream_btn(streaming)

        # микшер
        if not connected:
            if not self._mixer_off:
                self._mixer_off = True
                self._mixer_rev = -1
                self.control.mixer.show_message("OBS не подключен")
        else:
            rev = state.get("mixer_rev", 0)
            if self._mixer_off or rev != self._mixer_rev:
                self._mixer_off = False
                self._mixer_rev = rev
                if rev > 0:
                    self.control.mixer.update(state.get("mixer") or [])

        # мультипросмотр и окно сцен
        mv_open = bool(self.multiview and self.multiview.winfo_exists())
        if w:
            w.want_tiles = mv_open
        if mv_open:
            self.multiview.apply(latest, state, connected)
        if self.scenes_win and self.scenes_win.winfo_exists():
            self.scenes_win.refresh(connected, list(state.get("scenes") or []), state.get("program"))

    def handle_lost(self):
        self.control.log("[!] Связь с OBS потеряна")
        self._stop_worker()
        if self.obs:
            try:
                self.obs.disconnect()
            except Exception:
                pass
        self.control.set_obs_status(False)

    def _stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.worker = None

    # ---------- окна ----------
    def show_multiview(self):
        if self.multiview and self.multiview.winfo_exists():
            self.multiview.deiconify()
            self.multiview.lift()
            return
        self.multiview = MultiviewWindow(self.control, self)

    def show_scenes(self):
        if self.scenes_win and self.scenes_win.winfo_exists():
            self.scenes_win.deiconify()
            self.scenes_win.lift()
            return
        self.scenes_win = ScenesWindow(self.control, self)

    def on_profile(self):
        messagebox.showinfo("ShowControl", "Регистрация пока недоступна", parent=self.control)

    def on_info(self):
        messagebox.showinfo("ShowControl", "ShowControl\nMade by StickBuug", parent=self.control)

    def open_settings(self):
        SettingsDialog(self.control, self)

    # ---------- OBS ----------
    def open_obs_connect(self):
        OBSConnectDialog(self.control, self.config, self.connect_obs)

    def connect_obs(self, host, port, password):
        self._stop_worker()
        if self.obs:
            try:
                self.obs.disconnect()
            except Exception:
                pass

        self.obs = ObsLink(host=host, port=port, password=password)
        if self.obs.connect():
            self.control.set_obs_status(True)
            self.control.log(f"[+] OBS подключен ({host}:{port})")
            self.all_muted = False
            self.control.set_mute_all_state(False)
            self._mixer_rev = -1
            self._streaming = None
            self.worker = ObsWorker(self.obs)
            self.worker.start()
        else:
            self.control.set_obs_status(False)
            self.control.log("[!] Не удалось подключиться к OBS")
            messagebox.showerror(
                "OBS",
                "Не удалось подключиться к OBS.\n\n"
                "Проверь:\n"
                "• в OBS включён WebSocket (Инструменты → Настройки WebSocket-сервера)\n"
                "• порт и пароль совпадают с теми, что в OBS\n"
                "• OBS запущен",
                parent=self.control)

    # ---------- режим / LiveEdit ----------
    def toggle_manual_mode(self):
        self.manual_mode = not self.manual_mode
        self.config.config["manual_mode"] = self.manual_mode
        self.config.save()
        self.control.set_mode(self.manual_mode)
        self._update_auto_note()
        self.control.log(f"Режим: {'Ручной' if self.manual_mode else 'Авто'}")

    def _update_auto_note(self, text=None):
        if self.manual_mode:
            self.control.set_auto_note("")
        else:
            self.control.set_auto_note(text or "Нет запланированного действия")

    def toggle_liveedit(self):
        if not self.liveedit_active:
            ip = self.config.get("osc", "listen_ip", default="0.0.0.0")
            port = self.config.get("osc", "listen_port", default=3333)
            self.osc = OSCListener(ip=ip, port=port, on_message_callback=self.on_osc_message)
            self.osc.start()
            if not self.osc.running:
                self.osc = None
                self.control.log(f"[!] Не удалось открыть порт {port} (занят другой программой?)")
                messagebox.showerror(
                    "LiveEdit",
                    f"Не удалось открыть порт {port}.\n"
                    "Возможно, он уже занят (например, второй копией приложения).",
                    parent=self.control)
                return
            self.liveedit_active = True
            self.control.set_liveedit_status(True)
            self.control.log(f"[+] LiveEdit OSC слушает :{port}")
        else:
            if self.osc:
                self.osc.stop()
            self.liveedit_active = False
            self.control.set_liveedit_status(False)
            self.control.log("[-] LiveEdit отключен")

    def on_osc_message(self, address, args):
        # OSC приходит из другого потока — в интерфейс заходим через after()
        try:
            self.control.after(0, lambda: self._handle_osc(address, args))
        except Exception:
            pass

    def _handle_osc(self, address, args):
        if self.manual_mode:
            self.control.log(f"[OSC игнор: ручной режим] {address} {args}")
            return
        if address == "/scene" and args:
            name = str(args[0])
            self.switch_scene(name, quiet=True)
            self._update_auto_note(f"Последнее действие: {name} • {now_str()}")
        else:
            self.control.log(f"[OSC] {address} {args}")

    # ---------- сцены ----------
    def switch_scene(self, name, quiet=False):
        if not self.require_obs(quiet=quiet):
            return False
        if self.obs.set_program_scene(name):
            self.control.log(f"→ {name}")
            if self.worker:
                self.worker.state["program"] = name
            return True
        self.control.log(f"[!] Не удалось переключить на «{name}» (такой сцены нет в OBS?)")
        return False

    # ---------- звук ----------
    def set_input_mute(self, name, muted):
        if not self.require_obs():
            return False
        if self.obs.set_input_mute(name, muted):
            self.control.log(f"{'Заглушен' if muted else 'Звук включён'}: {name}")
            return True
        self.control.log(f"[!] Не удалось изменить звук «{name}»")
        return False

    def set_input_volume(self, name, db):
        if self.obs_connected():
            self.obs.set_input_volume_db(name, db)

    def toggle_mute_all(self):
        if not self.require_obs():
            return
        if not self.all_muted:
            inputs = self.obs.all_audio_inputs()
            self._prev_unmuted = [n for n, m in inputs if not m]
            for n in self._prev_unmuted:
                self.obs.set_input_mute(n, True)
            self.all_muted = True
            self.control.log(f"Заглушено всё ({len(self._prev_unmuted)} аудиопотоков)")
        else:
            for n in self._prev_unmuted:
                self.obs.set_input_mute(n, False)
            self.control.log("Звук возвращён")
            self._prev_unmuted = []
            self.all_muted = False
        self.control.set_mute_all_state(self.all_muted)

    # ---------- Emergency ----------
    def emergency_cfg(self):
        e = self.config.get("emergency", default=None)
        return e if isinstance(e, dict) and e.get("action") else None

    def emergency_text(self):
        e = self.emergency_cfg()
        if not e:
            return "Не настроен"
        a = e.get("action")
        scene = e.get("scene", "")
        if a == "scene":
            return f"Переключить на сцену «{scene}»"
        if a == "mute_all":
            return "Заглушить всё"
        return f"Сцена «{scene}» + заглушить всё"

    def open_emergency_settings(self, parent=None, after=None):
        def saved(data):
            self.config.config["emergency"] = data
            self.config.save()
            self.control.log(f"Emergency break настроен: {self.emergency_text()}")
            if after:
                after()
        EmergencyDialog(parent or self.control, self, self.emergency_cfg(), saved)

    def trigger_emergency(self):
        cfg = self.emergency_cfg()
        if not cfg:
            if messagebox.askyesno(
                    "Emergency break",
                    "Emergency break не настроен.\n"
                    "Нужно указать сцену или действие, которое будет выполняться при нажатии.\n\n"
                    "Настроить сейчас?", parent=self.control):
                self.open_emergency_settings()
            return
        if not self.require_obs():
            return
        self.run_emergency(cfg)

    def run_emergency(self, cfg):
        action = cfg.get("action")
        self.control.log("!!! EMERGENCY BREAK")
        if action in ("scene", "scene_mute") and cfg.get("scene"):
            self.switch_scene(cfg["scene"], quiet=True)
        if action in ("mute_all", "scene_mute") and not self.all_muted:
            self.toggle_mute_all()

    # ---------- трансляция ----------
    def toggle_stream(self):
        if not self.require_obs():
            return
        if self._streaming:
            if messagebox.askyesno("Трансляция", "Остановить трансляцию?", parent=self.control):
                ok = self.obs.stop_stream()
                self.control.log("Трансляция остановлена" if ok else "[!] Не удалось остановить трансляцию")
        else:
            if messagebox.askyesno("Трансляция", "Начать трансляцию?", parent=self.control):
                ok = self.obs.start_stream()
                self.control.log("Трансляция запущена" if ok else "[!] Не удалось начать трансляцию")

    # ---------- свои кнопки ----------
    def _save_buttons(self):
        self.config.config["custom_buttons"] = self.custom_buttons
        self.config.save()
        self.control.refresh_custom_buttons(self.custom_buttons)

    def open_add_button(self, edit_index=None):
        data = self.custom_buttons[edit_index] if edit_index is not None else None

        def saved(d):
            if edit_index is None:
                self.custom_buttons.append(d)
                self.control.log(f"+ Кнопка «{d['name']}»")
            else:
                self.custom_buttons[edit_index] = d
                self.control.log(f"Кнопка «{d['name']}» изменена")
            self._save_buttons()

        AddButtonDialog(self.control, self, saved, data)

    def duplicate_button(self, idx):
        copy = json.loads(json.dumps(self.custom_buttons[idx]))
        copy["name"] = copy.get("name", "") + " (копия)"
        self.custom_buttons.insert(idx + 1, copy)
        self._save_buttons()

    def remove_button(self, idx):
        data = self.custom_buttons[idx]
        if messagebox.askyesno("Удалить кнопку", f"Удалить кнопку «{data.get('name')}»?", parent=self.control):
            del self.custom_buttons[idx]
            self._save_buttons()
            self.control.log(f"− Кнопка «{data.get('name')}» удалена")

    def execute_custom_button(self, data):
        t = data.get("type")
        legacy = data.get("value", "")   # старый формат кнопок

        if t == "emergency":
            self.trigger_emergency()
            return
        if t == "mute_all":
            if self.require_obs() and not self.all_muted:
                self.toggle_mute_all()
            return
        if t == "unmute_all":
            if self.require_obs() and self.all_muted:
                self.toggle_mute_all()
            return
        if t == "stream_start":
            if self.require_obs() and not self._streaming:
                self.toggle_stream()
            return
        if t == "stream_stop":
            if self.require_obs() and self._streaming:
                self.toggle_stream()
            return

        if not self.require_obs():
            return

        if t == "scene":
            self.run_scene_button(data.get("scene") or legacy, data)
        elif t in ("mute", "unmute", "toggle_mute"):
            inp = data.get("input") or legacy
            if t == "toggle_mute":
                new = self.obs.toggle_input_mute(inp)
                if new is None:
                    self.control.log(f"[!] Нет аудиопотока «{inp}»")
                else:
                    self.control.log(f"{'Заглушен' if new else 'Звук включён'}: {inp}")
            else:
                if not self.obs.set_input_mute(inp, t == "mute"):
                    self.control.log(f"[!] Нет аудиопотока «{inp}»")
                else:
                    self.control.log(f"{'Заглушен' if t == 'mute' else 'Звук включён'}: {inp}")
        elif t == "volume":
            inp = data.get("input", "")
            db = float(data.get("db", 0))
            if self.obs.set_input_volume_db(inp, db):
                self.control.log(f"Громкость «{inp}»: {db:g} dB")
            else:
                self.control.log(f"[!] Нет аудиопотока «{inp}»")
        elif t == "source":
            self.set_source(data.get("scene", ""), data.get("source", ""), data.get("mode", "show"))

    def set_source(self, scene, source, mode):
        enabled = {"show": True, "hide": False}.get(mode)   # None = переключить
        res = self.obs.set_item_enabled(scene, source, enabled)
        if res is None:
            self.control.log(f"[!] Источник «{source}» не найден в сцене «{scene}»")
        else:
            self.control.log(f"{'Показан' if res else 'Скрыт'}: {source} ({scene})")

    def run_scene_button(self, scene, data):
        prev = self.current_program()
        for text in data.get("show_sources", []):
            sc, src = parse_source_ref(text, scene)
            self.set_source(sc, src, "show")
        for text in data.get("hide_sources", []):
            sc, src = parse_source_ref(text, scene)
            self.set_source(sc, src, "hide")

        if not self.switch_scene(scene, quiet=True):
            return
        secs = float(data.get("return_after", 0) or 0)
        if secs > 0 and prev and prev != scene:
            self.control.after(int(secs * 1000), lambda: self.switch_scene(prev, quiet=True))
            self.control.log(f"Вернусь на «{prev}» через {secs:g} сек")

    # ---------- шаблоны ----------
    def _templates_dir(self):
        d = os.path.join(BASE_DIR, "templates")
        os.makedirs(d, exist_ok=True)
        return d

    def save_template(self, parent=None):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialdir=self._templates_dir(), parent=parent or self.control)
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.custom_buttons, f, indent=2, ensure_ascii=False)
        self.control.log(f"Кнопки сохранены в файл: {os.path.basename(path)}")

    def load_template(self, parent=None):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")], initialdir=self._templates_dir(),
            parent=parent or self.control)
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("в файле должен быть список кнопок")
        except Exception as e:
            self.control.log(f"[!] Ошибка загрузки: {e}")
            return

        if self.custom_buttons:
            answer = messagebox.askyesnocancel(
                "Загрузить кнопки",
                "Добавить загруженные кнопки к текущим?\n\n"
                "Да — добавить, Нет — заменить текущие, Отмена — ничего не делать.",
                parent=self.control)
            if answer is None:
                return
            self.custom_buttons = (self.custom_buttons + data) if answer else data
        else:
            self.custom_buttons = data
        self._save_buttons()
        self.control.log(f"Кнопки загружены: {os.path.basename(path)}")

    # ---------- закрытие ----------
    def on_close(self):
        self._stop_worker()
        if self.osc:
            try:
                self.osc.stop()
            except Exception:
                pass
        if self.obs:
            try:
                self.obs.disconnect()
            except Exception:
                pass
        self.control.destroy()

    def run(self):
        self.control.mainloop()