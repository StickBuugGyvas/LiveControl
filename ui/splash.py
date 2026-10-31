import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE_DIR, "assets")
FONTS = os.path.join(ASSETS, "fonts")

BG_PATH = os.path.join(ASSETS, "splash_bg.png")
LOGO_PATH = os.path.join(ASSETS, "logo.png")
FONT_DEMI = os.path.join(FONTS, "ITCAvantGardeStd-Demi.ttf")
FONT_BOOK = os.path.join(FONTS, "ITCAvantGardeStd-Bk.ttf")


class SplashScreen(ctk.CTk):
    def __init__(self, on_finish_callback):
        super().__init__()
        self.on_finish = on_finish_callback

        self.overrideredirect(True)

        # Размер окна = размер фона (или фиксированный)
        self.W, self.H = 1000, 560
        self.geometry(f"{self.W}x{self.H}")
        self.configure(fg_color="#0a1628")

        # Центрирование
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.W // 2)
        y = (self.winfo_screenheight() // 2) - (self.H // 2)
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self.build_image()
        self.after(2300, self.finish)

    def build_image(self):
        # --- Фон ---
        try:
            bg = Image.open(BG_PATH).convert("RGBA")
            bg = bg.resize((self.W, self.H), Image.Resampling.LANCZOS)
        except Exception:
            # запасной градиент
            bg = Image.new("RGBA", (self.W, self.H), (10, 22, 45, 255))

        draw = ImageDraw.Draw(bg)

        # --- Логотип ---
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo = logo.resize((70, 70), Image.Resampling.LANCZOS)
            bg.paste(logo, (80, 145), logo)
        except Exception as e:
            print("Logo error:", e)

        # --- Шрифты ---
        try:
            font_title = ImageFont.truetype(FONT_DEMI, 44)
        except Exception:
            font_title = ImageFont.load_default()

        try:
            font_version = ImageFont.truetype(FONT_BOOK, 15)
            font_login = ImageFont.truetype(FONT_BOOK, 16)
            font_footer = ImageFont.truetype(FONT_BOOK, 13)
        except Exception:
            font_version = font_login = font_footer = ImageFont.load_default()

        # --- LiveControl ---
        draw.text((170, 155), "LiveControl", font=font_title, fill=(255, 255, 255, 255))

        # --- Version ---
        draw.text((170, 215), "Version 1.0.0", font=font_version, fill=(140, 155, 180, 255))

        # --- Login... ---
        draw.text((80, 300), "Login...", font=font_login, fill=(175, 190, 210, 255))

        # --- All rights reserved. ---
        draw.text((80, 510), "All rights reserved.", font=font_footer, fill=(90, 105, 130, 255))

        # Показываем
        self.photo = ImageTk.PhotoImage(bg)
        label = ctk.CTkLabel(self, image=self.photo, text="", fg_color="transparent")
        label.place(x=0, y=0)

    def finish(self):
        self.destroy()
        self.on_finish()