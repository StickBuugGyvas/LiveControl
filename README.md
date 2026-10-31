# LiveControl

**LiveControl** is a desktop application for managing OBS scenes and cameras during live shows, song contests, and Minecraft events (Eurovision-style productions).

It connects to OBS via WebSocket, supports LiveEdit OSC automation, custom control buttons, project saving, and a clean multiview interface.

---

## Features

-  Control up to 10 cameras (CAM1–CAM10)
-  Automatic scene switching via LiveEdit OSC
-  Manual / Auto mode
-  Emergency Break scene
-  Custom buttons constructor
-  Save & load projects
-  Multiview window (OBS-style)
-  Modern dark UI with splash screen
-  Optional LiveEdit connection

---

##  Requirements

- Windows 10/11
- [OBS Studio](https://obsproject.com/) (v28+ recommended)
- Python 3.10+ (only if running from source)

### Python packages

```bash
pip install customtkinter obs-websocket-py python-osc pillow
```


## Download

Go to the [Releases](https://github.com/StickBuugGyvas/LiveControl/releases) page and download the latest `LiveControl.exe`.

No installation required. Just download the file and run it.

## Author

StickBuug

## License

All rights reserved © 2026 StickBuug
