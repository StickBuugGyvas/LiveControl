from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
import threading


class OSCListener:
    def __init__(self, ip="0.0.0.0", port=3333, on_message_callback=None):
        self.ip = ip
        self.port = port
        self.on_message_callback = on_message_callback
        self.server = None
        self.thread = None
        self.running = False

    def _default_handler(self, address, *args):
        print(f"[OSC] Получено: {address}  args={args}")
        if self.on_message_callback:
            self.on_message_callback(address, args)

    def start(self):
        if self.running:
            return

        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._default_handler)

        try:
            self.server = BlockingOSCUDPServer((self.ip, self.port), dispatcher)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.running = True
            print(f"[OSC] Слушатель запущен на {self.ip}:{self.port}")
        except Exception as e:
            print(f"[OSC] Ошибка запуска слушателя: {e}")

    def stop(self):
        if self.server and self.running:
            self.server.shutdown()
            self.running = False
            print("[OSC] Слушатель остановлен")