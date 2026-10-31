import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.splash import SplashScreen
from ui.home_window import HomeWindow
from ui.main_window import App


def open_home():
    home = HomeWindow(on_open_project=open_project)
    home.mainloop()


def open_project(project_path):
    app = App(project_path=project_path)
    app.run()


if __name__ == "__main__":
    splash = SplashScreen(on_finish_callback=open_home)
    splash.mainloop()